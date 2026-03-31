from __future__ import annotations

from pathlib import Path


def test_skill_workspace_includes_branching_controls_and_suggestions() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')
    branch_meta = (repo_root / 'frontend' / 'lib' / 'branch-purpose.ts').read_text(encoding='utf-8')

    assert 'Optional Branch Paths' in content
    assert 'Create a custom branch move' in content
    assert 'Open branch move' in content
    assert 'Add branch to tree' in content
    assert 'Request branch suggestion' in content
    assert 'Study move:' in content
    assert 'Best when:' in content
    assert 'Style / Technique Practice' in branch_meta
    assert 'Compare & Contrast' in branch_meta
    assert 'keepCorePrimary' in branch_meta
    assert 'whenToUse' in branch_meta
    assert 'limit: 1' in content
    assert 'branch_size: 1' in content


def test_skill_workspace_focus_mode_gates_optional_tools() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert "type WorkspaceMode = 'focus' | 'detailed';" in content
    assert "const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(initialWorkspaceMode);" in content
    assert 'Study Focus' in content
    assert 'Open studio view' in content
    assert 'Studio view' in content
    assert 'focusDefaultTabForNode' in content
    assert "tabs.filter((tab) => tab.focusVisible !== false)" in content
    assert 'const showDetailedControls = workspaceMode === \'detailed\';' in content


def test_skill_workspace_moves_completion_and_generation_controls_out_of_focus_overview() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'After This Lesson' in content
    assert 'Mark lesson complete' in content
    assert 'showDetailedControls && (' in content


def test_skill_workspace_revealed_answer_uses_model_answer_label() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    page_path = repo_root / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
    content = page_path.read_text(encoding='utf-8')

    assert 'Model answer' in content
    assert 'whitespace-pre-wrap' in content
