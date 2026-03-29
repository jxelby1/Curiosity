from __future__ import annotations

from pathlib import Path


def test_readme_exists() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / 'README.md').exists()
