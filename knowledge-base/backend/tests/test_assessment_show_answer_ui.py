from __future__ import annotations

from pathlib import Path


def test_assessment_ui_includes_show_answer_and_practice_mode_copy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Show answers' in content
    assert 'Practice mode: mastery credit disabled for this assessment.' in content
    assert 'Generate a new assessment for mastery credit.' in content
