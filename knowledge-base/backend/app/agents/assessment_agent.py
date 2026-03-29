from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.course_preferences import (
    ASSESSMENT_STYLE_TO_QUESTION_TYPE,
    build_assessment_style_sequence,
    normalize_assessment_styles,
    normalize_starting_skill_level,
    normalize_technical_depth,
    technical_depth_prompt_guidance,
)
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentFeedback,
    AssessmentQuestion,
    AssessmentQuestionType,
    AssessmentResponse,
    LearningResource,
    ResourceType,
    SkillEdge,
    SkillNode,
    Topic,
    UserSkillState,
)
from app.schemas.llm import AssessmentEvaluationPlan, AssessmentPlan
from app.services.llm import LLMService


logger = logging.getLogger(__name__)
AssessmentSource = Literal['stored', 'generated', 'regenerated']


@dataclass
class ScoredQuestion:
    question: AssessmentQuestion
    score: float
    feedback: str
    selected_option_index: int | None
    answer_text: str
    confidence_score: float | None
    strengths: list[str]
    missing_concepts: list[str]
    graded: bool = True


@dataclass
class AssessmentScoringResult:
    attempt: AssessmentAttempt
    overall_score: float
    confidence_avg: float
    mastery_delta: float
    feedback: list[dict[str, Any]]
    strengths: list[str]
    weaknesses: list[str]
    review_next: str
    recommended_follow_up: str
    summary: str
    mastery_eligible: bool = True
    practice_mode: bool = False


class AssessmentAgent:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def _clamp(self, value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

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

    def _recommended_mix(self, *, style_sequence: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for style in style_sequence:
            counts[style] = counts.get(style, 0) + 1
        return counts

    def _active_generated_resource(
        self,
        db: Session,
        *,
        user_id: int,
        topic_id: int,
        skill_node_id: int,
        resource_type: ResourceType,
    ) -> LearningResource | None:
        return db.scalar(
            select(LearningResource)
            .where(
                LearningResource.user_id == user_id,
                LearningResource.topic_id == topic_id,
                LearningResource.skill_node_id == skill_node_id,
                LearningResource.resource_type == resource_type,
                LearningResource.is_active.is_(True),
            )
            .order_by(LearningResource.version.desc(), LearningResource.created_at.desc())
        )

    def _resource_payload(self, resource: LearningResource | None) -> dict[str, Any]:
        if resource is None:
            return {}
        if isinstance(resource.content_json, dict):
            return resource.content_json
        content = (resource.content or '').strip()
        if not content:
            return {}
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _normalize_concept(self, value: str) -> str:
        lowered = value.strip().lower().replace('_', ' ').replace('-', ' ')
        lowered = re.sub(r'[^a-z0-9 ]+', '', lowered)
        return ' '.join(lowered.split())

    def _dedupe_concepts(self, concepts: list[str], *, max_items: int = 20) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for concept in concepts:
            cleaned = str(concept or '').strip()
            if not cleaned:
                continue
            normalized = self._normalize_concept(cleaned)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(cleaned[:140])
            if len(deduped) >= max_items:
                break
        return deduped

    def _extract_taught_concepts(
        self,
        *,
        lesson_payload: dict[str, Any],
        examples_payload: dict[str, Any],
        skill_node: SkillNode,
    ) -> list[str]:
        concepts: list[str] = [skill_node.name]

        key_concepts = lesson_payload.get('key_concepts')
        if isinstance(key_concepts, list):
            for item in key_concepts:
                if not isinstance(item, dict):
                    continue
                term = str(item.get('term') or '').strip()
                if term:
                    concepts.append(term)

        learning_objectives = lesson_payload.get('learning_objectives')
        if isinstance(learning_objectives, list):
            concepts.extend(str(item).strip() for item in learning_objectives if str(item).strip())

        takeaways = lesson_payload.get('takeaways')
        if isinstance(takeaways, list):
            concepts.extend(str(item).strip() for item in takeaways if str(item).strip())

        examples = examples_payload.get('examples')
        if isinstance(examples, list):
            for item in examples:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or '').strip()
                why = str(item.get('why_it_matters') or '').strip()
                if name:
                    concepts.append(name)
                if why:
                    concepts.extend(self._extract_concepts_from_text(why, max_items=2))

        deduped = self._dedupe_concepts(concepts, max_items=24)
        return deduped or [skill_node.name]

    def _teaching_context(
        self,
        db: Session,
        *,
        user_id: int,
        topic: Topic,
        skill_node: SkillNode,
    ) -> tuple[list[str], str]:
        try:
            lesson_resource = self._active_generated_resource(
                db,
                user_id=user_id,
                topic_id=topic.id,
                skill_node_id=skill_node.id,
                resource_type=ResourceType.generated_lesson,
            )
            examples_resource = self._active_generated_resource(
                db,
                user_id=user_id,
                topic_id=topic.id,
                skill_node_id=skill_node.id,
                resource_type=ResourceType.generated_examples,
            )
            lesson_payload = self._resource_payload(lesson_resource)
            examples_payload = self._resource_payload(examples_resource)
            taught_concepts = self._extract_taught_concepts(
                lesson_payload=lesson_payload,
                examples_payload=examples_payload,
                skill_node=skill_node,
            )
            context_text = '\n'.join(f'- {concept}' for concept in taught_concepts[:14])
            return taught_concepts, context_text
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'assessment.teaching_context_unavailable topic_id=%s skill_id=%s error=%s',
                topic.id,
                skill_node.id,
                exc,
            )
            fallback = [skill_node.name]
            return fallback, f'- {skill_node.name}'

    def _filter_to_taught_concepts(
        self,
        concepts: list[str],
        *,
        taught_concepts: list[str],
    ) -> list[str]:
        if not taught_concepts:
            return self._dedupe_concepts(concepts, max_items=8)
        taught_pairs = [(item, self._normalize_concept(item)) for item in taught_concepts if item.strip()]
        filtered: list[str] = []
        for concept in concepts:
            normalized = self._normalize_concept(concept)
            if not normalized:
                continue
            for taught_raw, taught_norm in taught_pairs:
                if normalized in taught_norm or taught_norm in normalized:
                    filtered.append(taught_raw)
                    break
        return self._dedupe_concepts(filtered, max_items=8)

    def _extract_concepts_from_text(self, text: str, *, max_items: int = 3) -> list[str]:
        if not text:
            return []
        stop_words = {
            'what', 'which', 'when', 'where', 'why', 'how', 'that', 'this', 'from', 'with', 'into', 'about',
            'their', 'there', 'should', 'would', 'could', 'using', 'within', 'while', 'skill', 'topic',
            'question', 'answer', 'learner', 'level', 'node', 'apply', 'best', 'most', 'least', 'show', 'give',
        }
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_/-]{3,}", text.lower())
        concepts: list[str] = []
        for token in tokens:
            if token in stop_words:
                continue
            if token in concepts:
                continue
            concepts.append(token.replace('_', ' '))
            if len(concepts) >= max_items:
                break
        return concepts

    def _looks_like_guidance_not_answer(self, text: str) -> bool:
        value = (text or '').strip().lower()
        if len(value) < 18:
            return True
        weak_phrases = (
            'should include',
            'make sure to',
            'you should',
            'a strong answer',
            'a good answer',
            'the response should',
            'mention these points',
            'consider covering',
        )
        return any(phrase in value for phrase in weak_phrases)

    def _fallback_model_answer(
        self,
        *,
        assessment_style: str,
        question_type: str,
        prompt: str,
        concepts: list[str],
    ) -> str:
        concept_text = ', '.join(concepts[:3]) if concepts else 'the core concept'
        if question_type == 'multiple_choice':
            return (
                f'The correct choice is the option that directly applies {concept_text} to this prompt: "{prompt}". '
                'It is best because it is both accurate and specific to the asked scenario, while distractors are '
                'either incomplete, over-general, or conceptually wrong.'
            )
        if assessment_style in {'coding', 'code_completion', 'code_interpretation'}:
            return (
                '```python\n'
                'def solve(input_data):\n'
                '    """Model solution for the prompt."""\n'
                '    if input_data is None:\n'
                "        raise ValueError('input_data is required')\n"
                '    # 1) Validate inputs\n'
                '    # 2) Apply the target logic clearly\n'
                '    # 3) Return deterministic output\n'
                '    result = input_data\n'
                '    return result\n'
                '```\n'
                f'Why this works: it demonstrates {concept_text}, keeps control flow explicit, and is easy to test.'
            )
        if assessment_style == 'debugging':
            return (
                f'Root cause analysis: identify where "{prompt}" fails by tracing inputs and branches.\n'
                'Fix:\n'
                '1) reproduce the bug with a minimal test,\n'
                '2) isolate the failing line,\n'
                '3) apply a targeted code correction,\n'
                '4) confirm with regression checks.\n'
                f'Expected corrected reasoning should explicitly apply {concept_text}.'
            )
        if assessment_style == 'math_problem':
            first = concepts[0] if concepts else 'the relevant formula'
            return (
                f'Worked solution:\n'
                f'1) Write the governing relationship ({first}).\n'
                '2) Substitute the known values from the prompt.\n'
                '3) Simplify each intermediate step clearly.\n'
                '4) Compute the final value and verify units/constraints.\n'
                'Final answer: present one clear numeric/symbolic result with a short sanity check.'
            )
        if assessment_style == 'scenario':
            return (
                f'Model response:\n'
                f'- Decision: choose the option that best applies {concept_text}.\n'
                '- Reasoning: compare alternatives using concrete tradeoffs (risk, impact, feasibility).\n'
                '- Execution: define first step, ownership, and expected outcome.\n'
                '- Conclusion: justify why this option is strongest for the specific scenario.'
            )
        if assessment_style == 'flashcard':
            return f'{concept_text}: concise definition plus one practical implication tied to the prompt.'
        return (
            'Model answer:\n'
            f'1) Define the core idea ({concept_text}) in plain terms.\n'
            '2) Apply it directly to the exact question context.\n'
            '3) Add one concrete example or implication.\n'
            '4) Close with a crisp takeaway that answers the prompt.'
        )

    def _normalize_assessment_payload(
        self,
        payload: dict[str, Any],
        *,
        topic: Topic,
        skill_node: SkillNode,
        learner_level: str,
        question_count: int,
        style_sequence: list[str],
        taught_concepts: list[str],
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized['title'] = str(normalized.get('title') or f'{skill_node.name} Skill Assessment').strip()[:220]
        normalized['instructions'] = (
            str(normalized.get('instructions') or 'Answer each question in your own words where needed.').strip()[:380]
        )
        normalized['difficulty'] = max(1, min(5, int(normalized.get('difficulty') or skill_node.difficulty)))
        if normalized.get('target_level') not in {'beginner', 'intermediate', 'advanced'}:
            normalized['target_level'] = learner_level

        raw_questions = normalized.get('questions')
        if not isinstance(raw_questions, list):
            raw_questions = []

        expected_styles = style_sequence[:question_count]
        if len(expected_styles) < question_count:
            default_styles = build_assessment_style_sequence(
                allowed_styles=topic.allowed_assessment_styles,
                question_count=question_count,
                topic_text=f'{topic.name} {topic.description} {topic.goal}',
                skill_text=f'{skill_node.name} {skill_node.description}',
                learner_level=learner_level,
            )
            expected_styles = default_styles[:question_count]

        normalized_questions: list[dict[str, Any]] = []
        repaired_missing_concepts = 0

        for idx in range(min(len(raw_questions), question_count)):
            raw_question = raw_questions[idx] if isinstance(raw_questions[idx], dict) else {}
            assessment_style = str(raw_question.get('assessment_style') or '').strip()
            if assessment_style not in ASSESSMENT_STYLE_TO_QUESTION_TYPE:
                assessment_style = expected_styles[idx]

            question_type = raw_question.get('question_type')
            if question_type not in {
                'multiple_choice',
                'short_answer',
                'explain',
                'scenario',
                'error_spotting',
                'reflection',
            }:
                question_type = ASSESSMENT_STYLE_TO_QUESTION_TYPE[assessment_style]
            elif question_type != 'reflection':
                question_type = ASSESSMENT_STYLE_TO_QUESTION_TYPE[assessment_style]

            prompt = str(raw_question.get('prompt') or '').strip()
            if not prompt:
                prompt = f'Question {idx + 1}: apply {skill_node.name} in a practical way ({assessment_style.replace("_", " ")}).'

            expected_concepts = raw_question.get('expected_concepts')
            if isinstance(expected_concepts, list):
                concepts = [str(item).strip() for item in expected_concepts if str(item).strip()]
            else:
                concepts = []

            rubric_payload = raw_question.get('rubric')
            rubric: list[dict[str, Any]] = []
            if isinstance(rubric_payload, list):
                for criterion in rubric_payload:
                    if not isinstance(criterion, dict):
                        continue
                    concept = str(criterion.get('concept') or '').strip()
                    description = str(criterion.get('description') or '').strip()
                    if not concept:
                        continue
                    if not description:
                        description = f'Correctly addresses {concept}.'
                    weight_raw = criterion.get('weight', 0.5)
                    try:
                        weight = float(weight_raw)
                    except (TypeError, ValueError):
                        weight = 0.5
                    rubric.append(
                        {
                            'concept': concept[:120],
                            'description': description[:220],
                            'weight': max(0.0, min(1.0, weight)),
                        }
                    )

            if not concepts and rubric:
                concepts = [item['concept'] for item in rubric[:3]]
                repaired_missing_concepts += 1

            concepts = self._filter_to_taught_concepts(concepts, taught_concepts=taught_concepts)

            if not concepts and question_type != 'reflection':
                concept_seed = self._filter_to_taught_concepts(
                    self._extract_concepts_from_text(
                        f"{prompt} {skill_node.name} {skill_node.description}",
                        max_items=3,
                    ),
                    taught_concepts=taught_concepts,
                )
                if not concept_seed:
                    concept_seed = (taught_concepts[:3] or [skill_node.name.strip()[:80]])
                concepts = concept_seed
                repaired_missing_concepts += 1

            if question_type != 'reflection' and concepts:
                prompt_norm = self._normalize_concept(prompt)
                anchor = self._normalize_concept(concepts[0])
                if anchor and anchor not in prompt_norm:
                    prompt = f'{prompt.rstrip()} Focus on: {concepts[0]}.'

            model_answer = str(raw_question.get('model_answer') or '').strip()
            if question_type == 'reflection' and len(model_answer) < 12:
                model_answer = 'This is reflective; no single correct answer is required.'
            elif question_type != 'reflection' and len(model_answer) < 12:
                model_answer = self._fallback_model_answer(
                    assessment_style=assessment_style,
                    question_type=question_type,
                    prompt=prompt,
                    concepts=concepts,
                )
            elif question_type != 'reflection' and self._looks_like_guidance_not_answer(model_answer):
                model_answer = self._fallback_model_answer(
                    assessment_style=assessment_style,
                    question_type=question_type,
                    prompt=prompt,
                    concepts=concepts,
                )

            hints_payload = raw_question.get('hints')
            hints: list[str] = []
            if isinstance(hints_payload, list):
                hints = [str(item).strip() for item in hints_payload if str(item).strip()]
            if not hints:
                if concepts:
                    hints = [f'Center the response on: {concepts[0]}']
                    if len(concepts) > 1:
                        hints.append(f'Include this concept too: {concepts[1]}')
                else:
                    hints = ['Start with the core concept, then apply it directly to the prompt.']

            choices_payload = raw_question.get('choices')
            choices: list[str] | None = None
            answer_index: int | None = None
            if question_type == 'multiple_choice':
                base_choices: list[str] = []
                if isinstance(choices_payload, list):
                    base_choices = [str(item).strip() for item in choices_payload if str(item).strip()]
                if len(base_choices) < 4:
                    base_choices.extend(
                        [
                            f'Core {skill_node.name} concept',
                            'A partially correct approach with a key gap',
                            'A common misconception',
                            'An unrelated option',
                        ]
                    )
                choices = base_choices[:4]
                raw_answer = raw_question.get('answer_index', 0)
                try:
                    answer_index = int(raw_answer)
                except (TypeError, ValueError):
                    answer_index = 0
                answer_index = max(0, min(3, answer_index))
            else:
                answer_index = None

            if question_type in {'short_answer', 'explain', 'scenario', 'error_spotting'} and not rubric:
                weight = round(1.0 / max(1, len(concepts[:3])), 2)
                rubric = [
                    {
                        'concept': concept,
                        'description': f'Uses {concept} accurately in the response.',
                        'weight': weight,
                    }
                    for concept in concepts[:3]
                ]

            normalized_question: dict[str, Any] = {
                'id': str(raw_question.get('id') or f'q_{idx + 1}')[:40],
                'assessment_style': assessment_style,
                'question_type': question_type,
                'prompt': prompt[:700],
                'choices': choices,
                'answer_index': answer_index,
                'model_answer': model_answer[:2600],
                'hints': hints[:4],
                'expected_concepts': concepts[:8] if question_type != 'reflection' else [],
                'rubric': rubric[:8],
                'difficulty': max(1, min(5, int(raw_question.get('difficulty') or normalized['difficulty']))),
                'confidence_prompt': str(
                    raw_question.get('confidence_prompt') or 'How sure are you about this answer?'
                )[:120],
            }
            normalized_questions.append(normalized_question)

        while len(normalized_questions) < question_count:
            idx = len(normalized_questions)
            fallback_style = expected_styles[idx]
            fallback_type = ASSESSMENT_STYLE_TO_QUESTION_TYPE[fallback_style]
            concept = (taught_concepts[0] if taught_concepts else skill_node.name.strip()[:80])
            fallback_prompt = (
                f'Question {idx + 1}: '
                f'{"Choose the best option" if fallback_type == "multiple_choice" else "Respond briefly"} '
                f'for {skill_node.name} ({fallback_style.replace("_", " ")}).'
            )
            question_payload: dict[str, Any] = {
                'id': f'q_{idx + 1}',
                'assessment_style': fallback_style,
                'question_type': fallback_type,
                'prompt': fallback_prompt[:700],
                'choices': None,
                'answer_index': None,
                'model_answer': self._fallback_model_answer(
                    assessment_style=fallback_style,
                    question_type=fallback_type,
                    prompt=fallback_prompt,
                    concepts=[concept],
                ),
                'hints': [f'Use {concept} explicitly in your response.'],
                'expected_concepts': [] if fallback_type == 'reflection' else [concept],
                'rubric': [],
                'difficulty': normalized['difficulty'],
                'confidence_prompt': 'How sure are you about this answer?',
            }
            if fallback_type == 'multiple_choice':
                question_payload['choices'] = [
                    f'Correct foundational use of {skill_node.name}',
                    'An incomplete but plausible answer',
                    'A common misconception',
                    'An unrelated response',
                ]
                question_payload['answer_index'] = 0
            elif fallback_type in {'short_answer', 'explain', 'scenario', 'error_spotting'}:
                question_payload['rubric'] = [
                    {
                        'concept': concept,
                        'description': f'Accurately applies {concept}.',
                        'weight': 1.0,
                    }
                ]
            elif fallback_type == 'reflection':
                question_payload['model_answer'] = 'This is reflective; no single correct answer is required.'
            normalized_questions.append(question_payload)

        normalized['questions'] = normalized_questions[:question_count]
        style_counts: dict[str, int] = {}
        for item in normalized['questions']:
            style = str(item.get('assessment_style', 'unknown'))
            style_counts[style] = style_counts.get(style, 0) + 1
        logger.info(
            'assessment.normalize topic_id=%s skill_id=%s repaired_missing_concepts=%s composition=%s',
            topic.id,
            skill_node.id,
            repaired_missing_concepts,
            style_counts,
        )
        return normalized

    async def _generate_assessment_plan_with_fallback(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        learner_level: str,
        technical_depth: str,
        user_state: UserSkillState | None,
        difficulty_band: str,
        prerequisite_names: list[str],
        question_count: int,
        recommended_mix: dict[str, int],
        style_sequence: list[str],
        allowed_styles: list[str],
        taught_concepts: list[str],
        taught_context_text: str,
    ) -> tuple[AssessmentPlan, bool]:
        system_prompt = (
            'You are AssessmentAgent.\n'
            'Generate rigorous, learner-friendly assessments for one skill node.\n'
            'Assess understanding, application, reasoning, and confidence.\n'
            'Keep scope tightly aligned to the selected node and its prerequisites.\n'
            'Avoid domain assumptions; keep prompts reusable across technical and non-technical skills.'
        )
        user_prompt = (
            f'Topic: {topic.name}\\n'
            f'Topic goal: {topic.goal or "No explicit goal"}\\n'
            f'Skill node: {skill_node.name}\\n'
            f'Skill description: {skill_node.description}\\n'
            f'Skill difficulty (1-5): {skill_node.difficulty} ({difficulty_band})\\n'
            f'Learner level estimate: {learner_level}\\n'
            f'Technical depth preference: {technical_depth}\\n'
            f'Learner progress state: {user_state.progress_state if user_state else "not_started"}\\n'
            f'Prerequisites: {", ".join(prerequisite_names) if prerequisite_names else "None"}\\n'
            f'Target question count: {question_count}\\n'
            f'Allowed assessment styles: {json.dumps(allowed_styles)}\\n'
            f'Recommended style mix: {json.dumps(recommended_mix)}\\n'
            f'Required style order to follow: {json.dumps(style_sequence)}\\n\\n'
            'Taught concepts available in lesson/examples (assessment must stay inside this coverage):\\n'
            f'{taught_context_text or "- " + skill_node.name}\\n\\n'
            'Output contract:\\n'
            '- Include fields: title, instructions, difficulty, target_level, questions.\\n'
            '- For every question include: id, assessment_style, question_type, prompt, model_answer, hints, difficulty, confidence_prompt.\\n'
            '- assessment_style must be one of the allowed styles.\\n'
            '- question_type must align to style mapping:\\n'
            '  open_text->explain, short_answer->short_answer, multiple_choice->multiple_choice, flashcard->short_answer,\\n'
            '  scenario->scenario, coding->scenario, debugging->error_spotting, code_completion->short_answer,\\n'
            '  code_interpretation->explain, math_problem->short_answer.\\n'
            '- multiple_choice must include exactly 4 choices and answer_index 0..3.\\n'
            '- model_answer must be a concrete high-quality answer for the exact question, never generic guidance.\\n'
            '- non-multiple-choice questions must include expected_concepts (>=1) and rubric criteria.\\n'
            '- expected_concepts for non-reflection questions must come from taught concepts listed above.\\n'
            '- Do not test concepts that are not explicitly taught in lesson/examples context above.\\n'
            '- Never return empty arrays for required conceptual fields.\\n'
            '- Keep question prompts concise and node-specific.\\n'
            '- Intro/foundation nodes must avoid advanced capstone asks.\\n\\n'
            f'- Technical depth guidance: {technical_depth_prompt_guidance(normalize_technical_depth(technical_depth))}\\n\\n'
            'Valid example fragment:\\n'
            '{\"id\":\"q_1\",\"assessment_style\":\"short_answer\",\"question_type\":\"short_answer\",\"prompt\":\"...\",'
            '\"model_answer\":\"A concise but complete answer...\",\"hints\":[\"mention x clearly\"],\"expected_concepts\":[\"x\"],'
            '\"rubric\":[{\"concept\":\"x\",\"description\":\"...\",\"weight\":1.0}],\"difficulty\":2,'
            '\"confidence_prompt\":\"How sure are you about this answer?\"}'
        )

        def _repair(payload: dict[str, Any]) -> dict[str, Any]:
            return self._normalize_assessment_payload(
                payload,
                topic=topic,
                skill_node=skill_node,
                learner_level=learner_level,
                question_count=question_count,
                style_sequence=style_sequence,
                taught_concepts=taught_concepts,
            )

        try:
            plan = await self.llm_service.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=AssessmentPlan,
                temperature=0.2,
                max_tokens=2600,
                retries=2,
                repair_payload=_repair,
            )
            return plan, False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'assessment.primary_generation_failed topic_id=%s skill_id=%s error=%s',
                topic.id,
                skill_node.id,
                exc,
            )

        fallback_prompt = (
            f'Topic: {topic.name}\\n'
            f'Skill node: {skill_node.name}\\n'
            f'Skill description: {skill_node.description}\\n'
            f'Learner level: {learner_level}\\n'
            f'Technical depth: {technical_depth}\\n'
            f'Generate exactly {max(4, min(question_count, 5))} concise questions across 3-5 types.\\n'
            f'Allowed styles: {json.dumps(allowed_styles)}\\n'
            f'Style order to follow: {json.dumps(style_sequence[:max(4, min(question_count, 5))])}\\n'
            'Prioritize correctness and schema validity over creativity.\\n'
            'Keep each question practical and tightly scoped to this node.'
        )

        try:
            fallback_count = max(4, min(question_count, 5))
            plan = await self.llm_service.generate_structured(
                system_prompt='You are AssessmentAgent. Return only schema-valid JSON.',
                user_prompt=fallback_prompt,
                schema_model=AssessmentPlan,
                temperature=0.1,
                max_tokens=1800,
                retries=1,
                repair_payload=lambda payload: self._normalize_assessment_payload(
                    payload,
                    topic=topic,
                    skill_node=skill_node,
                    learner_level=learner_level,
                    question_count=fallback_count,
                    style_sequence=style_sequence[:fallback_count],
                    taught_concepts=taught_concepts,
                ),
            )
            logger.warning(
                'assessment.fallback_generation_used topic_id=%s skill_id=%s question_count=%s',
                topic.id,
                skill_node.id,
                fallback_count,
            )
            return plan, True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'assessment.fallback_generation_failed topic_id=%s skill_id=%s error=%s',
                topic.id,
                skill_node.id,
                exc,
            )

        deterministic = self._normalize_assessment_payload(
            {
                'title': f'{skill_node.name} Starter Assessment',
                'instructions': 'Answer each question and include your reasoning where applicable.',
                'difficulty': skill_node.difficulty,
                'target_level': learner_level,
                'questions': [],
            },
            topic=topic,
            skill_node=skill_node,
            learner_level=learner_level,
            question_count=max(4, min(question_count, 5)),
            style_sequence=style_sequence[: max(4, min(question_count, 5))],
            taught_concepts=taught_concepts,
        )
        plan = AssessmentPlan.model_validate(deterministic)
        logger.warning(
            'assessment.deterministic_fallback_used topic_id=%s skill_id=%s question_count=%s',
            topic.id,
            skill_node.id,
            len(plan.questions),
        )
        return plan, True

    def _active_assessment(self, db: Session, *, user_id: int, skill_node_id: int) -> Assessment | None:
        return db.scalar(
            select(Assessment)
            .where(
                Assessment.user_id == user_id,
                Assessment.skill_node_id == skill_node_id,
                Assessment.is_active.is_(True),
            )
            .order_by(Assessment.version.desc(), Assessment.created_at.desc())
        )

    def _serialize_questions(self, rows: list[AssessmentQuestion]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for row in rows:
            rubric = row.rubric or {}
            serialized.append(
                {
                    'id': f'q{row.id}',
                    'question_id': row.id,
                    'question_type': row.question_type.value,
                    'assessment_style': row.assessment_style or 'short_answer',
                    'prompt': row.prompt,
                    'choices': row.choices or [],
                    'expected_concepts': row.expected_concepts or [],
                    'rubric': rubric,
                    'difficulty': row.difficulty,
                    'order_index': row.order_index,
                }
            )
        serialized.sort(key=lambda item: item['order_index'])
        return serialized

    def _build_answer_reveal(self, question: AssessmentQuestion) -> dict[str, Any]:
        style = question.assessment_style or 'short_answer'
        key_points = question.expected_concepts or []
        if question.question_type == AssessmentQuestionType.reflection:
            return {
                'question_id': question.id,
                'question_type': question.question_type.value,
                'assessment_style': style,
                'answer': 'Reflection prompt: there is no single correct answer.',
                'key_points': [],
            }
        answer = (question.model_answer or '').strip()
        if not answer or self._looks_like_guidance_not_answer(answer):
            answer = self._fallback_model_answer(
                assessment_style=style,
                question_type=question.question_type.value,
                prompt=question.prompt,
                concepts=key_points,
            )
        if question.question_type == AssessmentQuestionType.multiple_choice:
            rubric = question.rubric or {}
            answer_index = rubric.get('answer_index')
            choice_line = ''
            if isinstance(answer_index, int) and question.choices and 0 <= answer_index < len(question.choices):
                choice_line = f'Correct option: {answer_index + 1}) {question.choices[answer_index]}'
            elif question.choices:
                choice_line = f'Correct option: {question.choices[0]}'
            if choice_line:
                answer = f'{choice_line}\nWhy: {answer}'
        hints = question.hints or []

        return {
            'question_id': question.id,
            'question_type': question.question_type.value,
            'assessment_style': style,
            'answer': answer,
            'key_points': list(dict.fromkeys(key_points + hints))[:6],
        }

    async def generate_assessment(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        user_id: int,
        question_count: int = 6,
        regenerate: bool = False,
        preferred_styles: list[str] | None = None,
    ) -> tuple[Assessment, AssessmentSource]:
        existing = self._active_assessment(db, user_id=user_id, skill_node_id=skill_node.id)
        if existing and not regenerate:
            logger.info(
                'assessment.loaded_from_store topic_id=%s skill_id=%s assessment_id=%s version=%s',
                topic.id,
                skill_node.id,
                existing.id,
                existing.version,
            )
            return existing, 'stored'

        question_count = max(4, min(10, question_count))
        user_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        learner_level = self._learner_level(user_state)
        technical_depth = normalize_technical_depth(getattr(topic, 'technical_depth', None))
        difficulty_band = self._difficulty_band(skill_node.difficulty)
        allowed_styles = normalize_assessment_styles(preferred_styles or topic.allowed_assessment_styles)
        learner_level_for_styles = normalize_starting_skill_level(learner_level)
        style_sequence = build_assessment_style_sequence(
            allowed_styles=allowed_styles,
            question_count=question_count,
            topic_text=f'{topic.name} {topic.description} {topic.goal}',
            skill_text=f'{skill_node.name} {skill_node.description}',
            learner_level=learner_level_for_styles,
        )
        recommended_mix = self._recommended_mix(style_sequence=style_sequence)
        logger.info(
            'assessment.style_plan topic_id=%s skill_id=%s allowed=%s sequence=%s',
            topic.id,
            skill_node.id,
            allowed_styles,
            style_sequence,
        )
        taught_concepts, taught_context_text = self._teaching_context(
            db,
            user_id=user_id,
            topic=topic,
            skill_node=skill_node,
        )
        logger.info(
            'assessment.teaching_context topic_id=%s skill_id=%s concepts=%s',
            topic.id,
            skill_node.id,
            len(taught_concepts),
        )

        prerequisite_ids = db.scalars(
            select(SkillEdge.parent_skill_id).where(
                SkillEdge.topic_id == topic.id,
                SkillEdge.child_skill_id == skill_node.id,
                SkillEdge.edge_type == 'prerequisite',
            )
        ).all()
        prerequisite_names = []
        if prerequisite_ids:
            prerequisite_names = [
                node.name
                for node in db.scalars(select(SkillNode).where(SkillNode.id.in_(prerequisite_ids))).all()
            ]

        plan, used_fallback = await self._generate_assessment_plan_with_fallback(
            topic=topic,
            skill_node=skill_node,
            learner_level=learner_level,
            technical_depth=technical_depth,
            user_state=user_state,
            difficulty_band=difficulty_band,
            prerequisite_names=prerequisite_names,
            question_count=question_count,
            recommended_mix=recommended_mix,
            style_sequence=style_sequence,
            allowed_styles=allowed_styles,
            taught_concepts=taught_concepts,
            taught_context_text=taught_context_text,
        )

        questions = plan.questions[:question_count]
        if len(questions) < 4:
            raise ValueError('Assessment generation returned too few questions.')

        next_version = 1
        if existing:
            next_version = existing.version + 1
            db.execute(
                update(Assessment)
                .where(
                    Assessment.user_id == user_id,
                    Assessment.skill_node_id == skill_node.id,
                    Assessment.is_active.is_(True),
                )
                .values(is_active=False)
            )

        assessment = Assessment(
            topic_id=topic.id,
            skill_node_id=skill_node.id,
            user_id=user_id,
            version=next_version,
            is_active=True,
            title=plan.title,
            difficulty=plan.difficulty,
            target_level=plan.target_level,
            question_mix=recommended_mix,
            questions=[],
        )
        db.add(assessment)
        db.flush()

        question_rows: list[AssessmentQuestion] = []
        for idx, question in enumerate(questions):
            rubric_payload = {
                'criteria': [criterion.model_dump() for criterion in question.rubric],
                'answer_index': question.answer_index,
                'confidence_prompt': question.confidence_prompt,
            }
            row = AssessmentQuestion(
                assessment_id=assessment.id,
                assessment_style=question.assessment_style,
                question_type=AssessmentQuestionType(question.question_type),
                prompt=question.prompt,
                choices=question.choices,
                model_answer=question.model_answer,
                hints=question.hints,
                expected_concepts=question.expected_concepts,
                rubric=rubric_payload,
                difficulty=question.difficulty,
                order_index=idx,
            )
            db.add(row)
            db.flush()
            question_rows.append(row)

        assessment.questions = self._serialize_questions(question_rows)
        db.commit()
        db.refresh(assessment)

        source: AssessmentSource = 'regenerated' if existing else 'generated'
        logger.info(
            'assessment.generated topic_id=%s skill_id=%s assessment_id=%s version=%s source=%s question_count=%s fallback=%s',
            topic.id,
            skill_node.id,
            assessment.id,
            assessment.version,
            source,
            len(question_rows),
            used_fallback,
        )
        return assessment, source

    def _mcq_score(
        self,
        *,
        question: AssessmentQuestion,
        selected_option_index: int | None,
    ) -> tuple[float, str]:
        rubric = question.rubric or {}
        expected_index = rubric.get('answer_index')
        if expected_index is None:
            return 0.0, 'No answer key was available for this question.'
        is_correct = int(expected_index) == int(selected_option_index) if selected_option_index is not None else False
        if is_correct:
            return 1.0, 'Correct choice. Solid recognition of the core concept.'
        return 0.0, 'Incorrect choice. Review the underlying concept and why alternatives are less appropriate.'

    async def _evaluate_open_response_questions(
        self,
        *,
        assessment: Assessment,
        topic: Topic,
        skill_node: SkillNode,
        responses: list[dict[str, Any]],
    ) -> AssessmentEvaluationPlan:
        system_prompt = (
            'You are AssessmentEvaluator.\n'
            'Score each learner answer against expected concepts and rubric criteria.\n'
            'Be fair, specific, and concise.\n'
            'Score in [0,1].\n'
            'Use concept coverage and reasoning quality, not exact wording.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Skill node: {skill_node.name}\n'
            f'Assessment title: {assessment.title}\n\n'
            'Evaluate the following learner responses:\n'
            f'{json.dumps(responses, indent=2)}\n\n'
            'Return question-level scoring plus concise overall strengths, weaknesses, review focus, and follow-up.'
        )
        return await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=AssessmentEvaluationPlan,
            temperature=0.15,
            max_tokens=2200,
        )

    def _compute_mastery_delta(
        self,
        *,
        overall_score: float,
        confidence_values: list[float],
    ) -> tuple[float, float]:
        confidence_avg = mean(confidence_values) if confidence_values else 0.0
        delta = (self._clamp(overall_score) - 0.55) * 0.45
        return self._clamp(delta, -0.25, 0.25), confidence_avg

    async def score_assessment(
        self,
        db: Session,
        *,
        assessment: Assessment,
        topic: Topic,
        skill_node: SkillNode,
        user_id: int,
        responses: list[dict[str, Any]],
        mastery_eligible: bool = True,
    ) -> AssessmentScoringResult:
        question_rows = db.scalars(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment.id)
            .order_by(AssessmentQuestion.order_index.asc())
        ).all()
        if not question_rows:
            raise ValueError('Assessment has no stored questions.')

        response_map: dict[int, dict[str, Any]] = {}
        for item in responses:
            question_id = int(item.get('question_id', 0))
            if question_id <= 0:
                continue
            response_map[question_id] = item

        open_eval_payload: list[dict[str, Any]] = []
        for question in question_rows:
            if question.question_type == AssessmentQuestionType.multiple_choice:
                continue
            if question.question_type == AssessmentQuestionType.reflection:
                continue
            response = response_map.get(question.id, {})
            open_eval_payload.append(
                {
                    'question_id': str(question.id),
                    'question_type': question.question_type.value,
                    'assessment_style': question.assessment_style or 'short_answer',
                    'prompt': question.prompt,
                    'expected_concepts': question.expected_concepts or [],
                    'rubric': question.rubric or {},
                    'learner_answer': (response.get('answer_text') or '').strip(),
                }
            )

        evaluation: AssessmentEvaluationPlan | None = None
        if open_eval_payload:
            evaluation = await self._evaluate_open_response_questions(
                assessment=assessment,
                topic=topic,
                skill_node=skill_node,
                responses=open_eval_payload,
            )

        evaluation_map = {
            int(item.question_id): item
            for item in (evaluation.question_feedback if evaluation else [])
            if str(item.question_id).isdigit()
        }

        scored_questions: list[ScoredQuestion] = []
        confidence_values: list[float] = []
        selected_indices_legacy: list[int] = []

        for question in question_rows:
            response = response_map.get(question.id, {})
            selected_option_index = response.get('selected_option_index')
            answer_text = (response.get('answer_text') or '').strip()
            confidence_raw = response.get('confidence_score')
            confidence_score = None
            if confidence_raw is not None:
                confidence_score = self._clamp(float(confidence_raw))
                confidence_values.append(confidence_score)

            if question.question_type == AssessmentQuestionType.multiple_choice:
                score, feedback = self._mcq_score(question=question, selected_option_index=selected_option_index)
                strengths = ['Correctly identified the right option.'] if score >= 1.0 else []
                missing = [] if score >= 1.0 else (question.expected_concepts or [])
                selected_indices_legacy.append(int(selected_option_index) if selected_option_index is not None else -1)
                graded = True
            elif question.question_type == AssessmentQuestionType.reflection:
                score = 0.0
                feedback = 'Recorded for your learning journal.'
                strengths = []
                missing = []
                selected_indices_legacy.append(-1)
                graded = False
            else:
                evaluated = evaluation_map.get(question.id)
                if evaluated is None:
                    score = 0.0
                    feedback = 'No evaluable response was found. Add a concise answer and retry.'
                    strengths = []
                    missing = question.expected_concepts or []
                else:
                    score = self._clamp(float(evaluated.score))
                    feedback = evaluated.feedback
                    strengths = evaluated.strengths
                    missing = evaluated.missing_concepts
                selected_indices_legacy.append(-1)
                graded = True

            scored_questions.append(
                ScoredQuestion(
                    question=question,
                    score=score,
                    feedback=feedback,
                    selected_option_index=int(selected_option_index)
                    if selected_option_index is not None
                    else None,
                    answer_text=answer_text,
                    confidence_score=confidence_score,
                    strengths=strengths,
                    missing_concepts=missing,
                    graded=graded,
                )
            )

        graded_questions = [item for item in scored_questions if item.graded]
        overall_score = self._clamp(mean(item.score for item in graded_questions)) if graded_questions else 0.0
        mastery_delta, confidence_avg = self._compute_mastery_delta(
            overall_score=overall_score,
            confidence_values=confidence_values,
        )
        if not mastery_eligible:
            mastery_delta = 0.0

        fallback_strengths = [
            item for scored in scored_questions for item in scored.strengths if item
        ][:4]
        fallback_weaknesses = [
            item for scored in scored_questions for item in scored.missing_concepts if item
        ][:4]
        strengths = (evaluation.strengths if evaluation else []) or fallback_strengths
        weaknesses = (evaluation.weaknesses if evaluation else []) or fallback_weaknesses
        review_next = (
            evaluation.review_next
            if evaluation
            else 'Review weak concepts from low-scoring questions and retry with shorter, concept-focused answers.'
        )
        recommended_follow_up = (
            evaluation.recommended_follow_up
            if evaluation
            else f'Regenerate a lesson for "{skill_node.name}" and revisit exercises before reassessment.'
        )
        summary = (
            evaluation.summary
            if evaluation
            else f'Overall score {round(overall_score * 100)}%. Continue with targeted review then reassess.'
        )
        if not mastery_eligible:
            summary = (
                'Practice attempt completed. Mastery was not updated because answers were revealed for this assessment. '
                'Generate a fresh assessment for mastery credit.'
            )

        feedback_rows = [
            {
                'question_id': item.question.id,
                'question_type': item.question.question_type.value,
                'assessment_style': item.question.assessment_style or 'short_answer',
                'score': round(item.score, 3) if item.graded else None,
                'confidence_score': round(item.confidence_score, 3) if item.confidence_score is not None else None,
                'feedback': item.feedback,
                'missing_concepts': item.missing_concepts,
            }
            for item in scored_questions
        ]

        attempt = AssessmentAttempt(
            assessment_id=assessment.id,
            user_id=user_id,
            answers=selected_indices_legacy,
            score=overall_score,
            confidence_avg=confidence_avg,
            mastery_delta=mastery_delta,
            mastery_eligible=mastery_eligible,
            practice_mode=not mastery_eligible,
            strengths=strengths,
            weaknesses=weaknesses,
            review_next=review_next,
            recommended_follow_up=recommended_follow_up,
            feedback=feedback_rows,
        )
        db.add(attempt)
        db.flush()

        for item in scored_questions:
            db.add(
                AssessmentResponse(
                    attempt_id=attempt.id,
                    question_id=item.question.id,
                    answer_text=item.answer_text,
                    selected_option_index=item.selected_option_index,
                    confidence_score=item.confidence_score,
                    score=item.score,
                    feedback=item.feedback,
                )
            )

        db.add(
            AssessmentFeedback(
                attempt_id=attempt.id,
                strengths=strengths,
                weaknesses=weaknesses,
                review_next=review_next,
                summary=summary,
            )
        )
        db.commit()
        db.refresh(attempt)

        logger.info(
            'assessment.scored assessment_id=%s user_id=%s attempt_id=%s score=%.3f confidence_avg=%.3f mastery_delta=%.3f mastery_eligible=%s',
            assessment.id,
            user_id,
            attempt.id,
            overall_score,
            confidence_avg,
            mastery_delta,
            mastery_eligible,
        )

        return AssessmentScoringResult(
            attempt=attempt,
            overall_score=overall_score,
            confidence_avg=confidence_avg,
            mastery_delta=mastery_delta,
            feedback=feedback_rows,
            strengths=strengths,
            weaknesses=weaknesses,
            review_next=review_next,
            recommended_follow_up=recommended_follow_up,
            summary=summary,
            mastery_eligible=mastery_eligible,
            practice_mode=not mastery_eligible,
        )

    def get_assessment(self, db: Session, *, assessment_id: int, user_id: int) -> Assessment | None:
        return db.scalar(select(Assessment).where(Assessment.id == assessment_id, Assessment.user_id == user_id))

    def get_attempt(self, db: Session, *, attempt_id: int, user_id: int) -> AssessmentAttempt | None:
        return db.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.id == attempt_id,
                AssessmentAttempt.user_id == user_id,
            )
        )

    def reveal_answers(
        self,
        db: Session,
        *,
        assessment: Assessment,
        user_id: int,
    ) -> list[dict[str, Any]]:
        if assessment.user_id != user_id:
            raise ValueError('Assessment does not belong to this user.')

        rows = db.scalars(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment.id)
            .order_by(AssessmentQuestion.order_index.asc())
        ).all()
        if not rows:
            raise ValueError('Assessment has no questions to reveal.')

        if not assessment.answers_revealed:
            assessment.answers_revealed = True
            assessment.answers_revealed_at = datetime.utcnow()
            db.commit()
            db.refresh(assessment)
            logger.info(
                'assessment.answers_revealed assessment_id=%s user_id=%s',
                assessment.id,
                user_id,
            )

        return [self._build_answer_reveal(row) for row in rows]
