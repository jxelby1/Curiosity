from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.course_preferences import normalize_starting_skill_level, starting_level_mastery_floor
from app.db.models import DocumentChunk, SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState
from app.services.skill_tree_graph import build_normalized_skill_graph


logger = logging.getLogger(__name__)

QUIZ_VERIFY_THRESHOLD = 0.7


class ProfileAgent:
    def _clamp(self, value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

    def ensure_states_for_topic(self, db: Session, user_id: int, topic_id: int) -> None:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic_id)).all()
        topic = db.scalar(select(Topic).where(Topic.id == topic_id))
        starting_level = normalize_starting_skill_level(topic.starting_skill_level if topic else 'beginner')
        created = 0
        for node in nodes:
            existing = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == node.id,
                )
            )
            if existing:
                continue
            baseline_mastery = max(node.mastery_estimate, starting_level_mastery_floor(starting_level, node.difficulty))
            db.add(
                UserSkillState(
                    user_id=user_id,
                    skill_node_id=node.id,
                    mastery=baseline_mastery,
                    confidence=min(1.0, baseline_mastery * 0.8),
                    status=node.status,
                    progress_state='not_started',
                    best_quiz_score=0.0,
                    last_activity_at=datetime.utcnow(),
                )
            )
            created += 1
        db.commit()
        if created:
            logger.info('profile.states_created user_id=%s topic_id=%s count=%s', user_id, topic_id, created)

    def _derive_progress_state(self, state: UserSkillState) -> str:
        if state.best_quiz_score >= QUIZ_VERIFY_THRESHOLD:
            return 'verified'
        if state.lesson_completed_at and state.exercises_completed_at:
            return 'completed'
        if state.lesson_completed_at or state.examples_generated_at or state.exercises_completed_at or state.quiz_taken_at:
            return 'learning'
        return 'not_started'

    def _sync_state_metrics(self, state: UserSkillState) -> None:
        state.progress_state = self._derive_progress_state(state)

        if state.progress_state == 'verified':
            verified_floor = 0.75 + max(0.0, state.best_quiz_score - QUIZ_VERIFY_THRESHOLD) * 0.833
            state.mastery = self._clamp(max(state.mastery, verified_floor))
            state.confidence = self._clamp(max(state.confidence, 0.78))
        elif state.progress_state == 'completed':
            state.mastery = self._clamp(max(state.mastery, 0.62))
            state.confidence = self._clamp(max(state.confidence, 0.58))
        elif state.progress_state == 'learning':
            state.mastery = self._clamp(max(state.mastery, 0.32))
            state.confidence = self._clamp(max(state.confidence, 0.4))
        else:
            state.mastery = self._clamp(max(state.mastery, 0.0))
            state.confidence = self._clamp(max(state.confidence, 0.0))

    def infer_mastery_from_notes(self, db: Session, user_id: int, topic_id: int) -> None:
        self.ensure_states_for_topic(db, user_id, topic_id)
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.topic_id == topic_id)).all()
        if not chunks:
            return

        corpus = ' '.join(chunk.text.lower() for chunk in chunks)
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic_id)).all()

        for node in nodes:
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == node.id,
                )
            )
            if not state:
                continue

            tokens = [token.lower() for token in node.name.split() if len(token) > 3]
            coverage = sum(1 for token in tokens if token in corpus)
            boost = min(0.18, coverage * 0.03)

            state.mastery = self._clamp(max(state.mastery, boost))
            state.confidence = self._clamp(max(state.confidence, boost * 0.8))
            state.last_activity_at = datetime.utcnow()
            self._sync_state_metrics(state)

        db.commit()
        self.recompute_unlocks(db, user_id, topic_id)

        logger.info('profile.notes_inferred user_id=%s topic_id=%s chunks=%s', user_id, topic_id, len(chunks))

    def recompute_unlocks(self, db: Session, user_id: int, topic_id: int) -> None:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic_id)).all()
        edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic_id)).all()
        normalized = build_normalized_skill_graph(
            nodes=nodes,
            edges=edges,
            include_edge_types={'prerequisite'},
            max_non_core_prereqs=2,
        )
        prereq_map = normalized.prereq_map

        state_map: dict[int, UserSkillState] = {}
        for node in nodes:
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == node.id,
                )
            )
            if state:
                self._sync_state_metrics(state)
                state_map[node.id] = state

        for node in nodes:
            state = state_map.get(node.id)
            if not state:
                continue

            prereqs = prereq_map.get(node.id, [])
            prereq_ready = all(
                state_map.get(parent_id) and state_map[parent_id].progress_state == 'verified'
                for parent_id in prereqs
            )
            branch_parent_ready = True
            if node.branch_parent_skill_id is not None:
                branch_parent_state = state_map.get(node.branch_parent_skill_id)
                branch_parent_ready = bool(
                    branch_parent_state and branch_parent_state.status != SkillStatus.locked
                )

            if (prereqs and not prereq_ready) or not branch_parent_ready:
                if state.force_unlocked:
                    if state.progress_state == 'verified':
                        state.status = SkillStatus.mastered
                    elif state.progress_state in ('learning', 'completed'):
                        state.status = SkillStatus.in_progress
                    else:
                        state.status = SkillStatus.available
                else:
                    state.status = SkillStatus.locked
                continue

            if state.progress_state == 'verified':
                state.status = SkillStatus.mastered
            elif state.progress_state in ('learning', 'completed'):
                state.status = SkillStatus.in_progress
            else:
                state.status = SkillStatus.available

        db.commit()

    def record_generated_content(self, db: Session, user_id: int, skill_node: SkillNode, kind: str) -> UserSkillState | None:
        state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        if not state:
            self.ensure_states_for_topic(db, user_id, skill_node.topic_id)
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == skill_node.id,
                )
            )

        changed = False
        now = datetime.utcnow()
        if kind == 'examples' and state.examples_generated_at is None:
            state.examples_generated_at = now
            changed = True

        if changed:
            state.last_activity_at = now
            self._sync_state_metrics(state)
            db.commit()
            db.refresh(state)
            self.recompute_unlocks(db, user_id, skill_node.topic_id)
            db.refresh(state)
            logger.info('profile.generated_content user_id=%s skill_id=%s kind=%s', user_id, skill_node.id, kind)

        return state

    def apply_progress_event(
        self,
        db: Session,
        user_id: int,
        skill_node: SkillNode,
        action: str,
    ) -> UserSkillState:
        state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        if not state:
            self.ensure_states_for_topic(db, user_id, skill_node.topic_id)
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == skill_node.id,
                )
            )

        now = datetime.utcnow()
        changed = False

        if action == 'complete_lesson':
            if state.lesson_completed_at is None:
                state.lesson_completed_at = now
                changed = True
        elif action == 'complete_exercises':
            if state.exercises_completed_at is None:
                state.exercises_completed_at = now
                changed = True
        else:
            raise ValueError(f'Unsupported progression action: {action}')

        if changed:
            state.last_activity_at = now
            self._sync_state_metrics(state)
            db.commit()
            db.refresh(state)
            self.recompute_unlocks(db, user_id, skill_node.topic_id)
            db.refresh(state)

        logger.info(
            'profile.progress_updated user_id=%s skill_id=%s action=%s changed=%s progress_state=%s',
            user_id,
            skill_node.id,
            action,
            changed,
            state.progress_state,
        )
        return state

    def apply_quiz_score(
        self,
        db: Session,
        user_id: int,
        skill_node: SkillNode,
        score: float,
    ) -> UserSkillState:
        score = self._clamp(score)
        mastery_delta = (score - 0.55) * 0.35
        return self.apply_assessment_result(
            db,
            user_id=user_id,
            skill_node=skill_node,
            score=score,
            mastery_delta=mastery_delta,
            confidence_signal=score,
        )

    def apply_dev_complete_node(
        self,
        db: Session,
        *,
        user_id: int,
        skill_node: SkillNode,
    ) -> UserSkillState:
        state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        if not state:
            self.ensure_states_for_topic(db, user_id, skill_node.topic_id)
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == skill_node.id,
                )
            )
        if not state:
            raise RuntimeError('Unable to load user skill state for developer completion.')

        now = datetime.utcnow()
        state.force_unlocked = True
        state.lesson_completed_at = state.lesson_completed_at or now
        state.exercises_completed_at = state.exercises_completed_at or now
        state.last_activity_at = now
        db.commit()
        db.refresh(state)

        target_mastery_floor = 0.92
        mastery_delta = max(0.0, target_mastery_floor - float(state.mastery))
        updated = self.apply_assessment_result(
            db,
            user_id=user_id,
            skill_node=skill_node,
            score=1.0,
            mastery_delta=mastery_delta,
            confidence_signal=1.0,
        )
        logger.info(
            'profile.dev_complete_applied user_id=%s skill_id=%s mastery=%.3f progress_state=%s',
            user_id,
            skill_node.id,
            updated.mastery,
            updated.progress_state,
        )
        return updated

    def apply_assessment_result(
        self,
        db: Session,
        *,
        user_id: int,
        skill_node: SkillNode,
        score: float,
        mastery_delta: float,
        confidence_signal: float | None = None,
    ) -> UserSkillState:
        state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        if not state:
            self.ensure_states_for_topic(db, user_id, skill_node.topic_id)
            state = db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_node_id == skill_node.id,
                )
            )

        now = datetime.utcnow()
        state.best_quiz_score = max(state.best_quiz_score, self._clamp(score))
        state.quiz_taken_at = now
        state.last_activity_at = now
        state.mastery = self._clamp(state.mastery + mastery_delta)
        if confidence_signal is not None:
            state.confidence = self._clamp((state.confidence * 0.7) + (self._clamp(confidence_signal) * 0.3))

        self._sync_state_metrics(state)
        user = db.scalar(select(User).where(User.id == user_id))
        if user:
            xp_gain = 8 + int(round(self._clamp(score) * 20))
            if mastery_delta > 0:
                xp_gain += int(round(mastery_delta * 40))
            user.xp = max(0, (user.xp or 0) + xp_gain)
            user.level = max(1, int(user.xp / 120) + 1)
            user.updated_at = now

        db.commit()
        db.refresh(state)

        self.recompute_unlocks(db, user_id, skill_node.topic_id)
        db.refresh(state)

        logger.info(
            'profile.assessment_applied user_id=%s skill_id=%s score=%.3f best=%.3f mastery_delta=%.3f progress_state=%s',
            user_id,
            skill_node.id,
            score,
            state.best_quiz_score,
            mastery_delta,
            state.progress_state,
        )
        return state

    def get_next_requirement(self, state: UserSkillState | None, status: SkillStatus) -> str:
        if status == SkillStatus.locked:
            return 'Verify prerequisite nodes first to unlock this node.'
        if not state:
            return 'Start by generating and completing the lesson.'
        if state.progress_state == 'not_started':
            return 'Complete the lesson to begin progression.'
        if state.progress_state == 'learning':
            if not state.exercises_completed_at:
                return 'Complete exercises to move this node to completed.'
            return 'Finish remaining learning steps, then take the quiz.'
        if state.progress_state == 'completed':
            return 'Take the quiz and score at least 70% to verify mastery.'
        return 'Node is verified. Move to dependent skills.'
