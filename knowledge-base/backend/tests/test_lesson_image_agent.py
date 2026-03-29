from __future__ import annotations

import asyncio

from app.agents.lesson_image_agent import LessonImageAgent
from app.core.config import get_settings
from app.db.models import SkillNode, Topic
from app.services.search import SearchResult


class _SearchStub:
    def __init__(self, results: list[SearchResult], image_results: list[SearchResult] | None = None) -> None:
        self.results = results
        self.image_results = image_results if image_results is not None else list(results)
        self.queries: list[str] = []
        self.image_queries: list[str] = []

    async def search(  # type: ignore[no-untyped-def]
        self,
        topic: str,
        skill: str,
        *,
        query: str | None = None,
        limit: int = 5,
        source_policy: str = 'strict_media',
    ) -> list[SearchResult]:
        _ = topic, skill, limit, source_policy
        if query:
            self.queries.append(query)
        return list(self.results)

    async def search_images(  # type: ignore[no-untyped-def]
        self,
        topic: str,
        skill: str,
        *,
        query: str | None = None,
        limit: int = 5,
        source_policy: str = 'strict_media',
    ) -> list[SearchResult]:
        _ = topic, skill, limit, source_policy
        if query:
            self.image_queries.append(query)
        return list(self.image_results)


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(
        user_id=1,
        name='Architecture through Cities',
        description='Study buildings through visual comparison and sketching.',
        goal='Develop spatial and stylistic judgment through observation.',
    )
    skill = SkillNode(
        topic_id=1,
        name='Gothic vs Modern Facade Reading',
        description='Compare building facades with attention to form and material.',
        difficulty=2,
        mastery_estimate=0.0,
    )
    return topic, skill


def _lesson_content() -> dict[str, object]:
    return {
        'title': 'Compare Gothic and Modern Facades',
        'summary': 'Use close visual reading to distinguish structural language.',
        'sections': [{'heading': 'Observe line, mass, and opening rhythm', 'content': 'Track what changes across styles.'}],
        'exemplar_focus': ['Chart one Gothic facade and one modern facade side by side.'],
        'comparison_prompts': ['Compare facade rhythm and material expression.'],
    }


def _photography_topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(
        user_id=1,
        name='Photography with Intention',
        description='Use light, timing, and editing choices to build visual voice.',
        goal='Develop practical photographic judgment through examples and critique.',
    )
    skill = SkillNode(
        topic_id=1,
        name='Photograph with Intention: Light, Timing, and Editing',
        description='Learn how light timing and edit decisions shape meaning.',
        difficulty=2,
        mastery_estimate=0.0,
    )
    return topic, skill


def _photography_lesson_content() -> dict[str, object]:
    return {
        'title': 'Photograph with Intention: Light, Timing, and Editing',
        'summary': 'Compare lighting conditions and timing choices across real photographs.',
        'sections': [{'heading': 'Observe light direction and timing', 'content': 'Notice how shadows and highlights reshape mood.'}],
        'exemplar_focus': ['Study two photographs with different light timing and edit treatment.'],
        'comparison_prompts': ['Compare how timing and light alter emotional tone in photography.'],
    }


def _general_topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(
        user_id=1,
        name='Probability Foundations',
        description='Build intuition for uncertainty and statistical reasoning.',
        goal='Understand probabilistic thinking for better decisions.',
    )
    skill = SkillNode(
        topic_id=1,
        name='Bayes Rule and Conditional Probability',
        description='Interpret conditional evidence and update beliefs.',
        difficulty=2,
        mastery_estimate=0.0,
    )
    return topic, skill


def _general_lesson_content() -> dict[str, object]:
    return {
        'title': 'Bayes Rule and Conditional Probability',
        'summary': 'Learn how conditional evidence updates probabilities in practical scenarios.',
        'sections': [{'heading': 'Conditional evidence', 'content': 'Track how prior and likelihood combine.'}],
    }


def test_lesson_image_agent_marks_visual_support_as_needed_for_visual_topics() -> None:
    topic, skill = _topic_and_skill()
    search_stub = _SearchStub(results=[])
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    decision = agent.assess_visual_support(
        topic=topic,
        skill_node=skill,
        lesson_content=_lesson_content(),
        kind='lesson',
        study_mode='standard',
    )

    assert decision['visual_support_needed'] is True
    assert decision['visual_priority'] in {'medium', 'high'}


def test_lesson_image_agent_selects_renderable_images_when_strong_matches_exist() -> None:
    topic, skill = _topic_and_skill()
    search_stub = _SearchStub(
        results=[],
        image_results=[
            SearchResult(
                title='Facade comparison reference',
                url='https://images.metmuseum.org/CRDImages/ad/original/DP-1234-001.jpg',
                kind='external_image',
                summary='High-quality architectural facade reference image.',
                source_domain='images.metmuseum.org',
                relevance_score=0.8,
            )
        ],
    )
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_images(
            topic=topic,
            skill_node=skill,
            lesson_content=_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(selection.media_items) >= 1
    assert all(item['media_type'] == 'image' for item in selection.media_items)
    assert all(item.get('preview_url') for item in selection.media_items)
    assert selection.diagnostics['selected_count'] >= 1


def test_lesson_image_agent_rejects_noisy_or_non_renderable_candidates_with_diagnostics() -> None:
    topic, skill = _topic_and_skill()
    search_stub = _SearchStub(
        results=[
            SearchResult(
                title='Stock image page',
                url='https://www.shutterstock.com/image-photo/city-architecture',
                kind='external_image',
                summary='Generic stock image listing.',
                source_domain='shutterstock.com',
                relevance_score=0.9,
            ),
            SearchResult(
                title='Architecture article',
                url='https://www.britannica.com/art/architecture',
                kind='external_article',
                summary='General architecture overview article.',
                source_domain='britannica.com',
                relevance_score=0.7,
            ),
        ]
    )
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_images(
            topic=topic,
            skill_node=skill,
            lesson_content=_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert selection.media_items == []
    assert selection.diagnostics['selected_count'] == 0
    assert selection.diagnostics['rejections']['blocked_domain'] >= 1
    assert selection.diagnostics['rejections']['non_renderable'] >= 1


def test_lesson_image_agent_rejects_wikimedia_sources_from_selection() -> None:
    topic, skill = _topic_and_skill()
    search_stub = _SearchStub(
        results=[],
        image_results=[
            SearchResult(
                title='Chapter-1.jpg',
                url='https://commons.wikimedia.org/wiki/File:Chapter-1.jpg',
                kind='external_image',
                summary='Wikimedia Commons image asset',
                source_domain='commons.wikimedia.org',
                relevance_score=0.9,
            )
        ],
    )
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_images(
            topic=topic,
            skill_node=skill,
            lesson_content=_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert selection.media_items == []
    assert selection.diagnostics['selected_count'] == 0
    assert selection.diagnostics['rejections']['deemphasized_domain'] >= 1


def test_filter_existing_media_items_drops_generic_existing_images_and_keeps_contextual_ones() -> None:
    topic, skill = _topic_and_skill()
    search_stub = _SearchStub(results=[])
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    media_items = [
        {
            'title': 'Chapter-1.jpg',
            'url': 'https://commons.wikimedia.org/wiki/File:Chapter-1.jpg',
            'media_type': 'image',
            'source_domain': 'commons.wikimedia.org',
            'relevance_reason': 'Wikimedia Commons image asset',
        },
        {
            'title': 'Milan Cathedral Facade',
            'url': 'https://images.metmuseum.org/CRDImages/ad/original/DP-1234-001.jpg',
            'media_type': 'image',
            'source_domain': 'images.metmuseum.org',
            'relevance_reason': 'Facade study for Gothic vs modern comparison in architecture.',
        },
    ]

    kept, diagnostics = agent.filter_existing_media_items(
        topic=topic,
        skill_node=skill,
        lesson_content=_lesson_content(),
        media_items=media_items,
    )

    assert len(kept) == 1
    assert kept[0]['title'] == 'Milan Cathedral Facade'
    assert diagnostics['dropped_generic_filename'] == 1
    assert diagnostics['dropped_insufficient_context_match'] == 0


def test_lesson_image_agent_rejects_opaque_filename_that_only_matches_keyword_substrings() -> None:
    topic, skill = _photography_topic_and_skill()
    search_stub = _SearchStub(
        results=[],
        image_results=[
            SearchResult(
                title='Chapter-1.jpg',
                url='https://visuals.example.edu/assets/Chapter-1.jpg',
                kind='external_image',
                summary='Generic filename with no real photography context.',
                source_domain='visuals.example.edu',
                relevance_score=0.9,
            )
        ],
    )
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_images(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert selection.media_items == []
    assert selection.diagnostics['selected_count'] == 0
    assert (
        selection.diagnostics['rejections']['generic_filename']
        + selection.diagnostics['rejections']['insufficient_context_match']
        + selection.diagnostics['rejections']['mode_mismatch']
    ) >= 1


def test_lesson_image_agent_builds_mode_specific_queries_for_photography_topics() -> None:
    topic, skill = _photography_topic_and_skill()
    search_stub = _SearchStub(results=[])
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    decision = agent.assess_visual_support(
        topic=topic,
        skill_node=skill,
        lesson_content=_photography_lesson_content(),
        kind='lesson',
        study_mode='standard',
    )
    queries = agent._build_image_queries(  # noqa: SLF001
        topic=topic,
        skill_node=skill,
        lesson_content=_photography_lesson_content(),
        visual_priority=decision['visual_priority'],
        visual_mode=decision['visual_mode'],
    )

    joined = ' '.join(queries).lower()
    assert decision['visual_mode'] == 'photography'
    assert 'photography' in joined or 'camera' in joined
    assert 'architecture design reference' not in joined


def test_lesson_image_agent_enables_contextual_visual_support_for_general_topics() -> None:
    topic, skill = _general_topic_and_skill()
    search_stub = _SearchStub(results=[])
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    decision = agent.assess_visual_support(
        topic=topic,
        skill_node=skill,
        lesson_content=_general_lesson_content(),
        kind='lesson',
        study_mode='standard',
    )

    assert decision['visual_support_needed'] is True
    assert decision['visual_mode'] == 'general'
    assert decision['visual_priority'] in {'low', 'medium'}


def test_lesson_image_agent_builds_contextual_queries_for_general_topics() -> None:
    topic, skill = _general_topic_and_skill()
    search_stub = _SearchStub(results=[])
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    decision = agent.assess_visual_support(
        topic=topic,
        skill_node=skill,
        lesson_content=_general_lesson_content(),
        kind='lesson',
        study_mode='standard',
    )
    queries = agent._build_image_queries(  # noqa: SLF001
        topic=topic,
        skill_node=skill,
        lesson_content=_general_lesson_content(),
        visual_priority=decision['visual_priority'],
        visual_mode=decision['visual_mode'],
    )

    joined = ' '.join(queries).lower()
    assert decision['visual_mode'] == 'general'
    assert any(token in joined for token in ('diagram', 'map', 'timeline', 'artifact'))


def test_lesson_image_agent_allows_photography_example_with_mode_tokens_even_when_keyword_overlap_is_light() -> None:
    topic, skill = _photography_topic_and_skill()
    search_stub = _SearchStub(
        results=[],
        image_results=[
            SearchResult(
                title='New York at Night Long Exposure',
                url='https://images.nationalgeographic.com/photo/new-york-night-long-exposure.jpg',
                kind='external_image',
                summary='City skyline long exposure photography image.',
                source_domain='images.nationalgeographic.com',
                relevance_score=0.8,
            )
        ],
    )
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_images(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(selection.media_items) >= 1
    assert selection.media_items[0]['media_type'] == 'image'


def test_lesson_image_agent_can_select_high_relevance_image_from_non_allowlisted_domain() -> None:
    topic, skill = _photography_topic_and_skill()
    search_stub = _SearchStub(
        results=[],
        image_results=[
            SearchResult(
                title='Street photography timing and light study',
                url='https://images.example.org/reference/street-light-timing-study.jpg',
                kind='external_image',
                summary='Photography exemplar focused on timing, light, and composition.',
                source_domain='images.example.org',
                relevance_score=0.86,
            )
        ],
    )
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_images(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(selection.media_items) == 1
    assert selection.media_items[0]['url'].endswith('.jpg')
    assert selection.diagnostics['selected_count'] == 1
