from __future__ import annotations

from pathlib import Path


def test_auth_gate_treats_root_as_public_route() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    auth_gate_path = repo_root / 'frontend' / 'components' / 'auth-provider.tsx'
    content = auth_gate_path.read_text(encoding='utf-8')

    assert "const PUBLIC_EXACT_PATHS = new Set(['/']);" in content
    assert "const PUBLIC_PREFIX_PATHS = ['/login', '/signup', '/forgot-password', '/reset-password'];" in content
