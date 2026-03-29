from __future__ import annotations

from pathlib import Path


def test_renderer_enforces_non_root_incoming_and_core_continuity_invariants() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'emergency_missing_incoming' in content
    assert 'emergency_core_continuity' in content
    assert 'emergency_declared_core' in content
    assert 'emergency_repair_incoming' in content
    assert 'emergency_repair_core' in content
    assert 'emergency_repair_declared_core' in content
    assert 'core_backbone_guarantee' in content
    assert 'core_backbone_repair' in content
    assert 'detachedCoreNodeIds' in content
    assert 'orphanNodeIds' in content


def test_renderer_has_three_tier_connector_routing_modes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert "routeMode: 'preferred' | 'fallback' | 'emergency'" in content
    assert 'preferredCoreConnectorPath' in content
    assert 'elbowConnectorPath' in content
    assert 'straightConnectorPath' in content
    assert 'fallbackConnectorEdgeKeys' in content
    assert 'emergencyConnectorEdgeKeys' in content


def test_vertical_and_near_vertical_chains_fall_back_to_direct_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'if (Math.abs(dx) <= 14 || Math.abs(dy) <= 16)' in content
    assert 'return straightConnectorPath(start, end);' in content
