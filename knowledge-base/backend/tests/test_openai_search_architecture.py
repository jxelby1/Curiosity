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


def test_search_images_keeps_direct_image_urls_even_when_kind_is_article() -> None:
    service = ExternalSearchService()

    async def fake_openai_web_search(**_: object) -> list[SearchResult]:
        return [
            SearchResult(
                title='Street photography exemplar',
                url='https://cdn.example.org/visuals/street-photography-exemplar.jpg',
                kind='external_article',
                summary='Direct image asset for composition study.',
                source_domain='cdn.example.org',
                relevance_score=0.74,
            ),
            SearchResult(
                title='Wikimedia file',
                url='https://commons.wikimedia.org/wiki/File:Chapter-1.jpg',
                kind='external_image',
                summary='Generic reference image',
                source_domain='commons.wikimedia.org',
                relevance_score=0.82,
            ),
        ]

    service._search_with_openai_web = fake_openai_web_search  # type: ignore[assignment]
    output = asyncio.run(
        service.search_images(
            topic='Photography with Intention',
            skill='Light, Timing, and Editing',
            query='street photography composition references',
            limit=3,
            source_policy='strict_media',
        )
    )

    assert len(output) == 1
    assert output[0].url.endswith('.jpg')
    assert output[0].source_domain == 'cdn.example.org'
