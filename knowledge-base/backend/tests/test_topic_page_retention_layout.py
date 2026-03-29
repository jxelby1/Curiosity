from __future__ import annotations

from pathlib import Path


def test_topic_page_prioritizes_retention_panels() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Next 3 actions' in content
    assert 'Unlock anticipation' in content
    assert (
        'Today’s plan' in content
        or "This week’s plan" in content
        or 'Today plan' in content
        or 'This week plan' in content
    )


def test_topic_page_no_longer_uses_large_tree_stage_panel() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'TopicTreeStage' not in content
    assert 'Growth Stage' in content
