from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.assessment_agent import AssessmentAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.resource_agent import ResourceAgent
from app.agents.skill_graph_agent import SkillGraphAgent
from app.core.course_preferences import assessment_question_count_for_depth, normalize_course_depth
from app.db.database import SessionLocal
from app.db.models import (
    Assessment,
    LearningResource,
    ResourceType,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    TopicInitializationJob,
    UserSkillState,
)
from app.services.skill_tree_graph import build_normalized_skill_graph


logger = logging.getLogger(__name__)
REQUIRED_FIRST_NODE_RESOURCE_TYPES = (
    ResourceType.generated_lesson,
    ResourceType.generated_examples,
    ResourceType.generated_exercises,
)


class TopicBootstrapService:
    def __init__(
        self,
        *,
        skill_graph_agent: SkillGraphAgent,
        profile_agent: ProfileAgent,
        resource_agent: ResourceAgent,
        assessment_agent: AssessmentAgent,
    ) -> None:
        self.skill_graph_agent = skill_graph_agent
        self.profile_agent = profile_agent
        self.resource_agent = resource_agent
        self.assessment_agent = assessment_agent
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._unlock_tasks: set[asyncio.Task[None]] = set()

    async def start_initialization(
        self,
        db: Session,
        *,
        topic: Topic,
        user_id: int,
        force: bool = False,
    ) -> TopicInitializationJob:
        job = db.scalar(
            select(TopicInitializationJob).where(
                TopicInitializationJob.topic_id == topic.id,
                TopicInitializationJob.user_id == user_id,
            )
        )

        if job and not force and job.status in ('running', 'preloading'):
            self._launch_task(job.id)
            return job

        now = datetime.utcnow()
        if job is None:
            job = TopicInitializationJob(
                topic_id=topic.id,
                user_id=user_id,
                status='queued',
                current_step='Setting up your topic',
                progress=0.0,
                ready_for_entry=False,
                background_complete=False,
                status_messages=['Setting up your topic'],
                error_text='',
                created_at=now,
                updated_at=now,
            )
            db.add(job)
        else:
            job.status = 'queued'
            job.current_step = 'Setting up your topic'
            job.progress = 0.0
            job.ready_for_entry = False
            job.background_complete = False
            job.first_ready_skill_id = None
            job.status_messages = ['Setting up your topic']
            job.error_text = ''
            job.started_at = None
            job.ready_at = None
            job.completed_at = None
            job.updated_at = now

        db.commit()
        db.refresh(job)
        self._launch_task(job.id)
        return job

    def _launch_task(self, job_id: int) -> None:
        existing = self._tasks.get(job_id)
        if existing and not existing.done():
            return

        task = asyncio.create_task(self._run_job(job_id))
        self._tasks[job_id] = task

        def _cleanup(_: asyncio.Task[None]) -> None:
            self._tasks.pop(job_id, None)

        task.add_done_callback(_cleanup)

    def prepare_unlocked_nodes(
        self,
        *,
        topic_id: int,
        user_id: int,
        node_ids: list[int] | set[int],
    ) -> None:
        node_id_list = sorted({int(node_id) for node_id in node_ids if int(node_id) > 0})
        if not node_id_list:
            return

        async def _runner() -> None:
            await self._run_unlock_preparation(topic_id=topic_id, user_id=user_id, node_ids=node_id_list)

        try:
            task = asyncio.create_task(_runner())
        except RuntimeError:
            # Fallback for contexts without a running event loop.
            asyncio.run(_runner())
            return

        self._unlock_tasks.add(task)

        def _cleanup(completed: asyncio.Task[None]) -> None:
            self._unlock_tasks.discard(completed)

        task.add_done_callback(_cleanup)

    async def _run_job(self, job_id: int) -> None:
        try:
            first_ready_skill_id = await self._run_blocking_stage(job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception('topic_bootstrap.blocking_stage_failed job_id=%s', job_id)
            with SessionLocal() as db:
                job = db.get(TopicInitializationJob, job_id)
                if job:
                    friendly_error = (
                        'We could not finish preparing your topic. '
                        'Please retry setup. If this keeps happening, refresh and try again.'
                    )
                    self._update_job(
                        db,
                        job,
                        status='failed',
                        current_step='Setup failed',
                        progress=job.progress if job.progress > 0 else 0.0,
                        error_text=friendly_error,
                        append_message='Setup failed. Retry to continue.',
                    )
            return

        try:
            await self._run_background_stage(job_id, first_ready_skill_id=first_ready_skill_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception('topic_bootstrap.background_stage_failed job_id=%s', job_id)
            with SessionLocal() as db:
                job = db.get(TopicInitializationJob, job_id)
                if job:
                    self._update_job(
                        db,
                        job,
                        status='ready',
                        current_step='Your topic is ready',
                        ready_for_entry=True,
                        background_complete=False,
                        progress=max(job.progress, 0.8),
                        error_text='Your topic is ready. Some additional materials may take a little longer.',
                        append_message='Finishing additional materials',
                    )

    def _append_message(self, job: TopicInitializationJob, message: str) -> None:
        messages = list(job.status_messages or [])
        if not messages or messages[-1] != message:
            messages.append(message)
        job.status_messages = messages[-14:]

    def _update_job(
        self,
        db: Session,
        job: TopicInitializationJob,
        *,
        status: str | None = None,
        current_step: str | None = None,
        progress: float | None = None,
        ready_for_entry: bool | None = None,
        background_complete: bool | None = None,
        first_ready_skill_id: int | None = None,
        error_text: str | None = None,
        append_message: str | None = None,
        mark_started: bool = False,
        mark_ready: bool = False,
        mark_completed: bool = False,
    ) -> None:
        now = datetime.utcnow()
        if status is not None:
            job.status = status
        if current_step is not None:
            job.current_step = current_step
        if progress is not None:
            job.progress = max(0.0, min(1.0, progress))
        if ready_for_entry is not None:
            job.ready_for_entry = ready_for_entry
        if background_complete is not None:
            job.background_complete = background_complete
        if first_ready_skill_id is not None:
            job.first_ready_skill_id = first_ready_skill_id
        if error_text is not None:
            job.error_text = error_text
        if append_message:
            self._append_message(job, append_message)
        if mark_started and job.started_at is None:
            job.started_at = now
        if mark_ready:
            job.ready_at = now
        if mark_completed:
            job.completed_at = now
        job.updated_at = now
        db.commit()
        db.refresh(job)

    async def _prepare_node_starter_content(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        user_id: int,
    ) -> None:
        preferred_question_count = assessment_question_count_for_depth(normalize_course_depth(topic.course_depth))
        await self.resource_agent.generate_material(
            db,
            user_id=user_id,
            topic=topic,
            skill_node=skill_node,
            kind='lesson',
            regenerate=False,
        )
        await self.resource_agent.generate_material(
            db,
            user_id=user_id,
            topic=topic,
            skill_node=skill_node,
            kind='examples',
            regenerate=False,
        )
        await self.resource_agent.generate_material(
            db,
            user_id=user_id,
            topic=topic,
            skill_node=skill_node,
            kind='exercises',
            regenerate=False,
        )
        await self.assessment_agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill_node,
            user_id=user_id,
            question_count=preferred_question_count,
            regenerate=False,
        )

    async def _prepare_first_node_starter_content(
        self,
        db: Session,
        *,
        topic: Topic,
        first_node: SkillNode,
        user_id: int,
    ) -> None:
        await self._prepare_node_starter_content(
            db,
            topic=topic,
            skill_node=first_node,
            user_id=user_id,
        )

    def _is_first_node_ready_for_entry(
        self,
        db: Session,
        *,
        topic_id: int,
        skill_node_id: int,
        user_id: int,
    ) -> bool:
        for resource_type in REQUIRED_FIRST_NODE_RESOURCE_TYPES:
            resource = db.scalar(
                select(LearningResource).where(
                    LearningResource.topic_id == topic_id,
                    LearningResource.skill_node_id == skill_node_id,
                    LearningResource.resource_type == resource_type,
                    LearningResource.is_active.is_(True),
                    LearningResource.user_id == user_id,
                )
            )
            if resource is None:
                return False

        assessment = db.scalar(
            select(Assessment).where(
                Assessment.topic_id == topic_id,
                Assessment.skill_node_id == skill_node_id,
                Assessment.user_id == user_id,
                Assessment.is_active.is_(True),
            )
        )
        return assessment is not None

    def _pick_first_unlocked_node(self, db: Session, *, topic_id: int, user_id: int) -> SkillNode | None:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic_id)).all()
        states = {
            state.skill_node_id: state
            for state in db.scalars(
                select(UserSkillState)
                .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
                .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic_id)
            ).all()
        }
        unlocked = [
            node
            for node in nodes
            if states.get(node.id) and states[node.id].status != SkillStatus.locked
        ]
        unlocked.sort(key=lambda node: (0 if node.node_kind == 'core' else 1, node.difficulty, node.id))
        return unlocked[0] if unlocked else None

    async def _run_blocking_stage(self, job_id: int) -> int:
        with SessionLocal() as db:
            job = db.get(TopicInitializationJob, job_id)
            if not job:
                raise ValueError('Initialization job no longer exists.')

            topic = db.scalar(
                select(Topic).where(
                    Topic.id == job.topic_id,
                    Topic.user_id == job.user_id,
                )
            )
            if not topic:
                raise ValueError('Topic not found for initialization job.')

            self._update_job(
                db,
                job,
                status='running',
                current_step='Creating your learning path',
                progress=0.08,
                append_message='Creating your learning path',
                mark_started=True,
            )

            existing_nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
            if not existing_nodes:
                await self.skill_graph_agent.create_skill_tree(db, topic)
            else:
                logger.info('topic_bootstrap.reused_skill_tree topic_id=%s node_count=%s', topic.id, len(existing_nodes))

            self._update_job(
                db,
                job,
                status='running',
                current_step='Setting up your starting path',
                progress=0.2,
                append_message='Setting up your starting path',
            )
            self.profile_agent.ensure_states_for_topic(db, job.user_id, topic.id)
            self.profile_agent.recompute_unlocks(db, job.user_id, topic.id)

            first_node = self._pick_first_unlocked_node(db, topic_id=topic.id, user_id=job.user_id)
            if first_node is None:
                raise ValueError('No unlocked node could be prepared for this topic.')

            self._update_job(
                db,
                job,
                status='running',
                current_step='Preparing your first lesson',
                progress=0.32,
                append_message='Preparing your first lesson',
            )

            self._update_job(
                db,
                job,
                status='running',
                current_step='Getting examples ready',
                progress=0.46,
                append_message='Getting examples ready',
            )

            self._update_job(
                db,
                job,
                status='running',
                current_step='Preparing your first activities',
                progress=0.58,
                append_message='Preparing your first activities',
            )

            await self._prepare_first_node_starter_content(
                db,
                topic=topic,
                first_node=first_node,
                user_id=job.user_id,
            )

            if not self._is_first_node_ready_for_entry(
                db,
                topic_id=topic.id,
                skill_node_id=first_node.id,
                user_id=job.user_id,
            ):
                raise ValueError('First node starter content is incomplete.')

            self._update_job(
                db,
                job,
                status='ready',
                current_step='Ready to start learning',
                progress=0.8,
                ready_for_entry=True,
                background_complete=False,
                first_ready_skill_id=first_node.id,
                error_text='',
                append_message='First module is ready',
                mark_ready=True,
            )

            logger.info(
                'topic_bootstrap.blocking_stage_complete job_id=%s topic_id=%s first_skill_id=%s',
                job.id,
                topic.id,
                first_node.id,
            )
            return first_node.id

    def _preload_priority_nodes(
        self,
        db: Session,
        *,
        topic_id: int,
        user_id: int,
        first_ready_skill_id: int,
        limit: int = 6,
        adjacent_to_node_ids: set[int] | None = None,
    ) -> list[SkillNode]:
        nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic_id)).all()
        node_map = {node.id: node for node in nodes}
        states = {
            state.skill_node_id: state
            for state in db.scalars(
                select(UserSkillState)
                .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
                .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic_id)
            ).all()
        }

        prereq_edges = db.scalars(
            select(SkillEdge).where(
                SkillEdge.topic_id == topic_id,
                SkillEdge.edge_type == 'prerequisite',
            )
        ).all()
        prereq_map = build_normalized_skill_graph(
            nodes=nodes,
            edges=prereq_edges,
            include_edge_types={'prerequisite'},
            max_non_core_prereqs=2,
        ).prereq_map
        unlocked_ids = {
            state.skill_node_id
            for state in states.values()
            if state.status != SkillStatus.locked
        }
        anchor_ids = (
            unlocked_ids.intersection(adjacent_to_node_ids)
            if adjacent_to_node_ids
            else unlocked_ids
        )

        adjacent_locked_ids: set[int] = set()
        for child_id, parent_ids in prereq_map.items():
            if child_id == first_ready_skill_id:
                continue
            child_state = states.get(child_id)
            if not child_state or child_state.status != SkillStatus.locked:
                continue
            if any(parent_id in anchor_ids for parent_id in parent_ids):
                adjacent_locked_ids.add(child_id)

        for node in nodes:
            if node.id == first_ready_skill_id:
                continue
            state = states.get(node.id)
            if not state or state.status != SkillStatus.locked:
                continue
            if node.branch_parent_skill_id and node.branch_parent_skill_id in anchor_ids:
                adjacent_locked_ids.add(node.id)

        ordered = [
            node_map[node_id]
            for node_id in adjacent_locked_ids
            if node_id in node_map
        ]
        ordered.sort(key=lambda node: (0 if node.node_kind == 'core' else 1, node.difficulty, node.id))
        return ordered[:limit]

    async def _run_background_stage(self, job_id: int, *, first_ready_skill_id: int) -> None:
        with SessionLocal() as db:
            job = db.get(TopicInitializationJob, job_id)
            if not job:
                return

            topic = db.scalar(
                select(Topic).where(
                    Topic.id == job.topic_id,
                    Topic.user_id == job.user_id,
                )
            )
            if not topic:
                return

            self._update_job(
                db,
                job,
                status='preloading',
                current_step='Preparing more lessons for you',
                progress=max(job.progress, 0.78),
                ready_for_entry=True,
                background_complete=False,
                append_message='Preparing more lessons for you',
            )

            priority_nodes = self._preload_priority_nodes(
                db,
                topic_id=topic.id,
                user_id=job.user_id,
                first_ready_skill_id=first_ready_skill_id,
                limit=6,
            )

            for index, node in enumerate(priority_nodes):
                progress = 0.8 + ((index + 1) / max(1, len(priority_nodes))) * 0.16
                self._update_job(
                    db,
                    job,
                    status='preloading',
                    current_step=f'Preparing {node.name}',
                    progress=progress,
                    ready_for_entry=True,
                    append_message=f'Preparing {node.name}',
                )

                try:
                    await self._prepare_node_starter_content(
                        db,
                        topic=topic,
                        skill_node=node,
                        user_id=job.user_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        'topic_bootstrap.preload_node_failed topic_id=%s node_id=%s error=%s',
                        topic.id,
                        node.id,
                        exc,
                    )

            self._update_job(
                db,
                job,
                status='completed',
                current_step='Topic ready',
                progress=1.0,
                ready_for_entry=True,
                background_complete=True,
                append_message='Topic fully prepared',
                mark_completed=True,
            )

            logger.info(
                'topic_bootstrap.background_stage_complete job_id=%s topic_id=%s preloaded=%s',
                job.id,
                topic.id,
                len(priority_nodes),
            )

    def _is_unlocked(self, db: Session, *, user_id: int, skill_node_id: int) -> bool:
        state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node_id,
            )
        )
        return bool(state and state.status != SkillStatus.locked)

    async def _run_unlock_preparation(
        self,
        *,
        topic_id: int,
        user_id: int,
        node_ids: list[int],
    ) -> None:
        with SessionLocal() as db:
            topic = db.scalar(
                select(Topic).where(
                    Topic.id == topic_id,
                    Topic.user_id == user_id,
                )
            )
            if not topic:
                return

            for node_id in node_ids:
                node = db.scalar(
                    select(SkillNode).where(
                        SkillNode.id == node_id,
                        SkillNode.topic_id == topic_id,
                    )
                )
                if not node:
                    continue
                if not self._is_unlocked(db, user_id=user_id, skill_node_id=node_id):
                    continue

                try:
                    await self._prepare_first_node_starter_content(
                        db,
                        topic=topic,
                        first_node=node,
                        user_id=user_id,
                    )
                    logger.info(
                        'topic_bootstrap.unlock_prepared topic_id=%s skill_id=%s user_id=%s',
                        topic_id,
                        node_id,
                        user_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        'topic_bootstrap.unlock_prepare_failed topic_id=%s skill_id=%s user_id=%s error=%s',
                        topic_id,
                        node_id,
                        user_id,
                        exc,
                    )

            adjacent_locked_nodes = self._preload_priority_nodes(
                db,
                topic_id=topic_id,
                user_id=user_id,
                first_ready_skill_id=0,
                limit=max(4, len(node_ids) * 3),
                adjacent_to_node_ids=set(node_ids),
            )
            for node in adjacent_locked_nodes:
                if self._is_unlocked(db, user_id=user_id, skill_node_id=node.id):
                    continue
                try:
                    await self._prepare_node_starter_content(
                        db,
                        topic=topic,
                        skill_node=node,
                        user_id=user_id,
                    )
                    logger.info(
                        'topic_bootstrap.adjacent_locked_prepared topic_id=%s skill_id=%s user_id=%s',
                        topic_id,
                        node.id,
                        user_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        'topic_bootstrap.adjacent_locked_prepare_failed topic_id=%s skill_id=%s user_id=%s error=%s',
                        topic_id,
                        node.id,
                        user_id,
                        exc,
                    )
