from __future__ import annotations

import asyncio

from app.services.search import ExternalSearchService, SearchResult


def test_source_policy_blocks_social_and_stock_domains() -> None:
    service = ExternalSearchService()
    results = [
        SearchResult(
            title='Good reference',
            url='https://en.wikipedia.org/wiki/Chalk_Farm',
            kind='external_article',
            summary='History and geography context',
            source_domain='wikipedia.org',
            relevance_score=0.62,
        ),
        SearchResult(
            title='Social clip',
            url='https://www.facebook.com/watch/123',
            kind='external_video',
            summary='Random clip',
            source_domain='facebook.com',
            relevance_score=0.9,
        ),
        SearchResult(
            title='Stock photo listing',
            url='https://www.gettyimages.com/photos/chalk-farm',
            kind='external_image',
            summary='Stock imagery',
            source_domain='gettyimages.com',
            relevance_score=0.87,
        ),
    ]
    filtered = service._apply_source_policy(results=results, source_policy='grounding', limit=5)
    assert len(filtered) == 1
    assert filtered[0].source_domain == 'wikipedia.org'


def test_search_prefers_openai_web_provider_path() -> None:
    service = ExternalSearchService()
    service.settings.search_provider = 'openai_web'

    async def fake_openai_web_search(**_: object) -> list[SearchResult]:
        return [
            SearchResult(
                title='Reference',
                url='https://www.britannica.com/place/Chalk-Farm',
                kind='external_article',
                summary='Context',
                source_domain='britannica.com',
                relevance_score=0.66,
            )
        ]

    service._search_with_openai_web = fake_openai_web_search  # type: ignore[assignment]
    output = asyncio.run(
        service.search(
            topic='Chalk Farm',
            skill='Hidden local spots',
            query='chalk farm hidden gems',
            limit=3,
            source_policy='grounding',
        )
    )

    assert len(output) == 1
    assert output[0].source_domain == 'britannica.com'
