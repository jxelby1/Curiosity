from __future__ import annotations

from pathlib import Path


def test_skill_workspace_includes_branching_controls_and_suggestions() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')
    branch_meta = (repo_root / 'frontend' / 'lib' / 'branch-purpose.ts').read_text(encoding='utf-8')

    assert 'Explore Further (Optional)' in content
    assert 'Open branch move' in content
    assert 'Recommended Study Move' in content
    assert 'Activate branch' in content
    assert 'Refresh suggestion' in content
    assert 'Style / Technique Practice' in branch_meta
    assert 'Compare & Contrast' in branch_meta
    assert 'limit: 1' in content
    assert 'branch_size: 1' in content


def test_skill_workspace_focus_mode_gates_optional_tools() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert "type WorkspaceMode = 'focus' | 'detailed';" in content
    assert "const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(initialWorkspaceMode);" in content
    assert 'Focus mode' in content
    assert 'Detailed tools' in content
    assert "tabs.filter((tab) => tab.focusVisible !== false)" in content
    assert "{workspaceMode === 'detailed' ? (" in content


def test_skill_workspace_revealed_answer_uses_model_answer_label() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Model answer' in content
    assert 'whitespace-pre-wrap' in content
