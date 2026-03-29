from __future__ import annotations

from pathlib import Path


def test_core_connectors_render_from_validated_edge_pipeline_not_backbone_only() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'const coreEdgePaths = useMemo(' in content
    assert 'edgePaths.filter((item) => item.edge.isCore)' in content
    assert 'data-core-edge-key={edge.key}' in content
    assert 'guaranteedCoreBackboneFallbackEdges' in content


def test_single_parent_vertical_chain_has_emergency_reliability_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'Deterministic one-parent vertical repair' in content
    assert 'declaredVisibleParents.length !== 1' in content
    assert 'const nearVertical = xGap <= 150 && yGap >= MIN_VISIBLE_CONNECTOR_DY;' in content
    assert "'emergency_single_parent_vertical'" in content
    assert "'emergency_repair_single_parent_vertical'" in content

