from __future__ import annotations

from pathlib import Path


def test_legacy_search_provider_removed_from_backend_media_pipeline() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    backend_app = repo_root / 'backend' / 'app'
    combined = '\n'.join(path.read_text(encoding='utf-8') for path in backend_app.rglob('*.py'))
    lowered = combined.lower()

    banned_provider = 'se' + 'rper'
    banned_host = 'google.' + 'se' + 'rper' + '.dev'
    assert banned_provider not in lowered
    assert banned_host not in lowered
