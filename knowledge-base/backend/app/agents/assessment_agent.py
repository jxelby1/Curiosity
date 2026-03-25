from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Assessment, AssessmentAttempt, SkillNode, Topic
from app.schemas.llm import QuizPlan
from app.services.llm import LLMService


logger = logging.getLogger(__name__)
QuizSource = Literal['stored', 'generated', 'regenerated']


class AssessmentAgent:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def _get_active_assessment(self, db: Session, *, user_id: int, skill_node_id: int) -> Assessment | None:
        return db.scalar(
            select(Assessment)
            .where(
                Assessment.user_id == user_id,
                Assessment.skill_node_id == skill_node_id,
                Assessment.is_active.is_(True),
            )
            .order_by(Assessment.version.desc(), Assessment.created_at.desc())
        )

    async def generate_quiz(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        user_id: int,
        num_questions: int = 3,
        regenerate: bool = False,
    ) -> tuple[Assessment, QuizSource]:
        existing = self._get_active_assessment(db, user_id=user_id, skill_node_id=skill_node.id)
        if existing and not regenerate:
            logger.info(
                'assessment.loaded_from_store topic_id=%s skill_id=%s assessment_id=%s version=%s',
                topic.id,
                skill_node.id,
                existing.id,
                existing.version,
            )
            return existing, 'stored'

        system_prompt = (
            'You are AssessmentAgent. Generate reliable multiple-choice assessments for a single skill node. '
            'Questions must test understanding, not trivia.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n'
            f'Number of questions: {num_questions}\n'
            'Each question must have exactly 4 choices and exactly one correct answer.'
        )

        quiz_plan = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=QuizPlan,
            temperature=0.3,
            max_tokens=1800,
        )

        questions = [question.model_dump() for question in quiz_plan.questions[:num_questions]]
        if len(questions) < num_questions:
            raise ValueError(f'Quiz generation returned only {len(questions)} questions; expected {num_questions}.')

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
            title=quiz_plan.title,
            questions=questions,
        )
        db.add(assessment)
        db.commit()
        db.refresh(assessment)

        source: QuizSource = 'regenerated' if existing else 'generated'
        logger.info(
            'assessment.generated topic_id=%s skill_id=%s assessment_id=%s version=%s source=%s',
            topic.id,
            skill_node.id,
            assessment.id,
            assessment.version,
            source,
        )
        return assessment, source

    def grade_assessment(
        self,
        db: Session,
        *,
        assessment: Assessment,
        user_id: int,
        answers: list[int],
    ) -> tuple[float, list[dict], AssessmentAttempt]:
        questions = assessment.questions
        if not questions:
            raise ValueError('Assessment has no questions.')

        total = len(questions)
        correct = 0
        feedback: list[dict] = []

        for idx, question in enumerate(questions):
            expected = int(question.get('answer_index', -1))
            user_answer = answers[idx] if idx < len(answers) else -1
            is_correct = user_answer == expected
            if is_correct:
                correct += 1

            feedback.append(
                {
                    'question_id': question.get('id', f'q{idx+1}'),
                    'correct': is_correct,
                    'expected_index': expected,
                    'user_index': user_answer,
                    'explanation': question.get('explanation', ''),
                }
            )

        score = correct / total
        attempt = AssessmentAttempt(
            assessment_id=assessment.id,
            user_id=user_id,
            answers=answers,
            score=score,
            feedback=feedback,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        logger.info(
            'assessment.graded assessment_id=%s user_id=%s score=%.3f total=%s',
            assessment.id,
            user_id,
            score,
            total,
        )
        return score, feedback, attempt

    def get_assessment(self, db: Session, assessment_id: int) -> Assessment | None:
        return db.scalar(select(Assessment).where(Assessment.id == assessment_id))
