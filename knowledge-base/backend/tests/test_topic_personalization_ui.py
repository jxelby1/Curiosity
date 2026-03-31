from __future__ import annotations

from pathlib import Path


def test_topic_creation_ui_exposes_course_personalization_controls() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'Studio defaults' in content
    assert 'Advanced setup' in content
    assert 'Refine setup' in content
    assert 'Most studies can begin well from here.' in content
    assert 'Course depth' in content
    assert 'Starting skill level' in content
    assert 'Technical depth' in content
    assert 'Assessment methods' in content
    assert 'Select all' in content
    assert 'Default: a balanced set of recall and explanation checks.' in content
