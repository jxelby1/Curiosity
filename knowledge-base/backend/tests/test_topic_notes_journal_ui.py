from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NOTES_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'notes' / 'page.tsx'


def test_notes_workspace_exposes_project_journal_view() -> None:
    content = NOTES_PAGE.read_text()
    assert 'Notebook timeline' in content
    assert 'Commonplace timeline' in content
    assert 'commonplace timeline' in content
    assert 'Notebook signals' in content
    assert 'Taste development' in content
    assert 'Reflection cue' in content
    assert 'direct evidence' in content
    assert 'Quick Notebook Templates' in content
    assert 'Notebook Tags' in content
    assert 'What Changed My View' in content
    assert 'Explore next' in content
