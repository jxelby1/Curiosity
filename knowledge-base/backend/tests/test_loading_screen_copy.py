from __future__ import annotations

from pathlib import Path
import re


def test_topic_initializing_copy_avoids_internal_wording() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'initializing' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')
    literals = [left or right for left, right in re.findall(r"'([^']*)'|\"([^\"]*)\"", content)]
    user_facing_literals = [item.lower() for item in literals if ' ' in item]

    banned_terms = ['queue', 'job', 'worker', 'pipeline', 'preload', 'orchestration', 'backend']
    for term in banned_terms:
        assert all(term not in item for item in user_facing_literals)


def test_topic_initializing_copy_includes_user_facing_steps() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'initializing' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Creating your learning path' in content
    assert 'Preparing your first lesson' in content
    assert 'Getting examples ready' in content
