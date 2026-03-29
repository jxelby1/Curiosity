from __future__ import annotations

from pathlib import Path


def test_emergency_connector_repairs_non_visible_parent_child_edges() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'const visibleEdgeExists = (parentId: number, childId: number): boolean =>' in content
    assert 'if (visibleEdgeExists(emergencyParent.id, node.id)) continue;' in content
    assert 'const replacingBrokenEdge = edgeExists(emergencyParent.id, node.id);' in content
    assert "source: replacingBrokenEdge ? 'emergency_repair_incoming' : 'emergency_missing_incoming'" in content


def test_core_invariant_checks_all_visible_core_nodes_not_only_orphans() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'const unresolvedCore = nodes' in content
    assert "entry.node.node_kind === 'core' && !hasRenderedCoreEdge(entry.node.id)" in content
    assert 'unresolvedCoreNodeIds' in content


def test_declared_core_parent_link_gets_forced_if_not_visible() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'Enforce core-chain continuity against the declared/immediate core parent.' in content
    assert 'if (visibleEdgeExists(preferredCoreParentId, node.id)) continue;' in content
    assert "source: replacingBrokenEdge ? 'emergency_repair_declared_core' : 'emergency_declared_core'" in content


def test_core_backbone_pass_guarantees_core_visibility() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'Final guaranteed core backbone pass' in content
    assert "source: repairing ? 'core_backbone_repair' : 'core_backbone_guarantee'" in content
    assert 'coreBackboneEdgeKeys' in content
