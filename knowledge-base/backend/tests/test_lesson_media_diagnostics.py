from __future__ import annotations

from pathlib import Path


def test_media_pipeline_emits_candidate_and_rejection_diagnostics() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert 'resource.deep_lesson_media_candidates topic_id=%s skill_id=%s phase=strict count=%s query=%s' in content
    assert 'resource.deep_lesson_media_candidates topic_id=%s skill_id=%s phase=fallback count=%s query=%s' in content
    assert 'resource.deep_lesson_media_diagnostics topic_id=%s skill_id=%s strict=%s fallback=%s broad=%s' in content
    assert "'skip_no_renderable_image'" in content
    assert "'skip_below_threshold'" in content


def test_media_attachment_and_payload_logs_are_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    agent_content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')
    lesson_image_content = (repo_root / 'backend' / 'app' / 'agents' / 'lesson_image_agent.py').read_text(encoding='utf-8')
    routes_content = (repo_root / 'backend' / 'app' / 'api' / 'routes.py').read_text(encoding='utf-8')

    assert 'resource.supporting_media_attached topic_id=%s skill_id=%s kind=%s selected=%s images=%s videos=%s' in agent_content
    assert 'resource.loaded_from_store topic_id=%s skill_id=%s kind=%s version=%s media_backfilled=%s' in agent_content
    assert 'resource.deep_lesson_media_payload topic_id=%s skill_id=%s selected=%s images=%s videos=%s' in routes_content
    assert 'resource.lesson_image_selection topic_id=%s skill_id=%s kind=%s visual_support_needed=%s priority=%s' in lesson_image_content
