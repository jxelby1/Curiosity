from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.services.embedding import EmbeddingService


logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: int
    text: str
    score: float


class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service

    async def retrieve_chunks(
        self,
        db: Session,
        *,
        topic_id: int,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        query_embedding = await self.embedding_service.embed_text(query)

        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        rows = db.execute(
            select(DocumentChunk, distance.label('distance'))
            .where(DocumentChunk.topic_id == topic_id)
            .order_by(distance)
            .limit(top_k)
        ).all()

        results: list[RetrievedChunk] = []
        for chunk, dist in rows:
            similarity = max(0.0, 1.0 - float(dist))
            results.append(RetrievedChunk(chunk_id=chunk.id, text=chunk.text, score=similarity))

        logger.info('retrieval.complete topic_id=%s top_k=%s hits=%s', topic_id, top_k, len(results))
        return results
