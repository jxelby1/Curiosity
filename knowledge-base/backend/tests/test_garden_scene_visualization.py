from __future__ import annotations

from pathlib import Path


def test_garden_scene_component_maps_topic_progress_to_visual_nodes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    scene_path = repo_root / 'frontend' / 'components' / 'garden' / 'garden-scene.tsx'
    content = scene_path.read_text(encoding='utf-8')

    assert 'buildGardenLayout' in content
    assert 'buildBedBands' in content
    assert 'activityWeight' in content
    assert 'momentumMeta' in content
    assert 'layeringLine' in content
    assert 'treeStageAsset' in content
    assert 'treeStageLabel' in content
    assert 'latest_activity_at' in content
    assert 'notes_count' in content
    assert 'branch_count' in content
    assert 'walkwayPath' not in content


def test_garden_page_uses_visual_scene_as_primary_experience() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'garden' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'GardenScene' in content
    assert '<GardenScene topics={summary.topics} />' in content
    assert 'Recently tended' in content
    assert 'Memory in bloom' in content
    assert 'Plots in the grove' in content
