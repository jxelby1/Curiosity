from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, ProviderError


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    kind: str
    summary: str


class ExternalSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(
        self,
        topic: str,
        skill: str,
        *,
        query: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        if self.settings.search_provider != 'serper':
            raise ConfigurationError('Only search provider "serper" is currently supported.')
        if not self.settings.search_api_key:
            raise ConfigurationError(
                'SEARCH_API_KEY is required for external resource search. '
                'Set SEARCH_API_KEY in your backend environment.'
            )

        final_query = (query or '').strip() or f'{topic} {skill} tutorial documentation guide'
        headers = {
            'X-API-KEY': self.settings.search_api_key,
            'Content-Type': 'application/json',
        }
        payload = {
            'q': final_query,
            'num': max(8, limit * 3),
            'gl': 'us',
            'hl': 'en',
        }

        logger.info('external_search.start provider=%s query=%s', self.settings.search_provider, final_query)

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                response = await client.post(self.settings.search_base_url, headers=headers, json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.exception('external_search.error query=%s', final_query)
                raise ProviderError(f'External search failed: {exc}') from exc

        data = response.json()
        organic = data.get('organic') or []
        videos = data.get('videos') or []

        candidates: list[dict] = []
        for item in organic:
            link = item.get('link') or item.get('url')
            if not link:
                continue
            candidates.append(
                {
                    'title': item.get('title', 'Untitled result'),
                    'url': link,
                    'snippet': item.get('snippet', ''),
                }
            )

        for item in videos:
            link = item.get('link') or item.get('url')
            if not link:
                continue
            candidates.append(
                {
                    'title': item.get('title', 'Untitled video'),
                    'url': link,
                    'snippet': item.get('snippet', ''),
                }
            )

        deduped: list[dict] = []
        seen_urls: set[str] = set()
        for candidate in candidates:
            if candidate['url'] in seen_urls:
                continue
            seen_urls.add(candidate['url'])
            deduped.append(candidate)

        results: list[SearchResult] = []
        for candidate in deduped:
            url = candidate['url'].lower()
            if 'youtube.com' in url or 'youtu.be' in url:
                kind = 'external_video'
            elif 'docs.' in url or 'documentation' in url or 'readthedocs' in url:
                kind = 'external_documentation'
            else:
                kind = 'external_article'

            results.append(
                SearchResult(
                    title=candidate['title'],
                    url=candidate['url'],
                    kind=kind,
                    summary=candidate.get('snippet', ''),
                )
            )
            if len(results) >= limit:
                break

        logger.info('external_search.complete query=%s results=%s', final_query, len(results))
        return results
