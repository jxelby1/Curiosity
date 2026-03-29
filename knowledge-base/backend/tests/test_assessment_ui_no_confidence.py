from __future__ import annotations

from pathlib import Path


def test_assessment_ui_has_no_confidence_controls() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'confidence_score' not in content
    assert 'Confidence' not in content
    assert 'type="range"' not in content
