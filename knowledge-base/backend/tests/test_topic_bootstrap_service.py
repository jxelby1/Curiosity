from __future__ import annotations

import asyncio

from app.db.models import Topic
from app.db.models import SkillEdge, SkillNode, SkillStatus, UserSkillState
from app.services.topic_bootstrap import TopicBootstrapService


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class _FakeSession:
    def __init__(self, *, nodes, states, edges):
        self.nodes = nodes
        self.states = states
        self.edges = edges

    def scalars(self, statement):
        sql = str(statement)
        if 'FROM user_skill_states JOIN skill_nodes' in sql:
            return _ScalarResult(self.states)
        if 'FROM skill_edges' in sql:
            return _ScalarResult(self.edges)
        if 'FROM skill_nodes' in sql:
            return _ScalarResult(self.nodes)
        return _ScalarResult([])


class _ScalarSequenceDB:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def scalar(self, statement):  # type: ignore[no-untyped-def]
        _ = statement
        if self.calls >= len(self._responses):
            self.calls += 1
            return None
        response = self._responses[self.calls]
        self.calls += 1
        return response


class _ResourceAgentRecorder:
    def __init__(self) -> None:
        self.kinds: list[str] = []
        self.regenerate_flags: list[bool] = []

    async def generate_material(self, db, *, kind, **kwargs):  # type: ignore[no-untyped-def]
        _ = db, kwargs
        self.kinds.append(kind)
        self.regenerate_flags.append(bool(kwargs.get('regenerate')))
        return object(), {'title': kind}, 'stored'


class _AssessmentAgentRecorder:
    def __init__(self) -> None:
        self.called = 0

    async def generate_assessment(self, db, **kwargs):  # type: ignore[no-untyped-def]
        _ = db, kwargs
        self.called += 1
        return object(), 'stored'


def _service() -> TopicBootstrapService:
    return TopicBootstrapService(
        skill_graph_agent=object(),  # type: ignore[arg-type]
        profile_agent=object(),  # type: ignore[arg-type]
        resource_agent=object(),  # type: ignore[arg-type]
        assessment_agent=object(),  # type: ignore[arg-type]
    )


def test_pick_first_unlocked_node_prefers_core_low_difficulty() -> None:
    service = _service()
    nodes = [
        SkillNode(id=1, topic_id=10, node_kind='core', name='A', description='A', difficulty=2, mastery_estimate=0.0),
        SkillNode(id=2, topic_id=10, node_kind='optional_branch', name='B', description='B', difficulty=1, mastery_estimate=0.0),
        SkillNode(id=3, topic_id=10, node_kind='core', name='C', description='C', difficulty=1, mastery_estimate=0.0),
    ]
    states = [
        UserSkillState(user_id=1, skill_node_id=1, status=SkillStatus.available),
        UserSkillState(user_id=1, skill_node_id=2, status=SkillStatus.available),
        UserSkillState(user_id=1, skill_node_id=3, status=SkillStatus.locked),
    ]
    fake_db = _FakeSession(nodes=nodes, states=states, edges=[])

    first = service._pick_first_unlocked_node(fake_db, topic_id=10, user_id=1)  # type: ignore[arg-type]
    assert first is not None
    assert first.id == 1


def test_preload_priority_nodes_only_includes_locked_nodes_adjacent_to_unlocked() -> None:
    service = _service()
    nodes = [
        SkillNode(id=1, topic_id=20, node_kind='core', name='Root', description='Root', difficulty=1, mastery_estimate=0.0),
        SkillNode(id=2, topic_id=20, node_kind='core', name='Unlocked', description='Unlocked', difficulty=2, mastery_estimate=0.0),
        SkillNode(id=3, topic_id=20, node_kind='core', name='Adjacent locked', description='A', difficulty=3, mastery_estimate=0.0),
        SkillNode(id=4, topic_id=20, node_kind='core', name='Two hop locked', description='B', difficulty=4, mastery_estimate=0.0),
        SkillNode(
            id=5,
            topic_id=20,
            node_kind='optional_branch',
            branch_parent_skill_id=2,
            name='Branch adjacent',
            description='C',
            difficulty=2,
            mastery_estimate=0.0,
        ),
    ]
    states = [
        UserSkillState(user_id=1, skill_node_id=1, status=SkillStatus.available, progress_state='verified'),
        UserSkillState(user_id=1, skill_node_id=2, status=SkillStatus.available, progress_state='learning'),
        UserSkillState(user_id=1, skill_node_id=3, status=SkillStatus.locked, progress_state='not_started'),
        UserSkillState(user_id=1, skill_node_id=4, status=SkillStatus.locked, progress_state='not_started'),
        UserSkillState(user_id=1, skill_node_id=5, status=SkillStatus.locked, progress_state='not_started'),
    ]
    edges = [
        SkillEdge(topic_id=20, parent_skill_id=2, child_skill_id=3, edge_type='prerequisite'),
        SkillEdge(topic_id=20, parent_skill_id=3, child_skill_id=4, edge_type='prerequisite'),
    ]

    fake_db = _FakeSession(nodes=nodes, states=states, edges=edges)
    ordered = service._preload_priority_nodes(  # type: ignore[arg-type]
        fake_db,
        topic_id=20,
        user_id=1,
        first_ready_skill_id=1,
        limit=4,
    )

    assert [node.id for node in ordered] == [3, 5]


def test_preload_priority_nodes_can_scope_to_newly_unlocked_nodes() -> None:
    service = _service()
    nodes = [
        SkillNode(id=10, topic_id=30, node_kind='core', name='A', description='A', difficulty=1, mastery_estimate=0.0),
        SkillNode(id=11, topic_id=30, node_kind='core', name='B', description='B', difficulty=2, mastery_estimate=0.0),
        SkillNode(id=12, topic_id=30, node_kind='core', name='C', description='C', difficulty=3, mastery_estimate=0.0),
        SkillNode(id=13, topic_id=30, node_kind='core', name='D', description='D', difficulty=4, mastery_estimate=0.0),
    ]
    states = [
        UserSkillState(user_id=1, skill_node_id=10, status=SkillStatus.available, progress_state='verified'),
        UserSkillState(user_id=1, skill_node_id=11, status=SkillStatus.available, progress_state='learning'),
        UserSkillState(user_id=1, skill_node_id=12, status=SkillStatus.locked, progress_state='not_started'),
        UserSkillState(user_id=1, skill_node_id=13, status=SkillStatus.locked, progress_state='not_started'),
    ]
    edges = [
        SkillEdge(topic_id=30, parent_skill_id=10, child_skill_id=12, edge_type='prerequisite'),
        SkillEdge(topic_id=30, parent_skill_id=11, child_skill_id=13, edge_type='prerequisite'),
    ]

    fake_db = _FakeSession(nodes=nodes, states=states, edges=edges)
    scoped = service._preload_priority_nodes(  # type: ignore[arg-type]
        fake_db,
        topic_id=30,
        user_id=1,
        first_ready_skill_id=10,
        limit=4,
        adjacent_to_node_ids={11},
    )

    assert [node.id for node in scoped] == [13]


def test_preload_priority_nodes_uses_core_repair_chain_when_declared_edges_are_missing() -> None:
    service = _service()
    nodes = [
        SkillNode(id=21, topic_id=40, node_kind='core', name='Root', description='Root', difficulty=1, mastery_estimate=0.0),
        SkillNode(id=22, topic_id=40, node_kind='core', name='Tail', description='Tail', difficulty=2, mastery_estimate=0.0),
    ]
    states = [
        UserSkillState(user_id=1, skill_node_id=21, status=SkillStatus.available, progress_state='learning'),
        UserSkillState(user_id=1, skill_node_id=22, status=SkillStatus.locked, progress_state='not_started'),
    ]
    edges: list[SkillEdge] = []

    fake_db = _FakeSession(nodes=nodes, states=states, edges=edges)
    ordered = service._preload_priority_nodes(  # type: ignore[arg-type]
        fake_db,
        topic_id=40,
        user_id=1,
        first_ready_skill_id=21,
        limit=4,
    )

    assert [node.id for node in ordered] == [22]


def test_prepare_first_node_starter_content_includes_examples() -> None:
    resource_agent = _ResourceAgentRecorder()
    assessment_agent = _AssessmentAgentRecorder()
    service = TopicBootstrapService(
        skill_graph_agent=object(),  # type: ignore[arg-type]
        profile_agent=object(),  # type: ignore[arg-type]
        resource_agent=resource_agent,  # type: ignore[arg-type]
        assessment_agent=assessment_agent,  # type: ignore[arg-type]
    )
    topic = Topic(id=11, user_id=1, name='Topic', description='Topic description', goal='Goal')
    first_node = SkillNode(topic_id=11, id=2, name='First', description='first node', difficulty=1, mastery_estimate=0.0)

    asyncio.run(
        service._prepare_first_node_starter_content(  # type: ignore[attr-defined]
            db=object(),
            topic=topic,
            first_node=first_node,
            user_id=1,
        )
    )

    assert resource_agent.kinds == ['lesson', 'examples', 'exercises']
    assert resource_agent.regenerate_flags == [False, False, False]
    assert assessment_agent.called == 1


def test_first_node_readiness_requires_examples_and_assessment() -> None:
    service = _service()
    ready_db = _ScalarSequenceDB([object(), object(), object(), object()])
    assert service._is_first_node_ready_for_entry(  # type: ignore[attr-defined]
        ready_db,  # type: ignore[arg-type]
        topic_id=1,
        skill_node_id=2,
        user_id=1,
    )

    missing_examples_db = _ScalarSequenceDB([object(), None])
    assert not service._is_first_node_ready_for_entry(  # type: ignore[attr-defined]
        missing_examples_db,  # type: ignore[arg-type]
        topic_id=1,
        skill_node_id=2,
        user_id=1,
    )
