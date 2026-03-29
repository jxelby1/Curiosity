from __future__ import annotations

from pathlib import Path


def test_topic_routes_include_plausibility_check_and_clarification_guardrail() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    routes_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    content = routes_path.read_text(encoding='utf-8')

    assert "/topics/plausibility-check" in content
    assert '_raise_topic_guardrail' in content
    assert 'topic_needs_context' in content
    assert "if plausibility.status in {'clarify', 'needs_context', 'block'} and payload.topic_mode == 'factual':" in content
