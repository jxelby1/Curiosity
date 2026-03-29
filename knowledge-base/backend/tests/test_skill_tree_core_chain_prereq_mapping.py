from __future__ import annotations

from sqlalchemy import create_engine, select
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


def test_core_chain_prerequisites_are_exposed_for_renderer_continuity() -> None:
    db = _session()
    user = User(email='core-chain@test.local', hashed_password='x', display_name='Core Chain')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Modern China', description='History chain', goal='Understand chronology')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    node_a = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='Chinese Civil War Overview',
        description='Civil war context.',
        difficulty=2,
        mastery_estimate=0.0,
        status=SkillStatus.available,
    )
    node_b = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name="Founding of the People's Republic",
        description='Founding transition.',
        difficulty=2,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
    )
    node_c = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='Early Maoist Policies and Campaigns',
        description='Early policy period.',
        difficulty=3,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
    )
    node_d = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='The Great Leap Forward',
        description='Great leap period.',
        difficulty=3,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
    )
    db.add_all([node_a, node_b, node_c, node_d])
    db.commit()
    for node in (node_a, node_b, node_c, node_d):
        db.refresh(node)

    db.add_all(
        [
            SkillEdge(topic_id=topic.id, parent_skill_id=node_a.id, child_skill_id=node_b.id, edge_type='prerequisite'),
            SkillEdge(topic_id=topic.id, parent_skill_id=node_b.id, child_skill_id=node_c.id, edge_type='prerequisite'),
            SkillEdge(topic_id=topic.id, parent_skill_id=node_c.id, child_skill_id=node_d.id, edge_type='prerequisite'),
        ]
    )
    db.commit()

    response = _build_skill_tree_response(db, topic, user.id)
    by_name = {item.name: item for item in response.nodes}

    assert by_name["Founding of the People's Republic"].prerequisites == [node_a.id]
    assert by_name['Early Maoist Policies and Campaigns'].prerequisites == [node_b.id]
    assert by_name['The Great Leap Forward'].prerequisites == [node_c.id]

    edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all()
    assert len(edges) == 3


def test_klimt_core_pair_prerequisite_is_preserved_for_connector_rendering() -> None:
    db = _session()
    user = User(email='klimt-core@test.local', hashed_password='x', display_name='Klimt Core')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name="Klimt's Art", description='Art topic', goal='Understand context')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    basics = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='Basics of Art History',
        description='Foundational art history context.',
        difficulty=1,
        mastery_estimate=0.0,
        status=SkillStatus.available,
    )
    austrian_context = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='Austrian Art and Culture in the Late 19th Century',
        description='Austrian context around Klimt.',
        difficulty=2,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
    )
    db.add_all([basics, austrian_context])
    db.commit()
    db.refresh(basics)
    db.refresh(austrian_context)

    db.add(
        SkillEdge(
            topic_id=topic.id,
            parent_skill_id=basics.id,
            child_skill_id=austrian_context.id,
            edge_type='prerequisite',
        )
    )
    db.commit()

    response = _build_skill_tree_response(db, topic, user.id)
    by_name = {item.name: item for item in response.nodes}

    assert by_name['Basics of Art History'].prerequisites == []
    assert by_name['Austrian Art and Culture in the Late 19th Century'].prerequisites == [basics.id]
