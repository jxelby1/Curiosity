from __future__ import annotations

import base64
import time

import pytest

from app.core.config import Settings
from app.services.media_cache import MediaCacheService


def _service(*, ttl_seconds: int = 300) -> MediaCacheService:
    settings = Settings(
        jwt_secret_key='test-media-cache-secret',
        media_cache_storage_dir='/tmp/canopy-test-media-cache',
        media_cache_token_ttl_seconds=ttl_seconds,
    )
    return MediaCacheService(settings=settings)


def _png_bytes(width: int, height: int) -> bytes:
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_len = (13).to_bytes(4, 'big')
    ihdr = b'IHDR' + width.to_bytes(4, 'big') + height.to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'
    # CRC bytes are not validated by dimension parsing; keep deterministic placeholder.
    return signature + ihdr_len + ihdr + b'\x00\x00\x00\x00'


def test_media_cache_builds_signed_proxy_tokens() -> None:
    service = _service()
    proxy_url = service.build_proxy_url(
        preferred_url='https://example.org/images/reference-photo.jpg',
        source_url='https://example.org/articles/reference',
    )

    assert proxy_url is not None
    token = proxy_url.rsplit('/', 1)[-1]
    assert '.' in token

    preferred_url, source_url = service._decode_proxy_token(token)  # noqa: SLF001
    assert preferred_url == 'https://example.org/images/reference-photo.jpg'
    assert source_url == 'https://example.org/articles/reference'


def test_media_cache_rejects_tampered_proxy_tokens() -> None:
    service = _service()
    proxy_url = service.build_proxy_url(
        preferred_url='https://example.org/images/reference-photo.jpg',
        source_url='https://example.org/articles/reference',
    )
    assert proxy_url is not None

    token = proxy_url.rsplit('/', 1)[-1]
    payload, _, signature = token.partition('.')
    tampered_payload = f'{payload[:-1]}A' if len(payload) > 1 else f'{payload}A'
    tampered = f'{tampered_payload}.{signature}'

    with pytest.raises(ValueError):
        service._decode_proxy_token(tampered)  # noqa: SLF001


def test_media_cache_rejects_expired_tokens() -> None:
    service = _service(ttl_seconds=10)
    stale_payload = {
        'u': 'https://example.org/images/reference-photo.jpg',
        's': 'https://example.org/articles/reference',
        'iat': int(time.time()) - 999,
    }
    token = service._encode_token_payload(stale_payload)  # noqa: SLF001

    with pytest.raises(ValueError):
        service._decode_proxy_token(token)  # noqa: SLF001


def test_media_cache_accepts_legacy_unsigned_tokens_in_non_production() -> None:
    service = _service()
    legacy_payload = 'https://example.org/images/reference-photo.jpg\nhttps://example.org/articles/reference'
    token = base64.urlsafe_b64encode(legacy_payload.encode('utf-8')).decode('ascii').rstrip('=')

    preferred_url, source_url = service._decode_proxy_token(token)  # noqa: SLF001
    assert preferred_url == 'https://example.org/images/reference-photo.jpg'
    assert source_url == 'https://example.org/articles/reference'


def test_media_cache_rejects_legacy_unsigned_tokens_in_production() -> None:
    settings = Settings(
        environment='production',
        jwt_secret_key='test-media-cache-secret',
        media_cache_storage_dir='/tmp/canopy-test-media-cache',
        media_cache_token_ttl_seconds=300,
    )
    service = MediaCacheService(settings=settings)
    legacy_payload = 'https://example.org/images/reference-photo.jpg\nhttps://example.org/articles/reference'
    token = base64.urlsafe_b64encode(legacy_payload.encode('utf-8')).decode('ascii').rstrip('=')

    with pytest.raises(ValueError):
        service._decode_proxy_token(token)  # noqa: SLF001


def test_media_cache_rejects_low_resolution_images_by_dimension_gate() -> None:
    service = _service()
    low_res = _png_bytes(220, 180)
    assert service._passes_image_quality_gate(data=low_res, content_type='image/png') is False  # noqa: SLF001


def test_media_cache_accepts_high_resolution_images_by_dimension_gate() -> None:
    service = _service()
    high_res = _png_bytes(1400, 900)
    assert service._passes_image_quality_gate(data=high_res, content_type='image/png') is True  # noqa: SLF001


def test_media_cache_temporarily_blocks_domains_after_access_denied() -> None:
    service = _service()
    assert service.is_domain_temporarily_blocked('https://example.org/path/to/image.jpg') is False
    service._mark_domain_temporarily_blocked(url='https://example.org/path/to/image.jpg', status_code=403)  # noqa: SLF001
    assert service.is_domain_temporarily_blocked('https://example.org/path/to/image.jpg') is True
    assert service.is_domain_temporarily_blocked('example.org') is True
