from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHAT_COMPONENT = ROOT / 'frontend' / 'components' / 'chat-message.tsx'
MARKDOWN_COMPONENT = ROOT / 'frontend' / 'components' / 'markdown-content.tsx'


def test_chat_assistant_message_uses_shared_markdown_renderer() -> None:
    content = CHAT_COMPONENT.read_text(encoding='utf-8')
    assert "import { MarkdownContent } from '@/components/markdown-content';" in content
    assert '<MarkdownContent' in content
    assert 'parseBlocks(' not in content


def test_markdown_renderer_supports_ordered_list_variants_and_continuation() -> None:
    content = MARKDOWN_COMPONENT.read_text(encoding='utf-8')
    assert "line.match(/^\\s*\\d+[.)]\\s+(.+)$/)" in content
    assert 'continuesOrdered' in content
