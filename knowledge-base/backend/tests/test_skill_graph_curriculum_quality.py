from __future__ import annotations

from app.agents.skill_graph_agent import SkillGraphAgent
from app.schemas.llm import SkillPlanNode


def _node(*, key: str, name: str, description: str, role: str) -> SkillPlanNode:
    return SkillPlanNode.model_validate(
        {
            'key': key,
            'name': name,
            'description': description,
            'instructional_role': role,
            'difficulty': 2,
            'prerequisites': [],
        }
    )


def test_core_redundancy_filters_same_role_near_duplicates() -> None:
    agent = SkillGraphAgent(llm_service=object())  # type: ignore[arg-type]
    accepted = [
        _node(
            key='a',
            name='Reading the geography of Chalk Farm',
            description='Interpret area maps and neighborhood boundaries.',
            role='foundational_concept',
        )
    ]
    candidate = _node(
        key='b',
        name='Understanding Chalk Farm geography',
        description='Read maps and boundaries for Chalk Farm.',
        role='foundational_concept',
    )

    assert (
        agent._is_core_node_redundant(  # type: ignore[attr-defined]
            node=candidate,
            accepted_nodes=accepted,
            future_lines=[],
        )
        is True
    )


def test_core_redundancy_allows_distinct_role_progression() -> None:
    agent = SkillGraphAgent(llm_service=object())  # type: ignore[arg-type]
    accepted = [
        _node(
            key='a',
            name='Character of Chalk Farm',
            description='Build a foundational view of neighborhood identity and layout.',
            role='foundational_concept',
        )
    ]
    candidate = _node(
        key='b',
        name='Planning a local-first exploration route',
        description='Apply the neighborhood model to design a practical walking sequence.',
        role='practical_application',
    )

    assert (
        agent._is_core_node_redundant(  # type: ignore[attr-defined]
            node=candidate,
            accepted_nodes=accepted,
            future_lines=[],
        )
        is False
    )
