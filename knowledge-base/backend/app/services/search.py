from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from openai import APIError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, ProviderError


logger = logging.getLogger(__name__)

_BLOCKED_SOURCE_DOMAINS = (
    'facebook.com',
    'fb.watch',
    'instagram.com',
    'tiktok.com',
    'x.com',
    'twitter.com',
    'threads.net',
    'snapchat.com',
    'pinterest.com',
    'reddit.com',
    'gettyimages.com',
    'istockphoto.com',
    'shutterstock.com',
    'stock.adobe.com',
    'adobestock.com',
    'dreamstime.com',
    'alamy.com',
    'depositphotos.com',
    '123rf.com',
)
_TRUSTED_GROUNDING_DOMAINS = (
    'wikipedia.org',
    'wikimedia.org',
    'britannica.com',
    'nationalgeographic.com',
    'history.com',
    'bbc.com',
    'bbc.co.uk',
    'reuters.com',
    'apnews.com',
    'nytimes.com',
    'washingtonpost.com',
    'theguardian.com',
    'economist.com',
    'bloomberg.com',
    'ft.com',
    'wsj.com',
    'pbs.org',
    'khanacademy.org',
    'openstax.org',
    'metmuseum.org',
    'moma.org',
    'tate.org.uk',
    'si.edu',
    'loc.gov',
    'archives.gov',
    'nasa.gov',
    'noaa.gov',
    'usgs.gov',
    'worldbank.org',
    'oecd.org',
    'imf.org',
    'who.int',
    'un.org',
    'unesco.org',
    'youtube.com',
    'youtu.be',
)
_DEEMPHASIZED_IMAGE_DOMAINS = (
    'wikipedia.org',
    'wikimedia.org',
)
_DIRECT_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif')


@dataclass
class SearchResult:
    title: str
    url: str
    kind: str
    summary: str
    source_domain: str = ''
    relevance_score: float = 0.0


@dataclass
class LessonMediaCandidate:
    title: str
    url: str
    media_type: Literal['image', 'video']
    source_domain: str = ''
    relevance_score: float = 0.0
    relevance_reason: str = ''
    preview_url: str = ''


class _OpenAIWebResult(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    url: str = Field(min_length=8, max_length=600)
    kind: Literal['external_article', 'external_video', 'external_documentation', 'external_image'] = 'external_article'
    summary: str = Field(default='', max_length=420)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)


class _OpenAIWebResponse(BaseModel):
    results: list[_OpenAIWebResult] = Field(default_factory=list, max_length=20)


class _OpenAILessonMediaCandidate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    source_url: str = Field(min_length=8, max_length=600)
    media_url: str = Field(min_length=8, max_length=600)
    source_domain: str = Field(default='', max_length=180)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_reason: str = Field(default='', max_length=320)


class _OpenAILessonMediaResponse(BaseModel):
    image_query: str = Field(min_length=3, max_length=240)
    video_query: str = Field(min_length=3, max_length=240)
    image_candidates: list[_OpenAILessonMediaCandidate] = Field(default_factory=list, max_length=12)
    video_candidates: list[_OpenAILessonMediaCandidate] = Field(default_factory=list, max_length=12)
    agent_decision: str = Field(default='', max_length=320)


class ExternalSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = (
            AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_seconds,
            )
            if self.settings.openai_api_key
            else None
        )

    def _simplify_query(self, query: str, *, topic: str, skill: str) -> str:
        cleaned = ' '.join((query or '').replace('\n', ' ').split())
        cleaned = cleaned.replace('site:.edu', 'site:edu')
        cleaned = cleaned.replace('(', ' ').replace(')', ' ')
        cleaned = re.sub(r'\bOR\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('?', ' ').replace(':', ' ')
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        if len(cleaned) > 220:
            cleaned = cleaned[:220]
            if ' ' in cleaned:
                cleaned = cleaned.rsplit(' ', 1)[0]

        if len(cleaned) < 10:
            cleaned = f'{topic} {skill} overview image video map'

        return cleaned

    def _domain_for_url(self, url: str) -> str:
        parsed = urlparse(url)
        netloc = (parsed.netloc or '').lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        return netloc

    @staticmethod
    def _looks_like_json_object(text: str) -> str:
        cleaned = (text or '').strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start >= 0 and end > start:
            return cleaned[start : end + 1]
        return cleaned

    def _is_blocked_domain(self, domain: str) -> bool:
        if not domain:
            return True
        return any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _BLOCKED_SOURCE_DOMAINS)

    def _is_trusted_domain(self, domain: str) -> bool:
        if not domain:
            return False
        if domain.endswith('.gov') or domain.endswith('.edu'):
            return True
        return any(domain == allowed or domain.endswith(f'.{allowed}') for allowed in _TRUSTED_GROUNDING_DOMAINS)

    def _is_deemphasized_image_domain(self, domain: str) -> bool:
        if not domain:
            return False
        return any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _DEEMPHASIZED_IMAGE_DOMAINS)

    def _strict_json_schema(self, schema: Any) -> Any:
        if isinstance(schema, list):
            return [self._strict_json_schema(item) for item in schema]
        if not isinstance(schema, dict):
            return schema

        normalized = {key: self._strict_json_schema(value) for key, value in schema.items()}
        schema_type = normalized.get('type')
        if schema_type == 'object' or 'properties' in normalized:
            properties = normalized.get('properties')
            if isinstance(properties, dict) and properties:
                normalized['required'] = list(properties.keys())
            normalized['additionalProperties'] = False
        return normalized

    def _structured_search_format(self) -> dict[str, object]:
        strict_schema = self._strict_json_schema(_OpenAIWebResponse.model_json_schema())
        return {
            'format': {
                'type': 'json_schema',
                'name': 'web_search_results',
                'description': 'Structured web-search results with relevance scoring.',
                'schema': strict_schema,
                'strict': True,
            }
        }

    def _structured_media_selection_format(self) -> dict[str, object]:
        # Explicit hand-authored schema to keep OpenAI Responses strict-mode validation stable.
        return {
            'format': {
                'type': 'json_schema',
                'name': 'lesson_media_selection',
                'description': 'Structured lesson media candidates from Google Images and YouTube queries.',
                'schema': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['image_query', 'video_query', 'image_candidates', 'video_candidates', 'agent_decision'],
                    'properties': {
                        'image_query': {'type': 'string'},
                        'video_query': {'type': 'string'},
                        'image_candidates': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'required': [
                                    'title',
                                    'source_url',
                                    'media_url',
                                    'source_domain',
                                    'relevance_score',
                                    'relevance_reason',
                                ],
                                'properties': {
                                    'title': {'type': 'string'},
                                    'source_url': {'type': 'string'},
                                    'media_url': {'type': 'string'},
                                    'source_domain': {'type': 'string'},
                                    'relevance_score': {'type': 'number'},
                                    'relevance_reason': {'type': 'string'},
                                },
                            },
                        },
                        'video_candidates': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'required': [
                                    'title',
                                    'source_url',
                                    'media_url',
                                    'source_domain',
                                    'relevance_score',
                                    'relevance_reason',
                                ],
                                'properties': {
                                    'title': {'type': 'string'},
                                    'source_url': {'type': 'string'},
                                    'media_url': {'type': 'string'},
                                    'source_domain': {'type': 'string'},
                                    'relevance_score': {'type': 'number'},
                                    'relevance_reason': {'type': 'string'},
                                },
                            },
                        },
                        'agent_decision': {'type': 'string'},
                    },
                },
                'strict': True,
            }
        }

    def _salvage_results_from_text(self, raw_text: str, *, limit: int) -> list[SearchResult]:
        text = (raw_text or '').strip()
        if not text:
            return []
        candidates: list[SearchResult] = []
        seen_urls: set[str] = set()

        def _append_candidate(title: str, url: str, summary: str, score: float) -> None:
            clean_url = (url or '').strip().rstrip(').,;')
            if not clean_url or not clean_url.startswith('http'):
                return
            if clean_url in seen_urls:
                return
            seen_urls.add(clean_url)
            domain = self._domain_for_url(clean_url)
            if self._is_blocked_domain(domain):
                return
            kind = self._infer_kind(url=clean_url, title=title, summary=summary, fallback_kind='external_article')
            candidates.append(
                SearchResult(
                    title=(title or 'Web reference').strip()[:240],
                    url=clean_url,
                    kind=kind,
                    summary=(summary or '').strip()[:420],
                    source_domain=domain,
                    relevance_score=max(0.16, min(1.0, score)),
                )
            )

        markdown_links = list(re.finditer(r'\[([^\]]{2,240})\]\((https?://[^\s)]+)\)', text))
        for idx, match in enumerate(markdown_links):
            title = match.group(1).strip()
            url = match.group(2).strip()
            start = max(0, match.start() - 180)
            end = min(len(text), match.end() + 180)
            context = re.sub(r'\s+', ' ', text[start:end]).strip()
            _append_candidate(title, url, context, 0.54 - min(0.2, idx * 0.03))

        if len(candidates) < max(4, limit):
            plain_urls = re.finditer(r'https?://[^\s)\]]+', text)
            for idx, match in enumerate(plain_urls):
                url = match.group(0).strip()
                start = max(0, match.start() - 120)
                end = min(len(text), match.end() + 120)
                context = re.sub(r'\s+', ' ', text[start:end]).strip()
                title = context[:140] if context else 'Web reference'
                _append_candidate(title, url, context, 0.4 - min(0.2, idx * 0.02))

        deduped: list[SearchResult] = []
        for item in sorted(candidates, key=lambda candidate: candidate.relevance_score, reverse=True):
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def _salvage_media_candidates_from_text(
        self,
        raw_text: str,
        *,
        image_query: str,
        video_query: str,
        limit_images: int,
        limit_videos: int,
    ) -> _OpenAILessonMediaResponse:
        text = (raw_text or '').strip()
        markdown_links = list(re.finditer(r'\[([^\]]{2,240})\]\((https?://[^\s)]+)\)', text))
        plain_urls = list(re.finditer(r'https?://[^\s)\]]+', text))

        image_candidates: list[_OpenAILessonMediaCandidate] = []
        video_candidates: list[_OpenAILessonMediaCandidate] = []
        seen: set[str] = set()

        def _append_candidate(title: str, source_url: str, media_url: str, score: float, reason: str) -> None:
            clean_source = source_url.strip().rstrip(').,;')
            clean_media = media_url.strip().rstrip(').,;')
            if not clean_source.startswith('http') or not clean_media.startswith('http'):
                return
            key = f'{clean_source}|{clean_media}'
            if key in seen:
                return
            seen.add(key)
            domain = self._domain_for_url(clean_source) or self._domain_for_url(clean_media)
            if self._is_blocked_domain(domain):
                return
            lowered = f'{title} {clean_source} {clean_media}'.lower()
            if 'youtube.com' in lowered or 'youtu.be' in lowered:
                video_candidates.append(
                    _OpenAILessonMediaCandidate(
                        title=(title or 'YouTube reference').strip()[:240],
                        source_url=clean_source,
                        media_url=clean_media,
                        source_domain=domain,
                        relevance_score=max(0.2, min(1.0, score)),
                        relevance_reason=reason[:320],
                    )
                )
            elif self._is_direct_image_url(clean_media) or self._is_direct_image_url(clean_source):
                image_candidates.append(
                    _OpenAILessonMediaCandidate(
                        title=(title or 'Image reference').strip()[:240],
                        source_url=clean_source,
                        media_url=clean_media if self._is_direct_image_url(clean_media) else clean_source,
                        source_domain=domain,
                        relevance_score=max(0.2, min(1.0, score)),
                        relevance_reason=reason[:320],
                    )
                )

        for idx, match in enumerate(markdown_links):
            title = match.group(1).strip()
            url = match.group(2).strip()
            score = 0.55 - min(0.2, idx * 0.03)
            _append_candidate(title, url, url, score, 'Recovered from OpenAI web-search output.')

        for idx, match in enumerate(plain_urls):
            url = match.group(0).strip()
            score = 0.36 - min(0.18, idx * 0.02)
            _append_candidate('Web media candidate', url, url, score, 'Recovered from OpenAI web-search output.')

        return _OpenAILessonMediaResponse(
            image_query=image_query,
            video_query=video_query,
            image_candidates=image_candidates[:limit_images],
            video_candidates=video_candidates[:limit_videos],
            agent_decision='Recovered media candidates via URL salvage because structured output was invalid.',
        )

    def _infer_kind(self, *, url: str, title: str, summary: str, fallback_kind: str) -> str:
        lowered = f'{title} {summary} {url}'.lower()
        domain = self._domain_for_url(url)
        if fallback_kind in {'external_video', 'external_image', 'external_documentation'}:
            return fallback_kind
        if 'youtube.com' in domain or 'youtu.be' in domain or any(token in lowered for token in ('video', 'documentary', 'lecture')):
            return 'external_video'
        if any(token in lowered for token in ('docs', 'documentation', 'readthedocs', 'manual', 'reference')):
            return 'external_documentation'
        if url.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')):
            return 'external_image'
        return 'external_article'

    def _is_direct_image_url(self, url: str) -> bool:
        lowered = (url or '').lower().split('?', 1)[0].split('#', 1)[0]
        return lowered.endswith(_DIRECT_IMAGE_EXTENSIONS)

    def _apply_source_policy(
        self,
        *,
        results: list[SearchResult],
        source_policy: Literal['standard', 'grounding', 'strict_media'],
        limit: int,
    ) -> list[SearchResult]:
        filtered: list[SearchResult] = []
        for item in results:
            domain = item.source_domain or self._domain_for_url(item.url)
            if self._is_blocked_domain(domain):
                continue

            if source_policy == 'strict_media':
                if item.kind not in {'external_video', 'external_image', 'external_article', 'external_documentation'}:
                    continue
                if item.relevance_score < 0.14:
                    continue
            elif source_policy == 'grounding':
                if item.relevance_score < 0.22 and not self._is_trusted_domain(domain):
                    continue

            filtered.append(
                SearchResult(
                    title=item.title,
                    url=item.url,
                    kind=item.kind,
                    summary=item.summary,
                    source_domain=domain,
                    relevance_score=item.relevance_score,
                )
            )

        deduped: list[SearchResult] = []
        seen_urls: set[str] = set()
        for item in sorted(filtered, key=lambda candidate: candidate.relevance_score, reverse=True):
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    async def _search_with_openai_web(
        self,
        *,
        topic: str,
        skill: str,
        query: str,
        limit: int,
        source_policy: Literal['standard', 'grounding', 'strict_media'],
    ) -> list[SearchResult]:
        if not self.settings.openai_api_key:
            raise ConfigurationError('OPENAI_API_KEY is required for OpenAI web search.')
        if self.client is None:
            raise ConfigurationError('OpenAI web-search client is not configured.')

        policy_instruction = (
            'For media-heavy requests, prioritize educational institutions, museums, archives, major publications, '
            'and reputable reference sources. Exclude social media and stock-photo marketplaces.'
            if source_policy in {'grounding', 'strict_media'}
            else 'Return broadly relevant high-quality sources while still excluding social media and stock-photo marketplaces.'
        )
        media_quality_instruction = (
            'When policy is strict_media, prioritize strongly relevant visual and audiovisual references. '
            'For external_image, return direct renderable asset URLs ending in .jpg/.jpeg/.png/.webp/.gif/.svg when possible. '
            'For external_video, prioritize playable pages such as YouTube or Vimeo. '
            'Avoid weakly related visuals even if they share one keyword.'
            if source_policy == 'strict_media'
            else 'Keep media quality high and relevance-focused.'
        )
        user_prompt = (
            f'Topic: {topic}\n'
            f'Skill focus: {skill}\n'
            f'Search query: {query}\n'
            f'Result limit: {max(4, min(12, limit * 2))}\n'
            f'Policy: {policy_instruction}\n\n'
            f'Media quality: {media_quality_instruction}\n\n'
            'Use web search and return JSON only:\n'
            '{\n'
            '  "results": [\n'
            '    {\n'
            '      "title": "...",\n'
            '      "url": "https://...",\n'
            '      "kind": "external_article|external_video|external_documentation|external_image",\n'
            '      "summary": "one concise sentence",\n'
            '      "relevance_score": 0.0-1.0\n'
            '    }\n'
            '  ]\n'
            '}\n'
            'Only include directly relevant results.'
        )

        base_request_kwargs: dict[str, Any] = {
            'model': self.settings.openai_web_search_model,
            'input': [
                {
                    'role': 'system',
                    'content': (
                        'You are a web research agent. Search the web, reason over sources, and return only '
                        'high-signal results in strict JSON.'
                    ),
                },
                {'role': 'user', 'content': user_prompt},
            ],
            'tools': [{'type': 'web_search_preview'}],
            'temperature': 0.0,
            'max_output_tokens': 1200,
        }

        try:
            response = await self.client.responses.create(
                **base_request_kwargs,
                text=self._structured_search_format(),
            )
        except (APITimeoutError, APIError) as exc:
            if 'invalid_json_schema' in str(exc).lower() or 'response_format' in str(exc).lower():
                logger.warning(
                    'external_search.strict_schema_retry provider=openai_web query=%s error=%s',
                    query,
                    exc,
                )
                try:
                    response = await self.client.responses.create(**base_request_kwargs)
                except (APITimeoutError, APIError) as retry_exc:
                    raise ProviderError(f'OpenAI web search failed: {retry_exc}') from retry_exc
                except Exception as retry_exc:  # noqa: BLE001
                    raise ProviderError(f'OpenAI web search failed: {retry_exc}') from retry_exc
            else:
                raise ProviderError(f'OpenAI web search failed: {exc}') from exc
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f'OpenAI web search failed: {exc}') from exc

        raw_text = (response.output_text or '').strip()
        if not raw_text:
            return []

        candidate_json = self._looks_like_json_object(raw_text)
        try:
            payload = json.loads(candidate_json)
            structured = _OpenAIWebResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning('external_search.parse_failed provider=openai_web error=%s raw=%s', exc, raw_text[:500])
            salvaged = self._salvage_results_from_text(raw_text, limit=max(6, limit * 2))
            if salvaged:
                logger.info(
                    'external_search.parse_salvaged provider=openai_web query=%s salvaged=%s',
                    query,
                    len(salvaged),
                )
                return self._apply_source_policy(results=salvaged, source_policy=source_policy, limit=limit)
            raise ProviderError(f'OpenAI web search returned invalid structured output: {exc}') from exc

        parsed: list[SearchResult] = []
        for item in structured.results:
            url = item.url.strip()
            title = item.title.strip()
            summary = item.summary.strip()
            if not url or not title:
                continue
            domain = self._domain_for_url(url)
            kind = self._infer_kind(url=url, title=title, summary=summary, fallback_kind=item.kind)
            parsed.append(
                SearchResult(
                    title=title,
                    url=url,
                    kind=kind,
                    summary=summary,
                    source_domain=domain,
                    relevance_score=float(item.relevance_score),
                )
            )

        return self._apply_source_policy(results=parsed, source_policy=source_policy, limit=limit)

    async def search(
        self,
        topic: str,
        skill: str,
        *,
        query: str | None = None,
        limit: int = 5,
        source_policy: Literal['standard', 'grounding', 'strict_media'] = 'standard',
    ) -> list[SearchResult]:
        final_query = (query or '').strip() or f'{topic} {skill} tutorial documentation guide'
        final_query = self._simplify_query(final_query, topic=topic, skill=skill)

        logger.info(
            'external_search.start provider=openai_web policy=%s query=%s',
            source_policy,
            final_query,
        )
        results = await self._search_with_openai_web(
            topic=topic,
            skill=skill,
            query=final_query,
            limit=limit,
            source_policy=source_policy,
        )

        logger.info(
            'external_search.complete provider=openai_web policy=%s query=%s results=%s',
            source_policy,
            final_query,
            len(results),
        )
        return results

    async def search_images(
        self,
        topic: str,
        skill: str,
        *,
        query: str | None = None,
        limit: int = 5,
        source_policy: Literal['standard', 'grounding', 'strict_media'] = 'strict_media',
    ) -> list[SearchResult]:
        final_query = (query or '').strip() or f'{topic} {skill} visual reference example'
        final_query = self._simplify_query(final_query, topic=topic, skill=skill)
        image_query = (
            f'{final_query} high-quality educational image reference '
            'museum archive gallery contextual visual example'
        )[:260]
        logger.info(
            'external_image_search.start provider=openai_web policy=%s query=%s',
            source_policy,
            image_query,
        )

        results = await self._search_with_openai_web(
            topic=topic,
            skill=skill,
            query=image_query,
            limit=max(6, limit * 3),
            source_policy=source_policy,
        )
        image_only = []
        for item in results:
            domain = item.source_domain or self._domain_for_url(item.url)
            if self._is_deemphasized_image_domain(domain):
                continue
            if item.kind == 'external_video':
                continue
            if item.kind != 'external_image' and not self._is_direct_image_url(item.url):
                continue
            image_only.append(item)
        if not image_only:
            # Practical fallback: keep top direct-image URLs from general web results.
            fallback_results = await self.search(
                topic,
                skill,
                query=image_query,
                limit=max(8, limit * 4),
                source_policy='standard',
            )
            for item in fallback_results:
                domain = item.source_domain or self._domain_for_url(item.url)
                if self._is_deemphasized_image_domain(domain) or self._is_blocked_domain(domain):
                    continue
                if self._is_direct_image_url(item.url):
                    image_only.append(
                        SearchResult(
                            title=item.title,
                            url=item.url,
                            kind='external_image',
                            summary=item.summary,
                            source_domain=domain,
                            relevance_score=item.relevance_score,
                        )
                    )
        logger.info(
            'external_image_search.complete provider=openai_web policy=%s query=%s results=%s',
            source_policy,
            image_query,
            len(image_only),
        )
        deduped: list[SearchResult] = []
        seen_urls: set[str] = set()
        for item in sorted(image_only, key=lambda candidate: candidate.relevance_score, reverse=True):
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def _is_direct_video_url(self, url: str) -> bool:
        lowered = (url or '').lower().split('?', 1)[0].split('#', 1)[0]
        return lowered.endswith(('.mp4', '.webm', '.ogg', '.mov', '.m4v'))

    def _normalize_lesson_media_candidates(
        self,
        *,
        candidates: list[_OpenAILessonMediaCandidate],
        media_type: Literal['image', 'video'],
        limit: int,
    ) -> list[LessonMediaCandidate]:
        normalized: list[LessonMediaCandidate] = []
        seen_keys: set[str] = set()

        for item in candidates:
            source_url = item.source_url.strip()
            media_url = item.media_url.strip()
            if not source_url and not media_url:
                continue

            domain = (item.source_domain or '').strip().lower()
            if not domain:
                domain = self._domain_for_url(source_url) or self._domain_for_url(media_url)
            if self._is_blocked_domain(domain):
                continue

            title = item.title.strip()
            if not title:
                continue
            score = float(item.relevance_score)
            reason = item.relevance_reason.strip()

            if media_type == 'image':
                preview_url = media_url if self._is_direct_image_url(media_url) else ''
                if not preview_url and self._is_direct_image_url(source_url):
                    preview_url = source_url
                if not preview_url:
                    continue
                url = source_url or media_url or preview_url
                key = preview_url or url
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                normalized.append(
                    LessonMediaCandidate(
                        title=title,
                        url=url,
                        media_type='image',
                        source_domain=domain,
                        relevance_score=max(0.0, min(1.0, score)),
                        relevance_reason=reason,
                        preview_url=preview_url,
                    )
                )
            else:
                video_url = source_url or media_url
                lowered = f'{source_url} {media_url}'.lower()
                is_embeddable_host = 'youtube.com' in lowered or 'youtu.be' in lowered or 'vimeo.com' in lowered
                if not (is_embeddable_host or self._is_direct_video_url(video_url)):
                    continue
                key = video_url.lower()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                normalized.append(
                    LessonMediaCandidate(
                        title=title,
                        url=video_url,
                        media_type='video',
                        source_domain=domain,
                        relevance_score=max(0.0, min(1.0, score)),
                        relevance_reason=reason,
                    )
                )

            if len(normalized) >= limit:
                break
        return normalized

    async def search_lesson_media_candidates(
        self,
        *,
        topic: str,
        skill: str,
        lesson_title: str,
        lesson_summary: str,
        limit_images: int = 8,
        limit_videos: int = 8,
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise ConfigurationError('OPENAI_API_KEY is required for OpenAI web search.')
        if self.client is None:
            raise ConfigurationError('OpenAI web-search client is not configured.')

        lesson_title_clean = ' '.join((lesson_title or '').split()) or 'Learning reference'
        lesson_summary_clean = ' '.join((lesson_summary or '').split())
        image_query = lesson_title_clean[:180]
        video_query = lesson_title_clean[:180]

        logger.info(
            'external_media_search.start provider=openai_web lesson_title=%s image_query=%s video_query=%s',
            lesson_title_clean,
            image_query,
            video_query,
        )

        user_prompt = (
            f'Topic: {topic}\n'
            f'Skill node: {skill}\n'
            f'Lesson title: {lesson_title_clean}\n'
            f'Lesson summary: {lesson_summary_clean}\n\n'
            'Run two focused web-search tasks and return JSON only:\n'
            f'1) Google Images intent query: "{image_query}"\n'
            f'2) YouTube intent query: "{video_query}"\n\n'
            'For image candidates, provide:\n'
            '- source_url: source page URL\n'
            '- media_url: direct renderable image URL (.jpg/.jpeg/.png/.webp/.gif/.svg)\n'
            '- title, source_domain, relevance_score (0-1), relevance_reason\n\n'
            'For video candidates, provide:\n'
            '- source_url: playable video page URL (prefer YouTube)\n'
            '- media_url: same as source_url unless a direct playable URL is clearly available\n'
            '- title, source_domain, relevance_score (0-1), relevance_reason\n\n'
            'Reject weak matches. Keep candidates tightly aligned to the lesson title.'
        )

        request_kwargs: dict[str, Any] = {
            'model': self.settings.openai_web_search_model,
            'input': [
                {
                    'role': 'system',
                    'content': (
                        'You are a lesson media agent. Use web search to gather high-relevance image and video '
                        'references for the lesson title. Prefer authoritative and educational sources.'
                    ),
                },
                {'role': 'user', 'content': user_prompt},
            ],
            'tools': [{'type': 'web_search_preview'}],
            'temperature': 0.0,
            'max_output_tokens': 1800,
        }

        try:
            response = await self.client.responses.create(
                **request_kwargs,
                text=self._structured_media_selection_format(),
            )
        except (APITimeoutError, APIError) as exc:
            if 'invalid_json_schema' in str(exc).lower() or 'response_format' in str(exc).lower():
                logger.warning(
                    'external_media_search.strict_schema_retry provider=openai_web lesson_title=%s error=%s',
                    lesson_title_clean,
                    exc,
                )
                try:
                    response = await self.client.responses.create(**request_kwargs)
                except (APITimeoutError, APIError) as retry_exc:
                    raise ProviderError(f'OpenAI lesson media search failed: {retry_exc}') from retry_exc
                except Exception as retry_exc:  # noqa: BLE001
                    raise ProviderError(f'OpenAI lesson media search failed: {retry_exc}') from retry_exc
            else:
                raise ProviderError(f'OpenAI lesson media search failed: {exc}') from exc
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f'OpenAI lesson media search failed: {exc}') from exc

        raw_text = (response.output_text or '').strip()
        if not raw_text:
            return {
                'image_query': image_query,
                'video_query': video_query,
                'image_candidates': [],
                'video_candidates': [],
                'agent_decision': 'No output from OpenAI lesson media search.',
            }

        candidate_json = self._looks_like_json_object(raw_text)
        try:
            payload = json.loads(candidate_json)
            structured = _OpenAILessonMediaResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning('external_media_search.parse_failed provider=openai_web error=%s raw=%s', exc, raw_text[:500])
            structured = self._salvage_media_candidates_from_text(
                raw_text,
                image_query=image_query,
                video_query=video_query,
                limit_images=limit_images,
                limit_videos=limit_videos,
            )
            logger.info(
                'external_media_search.parse_salvaged provider=openai_web lesson_title=%s images=%s videos=%s',
                lesson_title_clean,
                len(structured.image_candidates),
                len(structured.video_candidates),
            )

        image_candidates = self._normalize_lesson_media_candidates(
            candidates=list(structured.image_candidates),
            media_type='image',
            limit=limit_images,
        )
        video_candidates = self._normalize_lesson_media_candidates(
            candidates=list(structured.video_candidates),
            media_type='video',
            limit=limit_videos,
        )

        if not image_candidates:
            fallback_image_results = await self.search_images(
                topic=topic,
                skill=skill,
                query=image_query,
                limit=max(4, limit_images * 2),
                source_policy='strict_media',
            )
            image_candidates = [
                LessonMediaCandidate(
                    title=item.title,
                    url=item.url,
                    media_type='image',
                    source_domain=item.source_domain or self._domain_for_url(item.url),
                    relevance_score=item.relevance_score,
                    relevance_reason=item.summary or 'Selected from OpenAI web-search fallback for lesson image support.',
                    preview_url=item.url,
                )
                for item in fallback_image_results
                if self._is_direct_image_url(item.url)
            ][:limit_images]

        if not video_candidates:
            fallback_video_query = f'{video_query} site:youtube.com'
            fallback_video_results = await self.search(
                topic=topic,
                skill=skill,
                query=fallback_video_query,
                limit=max(5, limit_videos * 2),
                source_policy='strict_media',
            )
            video_candidates = []
            for item in fallback_video_results:
                domain = item.source_domain or self._domain_for_url(item.url)
                lowered = f'{item.url} {domain}'.lower()
                if 'youtube.com' not in lowered and 'youtu.be' not in lowered:
                    continue
                video_candidates.append(
                    LessonMediaCandidate(
                        title=item.title,
                        url=item.url,
                        media_type='video',
                        source_domain=domain,
                        relevance_score=max(0.2, item.relevance_score),
                        relevance_reason=item.summary
                        or 'Selected from OpenAI web-search fallback focused on YouTube lesson matches.',
                    )
                )
                if len(video_candidates) >= limit_videos:
                    break

        logger.info(
            'external_media_search.complete provider=openai_web lesson_title=%s image_query=%s video_query=%s image_candidates=%s video_candidates=%s',
            lesson_title_clean,
            structured.image_query,
            structured.video_query,
            len(image_candidates),
            len(video_candidates),
        )

        return {
            'image_query': structured.image_query,
            'video_query': structured.video_query,
            'image_candidates': image_candidates,
            'video_candidates': video_candidates,
            'agent_decision': structured.agent_decision,
        }
