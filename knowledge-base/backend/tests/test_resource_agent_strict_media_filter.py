from __future__ import annotations

import asyncio

from app.agents.resource_agent import ResourceAgent
from app.db.models import SkillNode, Topic
from app.services.search import SearchResult


class _LLMStub:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        raise AssertionError('LLM should not be called for strict media filtering test')


class _RetrievalStub:
    async def retrieve_chunks(self, db, *, topic_id, query, top_k):  # type: ignore[no-untyped-def]
        _ = db, topic_id, query, top_k
        return []


class _SearchStub:
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    async def search(
        self,
        topic: str,
        skill: str,
        *,
        query: str | None = None,
        limit: int = 5,
        source_policy: str | None = None,
    ) -> list[SearchResult]:
        _ = topic, skill, query, limit, source_policy
        return list(self._results)


def _agent_with_results(results: list[SearchResult]) -> ResourceAgent:
    return ResourceAgent(
        llm_service=_LLMStub(),  # type: ignore[arg-type]
        search_service=_SearchStub(results),  # type: ignore[arg-type]
        retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
    )


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(user_id=1, name="Klimt's Art", description='Study Austrian modernism', goal='Understand context')
    skill = SkillNode(
        topic_id=1,
        name='Austrian Art and Culture in the Late 19th Century',
        description='Political and cultural context for Klimt',
        difficulty=2,
        mastery_estimate=0.0,
    )
    return topic, skill


def test_strict_media_filter_keeps_only_high_relevance_trusted_sources() -> None:
    topic, skill = _topic_and_skill()
    deep_lesson = {'essential_questions': [], 'sections': [], 'key_terms': []}
    results = [
        SearchResult(
            title='Austrian Art and Culture in the Late 19th Century - Overview',
            url='https://www.britannica.com/art/Austrian-art',
            kind='external_article',
            summary='Historical overview with paintings and image references tied to Klimt.',
        ),
        SearchResult(
            title='Random art blog post',
            url='https://random-art-blog.example.com/klimt-history',
            kind='external_article',
            summary='Opinion piece with no source validation.',
        ),
        SearchResult(
            title='Beginner guitar tutorial',
            url='https://www.wikipedia.org/wiki/Guitar',
            kind='external_article',
            summary='Unrelated topic with no relevant context.',
        ),
        SearchResult(
            title='CrashCourse: Austrian Art and Culture in the Late 19th Century',
            url='https://www.youtube.com/watch?v=abc123',
            kind='external_video',
            summary='Trusted educational channel overview.',
        ),
    ]
    agent = _agent_with_results(results)

    media = asyncio.run(
        agent.fetch_strict_supporting_media(
            topic=topic,
            skill_node=skill,
            deep_lesson=deep_lesson,
            limit=3,
        )
    )

    assert len(media) == 2
    assert all(item['source_domain'] in {'britannica.com', 'youtube.com'} for item in media)
    assert all(item['media_type'] in {'image', 'video'} for item in media)
    assert all('random-art-blog.example.com' not in item['source_domain'] for item in media)


def test_strict_media_filter_returns_empty_for_low_relevance_candidates() -> None:
    topic, skill = _topic_and_skill()
    deep_lesson = {'essential_questions': [], 'sections': [], 'key_terms': []}
    results = [
        SearchResult(
            title='Completely unrelated economics article',
            url='https://www.britannica.com/money/finance',
            kind='external_article',
            summary='No mention of art history or Klimt.',
        ),
        SearchResult(
            title='Travel vlog',
            url='https://www.youtube.com/watch?v=zzz999',
            kind='external_video',
            summary='Lifestyle travel content from a personal channel.',
        ),
    ]
    agent = _agent_with_results(results)

    media = asyncio.run(
        agent.fetch_strict_supporting_media(
            topic=topic,
            skill_node=skill,
            deep_lesson=deep_lesson,
            limit=2,
        )
    )

    assert media == []


def test_strict_media_filter_keeps_map_references_from_trusted_sources() -> None:
    topic = Topic(user_id=1, name='Iran History', description='Geography and historical context', goal='Understand major regions')
    skill = SkillNode(
        topic_id=1,
        name='Geography of Iran',
        description='Regions, terrain, and strategic location',
        difficulty=2,
        mastery_estimate=0.0,
    )
    deep_lesson = {
        'essential_questions': ['How does Iran geography influence history?'],
        'sections': [{'heading': 'Terrain and regional geography', 'content': 'Mountains, deserts, and coastlines'}],
        'key_terms': [{'term': 'topography', 'description': 'land surface features'}],
    }
    results = [
        SearchResult(
            title='Map of Iran - Encyclopaedia Britannica',
            url='https://www.britannica.com/place/Iran',
            kind='external_article',
            summary='Map and regional overview of Iran geography and topography.',
        ),
        SearchResult(
            title='Iran geography explainer',
            url='https://unknown-site.example.com/iran-geography-map',
            kind='external_article',
            summary='Unofficial map article.',
        ),
    ]
    agent = _agent_with_results(results)

    media = asyncio.run(
        agent.fetch_strict_supporting_media(
            topic=topic,
            skill_node=skill,
            deep_lesson=deep_lesson,
            limit=2,
        )
    )

    assert len(media) == 1
    assert media[0]['source_domain'] == 'britannica.com'
    assert media[0]['media_type'] == 'image'


def test_social_media_candidates_are_blocked_even_in_development_fallback() -> None:
    topic = Topic(user_id=1, name='Iran Geography', description='Understand terrain', goal='Map understanding')
    skill = SkillNode(
        topic_id=1,
        name='Mountain Ranges of Iran',
        description='Geographic overview',
        difficulty=2,
        mastery_estimate=0.0,
    )
    deep_lesson = {
        'essential_questions': ['How does terrain affect movement?'],
        'sections': [{'heading': 'Terrain', 'content': 'Mountains and routes'}],
        'key_terms': [{'term': 'terrain', 'description': 'surface features'}],
    }
    results = [
        SearchResult(
            title='Iran mountain map explainer',
            url='https://www.facebook.com/watch/?v=12345',
            kind='external_video',
            summary='Helpful overview video',
        ),
        SearchResult(
            title='Iran mountain map thread',
            url='https://x.com/geography/status/123',
            kind='external_article',
            summary='Map discussion',
        ),
    ]
    agent = _agent_with_results(results)

    media = asyncio.run(
        agent.fetch_strict_supporting_media(
            topic=topic,
            skill_node=skill,
            deep_lesson=deep_lesson,
            limit=2,
        )
    )

    assert media == []


def test_stock_image_sites_are_blocked_while_bbc_and_medium_are_allowed() -> None:
    topic = Topic(user_id=1, name='Klimt Art History', description='Art context', goal='Understand symbolism')
    skill = SkillNode(
        topic_id=1,
        name="Klimt's Symbolic Techniques",
        description='Use of motifs and symbolism',
        difficulty=2,
        mastery_estimate=0.0,
    )
    deep_lesson = {
        'essential_questions': ['How did Klimt use symbolism in portraits?'],
        'sections': [{'heading': 'Symbolism', 'content': 'Motifs and interpretation'}],
        'key_terms': [{'term': 'symbolism', 'description': 'use of symbols'}],
    }
    results = [
        SearchResult(
            title='Getty Images: Klimt artwork',
            url='https://www.gettyimages.com/photos/gustav-klimt',
            kind='external_article',
            summary='Stock photo listing.',
        ),
        SearchResult(
            title='BBC Arts: Gustav Klimt and symbolism',
            url='https://www.bbc.com/culture/article/20200101-gustav-klimt-symbolism',
            kind='external_article',
            summary='BBC culture analysis with artwork context and references.',
        ),
        SearchResult(
            title='Medium: Reading Symbolism in Klimt',
            url='https://medium.com/art-history/reading-symbolism-in-klimt-abc123',
            kind='external_article',
            summary='Detailed long-form article discussing Klimt symbols and context.',
        ),
    ]
    agent = _agent_with_results(results)

    media = asyncio.run(
        agent.fetch_strict_supporting_media(
            topic=topic,
            skill_node=skill,
            deep_lesson=deep_lesson,
            limit=3,
        )
    )

    domains = {item['source_domain'] for item in media}
    assert 'gettyimages.com' not in domains
    assert 'bbc.com' in domains
    assert 'medium.com' in domains


def test_broad_fallback_can_return_relevant_non_social_non_stock_results() -> None:
    topic = Topic(user_id=1, name='Iranian Military History', description='Campaigns and terrain', goal='Understand movement constraints')
    skill = SkillNode(
        topic_id=1,
        name='Fundamentals of Iranian Geography',
        description='Mountain ranges and deserts affecting campaign movement',
        difficulty=2,
        mastery_estimate=0.0,
    )
    deep_lesson = {
        'essential_questions': ['How do mountain ranges shape force movement?'],
        'sections': [{'heading': 'Deserts and mountain passes', 'content': 'Operational constraints'}],
        'key_terms': [{'term': 'mountain pass', 'description': 'key route constraint'}],
    }
    results = [
        SearchResult(
            title='Iran geography map and terrain explainer',
            url='https://geography.example.org/iran-map-terrain-overview',
            kind='external_article',
            summary='A geography explainer with regional map context and movement constraints.',
        ),
    ]
    agent = _agent_with_results(results)

    media = asyncio.run(
        agent.fetch_strict_supporting_media(
            topic=topic,
            skill_node=skill,
            deep_lesson=deep_lesson,
            limit=2,
        )
    )

    assert len(media) == 1
    assert media[0]['source_domain'] == 'geography.example.org'
