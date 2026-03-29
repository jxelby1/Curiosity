from __future__ import annotations

from pathlib import Path


def test_premium_skill_tree_uses_anchored_edges_and_root_spine() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    content = tree_path.read_text(encoding='utf-8')

    assert 'buildAnchoredTreeEdges' in content
    assert 'rootSpineSegments' in content
    assert 'isSynthetic' in content
    assert 'skillPathSynthetic' in content


def test_premium_skill_tree_has_branch_reveal_animation_hooks() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tree_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'premium-skill-tree.tsx'
    css_path = repo_root / 'frontend' / 'app' / 'globals.css'
    tree_content = tree_path.read_text(encoding='utf-8')
    css_content = css_path.read_text(encoding='utf-8')

    assert 'revealedNodeIds' in tree_content
    assert 'skill-tree-edge-reveal' in tree_content
    assert 'skill-tree-node-reveal' in tree_content
    assert '@keyframes skill-tree-edge-reveal' in css_content
    assert '@keyframes skill-tree-node-reveal' in css_content
