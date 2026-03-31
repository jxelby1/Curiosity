from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEARNING_CONTENT = ROOT / 'frontend' / 'components' / 'learning-content.tsx'
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'


def test_learning_renderers_include_exemplar_compare_response_sections_without_media_cards() -> None:
    content = LEARNING_CONTENT.read_text(encoding='utf-8')

    assert 'exemplar_focus: string[]' in content
    assert 'comparison_prompts: string[]' in content
    assert 'observation_prompts: string[]' in content
    assert 'response_prompts: string[]' in content
    assert 'practice_hooks: string[]' in content
    assert 'supporting_media: SupportingMediaShape[]' in content
    assert 'function SupportingMediaSection' not in content
    assert 'Visual References' not in content
    assert 'Notice This' in content
    assert 'Compare This' in content
    assert 'Try This' in content


def test_skill_workspace_does_not_render_deep_lesson_media_fallback_section() -> None:
    content = SKILL_PAGE.read_text(encoding='utf-8')

    assert 'deepLessonHasInlineMedia' not in content
    assert '{deepLesson && !deepLessonHasInlineMedia && (' not in content
    assert 'Supporting media (strict relevance)' not in content
