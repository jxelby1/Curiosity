from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    MilestoneEvent,
    Recommendation,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    UserReminder,
    UserSkillState,
)


INACTIVITY_THRESHOLD_HOURS = 48
VERIFY_THRESHOLD = 0.7
IMPORTANT_PASS_THRESHOLD = 0.8


@dataclass
class ActionSuggestion:
    skill_node_id: int | None
    skill_name: str
    action_type: str
    title: str
    description: str
    tab: str
    priority: float


@dataclass
class UnlockAnticipation:
    skill_node_id: int
    skill_name: str
    status_label: str
    why_locked: str
    steps: list[str]
    next_step_skill_node_id: int | None
    next_step_tab: str


class RetentionService:
    def _node_status(self, node: SkillNode, state: UserSkillState | None) -> SkillStatus:
        if state is None:
            return node.status
        return state.status

    def _progress_state(self, state: UserSkillState | None) -> str:
        if state is None:
            return 'not_started'
        return state.progress_state

    def _examples_ready(self, state: UserSkillState | None) -> bool:
        return bool(state and state.examples_generated_at)

    def _lesson_done(self, state: UserSkillState | None) -> bool:
        return bool(state and state.lesson_completed_at)

    def _exercises_done(self, state: UserSkillState | None) -> bool:
        return bool(state and state.exercises_completed_at)

    def _quiz_taken(self, state: UserSkillState | None) -> bool:
        return bool(state and state.quiz_taken_at)

    def _best_quiz_score(self, state: UserSkillState | None) -> float:
        return float(state.best_quiz_score if state else 0.0)

    def _recent_activity_snapshot(self, states: list[UserSkillState]) -> tuple[datetime | None, int, int]:
        timestamps = [item.last_activity_at for item in states if item.last_activity_at]
        if not timestamps:
            return None, 0, 0

        latest = max(timestamps)
        today = datetime.utcnow().date()
        unique_days = sorted({item.date() for item in timestamps}, reverse=True)

        streak_days = 0
        expected = today
        for day in unique_days:
            if day == expected:
                streak_days += 1
                expected = expected - timedelta(days=1)
                continue
            if day > expected:
                continue
            break

        cutoff = today - timedelta(days=13)
        activity_days_last_14 = sum(1 for day in unique_days if day >= cutoff)
        return latest, streak_days, activity_days_last_14

    def _recommendation_rank(self, db: Session, *, topic_id: int, user_id: int) -> dict[int, int]:
        rows = db.scalars(
            select(Recommendation)
            .where(Recommendation.topic_id == topic_id, Recommendation.user_id == user_id)
            .order_by(Recommendation.created_at.desc())
        ).all()
        rank: dict[int, int] = {}
        for rec in rows:
            if rec.skill_node_id in rank:
                continue
            rank[rec.skill_node_id] = len(rank)
        return rank

    def _action_candidates(
        self,
        *,
        nodes: list[SkillNode],
        state_map: dict[int, UserSkillState],
        recommendation_rank: dict[int, int],
    ) -> list[ActionSuggestion]:
        candidates: list[ActionSuggestion] = []
        now = datetime.utcnow()

        for node in nodes:
            state = state_map.get(node.id)
            status = self._node_status(node, state)
            progress_state = self._progress_state(state)
            if status == SkillStatus.locked:
                continue

            recommendation_bonus = 0.0
            if node.id in recommendation_rank:
                recommendation_bonus = max(0.0, 18.0 - (recommendation_rank[node.id] * 4.0))

            status_bonus = 24.0 if status == SkillStatus.in_progress else 16.0 if status == SkillStatus.available else 8.0
            base_priority = 40.0 + recommendation_bonus + status_bonus + max(0.0, 8.0 - float(node.difficulty))
            if node.node_kind == 'core':
                base_priority += 5.0

            lesson_done = self._lesson_done(state)
            examples_ready = self._examples_ready(state)
            exercises_done = self._exercises_done(state)
            quiz_taken = self._quiz_taken(state)
            best_quiz = self._best_quiz_score(state)

            if not lesson_done:
                candidates.append(
                    ActionSuggestion(
                        skill_node_id=node.id,
                        skill_name=node.name,
                        action_type='complete_lesson',
                        title=f'Complete the lesson for {node.name}',
                        description='Build a strong baseline before moving into practice tasks.',
                        tab='lesson',
                        priority=base_priority + 30.0,
                    )
                )

            if lesson_done and not examples_ready:
                candidates.append(
                    ActionSuggestion(
                        skill_node_id=node.id,
                        skill_name=node.name,
                        action_type='review_examples',
                        title=f'Review examples for {node.name}',
                        description='Examples help bridge core concepts to practical pattern recognition.',
                        tab='examples',
                        priority=base_priority + 22.0,
                    )
                )

            if lesson_done and not exercises_done:
                candidates.append(
                    ActionSuggestion(
                        skill_node_id=node.id,
                        skill_name=node.name,
                        action_type='complete_exercises',
                        title=f'Finish exercises for {node.name}',
                        description='Completing exercises moves this node toward verified mastery.',
                        tab='exercises',
                        priority=base_priority + 20.0,
                    )
                )

            if lesson_done and (not quiz_taken or best_quiz < VERIFY_THRESHOLD):
                candidates.append(
                    ActionSuggestion(
                        skill_node_id=node.id,
                        skill_name=node.name,
                        action_type='take_assessment',
                        title=f'Take the assessment for {node.name}',
                        description='Verification unlocks downstream skills and improves progression confidence.',
                        tab='quiz',
                        priority=base_priority + 16.0,
                    )
                )

            if quiz_taken and best_quiz < VERIFY_THRESHOLD:
                candidates.append(
                    ActionSuggestion(
                        skill_node_id=node.id,
                        skill_name=node.name,
                        action_type='review_and_retry',
                        title=f'Review and retry {node.name}',
                        description='Your last assessment is below verification threshold; focus weak areas and retry.',
                        tab='lesson',
                        priority=base_priority + 18.0,
                    )
                )

            if progress_state == 'verified' and state and state.last_activity_at <= now - timedelta(days=9):
                candidates.append(
                    ActionSuggestion(
                        skill_node_id=node.id,
                        skill_name=node.name,
                        action_type='refresh_verified',
                        title=f'Quick refresh for {node.name}',
                        description='A short review helps keep verified skills sharp over time.',
                        tab='lesson',
                        priority=base_priority + 6.0,
                    )
                )

        deduped: dict[tuple[int | None, str, str], ActionSuggestion] = {}
        for item in candidates:
            key = (item.skill_node_id, item.tab, item.action_type)
            existing = deduped.get(key)
            if not existing or item.priority > existing.priority:
                deduped[key] = item

        ordered = sorted(deduped.values(), key=lambda item: item.priority, reverse=True)
        return ordered

    def _unlock_anticipation(
        self,
        *,
        nodes: list[SkillNode],
        state_map: dict[int, UserSkillState],
        edge_rows: list[SkillEdge],
        node_by_id: dict[int, SkillNode],
    ) -> UnlockAnticipation | None:
        prereq_map: dict[int, list[int]] = {}
        for edge in edge_rows:
            if edge.edge_type != 'prerequisite':
                continue
            prereq_map.setdefault(edge.child_skill_id, []).append(edge.parent_skill_id)

        candidates: list[tuple[float, SkillNode, list[int], int | None]] = []
        for node in nodes:
            state = state_map.get(node.id)
            status = self._node_status(node, state)
            if status != SkillStatus.locked:
                continue

            prereqs = prereq_map.get(node.id, [])
            missing_prereqs = [
                parent_id
                for parent_id in prereqs
                if not state_map.get(parent_id) or state_map[parent_id].progress_state != 'verified'
            ]
            branch_parent_missing: int | None = None
            if node.branch_parent_skill_id is not None:
                parent_state = state_map.get(node.branch_parent_skill_id)
                if not parent_state or parent_state.status == SkillStatus.locked:
                    branch_parent_missing = node.branch_parent_skill_id

            if not missing_prereqs and branch_parent_missing is None:
                continue

            step_count = len(missing_prereqs) + (1 if branch_parent_missing is not None else 0)
            score = (step_count * 10.0) + float(node.difficulty) + (2.5 if node.node_kind == 'optional_branch' else 0.0)
            candidates.append((score, node, missing_prereqs, branch_parent_missing))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        _, target, missing_prereqs, branch_parent_missing = candidates[0]
        step_count = len(missing_prereqs) + (1 if branch_parent_missing is not None else 0)

        steps: list[str] = []
        next_step_skill_node_id: int | None = None
        next_step_tab = 'overview'

        for parent_id in missing_prereqs[:3]:
            parent = node_by_id.get(parent_id)
            parent_state = state_map.get(parent_id)
            if not parent:
                continue
            if next_step_skill_node_id is None:
                next_step_skill_node_id = parent_id
                if parent_state and parent_state.progress_state == 'completed':
                    next_step_tab = 'quiz'
                elif parent_state and parent_state.progress_state == 'learning':
                    next_step_tab = 'exercises'
                else:
                    next_step_tab = 'lesson'

            if parent_state and parent_state.progress_state == 'completed':
                steps.append(f'Take and pass the assessment for {parent.name}.')
            elif parent_state and parent_state.progress_state == 'learning':
                steps.append(f'Finish exercises and verify {parent.name}.')
            else:
                steps.append(f'Progress {parent.name} to verified status.')

        if branch_parent_missing is not None and branch_parent_missing in node_by_id:
            branch_parent_name = node_by_id[branch_parent_missing].name
            if next_step_skill_node_id is None:
                next_step_skill_node_id = branch_parent_missing
                next_step_tab = 'lesson'
            steps.append(f'Unlock parent node {branch_parent_name} to open this branch.')

        if not steps:
            steps = ['Verify prerequisite nodes to unlock this skill.']

        status_label = '1 step away' if step_count == 1 else f'{step_count} steps away'
        why_locked = (
            f'{target.name} is locked until prerequisite skills are verified.'
            if missing_prereqs
            else f'{target.name} is locked until the parent branch is unlocked.'
        )

        return UnlockAnticipation(
            skill_node_id=target.id,
            skill_name=target.name,
            status_label=status_label,
            why_locked=why_locked,
            steps=steps,
            next_step_skill_node_id=next_step_skill_node_id,
            next_step_tab=next_step_tab,
        )

    def _ensure_inactivity_reminder(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        last_activity_at: datetime | None,
        next_actions: list[ActionSuggestion],
        unlock_anticipation: UnlockAnticipation | None,
    ) -> UserReminder | None:
        if not last_activity_at:
            return None

        now = datetime.utcnow()
        threshold = timedelta(hours=INACTIVITY_THRESHOLD_HOURS)
        if now - last_activity_at < threshold:
            return None

        key = f'inactivity:{topic.id}:{int(last_activity_at.timestamp())}'
        reminder = db.scalar(
            select(UserReminder).where(
                UserReminder.user_id == user_id,
                UserReminder.topic_id == topic.id,
                UserReminder.reminder_key == key,
            )
        )

        lead_action = next_actions[0] if next_actions else None
        action_skill_id = lead_action.skill_node_id if lead_action else unlock_anticipation.next_step_skill_node_id if unlock_anticipation else None
        action_tab = lead_action.tab if lead_action else unlock_anticipation.next_step_tab if unlock_anticipation else 'overview'

        if reminder is None:
            title = f'Pick up where you left off in {topic.name}'
            message_parts = []
            if lead_action:
                message_parts.append(lead_action.title)
            if unlock_anticipation:
                message_parts.append(f'You are {unlock_anticipation.status_label} from unlocking {unlock_anticipation.skill_name}.')
            if not message_parts:
                message_parts.append('A short focused session will help you regain momentum.')
            reminder = UserReminder(
                user_id=user_id,
                topic_id=topic.id,
                reminder_key=key,
                reminder_type='inactivity',
                title=title,
                message=' '.join(message_parts),
                action_skill_node_id=action_skill_id,
                action_tab=action_tab,
                payload={
                    'hours_inactive': int((now - last_activity_at).total_seconds() / 3600),
                    'next_action': lead_action.title if lead_action else '',
                    'unlock_target': unlock_anticipation.skill_name if unlock_anticipation else '',
                },
                last_activity_snapshot_at=last_activity_at,
            )
            db.add(reminder)
            db.commit()
            db.refresh(reminder)

        if reminder.dismissed_at is not None:
            return None
        return reminder

    def _ensure_milestone(
        self,
        db: Session,
        *,
        user_id: int,
        topic_id: int,
        skill_node_id: int | None,
        key: str,
        milestone_type: str,
        title: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        existing = db.scalar(
            select(MilestoneEvent.id).where(
                MilestoneEvent.user_id == user_id,
                MilestoneEvent.topic_id == topic_id,
                MilestoneEvent.milestone_key == key,
            )
        )
        if existing:
            return
        db.add(
            MilestoneEvent(
                user_id=user_id,
                topic_id=topic_id,
                skill_node_id=skill_node_id,
                milestone_key=key,
                milestone_type=milestone_type,
                title=title,
                message=message,
                payload=payload or {},
            )
        )

    def ensure_topic_milestones(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        nodes: list[SkillNode],
        state_map: dict[int, UserSkillState],
        tree_stage: int,
    ) -> list[MilestoneEvent]:
        child_count: dict[int, int] = {}
        for edge in db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all():
            if edge.edge_type == 'prerequisite':
                child_count[edge.parent_skill_id] = child_count.get(edge.parent_skill_id, 0) + 1

        verified = [
            node for node in nodes if state_map.get(node.id) and state_map[node.id].progress_state == 'verified'
        ]
        optional_unlocked = [
            node
            for node in nodes
            if node.node_kind == 'optional_branch'
            and state_map.get(node.id)
            and state_map[node.id].status != SkillStatus.locked
        ]

        if verified:
            self._ensure_milestone(
                db,
                user_id=user_id,
                topic_id=topic.id,
                skill_node_id=verified[0].id,
                key=f'topic:{topic.id}:first-verified',
                milestone_type='first_verified_skill',
                title='First skill verified',
                message=f'You verified your first skill in {topic.name}. Keep the momentum going.',
            )

        if optional_unlocked:
            self._ensure_milestone(
                db,
                user_id=user_id,
                topic_id=topic.id,
                skill_node_id=optional_unlocked[0].id,
                key=f'topic:{topic.id}:first-optional-branch',
                milestone_type='first_branch_unlocked',
                title='New branch unlocked',
                message='You unlocked your first optional branch. Explore deeper when you are ready.',
            )

        for threshold in (3, 5, 6):
            if tree_stage >= threshold:
                self._ensure_milestone(
                    db,
                    user_id=user_id,
                    topic_id=topic.id,
                    skill_node_id=None,
                    key=f'topic:{topic.id}:stage-{threshold}',
                    milestone_type='topic_growth_stage',
                    title=f'Topic growth milestone reached (Stage {threshold})',
                    message=f'Your learning tree in {topic.name} has advanced to a new growth stage.',
                    payload={'stage': threshold},
                )

        important_candidates = [
            node
            for node in nodes
            if (
                state_map.get(node.id)
                and state_map[node.id].best_quiz_score >= IMPORTANT_PASS_THRESHOLD
                and (child_count.get(node.id, 0) > 0 or node.difficulty >= 3)
            )
        ]
        if important_candidates:
            important_candidates.sort(key=lambda item: state_map[item.id].best_quiz_score, reverse=True)
            best = important_candidates[0]
            self._ensure_milestone(
                db,
                user_id=user_id,
                topic_id=topic.id,
                skill_node_id=best.id,
                key=f'topic:{topic.id}:assessment-pass:{best.id}',
                milestone_type='assessment_pass',
                title='Strong assessment performance',
                message=f'You passed an important assessment in {best.name}.',
                payload={'best_quiz_score': state_map[best.id].best_quiz_score},
            )

        if nodes and len(verified) == len(nodes):
            self._ensure_milestone(
                db,
                user_id=user_id,
                topic_id=topic.id,
                skill_node_id=None,
                key=f'topic:{topic.id}:completed',
                milestone_type='topic_completed',
                title='Topic completed',
                message=f'You verified all skills in {topic.name}. Excellent work.',
            )

        db.commit()
        return db.scalars(
            select(MilestoneEvent)
            .where(
                MilestoneEvent.user_id == user_id,
                MilestoneEvent.topic_id == topic.id,
                MilestoneEvent.seen_at.is_(None),
            )
            .order_by(MilestoneEvent.created_at.desc())
            .limit(4)
        ).all()

    def mark_milestone_seen(self, db: Session, *, milestone_id: int, topic_id: int, user_id: int) -> MilestoneEvent | None:
        event = db.scalar(
            select(MilestoneEvent).where(
                MilestoneEvent.id == milestone_id,
                MilestoneEvent.topic_id == topic_id,
                MilestoneEvent.user_id == user_id,
            )
        )
        if not event:
            return None
        if event.seen_at is None:
            event.seen_at = datetime.utcnow()
            db.commit()
            db.refresh(event)
        return event

    def dismiss_reminder(self, db: Session, *, reminder_id: int, topic_id: int, user_id: int) -> UserReminder | None:
        reminder = db.scalar(
            select(UserReminder).where(
                UserReminder.id == reminder_id,
                UserReminder.topic_id == topic_id,
                UserReminder.user_id == user_id,
            )
        )
        if not reminder:
            return None
        if reminder.dismissed_at is None:
            reminder.dismissed_at = datetime.utcnow()
            db.commit()
            db.refresh(reminder)
        return reminder

    def build_topic_loop(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        tree_stage: int,
    ) -> dict:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
        edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all()
        states = db.scalars(
            select(UserSkillState)
            .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
            .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic.id)
        ).all()
        state_map = {state.skill_node_id: state for state in states}
        node_by_id = {node.id: node for node in nodes}

        recommendation_rank = self._recommendation_rank(db, topic_id=topic.id, user_id=user_id)
        action_candidates = self._action_candidates(
            nodes=nodes,
            state_map=state_map,
            recommendation_rank=recommendation_rank,
        )
        next_actions = action_candidates[:3]
        unlock_anticipation = self._unlock_anticipation(
            nodes=nodes,
            state_map=state_map,
            edge_rows=edges,
            node_by_id=node_by_id,
        )

        latest_activity_at, streak_days, activity_days_last_14 = self._recent_activity_snapshot(states)
        reminder = self._ensure_inactivity_reminder(
            db,
            topic=topic,
            user_id=user_id,
            last_activity_at=latest_activity_at,
            next_actions=next_actions,
            unlock_anticipation=unlock_anticipation,
        )

        milestones = self.ensure_topic_milestones(
            db,
            topic=topic,
            user_id=user_id,
            nodes=nodes,
            state_map=state_map,
            tree_stage=tree_stage,
        )

        cadence = 'daily'
        if latest_activity_at and datetime.utcnow() - latest_activity_at > timedelta(days=2):
            cadence = 'weekly'
        if latest_activity_at is None:
            cadence = 'weekly'

        plan_items = list(next_actions[:3])
        if unlock_anticipation:
            plan_items.append(
                ActionSuggestion(
                    skill_node_id=unlock_anticipation.next_step_skill_node_id,
                    skill_name=unlock_anticipation.skill_name,
                    action_type='unlock_focus',
                    title=f'Work toward unlocking {unlock_anticipation.skill_name}',
                    description=unlock_anticipation.steps[0],
                    tab=unlock_anticipation.next_step_tab,
                    priority=15.0,
                )
            )
        plan_items = plan_items[:5]

        completed_nodes = sum(1 for state in states if state.progress_state in ('completed', 'verified'))
        lessons_completed = sum(1 for state in states if state.lesson_completed_at is not None)
        assessments_taken = sum(1 for state in states if state.quiz_taken_at is not None)
        verified_nodes = sum(1 for state in states if state.progress_state == 'verified')
        available_nodes = sum(1 for state in states if state.status != SkillStatus.locked)
        mastery_average = round(mean(state.mastery for state in states), 3) if states else 0.0

        return {
            'cadence': cadence,
            'latest_activity_at': latest_activity_at,
            'streak_days': streak_days,
            'activity_days_last_14': activity_days_last_14,
            'next_actions': next_actions,
            'plan_items': plan_items,
            'unlock_anticipation': unlock_anticipation,
            'reminder': reminder,
            'milestones': milestones,
            'completed_nodes': completed_nodes,
            'lessons_completed': lessons_completed,
            'assessments_taken': assessments_taken,
            'verified_nodes': verified_nodes,
            'available_nodes': available_nodes,
            'mastery_average': mastery_average,
        }
