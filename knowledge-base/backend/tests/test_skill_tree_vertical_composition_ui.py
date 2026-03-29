from __future__ import annotations

from pathlib import Path


def test_skill_tree_layout_uses_vertical_depth_bias_and_optional_side_offsets() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    layout_path = repo_root / 'frontend' / 'lib' / 'skill-tree-layout.ts'
    content = layout_path.read_text(encoding='utf-8')

    assert 'OPTIONAL_BASE_OFFSET' in content
    assert 'OPTIONAL_BRANCH_DEPTH_OFFSET' in content
    assert 'depthGap' in content
    assert 'centerX' in content
    assert 'resolveTierCollisions' in content
    assert 'CORE_PARENT_PULL' in content
    assert 'parentBarycenter' in content
    assert 'optionalTierOffset' in content


def test_skill_tree_component_renders_trunk_and_branch_motif() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    component_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = component_path.read_text(encoding='utf-8')

    assert 'skillTreeTrunk' in content
    assert 'skillTreeBranchGhost' in content
    assert 'skillPathOptional' in content
    assert 'coreConnectorPath' in content
    assert 'branchConnectorPath' in content
    assert 'primaryCoreEdges.map' in content
    assert 'edgePriority' in content
    assert 'Branch' in content and 'Core' in content
