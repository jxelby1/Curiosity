from __future__ import annotations

import json
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Recommendation, SkillEdge, SkillNode, SkillStatus, Topic, UserSkillState
from app.schemas.llm import RecommendationChoice, RecommendationPlan
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService


logger = logging.getLogger(__name__)


class RecommendationAgent:
    def __init__(self, llm_service: LLMService, retrieval_service: RetrievalService) -> None:
        self.llm_service = llm_service
        self.retrieval_service = retrieval_service

    async def generate_recommendations(self, db: Session, topic: Topic, user_id: int, limit: int = 1) -> list[Recommendation]:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
        edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all()

        state_map: dict[int, UserSkillState] = {}
        for state in db.scalars(
            select(UserSkillState)
            .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
            .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic.id)
        ).all():
            state_map[state.skill_node_id] = state

        child_count: dict[int, int] = {}
        prereq_count: dict[int, int] = {}
        for edge in edges:
            child_count[edge.parent_skill_id] = child_count.get(edge.parent_skill_id, 0) + 1
            prereq_count[edge.child_skill_id] = prereq_count.get(edge.child_skill_id, 0) + 1

        candidates: list[dict] = []
        for node in nodes:
            state = state_map.get(node.id)
            node_status = state.status if state else node.status
            mastery = state.mastery if state else node.mastery_estimate

            if node_status == SkillStatus.locked or mastery >= 0.95:
                continue

            bottleneck = child_count.get(node.id, 0)
            optional_penalty = 0.12 if node.node_kind == 'optional_branch' else 0.0
            base_score = (1.0 - mastery) * 0.7 + min(0.3, bottleneck * 0.1) - optional_penalty

            candidates.append(
                {
                    'skill_node_id': node.id,
                    'name': node.name,
                    'node_kind': node.node_kind,
                    'status': node_status.value,
                    'mastery': round(float(mastery), 3),
                    'difficulty': node.difficulty,
                    'prereq_count': prereq_count.get(node.id, 0),
                    'child_count': bottleneck,
                    'base_score': round(base_score, 3),
                }
            )

        candidates.sort(key=lambda item: item['base_score'], reverse=True)
        top_candidates = candidates[: max(limit * 2, 5)]

        if not top_candidates:
            db.execute(delete(Recommendation).where(Recommendation.topic_id == topic.id, Recommendation.user_id == user_id))
            db.commit()
            return []

        for candidate in top_candidates:
            retrieved = await self.retrieval_service.retrieve_chunks(
                db,
                topic_id=topic.id,
                query=candidate['name'],
                top_k=2,
            )
            if not retrieved:
                candidate['note_signal'] = 0.0
            else:
                candidate['note_signal'] = round(
                    sum(item.score for item in retrieved) / len(retrieved),
                    3,
                )

        system_prompt = (
            'You are RecommendationAgent. Rank next best skills to study in a dependency graph. '
            'Consider mastery gaps, bottlenecks, difficulty progression, and explicit user goal. '
            'Prefer core-path nodes by default. Recommend optional branches when clearly valuable.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Candidate skills (JSON):\n{json.dumps(top_candidates, indent=2)}\n\n'
            f'Select up to {limit} recommendations. '
            'Use action_type as one of: study_generated, study_external, practice_quiz.'
        )

        plan = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=RecommendationPlan,
            temperature=0.25,
            max_tokens=1200,
        )

        candidate_ids = {item['skill_node_id'] for item in top_candidates}
        filtered: list[RecommendationChoice] = []
        seen_ids: set[int] = set()
        for rec in plan.recommendations:
            if rec.skill_node_id not in candidate_ids:
                continue
            if rec.skill_node_id in seen_ids:
                continue
            seen_ids.add(rec.skill_node_id)
            filtered.append(rec)
            if len(filtered) >= limit:
                break

        if not filtered:
            for item in top_candidates[:limit]:
                filtered.append(
                    RecommendationChoice(
                        skill_node_id=item['skill_node_id'],
                        action_type='study_generated',
                        rationale=(
                            f"{item['name']} is unlocked with {item['mastery']:.0%} mastery and has "
                            f"{item['child_count']} dependent node(s)."
                        ),
                        confidence=min(0.95, 0.45 + item['base_score'] * 0.4),
                    )
                )

        db.execute(delete(Recommendation).where(Recommendation.topic_id == topic.id, Recommendation.user_id == user_id))

        records: list[Recommendation] = []
        for rec in filtered:
            record = Recommendation(
                topic_id=topic.id,
                user_id=user_id,
                skill_node_id=rec.skill_node_id,
                rationale=rec.rationale,
                action_type=rec.action_type,
                confidence=rec.confidence,
            )
            db.add(record)
            records.append(record)

        db.commit()
        for record in records:
            db.refresh(record)

        logger.info('recommendation.complete topic_id=%s user_id=%s count=%s', topic.id, user_id, len(records))
        return records
