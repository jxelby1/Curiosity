# Architecture Overview

## Runtime stack

- Frontend: Next.js + React + TypeScript + Tailwind
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL + pgvector
- AI provider: OpenAI Chat Completions + Embeddings
- External web resources: Serper Search API

## Core services

- `LLMService`
  - Executes live OpenAI chat calls.
  - Supports plain text and schema-validated structured JSON generation.
- `EmbeddingService`
  - Executes live OpenAI embedding calls.
  - Validates embedding dimensionality against `EMBEDDING_DIMENSIONS`.
- `RetrievalService`
  - Embeds query text with OpenAI.
  - Performs vector similarity search in `document_chunks.embedding` via pgvector cosine distance.
- `ExternalSearchService`
  - Calls Serper search API to fetch live external results.

## Multi-agent modules

- `SkillGraphAgent`
  - Generates topic-specific skill graph through structured LLM output.
- `IngestionAgent`
  - Stores source documents.
  - Chunks text and stores OpenAI embeddings in pgvector.
- `TutorAgent`
  - Retrieves note chunks and uses live LLM for adaptive tutoring responses.
- `RecommendationAgent`
  - Combines mastery + dependency data + retrieval signals.
  - Uses LLM to produce rationale and recommended action mode.
- `ResourceAgent`
  - Generates lessons/examples/exercises with LLM.
  - Fetches and ranks external resources from live search.
- `AssessmentAgent`
  - Generates quizzes with structured LLM output.
  - Grades submissions and stores attempts.
- `ProfileAgent`
  - Maintains mastery/confidence/status and unlock state transitions.

## Data flow

1. Topic creation triggers `SkillGraphAgent` to generate validated graph nodes and prerequisites.
2. Notes ingestion stores document text and vectorized chunks.
3. Chat requests retrieve similar note chunks and pass context into tutor generation.
4. Recommendation requests combine graph state with LLM reasoning.
5. Resource requests either generate personalized content or fetch/rank live web resources.
6. Quiz generation/submission updates mastery; unlock logic recomputes node availability.

## Initialization and config

- Startup validates required runtime config (`OPENAI_API_KEY`, PostgreSQL URL format).
- DB initialization enables pgvector extension and creates schema.
- Missing required provider settings produce explicit runtime errors (no silent mock fallback).
