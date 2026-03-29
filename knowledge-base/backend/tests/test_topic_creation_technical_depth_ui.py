from __future__ import annotations

from pathlib import Path


def test_topic_creation_includes_technical_depth_setting_and_payload() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_content = (repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx').read_text(encoding='utf-8')
    api_content = (repo_root / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')

    assert 'TECHNICAL_DEPTH_OPTIONS' in dashboard_content
    assert 'const [technicalDepth, setTechnicalDepth]' in dashboard_content
    assert 'technical_depth: technicalDepth' in dashboard_content

    assert 'technical_depth?: TechnicalDepth' in api_content
    assert "technical_depth: input.technical_depth ?? 'intermediate'" in api_content
