from __future__ import annotations

from pathlib import Path


def test_skill_tree_response_includes_optional_branch_edges_in_prerequisites() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    routes_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    content = routes_path.read_text(encoding='utf-8')

    assert "if edge.edge_type in {'prerequisite', 'optional_branch'}" in content
