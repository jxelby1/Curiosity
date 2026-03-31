from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORMATTER = ROOT / 'frontend' / 'lib' / 'display-format.ts'
NOTES_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'notes' / 'page.tsx'
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
TOPIC_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
CHAT_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'chat' / 'page.tsx'


def test_display_formatter_exists_and_handles_enum_style_values() -> None:
    content = FORMATTER.read_text(encoding='utf-8')
    assert 'export function formatDisplayTag' in content
    assert "replace(/[_-]+/g, ' ')" in content
    assert "UPPERCASE_TOKENS" in content


def test_ui_surfaces_use_centralized_display_tag_formatter() -> None:
    notes_content = NOTES_PAGE.read_text(encoding='utf-8')
    skill_content = SKILL_PAGE.read_text(encoding='utf-8')
    topic_content = TOPIC_PAGE.read_text(encoding='utf-8')
    chat_content = CHAT_PAGE.read_text(encoding='utf-8')

    assert "formatDisplayTag(note.note_type)" in notes_content
    assert "formatDisplayTag(note.source_type)" in notes_content
    assert "formatDisplayTag(node.status)" in skill_content
    assert "getBranchPurposeMeta(suggestion.purpose)" in skill_content
    assert "formatDisplayTag(tree.topic.course_depth)" in topic_content
    assert "formatDisplayTag(tree.topic.starting_skill_level)" in topic_content
    assert "Daily Plan" in topic_content
    assert "-Day Streak" in topic_content
    assert "formatDisplayTag(node.progress_state)" in chat_content
