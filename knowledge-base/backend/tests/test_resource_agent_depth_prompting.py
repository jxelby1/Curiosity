from __future__ import annotations

from pathlib import Path


def test_resource_agent_threads_technical_depth_into_generation_and_quality_refine() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert 'technical_depth = self._technical_depth(topic)' in content
    assert 'Technical depth preference: {technical_depth}' in content
    assert 'resource.lesson_quality_refine' in content
    assert 'technical_depth_prompt_guidance' in content
    assert '_lesson_quality_signals(' in content
