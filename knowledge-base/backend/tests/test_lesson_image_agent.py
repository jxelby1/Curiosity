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
        self.media_queries: list[tuple[str, str]] = []

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

    async def search_lesson_media_candidates(  # type: ignore[no-untyped-def]
        self,
        *,
        topic: str,
        skill: str,
        lesson_title: str,
        lesson_summary: str,
        limit_images: int = 8,
        limit_videos: int = 8,
    ) -> dict[str, object]:
        _ = topic, skill, lesson_summary, limit_images, limit_videos
        self.media_queries.append((lesson_title, lesson_title))
        image_candidates = []
        video_candidates = []
        for item in self.image_results:
            score = item.relevance_score if item.relevance_score > 0 else 0.62
            image_candidates.append(
                {
                    'title': item.title,
                    'url': item.url,
                    'preview_url': item.url if item.url.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')) else '',
                    'source_domain': item.source_domain,
                    'relevance_score': score,
                    'relevance_reason': item.summary,
                }
            )
        for item in self.results:
            if item.kind != 'external_video':
                continue
            score = item.relevance_score if item.relevance_score > 0 else 0.58
            video_candidates.append(
                {
                    'title': item.title,
                    'url': item.url,
                    'source_domain': item.source_domain,
                    'relevance_score': score,
                    'relevance_reason': item.summary,
                }
            )
        return {
            'image_query': lesson_title,
            'video_query': lesson_title,
            'image_candidates': image_candidates,
            'video_candidates': video_candidates,
            'agent_decision': 'Stubbed media candidates.',
        }


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


def test_lesson_image_agent_uses_proxy_preview_for_contextual_article_candidates() -> None:
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

    assert len(selection.media_items) == 1
    assert selection.media_items[0]['source_domain'] == 'britannica.com'
    assert '/api/media-cache/proxy/' in selection.media_items[0].get('preview_url', '')
    assert selection.diagnostics['selected_count'] == 1
    assert selection.diagnostics['rejections']['blocked_domain'] >= 1
    assert selection.diagnostics['rejections']['non_renderable'] == 0


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
    assert diagnostics['dropped_generic_filename'] + diagnostics['dropped_insufficient_context_match'] >= 1


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


def test_lesson_media_agent_uses_lesson_title_for_image_and_video_queries() -> None:
    topic, skill = _photography_topic_and_skill()
    search_stub = _SearchStub(results=[], image_results=[])
    agent = LessonImageAgent(search_service=search_stub, settings=get_settings())

    _ = asyncio.run(
        agent.select_supporting_media(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(search_stub.media_queries) == 1
    image_query, video_query = search_stub.media_queries[0]
    assert image_query == _photography_lesson_content()['title']
    assert video_query == _photography_lesson_content()['title']


def test_lesson_media_agent_accepts_non_direct_preview_urls_via_proxy() -> None:
    class _NonDirectPreviewStub:
        async def search_lesson_media_candidates(  # type: ignore[no-untyped-def]
            self,
            *,
            topic: str,
            skill: str,
            lesson_title: str,
            lesson_summary: str,
            limit_images: int = 8,
            limit_videos: int = 8,
        ) -> dict[str, object]:
            _ = topic, skill, lesson_title, lesson_summary, limit_images, limit_videos
            return {
                'image_query': 'Photograph with Intention: Light, Timing, and Editing',
                'video_query': 'Photograph with Intention: Light, Timing, and Editing',
                'image_candidates': [
                    {
                        'title': 'Camera settings article',
                        'url': 'https://www.photoworkout.com/essential-camera-settings/',
                        'preview_url': 'https://www.photoworkout.com/essential-camera-settings/',
                        'source_domain': 'photoworkout.com',
                        'relevance_score': 0.9,
                        'relevance_reason': 'Looks relevant but preview is not a direct image URL.',
                    }
                ],
                'video_candidates': [],
                'agent_decision': 'No valid direct image returned.',
            }

    topic, skill = _photography_topic_and_skill()
    agent = LessonImageAgent(search_service=_NonDirectPreviewStub(), settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_media(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(selection.media_items) == 1
    assert selection.media_items[0]['media_type'] == 'image'
    assert '/api/media-cache/proxy/' in selection.media_items[0].get('preview_url', '')
    assert selection.diagnostics['rejections']['non_renderable'] == 0


def test_lesson_media_agent_rejects_unplayable_video_candidates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _VideoOnlyStub:
        async def search_lesson_media_candidates(  # type: ignore[no-untyped-def]
            self,
            *,
            topic: str,
            skill: str,
            lesson_title: str,
            lesson_summary: str,
            limit_images: int = 8,
            limit_videos: int = 8,
        ) -> dict[str, object]:
            _ = topic, skill, lesson_title, lesson_summary, limit_images, limit_videos
            return {
                'image_query': 'Photograph with Intention: Light, Timing, and Editing',
                'video_query': 'Photograph with Intention: Light, Timing, and Editing',
                'image_candidates': [],
                'video_candidates': [
                    {
                        'title': 'Photograph with Intention: Light, Timing, and Editing',
                        'url': 'https://www.youtube.com/watch?v=abcdefghijk',
                        'source_domain': 'youtube.com',
                        'relevance_score': 0.92,
                        'relevance_reason': 'Title-aligned walkthrough.',
                    }
                ],
                'agent_decision': 'Single video candidate.',
            }

    topic, skill = _photography_topic_and_skill()
    agent = LessonImageAgent(search_service=_VideoOnlyStub(), settings=get_settings())

    async def _always_unplayable(url: str) -> bool:
        _ = url
        return False

    monkeypatch.setattr(agent, '_is_video_currently_playable', _always_unplayable)

    selection = asyncio.run(
        agent.select_supporting_media(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert selection.media_items == []
    assert selection.diagnostics['rejections']['video_not_playable'] >= 1


def test_lesson_media_agent_rejects_temporarily_blocked_image_source(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _ImageStub:
        async def search_lesson_media_candidates(  # type: ignore[no-untyped-def]
            self,
            *,
            topic: str,
            skill: str,
            lesson_title: str,
            lesson_summary: str,
            limit_images: int = 8,
            limit_videos: int = 8,
        ) -> dict[str, object]:
            _ = topic, skill, lesson_title, lesson_summary, limit_images, limit_videos
            return {
                'image_query': lesson_title,
                'video_query': lesson_title,
                'image_candidates': [
                    {
                        'title': 'Public space photo',
                        'url': 'https://blocked.example.org/path/photo.jpg',
                        'preview_url': 'https://blocked.example.org/path/photo.jpg',
                        'source_domain': 'blocked.example.org',
                        'relevance_score': 0.93,
                        'relevance_reason': 'Strong title alignment.',
                    }
                ],
                'video_candidates': [],
                'agent_decision': 'Single image candidate.',
            }

    topic, skill = _photography_topic_and_skill()
    agent = LessonImageAgent(search_service=_ImageStub(), settings=get_settings())

    def _blocked(url_or_domain: str) -> bool:
        return 'blocked.example.org' in (url_or_domain or '')

    monkeypatch.setattr(agent.media_cache_service, 'is_domain_temporarily_blocked', _blocked)

    selection = asyncio.run(
        agent.select_supporting_media(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert selection.media_items == []
    assert selection.diagnostics['rejections']['source_fetch_blocked'] >= 1


def test_lesson_media_agent_keeps_single_image_when_no_video_exists_for_lesson() -> None:
    class _ImageOnlyStub:
        async def search_lesson_media_candidates(  # type: ignore[no-untyped-def]
            self,
            *,
            topic: str,
            skill: str,
            lesson_title: str,
            lesson_summary: str,
            limit_images: int = 8,
            limit_videos: int = 8,
        ) -> dict[str, object]:
            _ = topic, skill, lesson_title, lesson_summary, limit_images, limit_videos
            return {
                'image_query': 'Photograph with Intention: Light, Timing, and Editing',
                'video_query': 'Photograph with Intention: Light, Timing, and Editing',
                'image_candidates': [
                    {
                        'title': 'Camera settings wheel close-up',
                        'url': 'https://images.example.org/photo/camera-dial.jpg',
                        'preview_url': 'https://images.example.org/photo/camera-dial.jpg',
                        'source_domain': 'images.example.org',
                        'relevance_score': 0.82,
                        'relevance_reason': 'Directly relevant image candidate.',
                    },
                    {
                        'title': 'Exposure triangle diagram',
                        'url': 'https://images.example.org/photo/exposure-triangle.jpg',
                        'preview_url': 'https://images.example.org/photo/exposure-triangle.jpg',
                        'source_domain': 'images.example.org',
                        'relevance_score': 0.8,
                        'relevance_reason': 'Second relevant image candidate.',
                    },
                ],
                'video_candidates': [],
                'agent_decision': 'Image-only results.',
            }

    topic, skill = _photography_topic_and_skill()
    agent = LessonImageAgent(search_service=_ImageOnlyStub(), settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_media(
            topic=topic,
            skill_node=skill,
            lesson_content=_photography_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(selection.media_items) == 1
    assert selection.media_items[0]['media_type'] == 'image'
