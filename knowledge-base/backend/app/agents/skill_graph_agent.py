from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.course_preferences import (
    depth_node_bounds,
    level_prompt_guidance,
    normalize_course_depth,
    normalize_starting_skill_level,
)
from app.db.models import BranchSuggestion, SkillEdge, SkillNode, SkillStatus, Topic, UserSkillState
from app.schemas.llm import (
    BranchSuggestionPlan,
    DeepDiveBranchPlan,
    SkillGraphPlan,
    SkillPlanNode,
)
from app.services.llm import LLMService


logger = logging.getLogger(__name__)
MAX_PREREQUISITES_PER_NODE = 2


class SkillGraphAgent:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def _learner_level(self, state: UserSkillState | None) -> str:
        if not state:
            return 'beginner'
        if state.progress_state == 'verified' or state.mastery >= 0.75:
            return 'advanced'
        if state.progress_state in ('learning', 'completed') or state.mastery >= 0.35:
            return 'intermediate'
        return 'beginner'

    @staticmethod
    def _limit_core_prerequisites(
        current_key: str,
        keys: list[str],
        key_position: dict[str, int],
    ) -> list[str]:
        unique: list[str] = []
        for key in keys:
            normalized = key.strip().lower()
            if (
                not normalized
                or normalized == current_key
                or normalized not in key_position
                or key_position[normalized] >= key_position[current_key]
                or normalized in unique
            ):
                continue
            unique.append(normalized)
        unique.sort(key=lambda item: key_position[item], reverse=True)
        return unique[:MAX_PREREQUISITES_PER_NODE]

    @staticmethod
    def _limit_branch_prerequisites(
        current_key: str,
        keys: list[str],
        key_position: dict[str, int],
    ) -> list[str]:
        wants_parent = any(item.strip().lower() == 'parent' for item in keys)
        siblings: list[str] = []
        for key in keys:
            normalized = key.strip().lower()
            if (
                normalized in ('', 'parent', current_key)
                or normalized not in key_position
                or key_position[normalized] >= key_position[current_key]
                or normalized in siblings
            ):
                continue
            siblings.append(normalized)
        siblings.sort(key=lambda item: key_position[item], reverse=True)

        selected: list[str] = []
        if wants_parent:
            selected.append('parent')
        for sibling in siblings:
            if len(selected) >= MAX_PREREQUISITES_PER_NODE:
                break
            selected.append(sibling)
        return selected[:MAX_PREREQUISITES_PER_NODE]

    async def create_skill_tree(self, db: Session, topic: Topic) -> list[SkillNode]:
        course_depth = normalize_course_depth(topic.course_depth)
        starting_level = normalize_starting_skill_level(topic.starting_skill_level)
        min_nodes, max_nodes = depth_node_bounds(course_depth)
        level_guidance = level_prompt_guidance(starting_level)

        system_prompt = (
            'You are SkillGraphAgent. Build a practical learning skill graph for a topic. '
            'Prefer atomic skills, clear prerequisite ordering, and realistic progression from fundamentals '
            'to applied practice. Keep graph acyclic and avoid redundant skills.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Description: {topic.description or "No description"}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n\n'
            f'Course depth preference: {course_depth}\n'
            f'Starting skill level preference: {starting_level}\n'
            f'Guidance: {level_guidance}\n\n'
            f'Create between {min_nodes} and {max_nodes} skill nodes. '
            'Each node needs key, name, description, difficulty (1-5), '
            'and prerequisites (list of node keys). '
            'Use at most 2 prerequisites per node, and prefer 0-1 unless absolutely needed.'
        )

        graph = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=SkillGraphPlan,
            temperature=0.2,
            max_tokens=2200,
        )

        unique_nodes = []
        seen_keys: set[str] = set()
        for node in graph.nodes:
            if node.key in seen_keys:
                continue
            seen_keys.add(node.key)
            unique_nodes.append(node)

        unique_nodes = unique_nodes[:max_nodes]

        while len(unique_nodes) < min_nodes:
            idx = len(unique_nodes) + 1
            fallback_key = f'auto_skill_{idx}'
            fallback_prereq = [unique_nodes[-1].key] if unique_nodes else []
            unique_nodes.append(
                SkillPlanNode(
                    key=fallback_key,
                    name=f'{topic.name} skill {idx}',
                    description=f'Practical progression step {idx} for {topic.name}.',
                    difficulty=min(5, max(1, 1 + (idx // 3))),
                    prerequisites=fallback_prereq,
                )
            )
            seen_keys.add(fallback_key)

        key_position = {node.key: idx for idx, node in enumerate(unique_nodes)}
        prereq_map: dict[str, list[str]] = {}
        for node in unique_nodes:
            filtered_prereqs = [key for key in node.prerequisites if key in seen_keys and key != node.key]
            prereq_map[node.key] = self._limit_core_prerequisites(
                current_key=node.key,
                keys=filtered_prereqs,
                key_position=key_position,
            )

        has_root = any(len(prereq_map[node.key]) == 0 for node in unique_nodes)
        if not has_root:
            logger.warning('skill_graph.no_root topic_id=%s forcing first node as root', topic.id)
            prereq_map[unique_nodes[0].key] = []

        key_to_node: dict[str, SkillNode] = {}
        created_nodes: list[SkillNode] = []

        for node in unique_nodes:
            status = SkillStatus.available if len(prereq_map[node.key]) == 0 else SkillStatus.locked
            record = SkillNode(
                topic_id=topic.id,
                node_kind='core',
                branch_origin='core',
                branch_purpose='core_curriculum',
                branch_depth=0,
                branch_parent_skill_id=None,
                name=node.name,
                description=node.description,
                difficulty=node.difficulty,
                mastery_estimate=0.0,
                status=status,
                suggested_resources=[],
                generated_lessons=[],
            )
            db.add(record)
            db.flush()

            key_to_node[node.key] = record
            created_nodes.append(record)

        for child_key, parent_keys in prereq_map.items():
            child = key_to_node[child_key]
            for parent_key in parent_keys:
                parent = key_to_node[parent_key]
                db.add(
                    SkillEdge(
                        topic_id=topic.id,
                        parent_skill_id=parent.id,
                        child_skill_id=child.id,
                        edge_type='prerequisite',
                    )
                )

        db.commit()
        for node in created_nodes:
            db.refresh(node)

        logger.info('skill_graph.created topic_id=%s node_count=%s', topic.id, len(created_nodes))
        return created_nodes

    async def create_deep_dive_branch(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
        focus: str | None = None,
        branch_size: int = 3,
        branch_origin: str = 'user_requested',
        branch_purpose: str = 'exploration',
    ) -> list[SkillNode]:
        user_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == parent_node.id,
            )
        )
        learner_level = self._learner_level(user_state)

        existing_branch_nodes = db.scalars(
            select(SkillNode)
            .where(
                SkillNode.topic_id == topic.id,
                SkillNode.branch_parent_skill_id == parent_node.id,
            )
            .order_by(SkillNode.created_at.desc())
            .limit(8)
        ).all()
        existing_branch_names = ', '.join(node.name for node in existing_branch_nodes) or 'None'

        system_prompt = (
            'You are SkillGraphAgent. Create optional deep-dive branch modules for a selected skill. '
            'Keep them narrow, relevant, and progression-friendly. Do not alter the core mandatory path.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Topic goal: {topic.goal or "No explicit goal"}\n'
            f'Parent skill: {parent_node.name}\n'
            f'Parent skill description: {parent_node.description}\n'
            f'Parent difficulty (1-5): {parent_node.difficulty}\n'
            f'Learner level at parent node: {learner_level}\n'
            f'User focus request: {focus or "None"}\n'
            f'Existing optional branch nodes under this parent: {existing_branch_names}\n\n'
            f'Generate {branch_size} optional branch nodes.\n'
            'Requirements:\n'
            '- The branch must be clearly optional.\n'
            '- Keep scope tightly tied to the parent node.\n'
            '- Use key, name, description, difficulty, prerequisites.\n'
            "- In prerequisites, use either sibling node keys or 'parent'.\n"
            '- Use no more than 2 prerequisites per node (including parent).\n'
            '- Keep beginner learners on foundational depth, not advanced capstone tasks.\n'
            '- Avoid duplicate or overlapping node names.'
        )

        plan = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=DeepDiveBranchPlan,
            temperature=0.3,
            max_tokens=1800,
        )

        existing_names_lower = {
            node.name.strip().lower()
            for node in db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
        }
        unique_nodes = []
        seen_keys: set[str] = set()
        for node in plan.nodes:
            normalized_name = node.name.strip().lower()
            if node.key in seen_keys:
                continue
            if normalized_name in existing_names_lower:
                continue
            seen_keys.add(node.key)
            unique_nodes.append(node)
            if len(unique_nodes) >= branch_size:
                break

        if len(unique_nodes) < 2:
            raise ValueError('Deep-dive generation returned too few unique optional nodes.')

        key_position = {node.key: idx for idx, node in enumerate(unique_nodes)}
        prereq_map: dict[str, list[str]] = {}
        for node in unique_nodes:
            prereq_map[node.key] = self._limit_branch_prerequisites(
                current_key=node.key,
                keys=node.prerequisites,
                key_position=key_position,
            )

        key_to_node: dict[str, SkillNode] = {}
        created_nodes: list[SkillNode] = []

        for node in unique_nodes:
            has_internal_prereq = any(item != 'parent' for item in prereq_map[node.key])
            status = SkillStatus.locked if has_internal_prereq else SkillStatus.available
            record = SkillNode(
                topic_id=topic.id,
                node_kind='optional_branch',
                branch_origin=branch_origin,
                branch_purpose=branch_purpose,
                branch_depth=max(1, (parent_node.branch_depth or 0) + 1),
                branch_parent_skill_id=parent_node.id,
                name=node.name,
                description=node.description,
                difficulty=min(5, max(parent_node.difficulty, min(parent_node.difficulty + 1, node.difficulty))),
                mastery_estimate=0.0,
                status=status,
                suggested_resources=[],
                generated_lessons=[],
            )
            db.add(record)
            db.flush()

            key_to_node[node.key] = record
            created_nodes.append(record)

        parent_linked_children: set[int] = set()
        for child_key, parent_keys in prereq_map.items():
            child = key_to_node[child_key]
            for parent_key in parent_keys:
                if parent_key == 'parent':
                    db.add(
                        SkillEdge(
                            topic_id=topic.id,
                            parent_skill_id=parent_node.id,
                            child_skill_id=child.id,
                            edge_type='optional_branch',
                        )
                    )
                    parent_linked_children.add(child.id)
                    continue

                parent = key_to_node.get(parent_key)
                if not parent:
                    continue
                db.add(
                    SkillEdge(
                        topic_id=topic.id,
                        parent_skill_id=parent.id,
                        child_skill_id=child.id,
                        edge_type='prerequisite',
                    )
                )

        root_keys = [node.key for node in unique_nodes if len(prereq_map.get(node.key, [])) == 0]
        for root_key in root_keys:
            root_id = key_to_node[root_key].id
            if root_id in parent_linked_children:
                continue
            db.add(
                SkillEdge(
                    topic_id=topic.id,
                    parent_skill_id=parent_node.id,
                    child_skill_id=root_id,
                    edge_type='optional_branch',
                )
            )
            parent_linked_children.add(root_id)

        if not parent_linked_children:
            db.add(
                SkillEdge(
                    topic_id=topic.id,
                    parent_skill_id=parent_node.id,
                    child_skill_id=created_nodes[0].id,
                    edge_type='optional_branch',
                )
            )

        db.commit()
        for node in created_nodes:
            db.refresh(node)

        logger.info(
            'skill_graph.deep_dive_created topic_id=%s parent_skill_id=%s node_count=%s origin=%s purpose=%s',
            topic.id,
            parent_node.id,
            len(created_nodes),
            branch_origin,
            branch_purpose,
        )
        return created_nodes

    async def suggest_branch_paths(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
        limit: int = 2,
        trigger_event: str = 'manual',
    ) -> list[BranchSuggestion]:
        limit = max(1, min(3, int(limit)))

        pending = db.scalars(
            select(BranchSuggestion).where(
                BranchSuggestion.topic_id == topic.id,
                BranchSuggestion.user_id == user_id,
                BranchSuggestion.parent_skill_id == parent_node.id,
                BranchSuggestion.status == 'pending',
            )
        ).all()
        if len(pending) >= limit:
            return pending[:limit]

        learner_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == parent_node.id,
            )
        )
        learner_level = self._learner_level(learner_state)

        system_prompt = (
            'You are SkillGraphAgent. Suggest optional branch pathways for a selected learning node. '
            'Suggestions must be specific, useful, and clearly optional.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Parent node: {parent_node.name}\n'
            f'Parent description: {parent_node.description}\n'
            f'Learner level: {learner_level}\n'
            f'Trigger event: {trigger_event}\n'
            f'Provide {limit} optional branch suggestions.\n'
            'Each suggestion must include: title, focus, rationale, purpose.\n'
            'purpose must be one of: enrichment, remediation, specialization, exploration, assessment_prep, project.'
        )
        plan = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=BranchSuggestionPlan,
            temperature=0.3,
            max_tokens=1200,
        )

        existing_focuses = {
            row.focus.strip().lower()
            for row in db.scalars(
                select(BranchSuggestion).where(
                    BranchSuggestion.topic_id == topic.id,
                    BranchSuggestion.user_id == user_id,
                    BranchSuggestion.parent_skill_id == parent_node.id,
                )
            ).all()
        }
        created: list[BranchSuggestion] = []
        for item in plan.suggestions:
            focus_key = item.focus.strip().lower()
            if not focus_key or focus_key in existing_focuses:
                continue
            existing_focuses.add(focus_key)
            record = BranchSuggestion(
                topic_id=topic.id,
                user_id=user_id,
                parent_skill_id=parent_node.id,
                title=item.title.strip(),
                focus=item.focus.strip(),
                rationale=item.rationale.strip(),
                purpose=item.purpose,
                origin='system_suggested',
                trigger_event=trigger_event,
                status='pending',
            )
            db.add(record)
            db.flush()
            created.append(record)
            if len(created) >= limit:
                break

        db.commit()
        for row in created:
            db.refresh(row)

        return created

    def create_performance_branch_suggestion(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
        score: float,
    ) -> BranchSuggestion | None:
        purpose = None
        title = ''
        rationale = ''
        focus = ''
        if score <= 0.45:
            purpose = 'remediation'
            title = f'Reinforcement: {parent_node.name} foundations'
            focus = f'Foundational reinforcement for {parent_node.name}'
            rationale = 'Recent assessment signals gaps. A focused reinforcement branch can strengthen prerequisites.'
        elif score >= 0.85:
            purpose = 'enrichment'
            title = f'Advanced extension: {parent_node.name}'
            focus = f'Advanced applications of {parent_node.name}'
            rationale = 'Strong performance detected. An enrichment branch can deepen mastery with advanced application.'

        if not purpose:
            return None

        existing_pending = db.scalar(
            select(BranchSuggestion).where(
                BranchSuggestion.topic_id == topic.id,
                BranchSuggestion.user_id == user_id,
                BranchSuggestion.parent_skill_id == parent_node.id,
                BranchSuggestion.purpose == purpose,
                BranchSuggestion.status == 'pending',
            )
        )
        if existing_pending:
            return existing_pending

        suggestion = BranchSuggestion(
            topic_id=topic.id,
            user_id=user_id,
            parent_skill_id=parent_node.id,
            title=title,
            focus=focus,
            rationale=rationale,
            purpose=purpose,
            origin='system_suggested',
            trigger_event='assessment_performance',
            status='pending',
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)
        return suggestion
