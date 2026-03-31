from __future__ import annotations

from pathlib import Path


def test_topics_dashboard_has_polished_first_time_state() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'Your core trunk starts here.' in content
    assert 'First study' in content
    assert 'Start your first study' in content
    assert 'Build taste' in content
    assert content.count('Start your first study') >= 1


def test_topics_dashboard_hides_local_dev_tools_upgrade_action_from_main_entry_flow() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / 'frontend' / 'components' / 'topics-dashboard.tsx'
    content = dashboard_path.read_text(encoding='utf-8')

    assert 'upgradeMyAccountToDev' not in content
    assert 'Enable dev tools (local)' not in content
