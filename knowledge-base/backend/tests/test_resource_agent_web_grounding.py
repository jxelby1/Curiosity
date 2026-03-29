from __future__ import annotations

from pathlib import Path


def test_resource_agent_threads_web_grounding_context_into_lessons() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert 'Curated web grounding references (optional; use only if directly relevant)' in content
    assert '_build_web_grounding_context(' in content
    assert "source_policy='grounding'" in content


def test_strict_media_retrieval_uses_strict_source_policy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert "source_policy='strict_media'" in content
    assert 'Development fallback media candidate' not in content
