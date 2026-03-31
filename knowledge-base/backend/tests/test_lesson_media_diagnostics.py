from __future__ import annotations

from pathlib import Path


def test_media_pipeline_emits_candidate_and_rejection_diagnostics() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')
    search_content = (repo_root / 'backend' / 'app' / 'services' / 'search.py').read_text(encoding='utf-8')

    assert 'resource.deep_lesson_media_selected topic_id=%s skill_id=%s selected=%s images=%s videos=%s requested_limit=%s diagnostics=%s' in content
    assert 'resource.lesson_media_selection_deduped topic_id=%s skill_id=%s kind=%s dropped_used=%s' in content
    assert "'video_not_embeddable'" in (repo_root / 'backend' / 'app' / 'agents' / 'lesson_image_agent.py').read_text(encoding='utf-8')
    assert "'video_not_playable'" in (repo_root / 'backend' / 'app' / 'agents' / 'lesson_image_agent.py').read_text(encoding='utf-8')
    assert "'source_fetch_blocked'" in (repo_root / 'backend' / 'app' / 'agents' / 'lesson_image_agent.py').read_text(encoding='utf-8')
    assert "'low_relevance'" in (repo_root / 'backend' / 'app' / 'agents' / 'lesson_image_agent.py').read_text(encoding='utf-8')
    assert 'external_search.parse_salvaged provider=openai_web query=%s salvaged=%s' in search_content
    assert 'external_media_search.strict_schema_retry provider=openai_web lesson_title=%s error=%s' in search_content
    assert 'external_media_search.parse_salvaged provider=openai_web lesson_title=%s images=%s videos=%s' in search_content


def test_media_attachment_and_payload_logs_are_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    agent_content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')
    lesson_image_content = (repo_root / 'backend' / 'app' / 'agents' / 'lesson_image_agent.py').read_text(encoding='utf-8')
    routes_content = (repo_root / 'backend' / 'app' / 'api' / 'routes.py').read_text(encoding='utf-8')

    assert 'resource.supporting_media_attached topic_id=%s skill_id=%s kind=%s selected=%s images=%s videos=%s' in agent_content
    assert 'resource.loaded_from_store topic_id=%s skill_id=%s kind=%s version=%s media_backfilled=%s' in agent_content
    assert 'resource.deep_lesson_media_disabled topic_id=%s skill_id=%s reason=feature_temporarily_disabled' in routes_content
    assert 'resource.lesson_media_selection topic_id=%s skill_id=%s kind=%s lesson_title=%s image_query=%s video_query=%s candidates=%s selected=%s selected_image=%s selected_image_preview=%s selected_video=%s domains=%s rejections=%s agent_decision=%s' in lesson_image_content
