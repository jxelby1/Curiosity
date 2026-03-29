from __future__ import annotations

from pathlib import Path


def test_topic_delete_removes_assessment_children_before_assessment_rows() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    route_path = repo_root / 'backend' / 'app' / 'api' / 'routes.py'
    content = route_path.read_text(encoding='utf-8')

    child_delete_pos = content.find('delete(AssessmentQuestion)')
    assessment_delete_pos = content.find('delete(Assessment).where(Assessment.id.in_(assessment_ids_subquery))')

    assert child_delete_pos != -1
    assert assessment_delete_pos != -1
    assert child_delete_pos < assessment_delete_pos
