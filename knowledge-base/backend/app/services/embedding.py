from __future__ import annotations

import logging
import time

from openai import APIError, APITimeoutError, AsyncOpenAI

from app.core.config import get_settings
from app.core.exceptions import ProviderError


logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.openai_api_key:
            raise ProviderError('OPENAI_API_KEY is required for embeddings.')

        self.client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
        )
        self.model = self.settings.openai_embedding_model
        self.expected_dimensions = self.settings.embedding_dimensions

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        started = time.perf_counter()
        logger.info('openai.embedding.start model=%s batch_size=%s', self.model, len(texts))
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
        except (APITimeoutError, APIError) as exc:
            logger.exception('openai.embedding.error model=%s', self.model)
            raise ProviderError(f'OpenAI embedding call failed: {exc}') from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info('openai.embedding.complete model=%s latency_ms=%s', self.model, elapsed_ms)

        vectors = [item.embedding for item in response.data]
        for idx, vector in enumerate(vectors):
            if len(vector) != self.expected_dimensions:
                raise ProviderError(
                    f'Embedding dimension mismatch at index {idx}: got {len(vector)}, '
                    f'expected {self.expected_dimensions}. '
                    'Set EMBEDDING_DIMENSIONS to match OPENAI_EMBEDDING_MODEL.'
                )
        return vectors
