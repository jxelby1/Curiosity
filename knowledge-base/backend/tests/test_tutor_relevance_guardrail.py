from __future__ import annotations

import asyncio

from app.agents.tutor_agent import TutorAgent
from app.db.models import SkillNode, Topic
from app.schemas.llm import TopicRelevancePlan


class _LLMStub:
    def __init__(self, relevance: str) -> None:
        self.relevance = relevance
        self.calls = 0

    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return TopicRelevancePlan(relevance=self.relevance, rationale='classification rationale')


class _RetrievalStub:
    pass


def test_relevant_message_is_not_blocked_by_guardrail() -> None:
    llm = _LLMStub('unrelated')
    agent = TutorAgent(llm_service=llm, retrieval_service=_RetrievalStub())  # type: ignore[arg-type]

    topic = Topic(id=1, user_id=1, name='Wine tasting', description='learn tasting notes', goal='improve palate')
    node = SkillNode(id=2, topic_id=1, name='Aroma basics', description='identify aromas in wine', difficulty=1, mastery_estimate=0.0)

    label = asyncio.run(
        agent._classify_topic_relevance(  # type: ignore[attr-defined]
            topic=topic,
            skill_node=node,
            message='How should I compare tannins and acidity in a red wine?',
        )
    )

    assert label in {'relevant', 'related'}
    assert llm.calls == 0


def test_unrelated_message_is_redirected_to_topic_context() -> None:
    llm = _LLMStub('unrelated')
    agent = TutorAgent(llm_service=llm, retrieval_service=_RetrievalStub())  # type: ignore[arg-type]

    topic = Topic(id=1, user_id=1, name='Wine tasting', description='learn tasting notes', goal='improve palate')
    label = asyncio.run(
        agent._classify_topic_relevance(  # type: ignore[attr-defined]
            topic=topic,
            skill_node=None,
            message='What car should I buy this year?',
        )
    )

    assert label == 'unrelated'
    redirect = agent._off_topic_redirect(topic=topic)  # type: ignore[attr-defined]
    assert 'Wine tasting' in redirect


def test_related_message_is_allowed_when_classifier_marks_related() -> None:
    llm = _LLMStub('related')
    agent = TutorAgent(llm_service=llm, retrieval_service=_RetrievalStub())  # type: ignore[arg-type]

    topic = Topic(id=1, user_id=1, name='Wine tasting', description='learn tasting notes', goal='improve palate')
    label = asyncio.run(
        agent._classify_topic_relevance(  # type: ignore[attr-defined]
            topic=topic,
            skill_node=None,
            message='How can I build a better sensory memory routine?',
        )
    )

    assert label == 'related'
    assert llm.calls >= 1
