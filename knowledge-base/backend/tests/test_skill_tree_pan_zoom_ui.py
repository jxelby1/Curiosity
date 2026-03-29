from __future__ import annotations

from pathlib import Path


def test_skill_tree_component_includes_pan_and_zoom_controls() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    component_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = component_path.read_text(encoding='utf-8')

    assert 'onWheel={onWheel}' in content
    assert 'onPointerDown={onPointerDown}' in content
    assert 'onPointerMove={onPointerMove}' in content
    assert 'onPointerUp={onPointerUp}' in content
    assert 'Reset' in content
    assert 'MIN_ZOOM' in content and 'MAX_ZOOM' in content
