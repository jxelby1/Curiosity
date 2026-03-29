from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NOTES_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'notes' / 'page.tsx'


def test_notes_workspace_exposes_project_journal_view() -> None:
    content = NOTES_PAGE.read_text()
    assert 'Project journal' in content
    assert 'Topic project book' in content
    assert 'persistent learning memory' in content
    assert 'Reflection cue' in content
    assert 'direct evidence' in content
