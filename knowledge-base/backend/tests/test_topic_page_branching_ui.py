from __future__ import annotations

from pathlib import Path


def test_topic_page_wires_branching_actions_into_inspector() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'branchSuggestionsByNode' in content
    assert 'handleCreateBranch' in content
    assert 'handleAcceptBranchSuggestion' in content
    assert 'handleRejectBranchSuggestion' in content
    assert 'onCreateBranch' in content and 'SkillNodeInspector' in content
    assert 'limit: 1' in content
    assert 'branch_size: 1' in content


def test_inspector_exposes_create_branch_and_suggestions_ui() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    inspector_path = repo_root / 'frontend' / 'components' / 'skill-tree' / 'skill-node-inspector.tsx'
    content = inspector_path.read_text(encoding='utf-8')

    assert 'Branch builder' in content
    assert 'Create' in content
    assert 'Suggest one' in content
    assert 'Add path' in content
    assert 'Not now' in content
