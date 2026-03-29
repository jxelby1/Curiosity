from __future__ import annotations

from pathlib import Path


def test_layout_includes_tier_recentering_for_balanced_fanout() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    layout_path = repo_root / 'frontend' / 'lib' / 'skill-tree-layout.ts'
    content = layout_path.read_text(encoding='utf-8')

    assert 'rebalanceTierAroundCenter' in content
    assert 'coreTierCenter' in content
    assert 'coreParentBarycenters' in content
    assert 'CORE_LANE_PULL' in content
    assert 'balanced = rebalanceTierAroundCenter' in content
    assert 'computeSubtreeWeights' in content
    assert 'coreLaneCenters' in content
    assert 'runLayoutBeautyPass' in content
    assert 'optionalParentId' in content
    assert 'OPTIONAL_CHAIN_DRIFT' in content
    assert 'optionalDirectionByNode' in content
