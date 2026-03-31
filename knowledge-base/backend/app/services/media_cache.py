from __future__ import annotations

import base64
import hmac
import hashlib
import html as html_lib
import ipaddress
import json
import logging
import mimetypes
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)

_BLOCKED_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}
_MAX_HTML_BYTES = 1_800_000
_DEFAULT_ACCEPT = (
    'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
)
_DEFAULT_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
)
_DEFAULT_ACCEPT_LANGUAGE = 'en-US,en;q=0.9'


class MediaCacheService:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_dir = Path(self.settings.media_cache_storage_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(1, int(self.settings.media_cache_max_mb)) * 1024 * 1024
        self.timeout_seconds = max(2.0, float(self.settings.media_cache_timeout_seconds))
        self.token_ttl_seconds = max(60, int(self.settings.media_cache_token_ttl_seconds))
        self.min_image_pixels = max(1, int(self.settings.media_cache_min_image_pixels))
        self.min_image_long_edge = max(1, int(self.settings.media_cache_min_image_long_edge))
        self.domain_block_ttl_seconds = max(60, int(self.settings.media_cache_domain_block_ttl_seconds))
        self.signing_secret = (self.settings.jwt_secret_key or '').encode('utf-8')
        self._blocked_domains_until: dict[str, float] = {}

    def build_proxy_url(self, *, preferred_url: str, source_url: str = '') -> str | None:
        preferred = (preferred_url or '').strip()
        source = (source_url or '').strip()
        if not self._is_safe_http_url(preferred):
            return None
        if source and not self._is_safe_http_url(source):
            source = ''

        payload = {
            'u': preferred,
            's': source,
            'iat': int(time.time()),
        }
        token = self._encode_token_payload(payload)
        if not token:
            return None
        return f'/api/media-cache/proxy/{token}'

    def _decode_proxy_token(self, token: str) -> tuple[str, str]:
        try:
            payload = self._decode_token_payload(token)
            preferred_url = str(payload.get('u') or '').strip()
            source_url = str(payload.get('s') or '').strip()
            issued_at = payload.get('iat')
            try:
                issued_ts = int(issued_at)
            except (TypeError, ValueError) as exc:
                raise ValueError('Invalid media proxy token.') from exc

            now = int(time.time())
            if issued_ts > (now + 300):
                raise ValueError('Invalid media proxy token timestamp.')
            if (now - issued_ts) > self.token_ttl_seconds:
                raise ValueError('Media proxy token expired.')
        except ValueError:
            if self.settings.environment.lower() == 'production':
                raise
            preferred_url, source_url = self._decode_legacy_proxy_token(token)

        if not self._is_safe_http_url(preferred_url):
            raise ValueError('Invalid media URL in proxy token.')
        if source_url and not self._is_safe_http_url(source_url):
            source_url = ''
        return preferred_url, source_url

    def _decode_legacy_proxy_token(self, token: str) -> tuple[str, str]:
        compact = (token or '').strip()
        if not compact:
            raise ValueError('Missing media proxy token.')
        padding = '=' * (-len(compact) % 4)
        try:
            decoded = base64.urlsafe_b64decode(f'{compact}{padding}'.encode('ascii')).decode('utf-8')
        except Exception as exc:  # noqa: BLE001
            raise ValueError('Invalid media proxy token.') from exc
        preferred, _, source = decoded.partition('\n')
        preferred_url = preferred.strip()
        source_url = source.strip()
        if not self._is_safe_http_url(preferred_url):
            raise ValueError('Invalid media URL in proxy token.')
        if source_url and not self._is_safe_http_url(source_url):
            source_url = ''
        logger.info('media_cache.legacy_token_used')
        return preferred_url, source_url

    def _encode_token_payload(self, payload: dict[str, str | int]) -> str:
        try:
            payload_bytes = json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
        except Exception:  # noqa: BLE001
            return ''
        payload_part = base64.urlsafe_b64encode(payload_bytes).decode('ascii').rstrip('=')
        signature = self._sign_payload(payload_bytes)
        if not payload_part or not signature:
            return ''
        return f'{payload_part}.{signature}'

    def _decode_token_payload(self, token: str) -> dict[str, Any]:
        compact = (token or '').strip()
        if not compact:
            raise ValueError('Missing media proxy token.')

        payload_part, sep, signature_part = compact.partition('.')
        if not payload_part or not sep or not signature_part:
            raise ValueError('Invalid media proxy token.')

        try:
            payload_bytes = base64.urlsafe_b64decode(f'{payload_part}{"=" * (-len(payload_part) % 4)}'.encode('ascii'))
            signature_bytes = base64.urlsafe_b64decode(f'{signature_part}{"=" * (-len(signature_part) % 4)}'.encode('ascii'))
        except Exception as exc:  # noqa: BLE001
            raise ValueError('Invalid media proxy token.') from exc

        expected_signature = hmac.new(self.signing_secret, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(signature_bytes, expected_signature):
            raise ValueError('Invalid media proxy signature.')

        try:
            payload = json.loads(payload_bytes.decode('utf-8'))
        except Exception as exc:  # noqa: BLE001
            raise ValueError('Invalid media proxy token.') from exc
        if not isinstance(payload, dict):
            raise ValueError('Invalid media proxy token payload.')
        return payload

    def _sign_payload(self, payload_bytes: bytes) -> str:
        signature = hmac.new(self.signing_secret, payload_bytes, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')

    async def resolve_proxy_token(self, token: str) -> tuple[Path, str]:
        preferred_url, source_url = self._decode_proxy_token(token)
        key_seed = f'{preferred_url}\n{source_url}'.encode('utf-8')
        cache_key = hashlib.sha256(key_seed).hexdigest()[:40]

        existing = self._cached_file_for_key(cache_key)
        if existing is not None:
            return existing, self._media_type_for_path(existing)

        image_url, content_type, data = await self._resolve_image_bytes(preferred_url=preferred_url, source_url=source_url)
        ext = self._extension_for_image(image_url=image_url, content_type=content_type)
        target = self.base_dir / f'{cache_key}{ext}'
        temp = self.base_dir / f'{cache_key}.tmp'
        temp.write_bytes(data)
        temp.replace(target)
        logger.info(
            'media_cache.store url=%s source=%s path=%s bytes=%s content_type=%s',
            image_url,
            source_url,
            target.name,
            len(data),
            content_type,
        )
        return target, self._media_type_for_path(target, fallback=content_type)

    def _cached_file_for_key(self, cache_key: str) -> Path | None:
        matches = sorted(self.base_dir.glob(f'{cache_key}.*'))
        if not matches:
            return None
        candidate = matches[0]
        if candidate.exists() and candidate.is_file():
            return candidate
        return None

    async def _resolve_image_bytes(self, *, preferred_url: str, source_url: str) -> tuple[str, str, bytes]:
        direct_candidates: list[tuple[str, str]] = []
        direct_candidates.append((preferred_url, source_url or preferred_url))
        if source_url and source_url != preferred_url:
            direct_candidates.append((source_url, source_url))

        for candidate, referer in direct_candidates:
            fetched = await self._fetch_direct_image(candidate, referer_url=referer)
            if fetched is not None:
                return fetched

        page_candidates = [source_url, preferred_url]
        seen_pages: set[str] = set()
        for page_url in page_candidates:
            clean = (page_url or '').strip()
            if not clean or clean in seen_pages:
                continue
            seen_pages.add(clean)
            html_doc = await self._fetch_html(clean)
            if html_doc is None:
                continue
            resolved_page_url, html_text = html_doc
            extracted_urls = self._extract_image_urls_from_html(html_text, base_url=resolved_page_url)
            for candidate_url in extracted_urls:
                fetched = await self._fetch_direct_image(candidate_url, referer_url=resolved_page_url)
                if fetched is not None:
                    return fetched

        raise ValueError('Unable to resolve a renderable image for this media reference.')

    def _domain_for_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
        except ValueError:
            return ''
        host = (parsed.netloc or '').lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        return host

    def _prune_domain_block_cache(self) -> None:
        now = time.time()
        expired = [domain for domain, until_ts in self._blocked_domains_until.items() if until_ts <= now]
        for domain in expired:
            self._blocked_domains_until.pop(domain, None)

    def is_domain_temporarily_blocked(self, url_or_domain: str) -> bool:
        self._prune_domain_block_cache()
        candidate = (url_or_domain or '').strip().lower()
        if not candidate:
            return False
        domain = self._domain_for_url(candidate) if candidate.startswith('http') else candidate
        if not domain:
            return False
        until_ts = self._blocked_domains_until.get(domain)
        return bool(until_ts and until_ts > time.time())

    def _mark_domain_temporarily_blocked(self, *, url: str, status_code: int) -> None:
        domain = self._domain_for_url(url)
        if not domain:
            return
        self._blocked_domains_until[domain] = time.time() + float(self.domain_block_ttl_seconds)
        logger.info('media_cache.domain_blocked domain=%s status=%s ttl_seconds=%s', domain, status_code, self.domain_block_ttl_seconds)

    async def _fetch_direct_image(self, url: str, *, referer_url: str = '') -> tuple[str, str, bytes] | None:
        clean = (url or '').strip()
        if not self._is_safe_http_url(clean):
            return None
        if self.is_domain_temporarily_blocked(clean):
            return None

        attempts: list[dict[str, str]] = []
        primary_headers = {
            'Accept': _DEFAULT_ACCEPT,
            'User-Agent': _DEFAULT_UA,
            'Accept-Language': _DEFAULT_ACCEPT_LANGUAGE,
        }
        if self._is_safe_http_url(referer_url):
            primary_headers['Referer'] = referer_url
        attempts.append(primary_headers)
        attempts.append(
            {
                'Accept': _DEFAULT_ACCEPT,
                'User-Agent': _DEFAULT_UA,
                'Accept-Language': _DEFAULT_ACCEPT_LANGUAGE,
            }
        )

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = None
            for headers in attempts:
                try:
                    response = await client.get(clean, headers=headers)
                except httpx.HTTPError:
                    continue
                if 200 <= response.status_code < 300:
                    break
                if response.status_code in {401, 403, 429}:
                    self._mark_domain_temporarily_blocked(url=clean, status_code=response.status_code)
            if response is None:
                return None
        if response.status_code < 200 or response.status_code >= 300:
            return None

        final_url = str(response.url)
        if not self._is_safe_http_url(final_url):
            return None
        content_type = (response.headers.get('content-type') or '').split(';', 1)[0].strip().lower()
        if not content_type.startswith('image/'):
            return None
        data = bytes(response.content or b'')
        if len(data) < 128 or len(data) > self.max_bytes:
            return None
        if not self._passes_image_quality_gate(data=data, content_type=content_type):
            logger.info(
                'media_cache.reject_low_quality_image url=%s content_type=%s bytes=%s',
                final_url,
                content_type,
                len(data),
            )
            return None
        return final_url, content_type, data

    async def _fetch_html(self, url: str) -> tuple[str, str] | None:
        clean = (url or '').strip()
        if not self._is_safe_http_url(clean):
            return None
        if self.is_domain_temporarily_blocked(clean):
            return None
        headers = {
            'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
            'User-Agent': _DEFAULT_UA,
            'Accept-Language': _DEFAULT_ACCEPT_LANGUAGE,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            try:
                response = await client.get(clean, headers=headers)
            except httpx.HTTPError:
                return None
        if response.status_code in {401, 403, 429}:
            self._mark_domain_temporarily_blocked(url=clean, status_code=response.status_code)
            return None
        if response.status_code < 200 or response.status_code >= 300:
            return None
        final_url = str(response.url)
        if not self._is_safe_http_url(final_url):
            return None

        content_type = (response.headers.get('content-type') or '').split(';', 1)[0].strip().lower()
        if content_type and 'html' not in content_type:
            return None

        body = bytes(response.content or b'')
        if not body:
            return None
        if len(body) > _MAX_HTML_BYTES:
            body = body[:_MAX_HTML_BYTES]
        try:
            text = body.decode('utf-8', errors='ignore')
        except Exception:  # noqa: BLE001
            return None
        if '<html' not in text.lower() and '<head' not in text.lower():
            return None
        return final_url, text

    def _extract_image_urls_from_html(self, html_text: str, *, base_url: str) -> list[str]:
        candidates: list[str] = []

        meta_patterns = [
            re.compile(
                r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
                re.IGNORECASE,
            ),
            re.compile(
                r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
                re.IGNORECASE,
            ),
            re.compile(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
                re.IGNORECASE,
            ),
            re.compile(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
                re.IGNORECASE,
            ),
        ]
        img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

        for pattern in meta_patterns:
            for match in pattern.finditer(html_text):
                raw = html_lib.unescape((match.group(1) or '').strip())
                if raw:
                    candidates.append(raw)
        for match in img_pattern.finditer(html_text):
            raw = html_lib.unescape((match.group(1) or '').strip())
            if raw:
                candidates.append(raw)

        resolved: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            url = urljoin(base_url, candidate)
            if url in seen:
                continue
            seen.add(url)
            if not self._is_safe_http_url(url):
                continue
            resolved.append(url)
            if len(resolved) >= 12:
                break
        return resolved

    def _is_safe_http_url(self, url: str) -> bool:
        candidate = (url or '').strip()
        if not candidate:
            return False
        try:
            parsed = urlparse(candidate)
        except Exception:  # noqa: BLE001
            return False
        if parsed.scheme not in {'http', 'https'}:
            return False
        host = (parsed.hostname or '').lower().strip()
        if not host:
            return False
        if host in _BLOCKED_HOSTS or host.endswith('.local'):
            return False

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is not None and (
            ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
        ):
            return False
        return True

    def _extension_for_image(self, *, image_url: str, content_type: str) -> str:
        content = (content_type or '').lower()
        if content == 'image/jpeg':
            return '.jpg'
        if content == 'image/png':
            return '.png'
        if content == 'image/webp':
            return '.webp'
        if content == 'image/gif':
            return '.gif'
        if content == 'image/svg+xml':
            return '.svg'
        if content == 'image/avif':
            return '.avif'
        parsed = urlparse(image_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.avif'}:
            return suffix
        guessed = mimetypes.guess_extension(content_type or '') or ''
        if guessed.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.avif'}:
            return guessed.lower()
        return '.jpg'

    def _passes_image_quality_gate(self, *, data: bytes, content_type: str) -> bool:
        kind = (content_type or '').lower()
        if kind == 'image/svg+xml':
            # SVG dimensions are expensive to infer robustly; gate by minimum payload size.
            return len(data) >= 1500

        dimensions = self._extract_image_dimensions(data=data, content_type=kind)
        if not dimensions:
            # If dimensions are unavailable, fall back to payload-size heuristic.
            return len(data) >= 22_000

        width, height = dimensions
        if width <= 0 or height <= 0:
            return False
        pixels = width * height
        long_edge = max(width, height)
        return pixels >= self.min_image_pixels and long_edge >= self.min_image_long_edge

    def _extract_image_dimensions(self, *, data: bytes, content_type: str) -> tuple[int, int] | None:
        if content_type == 'image/png':
            return self._png_dimensions(data)
        if content_type == 'image/jpeg':
            return self._jpeg_dimensions(data)
        if content_type == 'image/gif':
            return self._gif_dimensions(data)
        if content_type == 'image/webp':
            return self._webp_dimensions(data)
        if content_type == 'image/avif':
            return None
        return None

    def _png_dimensions(self, data: bytes) -> tuple[int, int] | None:
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            return None
        if data[12:16] != b'IHDR':
            return None
        width = int.from_bytes(data[16:20], 'big')
        height = int.from_bytes(data[20:24], 'big')
        return width, height

    def _gif_dimensions(self, data: bytes) -> tuple[int, int] | None:
        if len(data) < 10 or not (data.startswith(b'GIF87a') or data.startswith(b'GIF89a')):
            return None
        width = int.from_bytes(data[6:8], 'little')
        height = int.from_bytes(data[8:10], 'little')
        return width, height

    def _jpeg_dimensions(self, data: bytes) -> tuple[int, int] | None:
        if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
            return None
        index = 2
        size = len(data)
        while index + 9 < size:
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > size:
                break
            segment_length = int.from_bytes(data[index:index + 2], 'big')
            if segment_length < 2 or index + segment_length > size:
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if index + 7 >= size:
                    break
                height = int.from_bytes(data[index + 3:index + 5], 'big')
                width = int.from_bytes(data[index + 5:index + 7], 'big')
                return width, height
            index += segment_length
        return None

    def _webp_dimensions(self, data: bytes) -> tuple[int, int] | None:
        if len(data) < 30 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
            return None
        chunk = data[12:16]
        if chunk == b'VP8X' and len(data) >= 30:
            width_minus_one = int.from_bytes(data[24:27], 'little')
            height_minus_one = int.from_bytes(data[27:30], 'little')
            return width_minus_one + 1, height_minus_one + 1
        if chunk == b'VP8 ' and len(data) >= 30:
            # Lossy VP8 frame dimensions are stored in little endian at offsets 26..30.
            width = int.from_bytes(data[26:28], 'little') & 0x3FFF
            height = int.from_bytes(data[28:30], 'little') & 0x3FFF
            if width and height:
                return width, height
        if chunk == b'VP8L' and len(data) >= 25:
            b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
            width = 1 + (((b1 & 0x3F) << 8) | b0)
            height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
            if width and height:
                return width, height
        return None

    def _media_type_for_path(self, path: Path, *, fallback: str | None = None) -> str:
        guessed = mimetypes.guess_type(str(path))[0]
        if guessed:
            return guessed
        if fallback and fallback.startswith('image/'):
            return fallback
        return 'application/octet-stream'
