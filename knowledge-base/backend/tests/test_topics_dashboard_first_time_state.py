from __future__ import annotations

from pathlib import Path


def test_topics_dashboard_has_polished_first_time_state() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'Your learning tree starts here.' in content
    assert 'First steps' in content
    assert 'Create your first topic' in content
    assert 'Build momentum' in content
    assert content.count('Create your first topic') >= 1


def test_topics_dashboard_offers_local_dev_tools_upgrade_action() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'upgradeMyAccountToDev' in content
    assert 'Enable dev tools (local)' in content
