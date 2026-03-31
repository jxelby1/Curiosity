from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTES_FILE = ROOT / 'backend' / 'app' / 'api' / 'routes.py'
MEDIA_CACHE_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'media_cache.py'
RESOURCE_AGENT = ROOT / 'backend' / 'app' / 'agents' / 'resource_agent.py'


def test_backend_exposes_media_cache_proxy_route_and_service() -> None:
    routes_content = ROUTES_FILE.read_text(encoding='utf-8')
    service_content = MEDIA_CACHE_SERVICE.read_text(encoding='utf-8')
    agent_content = RESOURCE_AGENT.read_text(encoding='utf-8')

    assert "@router.get('/media-cache/proxy/{token}')" in routes_content
    assert 'current_user: CurrentUser' not in routes_content.split("@router.get('/media-cache/proxy/{token}')", 1)[1].split('@router.', 1)[0]
    assert 'media_cache_service.resolve_proxy_token(token)' in routes_content
    assert 'class MediaCacheService:' in service_content
    assert 'def build_proxy_url(self, *, preferred_url: str, source_url: str = \'\') -> str | None:' in service_content
    assert 'async def resolve_proxy_token(self, token: str) -> tuple[Path, str]:' in service_content
    assert 'media_cache_service.build_proxy_url(' in agent_content
