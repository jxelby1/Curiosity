from __future__ import annotations

from pathlib import Path


def test_connector_routing_uses_canonical_node_anchors() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'type AnchorPoint' in content
    assert 'nodeAnchorSet' in content
    assert 'connectorAnchors' in content
    assert 'start: descending ? parentAnchors.bottom : parentAnchors.top' in content
    assert 'end: descending ? childAnchors.top : childAnchors.bottom' in content


def test_connector_pipeline_has_path_validation_and_safe_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'safeConnectorPath' in content
    assert 'edgePaths' in content
    assert 'skill_tree.connector.validation_failed' in content
    assert 'detachedCoreNodeIds' in content
    assert 'forcedCore: true' in content
