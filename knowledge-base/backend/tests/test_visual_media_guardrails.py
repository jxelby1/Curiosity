from __future__ import annotations

from pathlib import Path


def test_visual_media_pipeline_keeps_social_and_stock_sources_blocked() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert "_BLOCKED_SOCIAL_MEDIA_DOMAINS = (" in content
    assert "'instagram.com'" in content
    assert "'tiktok.com'" in content
    assert "'x.com'" in content
    assert "_BLOCKED_STOCK_MEDIA_DOMAINS = (" in content
    assert "'shutterstock.com'" in content
    assert "'gettyimages.com'" in content
    assert 'def _is_trusted_media_candidate(' in content
    assert "source_policy='strict_media'" in content


def test_visual_media_pipeline_prefers_trusted_sources_before_any_broad_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / 'backend' / 'app' / 'agents' / 'resource_agent.py').read_text(encoding='utf-8')

    assert 'enforce_trusted_sources=True' in content
    assert 'if len(seed_media) + len(scored) < limit and len(scored) == 0:' in content
    assert 'source_policy=\'standard\'' in content
