from __future__ import annotations

import asyncio
import json

from app.agents.lesson_image_agent import LessonImageAgent
from app.core.config import get_settings
from app.db.models import SkillNode, Topic
from app.services.search import ExternalSearchService, SearchResult


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponsesClient:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return _FakeResponse(self.output_text)


class _FakeOpenAIClient:
    def __init__(self, output_text: str) -> None:
        self.responses = _FakeResponsesClient(output_text)


class _LessonMediaSearchStub:
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
        return {
            'image_query': lesson_title,
            'video_query': lesson_title,
            'agent_decision': 'Selected one image + one video.',
            'image_candidates': [
                {
                    'title': 'Street photography lighting study',
                    'url': 'https://images.example.org/photo/street-lighting-study.jpg',
                    'preview_url': 'https://images.example.org/photo/street-lighting-study.jpg',
                    'source_domain': 'images.example.org',
                    'relevance_score': 0.82,
                    'relevance_reason': 'Shows timing and light contrast relevant to the lesson.',
                }
            ],
            'video_candidates': [
                {
                    'title': 'Photograph with Intention: Light, Timing, and Editing walkthrough',
                    'url': 'https://www.youtube.com/watch?v=abc123',
                    'source_domain': 'youtube.com',
                    'relevance_score': 0.79,
                    'relevance_reason': 'Directly aligned walkthrough.',
                }
            ],
        }


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(
        user_id=1,
        name='Photography with Intention',
        description='Use light timing and editing choices to build visual voice.',
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


def _lesson_content() -> dict[str, object]:
    return {
        'title': 'Photograph with Intention: Light, Timing, and Editing',
        'summary': 'Compare lighting conditions and timing choices across real photographs.',
        'sections': [{'heading': 'Observe light direction and timing', 'content': 'Notice how shadows and highlights reshape mood.'}],
    }


def test_openai_lesson_media_search_uses_web_search_preview_tooling() -> None:
    payload = {
        'image_query': 'Photograph with Intention: Light, Timing, and Editing',
        'video_query': 'Photograph with Intention: Light, Timing, and Editing',
        'image_candidates': [
            {
                'title': 'Street photo lighting study',
                'source_url': 'https://images.example.org/photo/street-lighting-study.jpg',
                'media_url': 'https://images.example.org/photo/street-lighting-study.jpg',
                'source_domain': 'images.example.org',
                'relevance_score': 0.81,
                'relevance_reason': 'Lighting and timing exemplar.',
            }
        ],
        'video_candidates': [
            {
                'title': 'Photograph with Intention walkthrough',
                'source_url': 'https://www.youtube.com/watch?v=abc123',
                'media_url': 'https://www.youtube.com/watch?v=abc123',
                'source_domain': 'youtube.com',
                'relevance_score': 0.77,
                'relevance_reason': 'Node-aligned tutorial.',
            }
        ],
        'agent_decision': 'Strong image and video selected.',
    }
    service = ExternalSearchService()
    fake_client = _FakeOpenAIClient(json.dumps(payload))
    service.client = fake_client  # type: ignore[assignment]

    result = asyncio.run(
        service.search_lesson_media_candidates(
            topic='Photography with Intention',
            skill='Photograph with Intention: Light, Timing, and Editing',
            lesson_title='Photograph with Intention: Light, Timing, and Editing',
            lesson_summary='Compare lighting conditions and timing choices across real photographs.',
            limit_images=4,
            limit_videos=4,
        )
    )

    assert len(fake_client.responses.calls) == 1
    kwargs = fake_client.responses.calls[0]
    assert kwargs.get('tools') == [{'type': 'web_search_preview'}]
    assert len(result['image_candidates']) == 1
    assert len(result['video_candidates']) == 1


def test_lesson_media_agent_returns_image_and_video_for_lesson_when_both_exist() -> None:
    topic, skill = _topic_and_skill()
    agent = LessonImageAgent(search_service=_LessonMediaSearchStub(), settings=get_settings())

    selection = asyncio.run(
        agent.select_supporting_media(
            topic=topic,
            skill_node=skill,
            lesson_content=_lesson_content(),
            kind='lesson',
            study_mode='standard',
            limit=2,
        )
    )

    assert len(selection.media_items) == 2
    assert any(item['media_type'] == 'image' for item in selection.media_items)
    assert any(item['media_type'] == 'video' for item in selection.media_items)


def test_openai_lesson_media_search_falls_back_to_youtube_query_when_no_video_candidates() -> None:
    payload = {
        'image_query': 'Photograph with Intention: Light, Timing, and Editing',
        'video_query': 'Photograph with Intention: Light, Timing, and Editing',
        'image_candidates': [
            {
                'title': 'Street photo lighting study',
                'source_url': 'https://images.example.org/photo/street-lighting-study.jpg',
                'media_url': 'https://images.example.org/photo/street-lighting-study.jpg',
                'source_domain': 'images.example.org',
                'relevance_score': 0.81,
                'relevance_reason': 'Lighting and timing exemplar.',
            }
        ],
        'video_candidates': [],
        'agent_decision': 'No strong video surfaced in first pass.',
    }
    service = ExternalSearchService()
    fake_client = _FakeOpenAIClient(json.dumps(payload))
    service.client = fake_client  # type: ignore[assignment]
    async def fake_openai_web_search(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return [
            SearchResult(
                title='Photograph with Intention camera settings walkthrough',
                url='https://www.youtube.com/watch?v=abc123',
                kind='external_video',
                summary='Lesson-aligned camera settings tutorial.',
                source_domain='youtube.com',
                relevance_score=0.72,
            )
        ]

    service._search_with_openai_web = fake_openai_web_search  # type: ignore[assignment]

    result = asyncio.run(
        service.search_lesson_media_candidates(
            topic='Photography with Intention',
            skill='Photograph with Intention: Light, Timing, and Editing',
            lesson_title='Photograph with Intention: Light, Timing, and Editing',
            lesson_summary='Compare lighting conditions and timing choices across real photographs.',
            limit_images=4,
            limit_videos=4,
        )
    )

    assert len(result['video_candidates']) >= 1
    assert 'youtube.com' in str(result['video_candidates'][0].source_domain)
