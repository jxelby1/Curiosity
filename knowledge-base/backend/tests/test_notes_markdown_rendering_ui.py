from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MARKDOWN_COMPONENT = ROOT / 'frontend' / 'components' / 'markdown-content.tsx'
NOTES_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'notes' / 'page.tsx'


def test_markdown_component_supports_bold_inline_rendering() -> None:
    content = MARKDOWN_COMPONENT.read_text(encoding='utf-8')
    assert 'export function markdownToHtml' in content
    assert 'export function markdownToPlainText' in content
    assert ".replace(/\\*\\*([^*\\n]+?)\\*\\*/g, '<strong>$1</strong>')" in content
    assert ".replace(/__([^_\\n]+?)__/g, '<strong>$1</strong>')" in content
    assert ".replace(/\\\\([*_`~-])/g, '$1')" in content
    assert 'dangerouslySetInnerHTML' in content


def test_notes_read_mode_uses_markdown_renderer_component() -> None:
    content = NOTES_PAGE.read_text(encoding='utf-8')
    assert "from '@/components/markdown-content';" in content
    assert 'MarkdownContent' in content
    assert '<MarkdownContent markdown={selectedNote.body} />' in content
    assert '{markdownToPlainText(note.body)}' in content
    assert 'selectedNote && !isEditingNote' in content
