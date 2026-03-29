from __future__ import annotations

from pathlib import Path


def test_workspace_preloads_lesson_when_opened_via_tab_query() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert "if (activeTab === 'lesson')" in content
    assert "void ensureResource('lesson')" in content
    assert "if (activeTab === 'examples')" in content
    assert "if (activeTab === 'quiz')" in content
