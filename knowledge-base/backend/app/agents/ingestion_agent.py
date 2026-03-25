from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk
from app.services.embedding import EmbeddingService
from app.utils.text import chunk_text


logger = logging.getLogger(__name__)


class IngestionAgent:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service
        self.settings = get_settings()

    async def ingest_text(
        self,
        db: Session,
        *,
        topic_id: int,
        user_id: int,
        filename: str,
        content_type: str,
        text: str,
        note_id: int | None = None,
    ) -> tuple[Document, int]:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError('Cannot ingest empty text.')

        document = Document(
            topic_id=topic_id,
            user_id=user_id,
            note_id=note_id,
            filename=filename,
            content_type=content_type,
            raw_text=cleaned,
        )
        db.add(document)
        db.flush()

        chunks = chunk_text(cleaned, max_chars=self.settings.max_note_chunk_chars)
        embeddings = await self.embedding_service.embed_texts(chunks)

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    topic_id=topic_id,
                    chunk_index=idx,
                    text=chunk,
                    embedding=embedding,
                )
            )

        db.commit()
        db.refresh(document)

        logger.info(
            'ingestion.complete topic_id=%s document_id=%s chunks=%s filename=%s',
            topic_id,
            document.id,
            len(chunks),
            filename,
        )
        return document, len(chunks)
