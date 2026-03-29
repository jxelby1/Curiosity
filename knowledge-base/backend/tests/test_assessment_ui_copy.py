from __future__ import annotations

from pathlib import Path


def test_mastery_delta_not_visible_in_skill_results_ui() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Mastery delta:' not in content
    assert 'Progress updated.' in content
