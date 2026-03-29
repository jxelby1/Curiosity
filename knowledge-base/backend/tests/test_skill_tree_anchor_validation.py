from __future__ import annotations

from pathlib import Path


def test_layout_exposes_anchor_validation_and_correction_pass() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    layout_path = repo_root / 'frontend' / 'lib' / 'skill-tree-layout.ts'
    content = layout_path.read_text(encoding='utf-8')

    assert 'buildAnchoredTreeEdges' in content
    assert 'fallbackAnchorParentId' in content
    assert 'requiredDepth' in content
    assert 'hasImmediateTierAnchor' in content
    assert 'nearestVisualParentId' in content
    assert 'nearestTierParentByX' in content
    assert 'strictCoreParent' in content
    assert 'needsVisualRepair' in content
    assert 'synthetic: true' in content
    assert 'MAX_VISUAL_PARENT_ANCHORS' in content
    assert 'runLayoutBeautyPass' in content


def test_layout_limits_visual_prerequisites_to_two() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    layout_path = repo_root / 'frontend' / 'lib' / 'skill-tree-layout.ts'
    content = layout_path.read_text(encoding='utf-8')

    assert 'uniquePrerequisites' in content
    assert 'deduped.length >= MAX_VISUAL_PARENT_ANCHORS' in content
