from __future__ import annotations

from pathlib import Path


def test_tree_assets_exist_for_all_stages() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assets_dir = repo_root / 'frontend' / 'public' / 'assets' / 'tree-growth'

    for stage in range(1, 7):
        path = assets_dir / f'tree-stage-{stage}.svg'
        assert path.exists(), f'Missing asset: {path}'


def test_tree_growth_mapping_utility_has_6_stage_clamp() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    util_path = repo_root / 'frontend' / 'lib' / 'tree-growth.ts'
    content = util_path.read_text(encoding='utf-8')

    assert 'Math.max(1, Math.min(6, stage))' in content
    assert 'TREE_STAGE_LABELS' in content


def test_garden_page_links_into_topic_pages() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'garden' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Your topic forest' in content
    assert 'href={`/topics/${topic.topic_id}`}' in content
