from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'


def test_skill_workspace_shows_individual_exercise_completion_controls() -> None:
    content = SKILL_PAGE.read_text()
    assert 'Exercise Progress' in content
    assert 'Mark complete' in content
    assert 'accept="image/*,.pdf"' in content
    assert 'Mark exercises complete' not in content

