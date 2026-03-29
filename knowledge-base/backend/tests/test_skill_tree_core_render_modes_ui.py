from __future__ import annotations

from pathlib import Path


def test_renderer_supports_debug_and_core_only_query_modes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert "params.get('treeDebug') === '1'" in content
    assert "params.get('treeCoreOnly') === '1'" in content
    assert 'setTreeDebugMode(debug);' in content
    assert 'setCoreOnlyMode(coreOnly);' in content


def test_renderer_has_guaranteed_core_backbone_svg_layer_and_dom_validation() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'buildGuaranteedCoreBackboneEdges' in content
    assert 'data-core-backbone-key={edge.key}' in content
    assert 'skill_tree.core_backbone.dom_validation_failed' in content
    assert 'missingCoreConnectorElements' in content
    assert 'hiddenCoreConnectorElements' in content
    assert 'degenerateCoreConnectorElements' in content
    assert 'outOfBoundsCoreConnectorElements' in content
