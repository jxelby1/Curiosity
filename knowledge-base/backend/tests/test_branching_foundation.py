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
    ResourceType,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    User,
    UserSkillState,
)


class _BranchLLMStub:
    async def generate_structured(self, *, schema_model, **kwargs):  # type: ignore[no-untyped-def]
        if schema_model.__name__ == 'DeepDiveBranchPlan':
            return schema_model.model_validate(
                {
                    'branch_title': 'Timing extension branch',
                    'rationale': 'A focused optional path that deepens timing skills beyond the core path.',
                    'nodes': [
                        {
                            'key': 'branch_a',
                            'name': 'Timing drills',
                            'description': 'Practice precision timing.',
                            'difficulty': 2,
                            'prerequisites': ['parent'],
                        },
                        {
                            'key': 'branch_b',
                            'name': 'Sync confidence',
                            'description': 'Strengthen confidence under pressure.',
                            'difficulty': 2,
                            'prerequisites': ['branch_a'],
                        },
                        {
                            'key': 'branch_c',
                            'name': 'Micro transitions',
                            'description': 'Refine short transitions.',
                            'difficulty': 3,
                            'prerequisites': ['branch_b'],
                        },
                    ]
                }
            )
        if schema_model.__name__ == 'BranchSuggestionPlan':
            return schema_model.model_validate(
                {
                    'suggestions': [
                        {
                            'title': 'Remediate foundations',
                            'focus': 'Foundational reinforcement drills',
                            'rationale': 'Focus practice where performance dropped.',
                            'purpose': 'remediation',
                        },
                    ]
                }
            )
        raise AssertionError(f'Unexpected schema model: {schema_model}')


class _DenseBranchLLMStub:
    async def generate_structured(self, *, schema_model, **kwargs):  # type: ignore[no-untyped-def]
        if schema_model.__name__ == 'DeepDiveBranchPlan':
            return schema_model.model_validate(
                {
                    'branch_title': 'Dense branch',
                    'rationale': 'Stress test branch prerequisites.',
                    'nodes': [
                        {
                            'key': 'dense_a',
                            'name': 'Dense A',
                            'description': 'Start dense branch.',
                            'difficulty': 2,
                            'prerequisites': ['parent'],
                        },
                        {
                            'key': 'dense_b',
                            'name': 'Dense B',
                            'description': 'Continue dense branch.',
                            'difficulty': 3,
                            'prerequisites': ['parent', 'dense_a'],
                        },
                        {
                            'key': 'dense_c',
                            'name': 'Dense C',
                            'description': 'Final dense branch node.',
                            'difficulty': 3,
                            'prerequisites': ['parent', 'dense_a', 'dense_b'],
                        },
                    ],
                }
            )
        if schema_model.__name__ == 'BranchSuggestionPlan':
            return schema_model.model_validate({'suggestions': []})
        raise AssertionError(f'Unexpected schema model: {schema_model}')


class _OverlapBranchLLMStub:
    async def generate_structured(self, *, schema_model, **kwargs):  # type: ignore[no-untyped-def]
        if schema_model.__name__ == 'DeepDiveBranchPlan':
            return schema_model.model_validate(
                {
                    'branch_title': 'Overlapping branch',
                    'rationale': 'Intentionally overlaps to test filtering.',
                    'nodes': [
                        {
                            'key': 'overlap_a',
                            'name': 'Future Core Topic',
                            'description': 'This duplicates a future core node and should be rejected.',
                            'difficulty': 2,
                            'prerequisites': ['parent'],
                        },
                    ],
                }
            )
        if schema_model.__name__ == 'BranchSuggestionPlan':
            return schema_model.model_validate(
                {
                    'suggestions': [
                        {
                            'title': 'Future Core Topic',
                            'focus': 'Future Core Topic',
                            'rationale': 'This should be filtered because it overlaps future curriculum.',
                            'purpose': 'project',
                        },
                    ]
                }
            )
        raise AssertionError(f'Unexpected schema model: {schema_model}')


class _TaughtOverlapBranchLLMStub:
    async def generate_structured(self, *, schema_model, **kwargs):  # type: ignore[no-untyped-def]
        if schema_model.__name__ == 'DeepDiveBranchPlan':
            return schema_model.model_validate(
                {
                    'branch_title': 'Overlap probe',
                    'rationale': 'Used to verify taught-content overlap filtering.',
                    'nodes': [
                        {
                            'key': 'overlap_taught',
                            'name': 'Phrase Alignment Under Pressure',
                            'description': 'Rehearses phrase alignment under pressure with identical framing.',
                            'difficulty': 2,
                            'prerequisites': ['parent'],
                        },
                    ],
                }
            )
        if schema_model.__name__ == 'BranchSuggestionPlan':
            return schema_model.model_validate({'suggestions': []})
        raise AssertionError(f'Unexpected schema model: {schema_model}')


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


def _seed(db):
    user = User(email='branch@test.local', hashed_password='x', display_name='Branch User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='DJ skills', description='Core mixing', goal='Build consistency')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    parent = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='Beat matching basics',
        description='Core beat matching control.',
        difficulty=2,
        mastery_estimate=0.3,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    state = UserSkillState(
        user_id=user.id,
        skill_node_id=parent.id,
        mastery=0.35,
        progress_state='learning',
        status=SkillStatus.in_progress,
    )
    db.add(state)
    db.commit()

    return user, topic, parent


def _seed_with_future_core(db):
    user, topic, parent = _seed(db)
    future_core = SkillNode(
        topic_id=topic.id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name='Future Core Topic',
        description='Upcoming core module with distinct future coverage.',
        difficulty=3,
        mastery_estimate=0.0,
        status=SkillStatus.locked,
        suggested_resources=[],
        generated_lessons=[],
    )
    db.add(future_core)
    db.commit()
    db.refresh(future_core)
    db.add(
        SkillEdge(
            topic_id=topic.id,
            parent_skill_id=parent.id,
            child_skill_id=future_core.id,
            edge_type='prerequisite',
        )
    )
    db.commit()
    return user, topic, parent, future_core


def _seed_with_taught_concept_overlap(db):
    user, topic, parent = _seed(db)
    lesson = LearningResource(
        user_id=user.id,
        topic_id=topic.id,
        skill_node_id=parent.id,
        resource_type=ResourceType.generated_lesson,
        title='Beat lesson',
        content_json={
            'key_concepts': [
                {
                    'term': 'Phrase alignment under pressure',
                    'description': 'Align phrases reliably while transitions get crowded.',
                }
            ],
            'sections': [
                {'heading': 'Phrase alignment under pressure'},
            ],
        },
    )
    db.add(lesson)
    db.commit()
    return user, topic, parent


def test_deep_dive_branch_creation_is_single_available_optional_node() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_BranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='timing focus',
            branch_size=3,
            branch_origin='user_requested',
            branch_purpose='specialization',
        )
    )

    assert len(created) == 1
    created_node = created[0]
    assert created_node.status == SkillStatus.available
    assert all(node.node_kind == 'optional_branch' for node in created)
    assert all(node.branch_origin == 'user_requested' for node in created)
    assert all(node.branch_purpose == 'specialization' for node in created)
    assert all(node.branch_parent_skill_id == parent.id for node in created)
    assert all(node.branch_depth >= 1 for node in created)

    edges = db.scalars(
        select(SkillEdge).where(
            SkillEdge.topic_id == topic.id,
            SkillEdge.child_skill_id == created_node.id,
        )
    ).all()
    assert len(edges) == 1
    assert edges[0].edge_type == 'optional_branch'
    assert edges[0].parent_skill_id == parent.id


def test_exploration_branch_creates_single_available_node() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_BranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='quick exploration',
            branch_size=3,
            branch_origin='user_requested',
            branch_purpose='exploration',
        )
    )

    assert len(created) == 1
    assert created[0].status == SkillStatus.available
    assert created[0].branch_parent_skill_id == parent.id

    edges = db.scalars(
        select(SkillEdge).where(
            SkillEdge.topic_id == topic.id,
            SkillEdge.child_skill_id == created[0].id,
        )
    ).all()
    edge_types = {edge.edge_type for edge in edges}
    assert edge_types == {'optional_branch'}
    assert all(edge.parent_skill_id == parent.id for edge in edges)


def test_exploration_suggestion_acceptance_path_stays_single_node() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_BranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='suggested exploration',
            branch_size=5,
            branch_origin='system_suggested',
            branch_purpose='exploration',
        )
    )

    assert len(created) == 1
    assert created[0].status == SkillStatus.available
    assert created[0].branch_origin == 'system_suggested'
    assert created[0].branch_purpose == 'exploration'

    prereq_edges = db.scalars(
        select(SkillEdge).where(
            SkillEdge.topic_id == topic.id,
            SkillEdge.edge_type == 'prerequisite',
            SkillEdge.child_skill_id == created[0].id,
        )
    ).all()
    assert prereq_edges == []


def test_branch_suggestion_generation_and_performance_suggestion_dedup() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_BranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.suggest_branch_paths(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            limit=1,
            trigger_event='manual',
        )
    )
    assert len(created) == 1
    assert all(item.status == 'pending' for item in created)
    assert all(item.origin == 'system_suggested' for item in created)

    remediation = agent.create_performance_branch_suggestion(
        db,
        topic=topic,
        parent_node=parent,
        user_id=user.id,
        score=0.3,
    )
    assert remediation is not None
    assert remediation.purpose == 'remediation'

    remediation_again = agent.create_performance_branch_suggestion(
        db,
        topic=topic,
        parent_node=parent,
        user_id=user.id,
        score=0.2,
    )
    assert remediation_again is not None
    assert remediation_again.id == remediation.id


def test_deep_dive_branch_caps_prerequisites_to_2() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_DenseBranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='dense cap check',
            branch_size=3,
            branch_origin='user_requested',
            branch_purpose='specialization',
        )
    )
    created_ids = {node.id for node in created}
    incoming: dict[int, int] = {node.id: 0 for node in created}
    for edge in db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all():
        if edge.child_skill_id not in created_ids:
            continue
        if edge.edge_type not in {'optional_branch', 'prerequisite'}:
            continue
        incoming[edge.child_skill_id] += 1

    assert incoming
    assert max(incoming.values()) <= 2


def test_branch_generation_avoids_future_core_overlap_for_non_remediation() -> None:
    db = _session()
    user, topic, parent, future_core = _seed_with_future_core(db)
    agent = SkillGraphAgent(_OverlapBranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='future overlap probe',
            branch_size=1,
            branch_origin='user_requested',
            branch_purpose='enrichment',
        )
    )

    assert len(created) == 1
    assert created[0].name != future_core.name
    assert created[0].branch_purpose == 'enrichment'


def test_branch_creation_canonicalizes_extended_purpose_labels() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_BranchLLMStub())  # type: ignore[arg-type]

    created_project = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='project path',
            branch_size=1,
            branch_origin='user_requested',
            branch_purpose='project',
        )
    )
    created_assessment = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='assessment prep path',
            branch_size=1,
            branch_origin='user_requested',
            branch_purpose='assessment_prep',
        )
    )

    assert created_project[0].branch_purpose == 'specialization'
    assert created_assessment[0].branch_purpose == 'remediation'


def test_branch_suggestion_filters_overlap_and_falls_back_to_single_high_signal_item() -> None:
    db = _session()
    user, topic, parent, _future_core = _seed_with_future_core(db)
    agent = SkillGraphAgent(_OverlapBranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.suggest_branch_paths(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            limit=1,
            trigger_event='manual',
        )
    )

    assert len(created) == 1
    assert created[0].focus.lower() != 'future core topic'
    assert created[0].purpose in {'enrichment', 'specialization', 'remediation', 'exploration'}


def test_enrichment_branch_filters_taught_content_overlap() -> None:
    db = _session()
    user, topic, parent = _seed_with_taught_concept_overlap(db)
    agent = SkillGraphAgent(_TaughtOverlapBranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='phrase alignment',
            branch_size=1,
            branch_origin='user_requested',
            branch_purpose='enrichment',
        )
    )

    assert len(created) == 1
    assert created[0].name != 'Phrase Alignment Under Pressure'
    assert created[0].branch_purpose == 'enrichment'


def test_remediation_branch_can_revisit_taught_content_focus() -> None:
    db = _session()
    user, topic, parent = _seed_with_taught_concept_overlap(db)
    agent = SkillGraphAgent(_TaughtOverlapBranchLLMStub())  # type: ignore[arg-type]

    created = asyncio.run(
        agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            focus='phrase alignment',
            branch_size=1,
            branch_origin='user_requested',
            branch_purpose='remediation',
        )
    )

    assert len(created) == 1
    assert created[0].branch_purpose == 'remediation'
    assert 'phrase alignment under pressure' in created[0].name.lower()


def test_suggest_branch_paths_returns_only_one_pending_per_parent() -> None:
    db = _session()
    user, topic, parent = _seed(db)
    agent = SkillGraphAgent(_BranchLLMStub())  # type: ignore[arg-type]

    stale = BranchSuggestion(
        topic_id=topic.id,
        user_id=user.id,
        parent_skill_id=parent.id,
        title='Old branch idea',
        focus='Old focus',
        rationale='Old rationale',
        purpose='exploration',
        origin='system_suggested',
        trigger_event='manual',
        status='pending',
    )
    db.add(stale)
    db.commit()
    db.refresh(stale)

    newer = BranchSuggestion(
        topic_id=topic.id,
        user_id=user.id,
        parent_skill_id=parent.id,
        title='Latest branch idea',
        focus='Latest focus',
        rationale='Latest rationale',
        purpose='specialization',
        origin='system_suggested',
        trigger_event='manual',
        status='pending',
    )
    db.add(newer)
    db.commit()
    db.refresh(newer)

    suggestions = asyncio.run(
        agent.suggest_branch_paths(
            db,
            topic=topic,
            parent_node=parent,
            user_id=user.id,
            limit=3,
            trigger_event='manual',
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0].id == newer.id

    stale_row = db.scalar(select(BranchSuggestion).where(BranchSuggestion.id == stale.id))
    assert stale_row is not None
    assert stale_row.status == 'rejected'
