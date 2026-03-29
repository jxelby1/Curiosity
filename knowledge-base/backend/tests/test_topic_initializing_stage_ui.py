from __future__ import annotations

from pathlib import Path


def test_initializing_page_uses_stage_driven_progress_and_copy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'initializing' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'STAGE_PROGRESS_BOUNDS' in content
    assert 'STAGE_HINTS' in content
    assert 'stage_index' in content and 'stage_total' in content
    assert 'setDisplayProgress' in content
    assert 'Step {Math.max(1, status?.stage_index || 1)} of {Math.max(1, status?.stage_total || 8)}' in content


def test_initializing_page_routes_to_topic_overview_once_ready_for_entry() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'initializing' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'if (next.ready_for_entry)' in content
    assert 'router.replace(`/topics/${topicId}`);' in content
    assert 'router.replace(`/topics/${topicId}/skills/${next.first_ready_skill_id}`);' not in content
