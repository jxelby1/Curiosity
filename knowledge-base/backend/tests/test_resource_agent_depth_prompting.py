from __future__ import annotations

from pathlib import Path


def test_resource_agent_threads_technical_depth_into_generation_and_quality_refine() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert 'technical_depth = self._technical_depth(topic)' in content
    assert 'Technical depth preference: {technical_depth}' in content
    assert 'resource.lesson_quality_gate' in content
    assert '_quality_control_structured_content(' in content
    assert 'technical_depth_prompt_guidance' in content
    assert '_lesson_quality_signals(' in content
    assert 'anchor exemplar -> close observation -> interpretation or context -> response or practice transfer' in content
    assert 'Sequence examples as an intentional set: anchor example first, then variation or contrast, then transfer or response.' in content
    assert '_teaching_spine_issues(' in content
    assert 'No concept without evidence' in content
    assert 'No exemplar without operationalization' in content
    assert 'Do not ask the learner to reflect, compare, create, solve, or apply until the lesson has provided enough proof and explanation.' in content
    assert '_evidence_density_issues(' in content
    assert "'schema_invalid'" in content
