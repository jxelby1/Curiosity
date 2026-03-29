from __future__ import annotations

from pathlib import Path


def test_renderer_enforces_core_chain_invariant_with_declared_parent_priority() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'declaredCoreParentId' in content
    assert "reason: 'declared_core'" in content
    assert 'Prefer visual continuity on the core trunk if explicit prerequisites are absent.' in content
    assert 'const higherCore = nearestAboveNode(child, childPoint, true);' in content
    assert 'if (higherCore) return higherCore.id;' in content
    assert 'Skill tree connector invariant failed for node IDs' in content
    assert 'unresolvedCoreNodeCount' in content
    assert "if (process.env.NODE_ENV !== 'production')" in content


def test_renderer_uses_visibility_thresholds_for_connector_validity() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'MIN_VISIBLE_CONNECTOR_DY' in content
    assert 'MIN_VISIBLE_CONNECTOR_DISTANCE' in content
    assert 'hasVisibleConnectorGeometry' in content
    assert 'weakGeometryEdgeKeys' in content
