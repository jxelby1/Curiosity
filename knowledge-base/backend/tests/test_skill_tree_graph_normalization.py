from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import _build_skill_tree_response
from app.db.models import SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _core_node(topic_id: int, name: str, difficulty: int) -> SkillNode:
    return SkillNode(
        topic_id=topic_id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name=name,
        description=f'{name} description',
        difficulty=difficulty,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
    )


def _optional_node(topic_id: int, name: str, difficulty: int) -> SkillNode:
    return SkillNode(
        topic_id=topic_id,
        node_kind='optional_branch',
        branch_origin='user_created',
        branch_purpose='exploration',
        branch_depth=1,
        branch_parent_skill_id=None,
        name=name,
        description=f'{name} description',
        difficulty=difficulty,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
    )


def test_orphan_core_nodes_are_repaired_into_continuous_chain() -> None:
    db = _session()
    user = User(email='normalize@test.local', hashed_password='x', display_name='Normalize')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Chinese History Chain', description='test', goal='test')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    node_a = _core_node(topic.id, 'Basic Overview of Chinese History', 1)
    node_b = _core_node(topic.id, 'China in the Early 20th Century', 2)
    node_c = _core_node(topic.id, 'Biography of Mao Zedong', 3)
    node_d = _core_node(topic.id, 'The Chinese Communist Revolution', 4)
    db.add_all([node_a, node_b, node_c, node_d])
    db.commit()
    for node in (node_a, node_b, node_c, node_d):
        db.refresh(node)

    # Deliberately incomplete graph to reproduce floating-core risk.
    db.add(SkillEdge(topic_id=topic.id, parent_skill_id=node_a.id, child_skill_id=node_b.id, edge_type='prerequisite'))
    db.commit()

    response = _build_skill_tree_response(db, topic, user.id)
    by_name = {item.name: item for item in response.nodes}

    assert by_name['Basic Overview of Chinese History'].prerequisites == []
    assert by_name['China in the Early 20th Century'].prerequisites == [node_a.id]
    assert by_name['Biography of Mao Zedong'].prerequisites == [node_b.id]
    assert by_name['The Chinese Communist Revolution'].prerequisites == [node_c.id]

    core_nodes = [item for item in response.nodes if item.node_kind == 'core']
    roots = [item for item in core_nodes if len(item.prerequisites) == 0]
    assert len(roots) == 1
    assert roots[0].name == 'Basic Overview of Chinese History'
    assert all(len(item.prerequisites) == 1 for item in core_nodes if item.name != roots[0].name)


def test_branching_core_path_repairs_downstream_orphan_tail() -> None:
    db = _session()
    user = User(email='normalize-branch@test.local', hashed_password='x', display_name='Normalize Branch')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Mao Path', description='test', goal='test')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    root = _core_node(topic.id, 'Chinese Civil War Overview', 1)
    b = _core_node(topic.id, "Founding of the People's Republic", 2)
    c = _core_node(topic.id, 'Early Maoist Policies and Campaigns', 3)
    d = _core_node(topic.id, 'The Great Leap Forward', 4)
    legacy = _core_node(topic.id, "Legacy and Impact of Mao's Dynasty", 5)
    db.add_all([root, b, c, d, legacy])
    db.commit()
    for node in (root, b, c, d, legacy):
        db.refresh(node)

    db.add_all(
        [
            SkillEdge(topic_id=topic.id, parent_skill_id=root.id, child_skill_id=b.id, edge_type='prerequisite'),
            SkillEdge(topic_id=topic.id, parent_skill_id=b.id, child_skill_id=c.id, edge_type='prerequisite'),
            SkillEdge(topic_id=topic.id, parent_skill_id=c.id, child_skill_id=d.id, edge_type='prerequisite'),
            # legacy intentionally orphaned
        ]
    )
    db.commit()

    response = _build_skill_tree_response(db, topic, user.id)
    by_name = {item.name: item for item in response.nodes}
    assert by_name["Legacy and Impact of Mao's Dynasty"].prerequisites == [d.id]
    assert by_name['The Great Leap Forward'].prerequisites == [c.id]


def test_parentless_optional_node_remains_independent_side_node() -> None:
    db = _session()
    user = User(email='normalize-optional@test.local', hashed_password='x', display_name='Normalize Optional')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Optional Node Case', description='test', goal='test')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    root = _core_node(topic.id, 'Root Core', 1)
    optional = _optional_node(topic.id, 'Independent Side Topic', 2)
    db.add_all([root, optional])
    db.commit()
    db.refresh(root)
    db.refresh(optional)

    response = _build_skill_tree_response(db, topic, user.id)
    by_name = {item.name: item for item in response.nodes}
    assert by_name['Independent Side Topic'].node_kind == 'optional_branch'
    assert by_name['Independent Side Topic'].prerequisites == []
