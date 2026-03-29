from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.resource_agent import ResourceAgent
from app.db.models import LearningResource, ResourceType, SkillNode, Topic, User


class _LLMStub:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        raise AssertionError('LLM should not be called for supporting media attachment tests')


class _RetrievalStub:
    async def retrieve_chunks(self, db, *, topic_id, query, top_k):  # type: ignore[no-untyped-def]
        _ = db, topic_id, query, top_k
        return []


class _SearchStub:
    async def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return []


class _AttachAgent(ResourceAgent):
    def __init__(self, media_payload: list[dict[str, str]]) -> None:
        super().__init__(
            llm_service=_LLMStub(),  # type: ignore[arg-type]
            search_service=_SearchStub(),  # type: ignore[arg-type]
            retrieval_service=_RetrievalStub(),  # type: ignore[arg-type]
        )
        self.media_payload = media_payload
        self.requested_limits: list[int] = []

    async def fetch_strict_supporting_media(  # type: ignore[override]
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        deep_lesson: dict,
        kind: str = 'lesson',
        study_mode: str = 'standard',
        limit: int = 2,
        exclude_media_keys: set[str] | None = None,
    ) -> list[dict[str, str]]:
        _ = topic, skill_node, deep_lesson, kind, study_mode, exclude_media_keys
        self.requested_limits.append(limit)
        return list(self.media_payload[:limit])


class _FakeDB:
    def __init__(self) -> None:
        self.committed = False
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, value: object) -> None:
        _ = value


def _real_session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    LearningResource.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(
        user_id=1,
        name='Photography Composition Practice',
        description='Learn visual composition through examples',
        goal='Build taste through observation and making',
    )
    skill = SkillNode(
        topic_id=1,
        name='Rule of Thirds in Street Photography',
        description='Observe and apply composition in real scenes',
        difficulty=2,
        mastery_estimate=0.0,
    )
    return topic, skill


def test_lesson_media_attachment_adds_renderable_images_to_payload() -> None:
    topic, skill = _topic_and_skill()
    agent = _AttachAgent(
        [
            {
                'title': 'Street photography composition example',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/2/24/Street_photo_composition.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Shows compositional balance with clear framing cues.',
            }
        ]
    )
    structured = {
        'title': 'Composition in Street Photography',
        'summary': 'Observe structure before style.',
        'sections': [{'heading': 'Observe framing', 'content': 'Track subject placement and tension.'}],
    }

    updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=skill,
            structured_content=structured,
            kind='lesson',
            study_mode='standard',
        )
    )

    media = updated.get('supporting_media')
    assert isinstance(media, list)
    assert len(media) == 1
    assert media[0]['media_type'] == 'image'
    assert media[0]['preview_url'] == 'https://upload.wikimedia.org/wikipedia/commons/2/24/Street_photo_composition.jpg'


def test_lesson_media_attachment_rejects_non_renderable_image_links() -> None:
    topic, skill = _topic_and_skill()
    agent = _AttachAgent(
        [
            {
                'title': 'Article mentioning composition',
                'url': 'https://www.britannica.com/art/photography',
                'media_type': 'image',
                'source_domain': 'britannica.com',
                'relevance_reason': 'Contains references to composition history.',
            }
        ]
    )
    structured = {
        'title': 'Composition foundations',
        'summary': 'Use visual anchors to guide attention.',
        'sections': [{'heading': 'Frame', 'content': 'Subject placement matters.'}],
    }

    updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=skill,
            structured_content=structured,
            kind='lesson',
            study_mode='standard',
        )
    )

    assert updated.get('supporting_media') in (None, [])


def test_lesson_and_deep_lesson_media_paths_keep_expected_limits() -> None:
    topic, skill = _topic_and_skill()
    agent = _AttachAgent(
        [
            {
                'title': 'Example one',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/1/11/example_one.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Primary example.',
            },
            {
                'title': 'Example two',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/2/22/example_two.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Secondary example.',
            },
            {
                'title': 'Example three',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/3/33/example_three.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Comparative example.',
            },
        ]
    )

    lesson_updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=skill,
            structured_content={'title': 'Lesson', 'summary': 'x', 'sections': [{'heading': 'A', 'content': 'B'}]},
            kind='lesson',
            study_mode='standard',
        )
    )
    deep_lesson_updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=skill,
            structured_content={'title': 'Deep', 'summary': 'x', 'sections': [{'heading': 'A', 'content': 'B'}]},
            kind='deep_lesson',
            study_mode='standard',
        )
    )

    lesson_media = lesson_updated.get('supporting_media') or []
    deep_lesson_media = deep_lesson_updated.get('supporting_media') or []

    assert len(lesson_media) <= 2
    assert len(deep_lesson_media) <= 3
    assert agent.requested_limits == [2, 3]


def test_generate_material_backfills_stored_lesson_media_when_missing() -> None:
    topic, skill = _topic_and_skill()
    base_agent = _AttachAgent(
        [
            {
                'title': 'Street photography composition example',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/2/24/Street_photo_composition.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Shows compositional balance with clear framing cues.',
            }
        ]
    )

    class _StoredResource:
        def __init__(self) -> None:
            self.version = 2
            self.content_json = {
                'title': 'Composition in Street Photography',
                'summary': 'Observe structure before style.',
                'sections': [{'heading': 'Observe framing', 'content': 'Track subject placement and tension.'}],
            }
            self.content = ''
            self.summary = ''

    stored = _StoredResource()

    def _get_active_generated_resource(db, *, user_id, skill_node_id, resource_type):  # type: ignore[no-untyped-def]
        _ = db, user_id, skill_node_id, resource_type
        return stored

    base_agent._get_active_generated_resource = _get_active_generated_resource  # type: ignore[method-assign]
    db = _FakeDB()

    resource, structured, source = asyncio.run(
        base_agent.generate_material(
            db,  # type: ignore[arg-type]
            user_id=1,
            topic=topic,
            skill_node=skill,
            kind='lesson',
            regenerate=False,
            study_mode='standard',
        )
    )

    assert source == 'stored'
    assert resource is stored
    assert structured is not None
    assert isinstance(structured.get('supporting_media'), list)
    assert len(structured['supporting_media']) == 1
    assert structured['supporting_media'][0]['media_type'] == 'image'
    assert db.committed is True


def test_lesson_media_attachment_revalidates_existing_generic_images_before_returning() -> None:
    topic, skill = _topic_and_skill()
    agent = _AttachAgent(
        [
            {
                'title': 'Notre-Dame facade detail',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/7/70/Notre_Dame_facade_detail.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Directly supports facade observation and comparison practice.',
            }
        ]
    )
    structured = {
        'title': 'Read a Gothic facade',
        'summary': 'Learn to observe vertical rhythm and ornament.',
        'sections': [{'heading': 'Observe', 'content': 'Track aperture rhythm and structural emphasis.'}],
        'supporting_media': [
            {
                'title': 'Chapter-1.jpg',
                'url': 'https://commons.wikimedia.org/wiki/File:Chapter-1.jpg',
                'media_type': 'image',
                'source_domain': 'commons.wikimedia.org',
                'relevance_reason': 'Wikimedia Commons image asset',
            }
        ],
    }

    updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=skill,
            structured_content=structured,
            kind='lesson',
            study_mode='standard',
        )
    )

    media = updated.get('supporting_media') or []
    assert len(media) == 1
    assert media[0]['title'] == 'Notre-Dame facade detail'
    assert media[0]['media_type'] == 'image'


def test_lesson_media_attachment_removes_unrelated_existing_image_when_no_replacement_found() -> None:
    topic, skill = _topic_and_skill()
    agent = _AttachAgent([])
    structured = {
        'title': 'Read a Gothic facade',
        'summary': 'Learn to observe vertical rhythm and ornament.',
        'sections': [{'heading': 'Observe', 'content': 'Track aperture rhythm and structural emphasis.'}],
        'supporting_media': [
            {
                'title': 'Chapter-1.jpg',
                'url': 'https://commons.wikimedia.org/wiki/File:Chapter-1.jpg',
                'media_type': 'image',
                'source_domain': 'commons.wikimedia.org',
                'relevance_reason': 'Wikimedia Commons image asset',
            }
        ],
    }

    updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=skill,
            structured_content=structured,
            kind='lesson',
            study_mode='standard',
        )
    )

    assert updated.get('supporting_media') == []
    assert updated.get('visual_support_selected_count') == 0


def test_lesson_media_attachment_blocks_cross_node_duplicate_youtube_media() -> None:
    db = _real_session()
    user = User(email='media-unique@test.local', hashed_password='x', display_name='Media User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(
        user_id=user.id,
        name='Photography Composition Practice',
        description='Learn visual composition through examples',
        goal='Build taste through observation and making',
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    current_skill = SkillNode(
        topic_id=topic.id,
        name='Rule of Thirds in Street Photography',
        description='Observe and apply composition in real scenes',
        difficulty=2,
        mastery_estimate=0.0,
    )
    other_skill = SkillNode(
        topic_id=topic.id,
        name='Street Photography Timing',
        description='Read movement and timing in urban scenes',
        difficulty=2,
        mastery_estimate=0.0,
    )
    db.add(current_skill)
    db.add(other_skill)
    db.commit()
    db.refresh(current_skill)
    db.refresh(other_skill)

    existing_other_resource = LearningResource(
        user_id=user.id,
        topic_id=topic.id,
        skill_node_id=other_skill.id,
        resource_type=ResourceType.generated_lesson,
        title='Other lesson',
        content_json={
            'title': 'Other lesson',
            'summary': 'x',
            'supporting_media': [
                {
                    'title': 'Street photo timing video',
                    'url': 'https://youtu.be/abc123',
                    'media_type': 'video',
                    'source_domain': 'youtube.com',
                    'relevance_reason': 'Timing reference.',
                }
            ],
        },
        content='',
        summary='',
    )
    db.add(existing_other_resource)
    db.commit()

    agent = _AttachAgent(
        [
            {
                'title': 'Street photo timing video duplicate',
                'url': 'https://www.youtube.com/watch?v=abc123',
                'media_type': 'video',
                'source_domain': 'youtube.com',
                'relevance_reason': 'Duplicate timing reference.',
            },
            {
                'title': 'Street composition still',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/5/51/Street_composition_still.jpg',
                'media_type': 'image',
                'source_domain': 'upload.wikimedia.org',
                'relevance_reason': 'Distinct composition reference.',
            },
        ]
    )
    structured = {
        'title': 'Composition in Street Photography',
        'summary': 'Observe structure before style.',
        'sections': [{'heading': 'Observe framing', 'content': 'Track subject placement and tension.'}],
    }

    updated = asyncio.run(
        agent._attach_supporting_media_if_relevant(  # noqa: SLF001
            topic=topic,
            skill_node=current_skill,
            structured_content=structured,
            kind='lesson',
            study_mode='standard',
            db=db,
            user_id=user.id,
        )
    )

    media = updated.get('supporting_media') or []
    urls = {item['url'] for item in media}
    assert 'https://www.youtube.com/watch?v=abc123' not in urls
    assert 'https://upload.wikimedia.org/wikipedia/commons/5/51/Street_composition_still.jpg' in urls
