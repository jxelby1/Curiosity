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

    assert 'Your study grove' in content
    assert 'href={`/topics/${topic.topic_id}`}' in content


def test_garden_progress_summary_carries_momentum_and_memory_signals() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    route_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    schema_path = repo_root / 'backend' / 'app' / 'schemas' / 'api.py'
    types_path = repo_root / 'frontend' / 'lib' / 'types.ts'

    route_content = route_path.read_text(encoding='utf-8')
    schema_content = schema_path.read_text(encoding='utf-8')
    types_content = types_path.read_text(encoding='utf-8')

    assert 'branch_count=branch_count' in route_content
    assert 'notes_count=notes_count' in route_content
    assert 'latest_activity_at=latest_activity_at' in route_content
    assert 'branch_count: int = 0' in schema_content
    assert 'notes_count: int = 0' in schema_content
    assert 'latest_activity_at: datetime | None = None' in schema_content
    assert 'branch_count: number;' in types_content
    assert 'notes_count: number;' in types_content
    assert 'latest_activity_at: string | null;' in types_content
