from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import SkillEdge, SkillNode, SkillStatus, Topic
from app.schemas.llm import SkillGraphPlan
from app.services.llm import LLMService


logger = logging.getLogger(__name__)


class SkillGraphAgent:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

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
