from __future__ import annotations

from pathlib import Path


def test_branch_suggestion_routes_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    routes_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    content = routes_path.read_text(encoding='utf-8')

    assert "/skills/{skill_id}/branch-suggestions" in content
    assert "/skills/{skill_id}/branch-suggestions/generate" in content
    assert "/branch-suggestions/{suggestion_id}/accept" in content
    assert "/branch-suggestions/{suggestion_id}/reject" in content
