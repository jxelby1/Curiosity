from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SkillEdge, SkillNode, SkillStatus, Topic, UserSkillState
from app.schemas.llm import DeepDiveBranchPlan, SkillGraphPlan
from app.services.llm import LLMService


logger = logging.getLogger(__name__)


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

    async def create_skill_tree(self, db: Session, topic: Topic) -> list[SkillNode]:
        system_prompt = (
            'You are SkillGraphAgent. Build a practical learning skill graph for a topic. '
            'Prefer atomic skills, clear prerequisite ordering, and realistic progression from fundamentals '
            'to applied practice. Keep graph acyclic and avoid redundant skills.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Description: {topic.description or "No description"}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n\n'
            'Create between 7 and 12 skill nodes. Each node needs key, name, description, difficulty (1-5), '
            'and prerequisites (list of node keys).'
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

        if len(unique_nodes) < 5:
            raise ValueError('Skill graph generation returned too few unique nodes.')

        prereq_map: dict[str, list[str]] = {}
        for node in unique_nodes:
            filtered_prereqs = [key for key in node.prerequisites if key in seen_keys and key != node.key]
            prereq_map[node.key] = list(dict.fromkeys(filtered_prereqs))

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

        prereq_map: dict[str, list[str]] = {}
        for node in unique_nodes:
            filtered: list[str] = []
            for key in node.prerequisites:
                normalized = key.strip().lower()
                if normalized == 'parent' or normalized in seen_keys:
                    filtered.append(normalized)
            prereq_map[node.key] = list(dict.fromkeys(filtered))

        key_to_node: dict[str, SkillNode] = {}
        created_nodes: list[SkillNode] = []

        for node in unique_nodes:
            has_internal_prereq = any(item != 'parent' for item in prereq_map[node.key])
            status = SkillStatus.locked if has_internal_prereq else SkillStatus.available
            record = SkillNode(
                topic_id=topic.id,
                node_kind='optional_branch',
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
            'skill_graph.deep_dive_created topic_id=%s parent_skill_id=%s node_count=%s',
            topic.id,
            parent_node.id,
            len(created_nodes),
        )
        return created_nodes
