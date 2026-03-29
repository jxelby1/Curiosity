from __future__ import annotations

from pathlib import Path


def test_initializing_page_handles_failed_status_and_retry() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'initializing' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert "next.status === 'failed'" in content
    assert 'Initialization did not complete successfully.' in content
    assert 'Try again' in content
    assert 'setPollNonce' in content
