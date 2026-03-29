from __future__ import annotations

import asyncio

from app.db.models import SkillNode, Topic
from app.services.course_memory import CourseMemorySnapshot
from app.services.course_research import CourseResearchService
from app.services.search import SearchResult


class _SearchStub:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    async def search(self, topic: str, skill: str, **kwargs):  # type: ignore[no-untyped-def]
        _ = topic, skill, kwargs
        return list(self.results)


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(
        user_id=1,
        name='Finding hidden gems in Chalk Farm',
        description='Local neighborhood exploration',
        goal='Build practical local knowledge',
    )
    skill = SkillNode(
        topic_id=1,
        name='Independent cafes and venues',
        description='Identify high-signal local places',
        difficulty=2,
        mastery_estimate=0.0,
    )
    return topic, skill


def test_research_service_is_selective_for_static_topics() -> None:
    service = CourseResearchService(_SearchStub([]))  # type: ignore[arg-type]
    static_topic = Topic(user_id=1, name='Linear algebra fundamentals', description='Core math concepts', goal='Learn vectors')
    static_skill = SkillNode(
        topic_id=1,
        name='Vector spaces',
        description='Definitions and basis',
        difficulty=2,
        mastery_estimate=0.0,
    )
    memory = CourseMemorySnapshot(
        source_backed_examples=[
            'OpenStax vector space chapter',
            'MIT linear algebra notes',
        ]
    )
    assert (
        service.should_research(
            topic=static_topic,
            skill_node=static_skill,
            kind='lesson',
            retrieval_hits=4,
            memory=memory,
        )
        is False
    )


def test_research_service_triggers_for_dynamic_topic_context() -> None:
    service = CourseResearchService(_SearchStub([]))  # type: ignore[arg-type]
    topic, skill = _topic_and_skill()
    assert (
        service.should_research(
            topic=topic,
            skill_node=skill,
            kind='lesson',
            retrieval_hits=3,
            memory=CourseMemorySnapshot(),
        )
        is True
    )


def test_research_service_ranks_and_filters_results() -> None:
    topic, skill = _topic_and_skill()
    results = [
        SearchResult(
            title='Chalk Farm independent cafes map',
            url='https://www.timeout.com/london/chalk-farm-cafes',
            kind='external_article',
            summary='A practical guide with map references and local venues.',
            source_domain='timeout.com',
            relevance_score=0.35,
        ),
        SearchResult(
            title='Generic UK food blog',
            url='https://example.com/food',
            kind='external_article',
            summary='No Chalk Farm specificity.',
            source_domain='example.com',
            relevance_score=0.1,
        ),
    ]
    service = CourseResearchService(_SearchStub(results))  # type: ignore[arg-type]
    memory = CourseMemorySnapshot(used_examples=['Chalk Farm independent cafes map'])

    insights = asyncio.run(
        service.gather_for_skill(
            topic=topic,
            skill_node=skill,
            kind='examples',
            memory=memory,
            retrieval_hits=0,
            limit=3,
            force=True,
        )
    )

    assert len(insights) == 1
    assert insights[0].url == 'https://www.timeout.com/london/chalk-farm-cafes'
    assert 'timeout.com' in service.format_prompt_context(insights)


def test_research_service_prefers_trusted_domain_when_available() -> None:
    topic, skill = _topic_and_skill()
    results = [
        SearchResult(
            title='Some personal blog on Chalk Farm',
            url='https://random-blog.example/chalk-farm',
            kind='external_article',
            summary='A personal opinion list.',
            source_domain='random-blog.example',
            relevance_score=0.36,
        ),
        SearchResult(
            title='BBC London guide to Chalk Farm',
            url='https://www.bbc.com/travel/article/chalk-farm-guide',
            kind='external_article',
            summary='Context-rich area guide from BBC Travel.',
            source_domain='bbc.com',
            relevance_score=0.33,
        ),
    ]
    service = CourseResearchService(_SearchStub(results))  # type: ignore[arg-type]

    insights = asyncio.run(
        service.gather_for_skill(
            topic=topic,
            skill_node=skill,
            kind='lesson',
            memory=CourseMemorySnapshot(),
            retrieval_hits=0,
            limit=1,
            force=True,
        )
    )

    assert len(insights) == 1
    assert insights[0].source_domain == 'bbc.com'


def test_research_service_limits_domain_monoculture_in_selection() -> None:
    topic, skill = _topic_and_skill()
    results = [
        SearchResult(
            title='Source A1',
            url='https://news.example.com/chalk-farm-1',
            kind='external_article',
            summary='Specific local venue context.',
            source_domain='news.example.com',
            relevance_score=0.9,
        ),
        SearchResult(
            title='Source A2',
            url='https://news.example.com/chalk-farm-2',
            kind='external_article',
            summary='More local venue context.',
            source_domain='news.example.com',
            relevance_score=0.85,
        ),
        SearchResult(
            title='Source B',
            url='https://bbc.com/travel/chalk-farm',
            kind='external_article',
            summary='Independent area guide.',
            source_domain='bbc.com',
            relevance_score=0.7,
        ),
        SearchResult(
            title='Source C',
            url='https://metmuseum.org/learning/chalk-farm-context',
            kind='external_documentation',
            summary='Historical framing context.',
            source_domain='metmuseum.org',
            relevance_score=0.68,
        ),
    ]
    service = CourseResearchService(_SearchStub(results))  # type: ignore[arg-type]

    insights = asyncio.run(
        service.gather_for_skill(
            topic=topic,
            skill_node=skill,
            kind='deep_lesson',
            memory=CourseMemorySnapshot(),
            retrieval_hits=0,
            limit=3,
            force=True,
        )
    )

    assert len(insights) == 3
    domains = [item.source_domain for item in insights]
    assert domains.count('news.example.com') <= 1
