from __future__ import annotations

import asyncio
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import ProviderError
from app.agents.resource_agent import ResourceAgent, _clean_clipped_fragment
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    BranchSuggestion,
    LearningResource,
    ResourceType,
    SkillEdge,
    SkillNode,
    Topic,
    User,
    UserSkillState,
)


class _FailingLLM:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        raise ProviderError('forced structured generation failure')


class _RetrievalStub:
    async def retrieve_chunks(self, db, *, topic_id, query, top_k):  # type: ignore[no-untyped-def]
        _ = db, topic_id, query, top_k
        return []


class _SearchStub:
    async def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return []


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


def test_resource_generation_uses_deterministic_fallback_when_llm_fails() -> None:
    db = _session()
    user = User(email='resource-fallback@test.local', hashed_password='x', display_name='Fallback User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Cooking', description='Basics', goal='Start')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Knife safety', description='Core handling safety', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    agent = ResourceAgent(
        llm_service=_FailingLLM(),  # type: ignore[arg-type]
        search_service=_SearchStub(),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )

    resource, content, source = asyncio.run(
        agent.generate_material(
            db,
            user_id=user.id,
            topic=topic,
            skill_node=skill,
            kind='exercises',
            regenerate=False,
        )
    )

    assert source == 'generated'
    assert resource.content_json is not None
    assert content is not None
    assert content['title']
    assert len(content['exercises']) == 2
    assert isinstance(topic.curriculum_ledger, dict)
    assert 'generated_exercises' in str(topic.curriculum_ledger.get('reason', '')) or 'latest_exercises_research' in topic.curriculum_ledger


def test_deep_lesson_generation_uses_fallback_when_llm_fails() -> None:
    db = _session()
    user = User(email='deep-fallback@test.local', hashed_password='x', display_name='Deep Fallback User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Art History', description='Basics', goal='Understand context')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Austrian Art Context', description='Context and influences', difficulty=2, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    agent = ResourceAgent(
        llm_service=_FailingLLM(),  # type: ignore[arg-type]
        search_service=_SearchStub(),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )

    content, source = asyncio.run(
        agent.generate_deep_lesson_material(
            db,
            user_id=user.id,
            topic=topic,
            skill_node=skill,
        )
    )

    assert source == 'fallback'
    assert content['title']
    assert len(content['sections']) >= 3
    assert len(content['study_prompts']) >= 2


def test_existing_resource_is_reused_without_regeneration() -> None:
    db = _session()
    user = User(email='resource-reuse@test.local', hashed_password='x', display_name='Reuse User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Art History', description='Context', goal='Understand works')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Klimt overview', description='Foundational context', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    existing = LearningResource(
        user_id=user.id,
        topic_id=topic.id,
        skill_node_id=skill.id,
        resource_type=ResourceType.generated_lesson,
        version=1,
        is_active=True,
        title='Stored lesson',
        summary='Stored summary.',
        content_json={'title': 'Stored lesson', 'summary': 'Stored summary.', 'sections': []},
        content='{"title":"Stored lesson"}',
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    agent = ResourceAgent(
        llm_service=_FailingLLM(),  # type: ignore[arg-type]
        search_service=_SearchStub(),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )

    resource, content, source = asyncio.run(
        agent.generate_material(
            db,
            user_id=user.id,
            topic=topic,
            skill_node=skill,
            kind='lesson',
            regenerate=False,
        )
    )

    assert source == 'stored'
    assert resource.id == existing.id
    assert content is not None
    assert content['title'] == 'Stored lesson'


def test_fallback_lesson_summary_polishes_long_text_without_midword_cutoff() -> None:
    db = _session()
    user = User(email='fallback-summary@test.local', hashed_password='x', display_name='Fallback Summary User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(
        user_id=user.id,
        name='Extremely Long Domain Context Name For Testing',
        description='Validation topic',
        goal='Ensure card summaries are readable',
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    long_skill_name = ' '.join(['Foundational'] * 80)
    skill = SkillNode(
        topic_id=topic.id,
        name=long_skill_name,
        description='Long-name fallback test',
        difficulty=1,
        mastery_estimate=0.0,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)

    agent = ResourceAgent(
        llm_service=_FailingLLM(),  # type: ignore[arg-type]
        search_service=_SearchStub(),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )

    _, content, _ = asyncio.run(
        agent.generate_material(
            db,
            user_id=user.id,
            topic=topic,
            skill_node=skill,
            kind='lesson',
            regenerate=True,
        )
    )

    assert content is not None
    summary = str(content['summary'])
    assert len(summary) <= 300
    assert summary.endswith('.')
    assert not summary.endswith('…')


def test_clean_clipped_fragment_repairs_trailing_ellipsis_to_complete_sentence() -> None:
    clipped = (
        "The Cotswolds is a region in south-central England spanning approximately 800 square miles across six "
        "counties, including Gloucestershire, Oxfordshire, Warwickshire, Wiltshire, Worcestershire, and Somerset, "
        "with its core area primarily in Gloucestershire and…"
    )

    repaired = _clean_clipped_fragment(clipped, max_len=300)

    assert repaired.endswith('.')
    assert not repaired.endswith('…')
    assert len(repaired) <= 300
    assert re.search(r'[.!?]$', repaired)
