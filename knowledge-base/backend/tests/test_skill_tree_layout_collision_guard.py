from __future__ import annotations

from pathlib import Path


def test_layout_includes_collision_resolution_and_spacing_guards() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    layout_path = repo_root / 'frontend' / 'lib' / 'skill-tree-layout.ts'
    content = layout_path.read_text(encoding='utf-8')

    assert 'resolveTierCollisions' in content
    assert 'MIN_VERTICAL_GAP' in content
    assert 'MIN_HORIZONTAL_GAP' in content
    assert 'NODE_VERTICAL_FOOTPRINT' in content
    assert 'orderTierNodes' in content


def test_layout_no_longer_relies_on_fit_scale_compression() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    layout_path = repo_root / 'frontend' / 'lib' / 'skill-tree-layout.ts'
    content = layout_path.read_text(encoding='utf-8')

    assert 'fitScale' not in content
