from __future__ import annotations

from pathlib import Path


def test_backend_and_frontend_default_to_single_node_branch_creation() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    backend_schema = (repo_root / 'backend' / 'app' / 'schemas' / 'api.py').read_text(encoding='utf-8')
    backend_routes = (repo_root / 'backend' / 'app' / 'api' / 'routes.py').read_text(encoding='utf-8')
    frontend_api = (repo_root / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')

    assert "branch_size: int = Field(default=1, ge=1, le=5)" in backend_schema
    assert "branch_size: int = Query(default=1, ge=1, le=5)" in backend_routes
    assert "const resolvedBranchSize = input.branch_size ?? 1;" in frontend_api
    assert "const query = `?branch_size=${input.branch_size ?? 1}`;" in frontend_api
