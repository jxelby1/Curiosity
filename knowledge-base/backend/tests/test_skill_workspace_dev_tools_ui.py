from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'


def test_dev_tools_controls_are_role_gated_in_skill_workspace() -> None:
    content = SKILL_PAGE.read_text(encoding='utf-8')
    assert "const canUseDevTools = !!user?.dev_tools_enabled;" in content
    assert 'Dev: Complete node' in content
    assert 'isLocked && canUseDevTools' in content
    assert 'canUseDevTools && (' in content


def test_skill_workspace_calls_dev_complete_api() -> None:
    content = SKILL_PAGE.read_text(encoding='utf-8')
    assert 'await devCompleteSkill(nodeId);' in content
    assert "setLoadingState('dev-complete', true, nodeId);" in content
