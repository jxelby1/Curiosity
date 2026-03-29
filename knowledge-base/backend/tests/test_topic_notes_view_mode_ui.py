from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NOTES_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'notes' / 'page.tsx'


def test_existing_notes_default_to_read_mode_with_explicit_edit_button() -> None:
    content = NOTES_PAGE.read_text(encoding='utf-8')
    assert 'selectedNote && !isEditingNote' in content
    assert 'Edit note' in content
    assert 'beginEditingSelectedNote' in content
    assert '<MarkdownContent markdown={selectedNote.body} />' in content
    assert '{markdownToPlainText(note.body)}' in content


def test_note_editor_has_cancel_and_returns_from_edit_mode() -> None:
    content = NOTES_PAGE.read_text(encoding='utf-8')
    assert 'cancelEditingSelectedNote' in content
    assert 'setIsEditingNote(false);' in content
    assert 'setIsEditingNote(true);' in content
