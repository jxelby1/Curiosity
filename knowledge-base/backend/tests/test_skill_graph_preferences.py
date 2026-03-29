from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agents.skill_graph_agent import SkillGraphAgent
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    BranchSuggestion,
    LearningResource,
    SkillEdge,
    SkillNode,
    Topic,
    User,
    UserSkillState,
)


class _SkillGraphLLMStub:
    def __init__(self, node_count: int) -> None:
        self.node_count = node_count
        self.user_prompt = ''

    async def generate_structured(self, *, schema_model, user_prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        self.user_prompt = user_prompt
        nodes = []
        for idx in range(self.node_count):
            key = f'n_{idx + 1}'
            prereqs = [f'n_{idx}'] if idx > 0 else []
            nodes.append(
                {
                    'key': key,
                    'name': f'Node {idx + 1}',
                    'description': f'Description for node {idx + 1}',
                    'difficulty': min(5, 1 + (idx // 3)),
                    'prerequisites': prereqs,
                }
            )
        return schema_model.model_validate({'nodes': nodes})


class _DensePrereqSkillGraphLLMStub:
    async def generate_structured(self, *, schema_model, user_prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        nodes = []
        for idx in range(8):
            key = f'dense_{idx + 1}'
            prereqs = [f'dense_{j + 1}' for j in range(idx)]
            nodes.append(
                {
                    'key': key,
                    'name': f'Dense Node {idx + 1}',
                    'description': f'Dense description for node {idx + 1}',
                    'difficulty': min(5, 1 + (idx // 2)),
                    'prerequisites': prereqs,
                }
            )
        return schema_model.model_validate({'nodes': nodes})


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    LearningResource.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentAttempt.__table__.create(bind=engine)
    BranchSuggestion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_skill_graph_generation_uses_depth_and_starting_level_preferences() -> None:
    db = _session()
    user = User(email='graph@test.local', hashed_password='x', display_name='Graph User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(
        user_id=user.id,
        name='Python debugging',
        description='Debugging workflows',
        goal='Improve reliability',
        course_depth='deep_dive',
        starting_skill_level='advanced',
        technical_depth='masters',
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    stub = _SkillGraphLLMStub(node_count=13)
    agent = SkillGraphAgent(stub)  # type: ignore[arg-type]
    created = asyncio.run(agent.create_skill_tree(db, topic))

    assert 12 <= len(created) <= 16
    assert all(node.instructional_role for node in created)
    assert isinstance(topic.curriculum_blueprint, dict)
    assert isinstance(topic.curriculum_ledger, dict)
    assert len(topic.curriculum_blueprint.get('core_arc', [])) >= 5
    assert 'Course depth preference: deep_dive' in stub.user_prompt
    assert 'Starting skill level preference: advanced' in stub.user_prompt
    assert 'Technical depth preference: masters' in stub.user_prompt
    assert 'Create between 12 and 16 skill nodes.' in stub.user_prompt


def test_skill_graph_generation_light_depth_uses_smaller_target_range() -> None:
    db = _session()
    user = User(email='graph-light@test.local', hashed_password='x', display_name='Graph Light')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(
        user_id=user.id,
        name='Wine tasting',
        description='Foundations',
        goal='Get started',
        course_depth='light',
        starting_skill_level='beginner',
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    stub = _SkillGraphLLMStub(node_count=6)
    agent = SkillGraphAgent(stub)  # type: ignore[arg-type]
    created = asyncio.run(agent.create_skill_tree(db, topic))

    assert len(created) == 6
    assert 'Course depth preference: light' in stub.user_prompt
    assert 'Starting skill level preference: beginner' in stub.user_prompt
    assert 'Create between 6 and 8 skill nodes.' in stub.user_prompt


def test_skill_graph_generation_caps_prerequisites_per_node() -> None:
    db = _session()
    user = User(email='graph-dense@test.local', hashed_password='x', display_name='Graph Dense')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(
        user_id=user.id,
        name='Dense dependency topic',
        description='Stress prerequisite fan-in',
        goal='Keep tree readable',
        course_depth='standard',
        starting_skill_level='intermediate',
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    agent = SkillGraphAgent(_DensePrereqSkillGraphLLMStub())  # type: ignore[arg-type]
    created = asyncio.run(agent.create_skill_tree(db, topic))
    assert len(created) >= 5

    edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all()
    incoming_count: dict[int, int] = {}
    for edge in edges:
        if edge.edge_type != 'prerequisite':
            continue
        incoming_count[edge.child_skill_id] = incoming_count.get(edge.child_skill_id, 0) + 1

    assert incoming_count
    assert max(incoming_count.values()) <= 2
