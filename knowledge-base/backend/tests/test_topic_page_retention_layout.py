from __future__ import annotations

from pathlib import Path


def test_topic_page_prioritizes_retention_panels() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Primary Next Step' in content
    assert 'Notebook Memory' in content
    assert 'Studio Loop' in content
    assert 'Study Signals' in content
    assert 'Study tools' in content
    assert 'retention?.plan_summary' in content
    assert 'retention?.unlock_anticipation' in content
    assert 'retention?.notebook_memory?.prompt' in content
    assert 'retention?.notebook_memory?.growth_signal' in content


def test_topic_page_demotes_old_progress_and_header_clutter() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'TopicTreeStage' not in content
    assert 'Study Stage' in content
    assert 'Study progression' not in content
