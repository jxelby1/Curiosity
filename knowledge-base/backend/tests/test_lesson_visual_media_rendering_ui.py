from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEARNING_CONTENT = ROOT / 'frontend' / 'components' / 'learning-content.tsx'
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'


def test_learning_content_stands_down_inline_supporting_media_ui() -> None:
    content = LEARNING_CONTENT.read_text(encoding='utf-8')

    assert 'function SupportingMediaSection' not in content
    assert 'data-testid="supporting-media-image"' not in content
    assert 'Visual References' not in content
    assert 'Supporting Video' not in content


def test_deep_lesson_page_removes_fallback_media_panel() -> None:
    content = SKILL_PAGE.read_text(encoding='utf-8')

    assert 'deepLessonHasInlineMedia' not in content
    assert 'Supporting media (strict relevance)' not in content
    assert 'No clearly relevant supporting media found for this node yet.' not in content
    assert 'toVideoEmbedSource(' not in content
    assert 'renderableImageUrl(' not in content
