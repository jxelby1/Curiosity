from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
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


@dataclass
class SearchResult:
    title: str
    url: str
    kind: str
    summary: str
    source_domain: str = ''
    relevance_score: float = 0.0


class _OpenAIWebResult(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    url: str = Field(min_length=8, max_length=600)
    kind: Literal['external_article', 'external_video', 'external_documentation', 'external_image'] = 'external_article'
    summary: str = Field(default='', max_length=420)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)


class _OpenAIWebResponse(BaseModel):
    results: list[_OpenAIWebResult] = Field(default_factory=list, max_length=20)


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
                if not self._is_trusted_domain(domain):
                    continue
                if item.kind not in {'external_video', 'external_image', 'external_article', 'external_documentation'}:
                    continue
                if item.relevance_score < 0.2:
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
        user_prompt = (
            f'Topic: {topic}\n'
            f'Skill focus: {skill}\n'
            f'Search query: {query}\n'
            f'Result limit: {max(4, min(12, limit * 2))}\n'
            f'Policy: {policy_instruction}\n\n'
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

        try:
            response = await self.client.responses.create(
                model=self.settings.openai_web_search_model,
                input=[
                    {
                        'role': 'system',
                        'content': (
                            'You are a web research agent. Search the web, reason over sources, and return only '
                            'high-signal results in strict JSON.'
                        ),
                    },
                    {'role': 'user', 'content': user_prompt},
                ],
                tools=[{'type': 'web_search_preview'}],
                temperature=0.0,
                max_output_tokens=1200,
            )
        except (APITimeoutError, APIError) as exc:
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

    async def _search_with_serper(
        self,
        *,
        topic: str,
        skill: str,
        query: str,
        limit: int,
        source_policy: Literal['standard', 'grounding', 'strict_media'],
    ) -> list[SearchResult]:
        if not self.settings.search_api_key:
            raise ConfigurationError(
                'SEARCH_API_KEY is required for Serper search. '
                'Set SEARCH_API_KEY in your backend environment.'
            )
        headers = {
            'X-API-KEY': self.settings.search_api_key,
            'Content-Type': 'application/json',
        }
        payload = {
            'q': query,
            'num': max(8, limit * 3),
            'gl': 'us',
            'hl': 'en',
        }

        simplified_query = self._simplify_query(query, topic=topic, skill=skill)

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                response = await client.post(self.settings.search_base_url, headers=headers, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 400 and simplified_query != query:
                    payload['q'] = simplified_query
                    retry_response = await client.post(self.settings.search_base_url, headers=headers, json=payload)
                    retry_response.raise_for_status()
                    response = retry_response
                else:
                    logger.exception('external_search.error provider=serper query=%s', query)
                    raise ProviderError(f'External search failed: {exc}') from exc
            except httpx.HTTPError as exc:
                logger.exception('external_search.error provider=serper query=%s', query)
                raise ProviderError(f'External search failed: {exc}') from exc

        data = response.json()
        organic = data.get('organic') or []
        videos = data.get('videos') or []
        candidates: list[SearchResult] = []

        for item in organic:
            link = item.get('link') or item.get('url')
            if not link:
                continue
            title = (item.get('title') or 'Untitled result').strip()
            summary = (item.get('snippet') or '').strip()
            kind = self._infer_kind(url=link, title=title, summary=summary, fallback_kind='external_article')
            candidates.append(
                SearchResult(
                    title=title,
                    url=link,
                    kind=kind,
                    summary=summary,
                    source_domain=self._domain_for_url(link),
                    relevance_score=0.35,
                )
            )

        for item in videos:
            link = item.get('link') or item.get('url')
            if not link:
                continue
            title = (item.get('title') or 'Untitled video').strip()
            summary = (item.get('snippet') or '').strip()
            candidates.append(
                SearchResult(
                    title=title,
                    url=link,
                    kind='external_video',
                    summary=summary,
                    source_domain=self._domain_for_url(link),
                    relevance_score=0.42,
                )
            )

        return self._apply_source_policy(results=candidates, source_policy=source_policy, limit=limit)

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
            'external_search.start provider=%s policy=%s query=%s',
            self.settings.search_provider,
            source_policy,
            final_query,
        )

        if self.settings.search_provider == 'openai_web':
            try:
                results = await self._search_with_openai_web(
                    topic=topic,
                    skill=skill,
                    query=final_query,
                    limit=limit,
                    source_policy=source_policy,
                )
            except ProviderError as exc:
                if self.settings.search_api_key:
                    logger.warning('external_search.openai_web_failed_fallback_to_serper error=%s', exc)
                    results = await self._search_with_serper(
                        topic=topic,
                        skill=skill,
                        query=final_query,
                        limit=limit,
                        source_policy=source_policy,
                    )
                else:
                    raise
        elif self.settings.search_provider == 'serper':
            results = await self._search_with_serper(
                topic=topic,
                skill=skill,
                query=final_query,
                limit=limit,
                source_policy=source_policy,
            )
        else:
            raise ConfigurationError(f'Unsupported search provider: {self.settings.search_provider}')

        logger.info(
            'external_search.complete provider=%s policy=%s query=%s results=%s',
            self.settings.search_provider,
            source_policy,
            final_query,
            len(results),
        )
        return results
