from __future__ import annotations

import json
import logging
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import LearningResource, ResourceType, SkillEdge, SkillNode, Topic, UserSkillState
from app.core.exceptions import ProviderError
from app.schemas.llm import (
    ExamplesPlan,
    ExercisesPlan,
    ExternalResourceReasoningPlan,
    LessonPlan,
)
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService


logger = logging.getLogger(__name__)
ResourceSource = Literal['stored', 'generated', 'regenerated']


class ResourceAgent:
    def __init__(
        self,
        llm_service: LLMService,
        search_service: ExternalSearchService,
        retrieval_service: RetrievalService,
    ) -> None:
        self.llm_service = llm_service
        self.search_service = search_service
        self.retrieval_service = retrieval_service

    def _difficulty_band(self, difficulty: int) -> str:
        if difficulty <= 2:
            return 'foundation'
        if difficulty == 3:
            return 'intermediate'
        return 'advanced'

    def _learner_level(self, state: UserSkillState | None) -> str:
        if not state:
            return 'beginner'
        if state.progress_state == 'verified' or state.mastery >= 0.75:
            return 'advanced'
        if state.progress_state in ('learning', 'completed') or state.mastery >= 0.35:
            return 'intermediate'
        return 'beginner'

    def _alignment_rules(self, difficulty: int, learner_level: str, kind: str) -> str:
        base = (
            '- Stay strictly scoped to this node title and description.\n'
            '- Assume only prerequisite knowledge, not downstream skills.\n'
            '- Do not include capstone or multi-skill project tasks unless node difficulty is advanced.\n'
        )

        if difficulty <= 2 or learner_level == 'beginner':
            beginner = (
                '- Treat learner as beginner/foundation for this node.\n'
                '- Use plain language, short steps, and foundational concepts.\n'
                '- Exercises must be short micro-practice tasks (5-15 minutes each).\n'
                '- Do NOT ask for full sets, long performances, or complex end-to-end production workflows.\n'
            )
            return base + beginner

        if kind == 'exercises':
            return (
                base
                + '- Use applied tasks that are realistic for node scope.\n'
                '- Prefer progressive tasks from easier to harder.\n'
            )
        return base

    def _field_length_rules(self, kind: str) -> str:
        if kind == 'lesson':
            return (
                '- Keep summary under 280 characters.\n'
                '- Keep section content concise (2-5 short paragraphs each).\n'
            )
        if kind == 'examples':
            return (
                '- Keep intro under 260 characters.\n'
                '- Keep each explanation concise and practical.\n'
            )
        if kind == 'exercises':
            return (
                '- Keep intro under 260 characters.\n'
                '- Keep each task scoped to one focused activity.\n'
            )
        return ''

    def _contains_advanced_pattern(self, text: str) -> bool:
        lowered = text.lower()
        patterns = (
            '5-minute set',
            '5 minute set',
            'full set',
            'live set',
            'perform a set',
            'end-to-end',
            'end to end',
            'full production workflow',
            'release-ready',
            'mastering chain',
        )
        return any(pattern in lowered for pattern in patterns)

    def _exercise_signature(self, title: str, task: str) -> str:
        compact = f'{title.strip().lower()}::{task.strip().lower()}'
        compact = compact.replace('\n', ' ')
        return ' '.join(compact.split())

    def _normalize_exercise_collection(self, structured_content: dict[str, Any]) -> dict[str, Any]:
        exercises = structured_content.get('exercises')
        if not isinstance(exercises, list):
            return structured_content

        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in exercises:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get('title') or '').strip()
            task = str(raw.get('task') or '').strip()
            if not title or not task:
                continue
            signature = self._exercise_signature(title, task)
            if signature in seen:
                continue
            seen.add(signature)
            difficulty_raw = str(raw.get('difficulty') or 'medium').strip().lower()
            difficulty = difficulty_raw if difficulty_raw in {'easy', 'medium', 'hard'} else 'medium'
            hints_raw = raw.get('hints')
            hints = (
                [str(item).strip() for item in hints_raw if str(item).strip()]
                if isinstance(hints_raw, list)
                else []
            )[:4]
            if not hints:
                hints = ['Break the task into one small focused step.', 'Validate one result before moving on.']
            expected_outcome = str(raw.get('expected_outcome') or '').strip()
            if not expected_outcome:
                expected_outcome = 'You complete one focused attempt and identify one concrete improvement.'

            normalized.append(
                {
                    'title': title[:120],
                    'task': task[:500],
                    'hints': hints,
                    'expected_outcome': expected_outcome[:300],
                    'difficulty': difficulty,
                }
            )

        if len(normalized) > 2:
            selected: list[dict[str, Any]] = []
            used_indexes: set[int] = set()
            for target in ('easy', 'medium', 'hard'):
                for idx, item in enumerate(normalized):
                    if idx in used_indexes or item.get('difficulty') != target:
                        continue
                    selected.append(item)
                    used_indexes.add(idx)
                    break
                if len(selected) >= 2:
                    break
            if len(selected) < 2:
                for idx, item in enumerate(normalized):
                    if idx in used_indexes:
                        continue
                    selected.append(item)
                    used_indexes.add(idx)
                    if len(selected) >= 2:
                        break
            normalized = selected[:2]

        if len(normalized) == 1:
            first = normalized[0]
            normalized.append(
                {
                    'title': f'{first["title"]} (variation)'[:120],
                    'task': (
                        f'{first["task"]}\n\nVariation: repeat with one controlled change and compare outcomes.'
                    )[:500],
                    'hints': (
                        list(first.get('hints') or [])[:2]
                        + ['Change only one variable so you can compare results clearly.']
                    )[:4],
                    'expected_outcome': (
                        str(first.get('expected_outcome') or '')
                        + ' You can explain the difference between attempt A and attempt B.'
                    )[:300],
                    'difficulty': first.get('difficulty') if first.get('difficulty') in {'easy', 'medium', 'hard'} else 'medium',
                }
            )
        elif len(normalized) == 0:
            normalized = [
                {
                    'title': 'Focused practice drill',
                    'task': 'Complete one short focused practice attempt on the core concept.',
                    'hints': ['Keep scope narrow.', 'Check one outcome at the end.'],
                    'expected_outcome': 'You can explain one thing that improved after this drill.',
                    'difficulty': 'easy',
                },
                {
                    'title': 'Apply and compare',
                    'task': 'Run a second attempt with one controlled change and compare results.',
                    'hints': ['Change one variable only.', 'Write down the before/after difference.'],
                    'expected_outcome': 'You can describe which change improved the outcome and why.',
                    'difficulty': 'medium',
                },
            ]

        structured_content['exercises'] = normalized[:2]
        return structured_content

    def _enforce_foundation_scope(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        skill_name: str,
    ) -> dict[str, Any]:
        if kind != 'exercises':
            return structured_content

        exercises = structured_content.get('exercises')
        if not isinstance(exercises, list):
            return structured_content

        normalized_exercises: list[dict[str, Any]] = []
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue

            text = ' '.join(
                [
                    str(exercise.get('title', '')),
                    str(exercise.get('task', '')),
                    str(exercise.get('expected_outcome', '')),
                ]
            )
            if self._contains_advanced_pattern(text):
                exercise['task'] = (
                    f'In a short 10-minute practice, focus on one core "{skill_name}" technique only. '
                    'Repeat the same simple pattern until timing and control are stable.'
                )
                exercise['expected_outcome'] = (
                    'You can demonstrate one foundational pattern cleanly for 30-60 seconds and explain what improved.'
                )
                hints = exercise.get('hints')
                if isinstance(hints, list):
                    exercise['hints'] = (hints[:2] + ['Keep the scope small: one pattern, one technique.'])[:4]
                else:
                    exercise['hints'] = [
                        'Start with one simple pattern.',
                        'Keep the drill short and repeatable.',
                    ]
                exercise['difficulty'] = 'easy'

            normalized_exercises.append(exercise)

        if normalized_exercises:
            structured_content['exercises'] = normalized_exercises
        return structured_content

    def _resource_type_for_kind(self, kind: str) -> ResourceType:
        mapping = {
            'lesson': ResourceType.generated_lesson,
            'examples': ResourceType.generated_examples,
            'exercises': ResourceType.generated_exercises,
        }
        if kind not in mapping:
            raise ValueError('Unsupported resource kind.')
        return mapping[kind]

    def _fallback_lesson_content(self, *, topic: Topic, skill_node: SkillNode, learner_level: str) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Starter lesson',
            'summary': (
                f'A concise introduction to {skill_node.name} for {learner_level} learners in {topic.name}.'
            )[:300],
            'learning_objectives': [
                f'Explain the core purpose of {skill_node.name}.',
                'Apply one foundational method correctly in a small example.',
            ],
            'key_concepts': [
                {
                    'term': skill_node.name[:100],
                    'description': 'The core concept this node teaches and why it matters in practice.',
                },
                {
                    'term': 'Foundational workflow',
                    'description': 'A repeatable sequence of steps for basic execution and review.',
                },
            ],
            'sections': [
                {
                    'heading': 'What this skill is for',
                    'content': (
                        f'{skill_node.name} helps you make reliable progress inside {topic.name}. '
                        'Focus on one clear concept at a time before adding complexity.'
                    )[:800],
                },
                {
                    'heading': 'How to practice this node',
                    'content': (
                        'Use short focused practice rounds. Run one attempt, review what happened, and repeat with '
                        'a single adjustment so progress is measurable.'
                    )[:800],
                },
            ],
            'takeaways': [
                f'You should be able to describe {skill_node.name} in plain language.',
                'Small, repeatable drills build faster mastery than broad unfocused practice.',
            ],
            'next_steps': [
                'Open examples to see the concept applied in context.',
                'Move to exercises and complete one short task end-to-end.',
            ],
        }

    def _fallback_examples_content(self, *, topic: Topic, skill_node: SkillNode) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Worked examples',
            'intro': (
                f'These examples show practical, beginner-safe uses of {skill_node.name} in {topic.name}.'
            )[:420],
            'examples': [
                {
                    'name': 'Baseline example',
                    'explanation': (
                        f'Start with a minimal case where {skill_node.name} is applied once with clear inputs and outputs.'
                    )[:500],
                    'why_it_matters': 'This anchors the core concept before adding edge cases.'[:280],
                },
                {
                    'name': 'Common mistake and correction',
                    'explanation': (
                        f'Show a frequent mistake in {skill_node.name}, then demonstrate the corrected approach.'
                    )[:500],
                    'why_it_matters': 'Seeing failure modes early improves retention and confidence.'[:280],
                },
            ],
        }

    def _fallback_exercises_content(self, *, topic: Topic, skill_node: SkillNode) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Starter exercises',
            'intro': (
                f'Complete these short drills to build confidence in {skill_node.name} within {topic.name}.'
            )[:420],
            'exercises': [
                {
                    'title': 'Quick concept drill',
                    'task': (
                        f'Spend 10 minutes applying one core {skill_node.name} technique in a minimal practice setup.'
                    )[:500],
                    'hints': [
                        'Keep the task narrow and repeatable.',
                        'Check one variable at a time.',
                    ],
                    'expected_outcome': (
                        'You can perform one clean attempt and explain what worked and what to improve next.'
                    )[:300],
                    'difficulty': 'easy',
                },
                {
                    'title': 'Error-spotting mini task',
                    'task': (
                        f'Review a flawed {skill_node.name} attempt, identify one mistake, and produce a corrected version.'
                    )[:500],
                    'hints': [
                        'Write down the mistake before fixing it.',
                        'Validate the correction with one quick re-test.',
                    ],
                    'expected_outcome': (
                        'You can identify a common error pattern and apply a targeted correction.'
                    )[:300],
                    'difficulty': 'medium',
                },
            ],
        }

    def _fallback_structured_content(
        self,
        *,
        kind: str,
        topic: Topic,
        skill_node: SkillNode,
        learner_level: str,
    ) -> dict[str, Any]:
        if kind == 'lesson':
            return self._fallback_lesson_content(topic=topic, skill_node=skill_node, learner_level=learner_level)
        if kind == 'examples':
            return self._fallback_examples_content(topic=topic, skill_node=skill_node)
        if kind == 'exercises':
            return self._fallback_exercises_content(topic=topic, skill_node=skill_node)
        raise ValueError('Unsupported resource kind for fallback.')

    def _get_active_generated_resource(
        self,
        db: Session,
        *,
        user_id: int,
        skill_node_id: int,
        resource_type: ResourceType,
    ) -> LearningResource | None:
        return db.scalar(
            select(LearningResource)
            .where(
                LearningResource.skill_node_id == skill_node_id,
                LearningResource.resource_type == resource_type,
                LearningResource.is_active.is_(True),
                (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
            )
            .order_by(LearningResource.version.desc(), LearningResource.created_at.desc())
        )

    def _extract_structured_content(self, resource: LearningResource) -> dict[str, Any] | None:
        if resource.content_json:
            return resource.content_json

        content = (resource.content or '').strip()
        if not content:
            return None
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    async def generate_material(
        self,
        db: Session,
        *,
        user_id: int,
        topic: Topic,
        skill_node: SkillNode,
        kind: str,
        regenerate: bool = False,
    ) -> tuple[LearningResource, dict[str, Any] | None, ResourceSource]:
        resource_type = self._resource_type_for_kind(kind)
        existing = self._get_active_generated_resource(
            db,
            user_id=user_id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
        )

        if existing and not regenerate:
            structured = self._extract_structured_content(existing)
            logger.info(
                'resource.loaded_from_store topic_id=%s skill_id=%s kind=%s version=%s',
                topic.id,
                skill_node.id,
                kind,
                existing.version,
            )
            return existing, structured, 'stored'

        prompts = {
            'lesson': (
                LessonPlan,
                (
                    'Create a practical lesson for this skill node. Keep it concise and clear for self-study. '
                    'Keep summary concise and avoid unnecessary verbosity.'
                ),
                1400,
            ),
            'examples': (
                ExamplesPlan,
                (
                    'Create concrete examples that build from simple to challenging and explain the reasoning. '
                    'Keep intro concise (roughly 2-3 sentences).'
                ),
                1000,
            ),
            'exercises': (
                ExercisesPlan,
                (
                    'Create exercises for short practice sessions with clear expected outcomes. '
                    'Keep intro concise (roughly 2-3 sentences).'
                ),
                1100,
            ),
        }
        schema_model, instruction, max_tokens = prompts[kind]

        retrieved = await self.retrieval_service.retrieve_chunks(
            db,
            topic_id=topic.id,
            query=f'{topic.name} {skill_node.name}',
            top_k=3,
        )
        notes_context = '\n\n'.join(f'- {item.text[:320]}' for item in retrieved)
        user_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        prerequisite_ids = db.scalars(
            select(SkillEdge.parent_skill_id).where(
                SkillEdge.topic_id == topic.id,
                SkillEdge.child_skill_id == skill_node.id,
            )
        ).all()
        prerequisite_names: list[str] = []
        if prerequisite_ids:
            prerequisite_nodes = db.scalars(select(SkillNode).where(SkillNode.id.in_(prerequisite_ids))).all()
            prerequisite_names = [node.name for node in prerequisite_nodes]

        difficulty_band = self._difficulty_band(skill_node.difficulty)
        learner_level = self._learner_level(user_state)
        alignment_rules = self._alignment_rules(skill_node.difficulty, learner_level, kind)
        field_length_rules = self._field_length_rules(kind)

        system_prompt = (
            'You are ResourceAgent. Produce high-quality learning material that is technically correct and '
            'tailored to learner context.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n\n'
            f'Skill difficulty (1-5): {skill_node.difficulty} ({difficulty_band})\n'
            f'Learner level for this node: {learner_level}\n'
            f'Learner progress state: {user_state.progress_state if user_state else "not_started"}\n'
            f'Prerequisites for this node: {", ".join(prerequisite_names) if prerequisite_names else "None"}\n\n'
            f'Retrieved learner notes:\n{notes_context or "No notes available"}\n\n'
            f'Alignment rules:\n{alignment_rules}\n'
            f'Formatting constraints:\n{field_length_rules}\n'
            f'Instruction: {instruction}'
        )

        used_fallback = False
        try:
            structured_model = await self.llm_service.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                temperature=0.3,
                max_tokens=max_tokens,
            )
            structured_content = structured_model.model_dump()
        except ProviderError as exc:
            used_fallback = True
            logger.warning(
                'resource.generation_fallback kind=%s topic_id=%s skill_id=%s error=%s',
                kind,
                topic.id,
                skill_node.id,
                exc,
            )
            structured_content = self._fallback_structured_content(
                kind=kind,
                topic=topic,
                skill_node=skill_node,
                learner_level=learner_level,
            )
        if skill_node.difficulty <= 2 or learner_level == 'beginner':
            structured_content = self._enforce_foundation_scope(
                kind=kind,
                structured_content=structured_content,
                skill_name=skill_node.name,
            )
        if kind == 'exercises':
            structured_content = self._normalize_exercise_collection(structured_content)
        content = json.dumps(structured_content, indent=2)
        summary = structured_content.get('summary') or structured_content.get('intro') or content[:240]

        next_version = 1
        if existing:
            next_version = existing.version + 1
            db.execute(
                update(LearningResource)
                .where(
                    LearningResource.skill_node_id == skill_node.id,
                    LearningResource.resource_type == resource_type,
                    LearningResource.is_active.is_(True),
                    (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
                )
                .values(is_active=False)
            )

        resource = LearningResource(
            user_id=user_id,
            topic_id=topic.id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
            version=next_version,
            is_active=True,
            title=structured_content.get('title') or f'{skill_node.name} {kind.title()}',
            summary=summary,
            content_json=structured_content,
            content=content,
            url='',
            relevance_reason='Generated to match learner progression, selected skill, and uploaded note context.',
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

        source: ResourceSource = 'regenerated' if existing else 'generated'
        logger.info(
            'resource.generated topic_id=%s skill_id=%s kind=%s version=%s source=%s fallback=%s',
            topic.id,
            skill_node.id,
            kind,
            resource.version,
            source,
            used_fallback,
        )
        return resource, structured_content, source

    async def fetch_external_resources(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        limit: int = 3,
    ) -> list[LearningResource]:
        search_results = await self.search_service.search(topic.name, skill_node.name, limit=max(6, limit * 2))
        if not search_results:
            return []

        result_payload = [
            {
                'title': item.title,
                'url': item.url,
                'kind': item.kind,
                'summary': item.summary,
            }
            for item in search_results
        ]

        system_prompt = (
            'You are ResourceAgent. Select the most relevant external resources for a learner and provide concise '
            'relevance reasons tied to the selected skill.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n'
            f'Select up to {limit} resources from these candidates:\n{json.dumps(result_payload, indent=2)}'
        )

        reasoning = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=ExternalResourceReasoningPlan,
            temperature=0.2,
            max_tokens=1200,
        )

        candidate_map = {item.url: item for item in search_results}
        selected_urls: list[str] = []
        reasons_by_url: dict[str, str] = {}

        for item in reasoning.resources:
            if item.url not in candidate_map:
                continue
            if item.url in reasons_by_url:
                continue
            reasons_by_url[item.url] = item.relevance_reason
            selected_urls.append(item.url)
            if len(selected_urls) >= limit:
                break

        if not selected_urls:
            selected_urls = [item.url for item in search_results[:limit]]
            for url in selected_urls:
                reasons_by_url[url] = 'Relevant to the selected skill path and current learning objective.'

        created: list[LearningResource] = []
        for url in selected_urls:
            source = candidate_map[url]
            existing = db.scalar(
                select(LearningResource).where(
                    LearningResource.topic_id == topic.id,
                    LearningResource.skill_node_id == skill_node.id,
                    LearningResource.url == source.url,
                )
            )
            if existing:
                created.append(existing)
                continue

            resource = LearningResource(
                user_id=None,
                topic_id=topic.id,
                skill_node_id=skill_node.id,
                resource_type=ResourceType(source.kind),
                title=source.title,
                url=source.url,
                summary=source.summary,
                content_json=None,
                content='',
                relevance_reason=reasons_by_url.get(source.url, 'Relevant to current skill progression.'),
            )
            db.add(resource)
            db.flush()
            created.append(resource)

        db.commit()
        for item in created:
            db.refresh(item)

        logger.info('resource.external topic_id=%s skill_id=%s count=%s', topic.id, skill_node.id, len(created))
        return created
