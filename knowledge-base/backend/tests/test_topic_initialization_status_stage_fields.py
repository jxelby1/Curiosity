from __future__ import annotations

from pathlib import Path


def test_topic_init_status_response_includes_stage_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    routes_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    content = routes_path.read_text(encoding='utf-8')

    assert 'stage_key=' in content
    assert 'stage_label=' in content
    assert 'stage_index=' in content
    assert 'stage_total=' in content
    assert "'preloading'" in content and 'Preparing extra modules' in content
