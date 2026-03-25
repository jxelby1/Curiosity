from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from statistics import mean
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ProviderError
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentFeedback,
    AssessmentQuestion,
    AssessmentQuestionType,
    AssessmentResponse,
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

    def _recommended_mix(self, *, learner_level: str, question_count: int) -> dict[str, int]:
        question_count = max(4, min(10, question_count))
        if learner_level == 'beginner':
            pattern = ['multiple_choice', 'multiple_choice', 'short_answer', 'explain', 'scenario', 'reflection']
        elif learner_level == 'intermediate':
            pattern = ['multiple_choice', 'short_answer', 'explain', 'scenario', 'error_spotting', 'reflection']
        else:
            pattern = ['multiple_choice', 'short_answer', 'explain', 'scenario', 'error_spotting', 'reflection']

        counts: dict[str, int] = {}
        for idx in range(question_count):
            key = pattern[idx % len(pattern)]
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _question_type_sequence(self, *, learner_level: str, question_count: int) -> list[str]:
        if learner_level == 'beginner':
            pattern = ['multiple_choice', 'multiple_choice', 'short_answer', 'scenario', 'reflection']
        elif learner_level == 'intermediate':
            pattern = ['multiple_choice', 'short_answer', 'explain', 'scenario', 'reflection']
        else:
            pattern = ['multiple_choice', 'short_answer', 'explain', 'scenario', 'error_spotting', 'reflection']
        return [pattern[idx % len(pattern)] for idx in range(question_count)]

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

    def _normalize_assessment_payload(
        self,
        payload: dict[str, Any],
        *,
        topic: Topic,
        skill_node: SkillNode,
        learner_level: str,
        question_count: int,
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

        expected_types = self._question_type_sequence(learner_level=learner_level, question_count=question_count)
        normalized_questions: list[dict[str, Any]] = []
        repaired_missing_concepts = 0

        for idx in range(min(len(raw_questions), question_count)):
            raw_question = raw_questions[idx] if isinstance(raw_questions[idx], dict) else {}
            question_type = raw_question.get('question_type')
            if question_type not in {
                'multiple_choice',
                'short_answer',
                'explain',
                'scenario',
                'error_spotting',
                'reflection',
            }:
                question_type = expected_types[idx]

            prompt = str(raw_question.get('prompt') or '').strip()
            if not prompt:
                prompt = f'Question {idx + 1}: apply {skill_node.name} in a practical way.'

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

            if not concepts and question_type != 'reflection':
                concept_seed = self._extract_concepts_from_text(
                    f"{prompt} {skill_node.name} {skill_node.description}",
                    max_items=3,
                )
                if not concept_seed:
                    concept_seed = [skill_node.name.strip()[:80]]
                concepts = concept_seed
                repaired_missing_concepts += 1

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
                'question_type': question_type,
                'prompt': prompt[:700],
                'choices': choices,
                'answer_index': answer_index,
                'expected_concepts': concepts[:8] if question_type != 'reflection' else [],
                'rubric': rubric[:8],
                'difficulty': max(1, min(5, int(raw_question.get('difficulty') or normalized['difficulty']))),
                'confidence_prompt': str(
                    raw_question.get('confidence_prompt') or 'How confident are you in your answer?'
                )[:120],
            }
            normalized_questions.append(normalized_question)

        while len(normalized_questions) < question_count:
            idx = len(normalized_questions)
            fallback_type = expected_types[idx]
            concept = skill_node.name.strip()[:80]
            fallback_prompt = (
                f'Question {idx + 1}: '
                f'{"Choose the best option" if fallback_type == "multiple_choice" else "Respond briefly"} '
                f'for {skill_node.name}.'
            )
            question_payload: dict[str, Any] = {
                'id': f'q_{idx + 1}',
                'question_type': fallback_type,
                'prompt': fallback_prompt[:700],
                'choices': None,
                'answer_index': None,
                'expected_concepts': [] if fallback_type == 'reflection' else [concept],
                'rubric': [],
                'difficulty': normalized['difficulty'],
                'confidence_prompt': 'How confident are you in your answer?',
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
            normalized_questions.append(question_payload)

        normalized['questions'] = normalized_questions[:question_count]
        type_counts: dict[str, int] = {}
        for item in normalized['questions']:
            question_type = str(item.get('question_type', 'unknown'))
            type_counts[question_type] = type_counts.get(question_type, 0) + 1
        logger.info(
            'assessment.normalize topic_id=%s skill_id=%s repaired_missing_concepts=%s composition=%s',
            topic.id,
            skill_node.id,
            repaired_missing_concepts,
            type_counts,
        )
        return normalized

    async def _generate_assessment_plan_with_fallback(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        learner_level: str,
        user_state: UserSkillState | None,
        difficulty_band: str,
        prerequisite_names: list[str],
        question_count: int,
        recommended_mix: dict[str, int],
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
            f'Learner progress state: {user_state.progress_state if user_state else "not_started"}\\n'
            f'Prerequisites: {", ".join(prerequisite_names) if prerequisite_names else "None"}\\n'
            f'Target question count: {question_count}\\n'
            f'Recommended question-type mix: {json.dumps(recommended_mix)}\\n\\n'
            'Output contract:\\n'
            '- Include fields: title, instructions, difficulty, target_level, questions.\\n'
            '- For every question include: id, question_type, prompt, difficulty, confidence_prompt.\\n'
            '- multiple_choice must include exactly 4 choices and answer_index 0..3.\\n'
            '- short_answer/explain/scenario/error_spotting must include expected_concepts (>=1) and rubric criteria.\\n'
            '- reflection should focus on confidence/metacognition and may have empty expected_concepts.\\n'
            '- Never return empty arrays for required conceptual fields.\\n'
            '- Keep question prompts concise and node-specific.\\n'
            '- Intro/foundation nodes must avoid advanced capstone asks.\\n\\n'
            'Valid example fragment:\\n'
            '{\"id\":\"q_1\",\"question_type\":\"short_answer\",\"prompt\":\"...\",\"expected_concepts\":[\"x\"],'
            '\"rubric\":[{\"concept\":\"x\",\"description\":\"...\",\"weight\":1.0}],\"difficulty\":2,'
            '\"confidence_prompt\":\"How confident are you in your answer?\"}'
        )

        def _repair(payload: dict[str, Any]) -> dict[str, Any]:
            return self._normalize_assessment_payload(
                payload,
                topic=topic,
                skill_node=skill_node,
                learner_level=learner_level,
                question_count=question_count,
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
            f'Generate exactly {max(4, min(question_count, 5))} concise questions across 3-5 types.\\n'
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

    async def generate_assessment(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        user_id: int,
        question_count: int = 6,
        regenerate: bool = False,
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
        difficulty_band = self._difficulty_band(skill_node.difficulty)
        recommended_mix = self._recommended_mix(learner_level=learner_level, question_count=question_count)

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
            user_state=user_state,
            difficulty_band=difficulty_band,
            prerequisite_names=prerequisite_names,
            question_count=question_count,
            recommended_mix=recommended_mix,
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
                question_type=AssessmentQuestionType(question.question_type),
                prompt=question.prompt,
                choices=question.choices,
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
            response = response_map.get(question.id, {})
            open_eval_payload.append(
                {
                    'question_id': str(question.id),
                    'question_type': question.question_type.value,
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
                )
            )

        overall_score = self._clamp(mean(item.score for item in scored_questions))
        mastery_delta, confidence_avg = self._compute_mastery_delta(
            overall_score=overall_score,
            confidence_values=confidence_values,
        )

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

        feedback_rows = [
            {
                'question_id': item.question.id,
                'question_type': item.question.question_type.value,
                'score': round(item.score, 3),
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
            'assessment.scored assessment_id=%s user_id=%s attempt_id=%s score=%.3f confidence_avg=%.3f mastery_delta=%.3f',
            assessment.id,
            user_id,
            attempt.id,
            overall_score,
            confidence_avg,
            mastery_delta,
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
