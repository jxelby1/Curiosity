from __future__ import annotations

from pathlib import Path


def test_topic_creation_persists_custom_assessment_style_selection() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'setAssessmentStyles' in content
    assert 'assessment_styles: assessmentStyles' in content
    assert 'Customize' in content
    assert 'Reset to defaults' in content
