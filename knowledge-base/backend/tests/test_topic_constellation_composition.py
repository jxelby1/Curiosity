from __future__ import annotations

from pathlib import Path


def test_topic_page_balances_constellation_canvas_with_inspector_panel() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Living Study Constellation' in content
    assert 'lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)]' in content
    assert 'xl:grid-cols-[minmax(0,1.68fr)_minmax(340px,1fr)]' in content
    assert 'Branch opportunities are intentionally sparse and shown one at a time.' in content


def test_skill_node_inspector_keeps_branch_builder_visible_but_compact() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    inspector_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'skill-node-inspector.tsx'
    content = inspector_path.read_text(encoding='utf-8')

    assert 'Branch move' in content
    assert 'Next move' in content
    assert 'recommended_next_action' in content
    assert 'Suggest' in content
    assert 'Create' in content
    assert 'Developer override' in content
