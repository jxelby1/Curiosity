from __future__ import annotations

import asyncio
import json
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.recommendation_agent import RecommendationAgent
from app.db.models import Recommendation, SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState


class _LLMStub:
    async def generate_structured(self, *, schema_model, user_prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        ids = [1, 2]
        match = re.search(r'Candidate skills \(JSON\):\n(\[.*\])\n\nSelect up to', user_prompt, flags=re.DOTALL)
        if match:
            try:
                candidates = json.loads(match.group(1))
                parsed_ids = [
                    int(item.get('skill_node_id'))
                    for item in candidates
                    if isinstance(item, dict) and item.get('skill_node_id') is not None
                ]
                if parsed_ids:
                    ids = parsed_ids[:2] if len(parsed_ids) >= 2 else [parsed_ids[0], parsed_ids[0]]
            except json.JSONDecodeError:
                pass
        return schema_model.model_validate(
            {
                'recommendations': [
                    {
                        'skill_node_id': ids[0],
                        'action_type': 'study_generated',
                        'rationale': 'Start with the first available node.',
                        'confidence': 0.88,
                    },
                    {
                        'skill_node_id': ids[1],
                        'action_type': 'study_generated',
                        'rationale': 'Then continue to the second node.',
                        'confidence': 0.77,
                    },
                ]
            }
        )


class _RetrievalStub:
    async def retrieve_chunks(self, db, *, topic_id, query, top_k):  # type: ignore[no-untyped-def]
        _ = db, topic_id, query, top_k
        return []


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    Recommendation.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _seed_graph():
    db = _session()
    user = User(email='recs@test.local', hashed_password='x', display_name='Rec User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='History fundamentals', description='Core timeline', goal='Learn progression')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    n1 = SkillNode(
        topic_id=topic.id,
        name='Node One',
        description='First node',
        difficulty=1,
        status=SkillStatus.available,
        mastery_estimate=0.05,
    )
    n2 = SkillNode(
        topic_id=topic.id,
        name='Node Two',
        description='Second node',
        difficulty=2,
        status=SkillStatus.available,
        mastery_estimate=0.15,
    )
    n3 = SkillNode(
        topic_id=topic.id,
        name='Node Three',
        description='Third node',
        difficulty=3,
        status=SkillStatus.available,
        mastery_estimate=0.2,
    )
    db.add_all([n1, n2, n3])
    db.commit()
    db.refresh(n1)
    db.refresh(n2)
    db.refresh(n3)

    db.add(
        SkillEdge(
            topic_id=topic.id,
            parent_skill_id=n1.id,
            child_skill_id=n2.id,
            edge_type='prerequisite',
        )
    )
    db.add(
        SkillEdge(
            topic_id=topic.id,
            parent_skill_id=n2.id,
            child_skill_id=n3.id,
            edge_type='prerequisite',
        )
    )
    db.add(UserSkillState(user_id=user.id, skill_node_id=n1.id, status=SkillStatus.available, mastery=0.1))
    db.add(UserSkillState(user_id=user.id, skill_node_id=n2.id, status=SkillStatus.available, mastery=0.2))
    db.add(UserSkillState(user_id=user.id, skill_node_id=n3.id, status=SkillStatus.available, mastery=0.3))
    db.commit()
    return db, topic, user


def test_recommendation_agent_defaults_to_single_primary_item() -> None:
    db, topic, user = _seed_graph()
    agent = RecommendationAgent(_LLMStub(), _RetrievalStub())  # type: ignore[arg-type]

    records = asyncio.run(agent.generate_recommendations(db, topic, user.id))

    assert len(records) == 1
    assert records[0].confidence > 0


def test_recommendation_agent_can_return_multiple_when_limit_explicit() -> None:
    db, topic, user = _seed_graph()
    agent = RecommendationAgent(_LLMStub(), _RetrievalStub())  # type: ignore[arg-type]

    records = asyncio.run(agent.generate_recommendations(db, topic, user.id, limit=2))

    assert len(records) == 2
