from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTES_FILE = ROOT / 'backend' / 'app' / 'api' / 'routes.py'


def test_routes_include_exercise_completion_and_journal_endpoints() -> None:
    content = ROUTES_FILE.read_text()
    assert "/skills/{skill_id}/exercises/completions" in content
    assert "/skills/{skill_id}/exercises/{exercise_index}/complete" in content
    assert "/exercise-completions/{completion_id}/proof" in content
    assert "/topics/{topic_id}/journal" in content

