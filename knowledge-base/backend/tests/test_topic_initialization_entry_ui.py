from __future__ import annotations

from pathlib import Path


def test_topic_initialization_page_sets_a_calm_confident_entry_expectation() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    init_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'initializing' / 'page.tsx'
    content = init_path.read_text(encoding='utf-8')

    assert 'Preparing your first study session in {PRODUCT_NAME}' in content
    assert 'No setup choices are needed now.' in content
    assert 'What happens here' in content
    assert 'First lesson' in content
    assert 'First practice' in content
    assert 'Notebook cue' in content
