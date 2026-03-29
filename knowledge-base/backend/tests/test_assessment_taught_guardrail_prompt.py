from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSESSMENT_AGENT = ROOT / 'backend' / 'app' / 'agents' / 'assessment_agent.py'


def test_assessment_prompt_enforces_taught_content_guardrail() -> None:
    content = ASSESSMENT_AGENT.read_text()
    assert 'Taught concepts available in lesson/examples' in content
    assert 'Do not test concepts that are not explicitly taught in lesson/examples context above.' in content

