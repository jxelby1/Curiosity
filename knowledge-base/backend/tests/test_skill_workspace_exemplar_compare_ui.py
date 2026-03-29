from __future__ import annotations

from pathlib import Path


def test_skill_workspace_examples_tab_supports_exemplar_and_compare_modes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Study Mode' in content
    assert 'Exemplar-first' in content
    assert 'Compare mode' in content
    assert 'Generate exemplar study' in content
    assert 'Generate comparison study' in content
    assert 'handleGenerateExamplesByMode' in content
    assert 'Custom study modes also save a notebook entry' in content
