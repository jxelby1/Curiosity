# Knowledge Base (Live MVP)

`knowledge-base` is a locally runnable multi-agent learning system that helps a learner progress through any topic as a skill tree.

This version is a **live MVP**, not a mock PoC:

- live OpenAI calls for skill graph generation, tutoring, lesson generation, quiz generation
- live OpenAI embeddings for note chunks
- live retrieval from PostgreSQL + pgvector
- real persistence for progression, chat, assessments, and recommendations
- live external resource search via Serper API

## What the system does

- creates a learning topic and generates a dependency-based skill graph
- ingests learner notes (text/markdown/pdf)
- embeds and retrieves note chunks during tutoring and planning
- tracks per-node progression state and lock/unlock progression
- recommends the next best skill to study and why
- generates lessons/examples/exercises for selected skills
- generates quizzes and updates mastery from quiz attempts
- fetches external resources (article/docs/video) for selected skills

## Tech stack

- Frontend: Next.js + React + TypeScript + Tailwind
- Backend: FastAPI + Python
- Database: PostgreSQL
- Vector storage: pgvector
- ORM: SQLAlchemy
- Provider integrations:
  - OpenAI Chat + Embeddings
  - Serper Search API

## Repository structure

```text
knowledge-base/
  backend/
    app/
      agents/
      api/
      core/
      db/
      schemas/
      services/
      utils/
      main.py
    scripts/
      seed_demo.py
      smoke_live_flow.py
    requirements.txt
  frontend/
    app/
      page.tsx
      topics/page.tsx
      topics/[topicId]/page.tsx
      topics/[topicId]/skills/[skillId]/page.tsx
      topics/[topicId]/chat/page.tsx
      topics/[topicId]/notes/page.tsx
    components/
      learning-content.tsx
      topic-header.tsx
      topics-dashboard.tsx
    lib/
      api.ts
      types.ts
    package.json
  docker/
    postgres/
      init/01-enable-pgvector.sql
  docs/
    architecture.md
  .env.example
  docker-compose.yml
  README.md
```

## Agent orchestration

- `SkillGraphAgent`
  - Uses structured LLM output to generate graph nodes and prerequisites.
- `ProfileAgent`
  - Maintains `UserSkillState` and unlock logic.
- `IngestionAgent`
  - Stores documents, chunks text, calls OpenAI embeddings, stores vectors.
- `TutorAgent`
  - Retrieves top note chunks and generates adaptive tutor responses.
- `RecommendationAgent`
  - Combines state heuristics and LLM reasoning for next-step recommendations.
- `ResourceAgent`
  - Generates learning material or fetches/ranks external resources.
- `AssessmentAgent`
  - Generates quizzes with structured output and grades attempts.

API routes orchestrate these agents directly for clear flow and testability.

## Progression model (status-first)

Each node exposes learner-facing progression states:

- `not_started`
- `learning`
- `completed`
- `verified`

Progression rules:

- lesson completion is a one-time, idempotent state transition
- exercise completion is a one-time, idempotent state transition
- quiz score is the verification gate (>= 70% marks node as `verified`)
- child nodes unlock only when all prerequisite nodes are `verified`

The backend still maintains an internal numeric `mastery` signal for ranking/recommendation, but the primary UX uses node states and checklist evidence (`lesson_completed`, `exercises_completed`, `quiz_taken`, `best_quiz_score`).

## Generated content persistence

Generated lesson/examples/exercises/quiz payloads are persisted and versioned.

- First request: generate via LLM, save, return `source=generated`.
- Subsequent requests: load saved active version, return `source=stored`.
- Explicit regenerate: call same endpoint with `?regenerate=true`, create a new active version and return `source=regenerated`.

This behavior is implemented for:

- `POST /api/skills/{skill_id}/resources/generate`
- `POST /api/skills/{skill_id}/quiz/generate`

## Frontend IA

- `/topics`
  - Topic dashboard and creation.
- `/topics/[topicId]`
  - Topic overview: progress summary, skill tree, recommendations.
- `/topics/[topicId]/skills/[skillId]`
  - Focused node workspace with tabbed learning views (`Overview`, `Lesson`, `Examples`, `Exercises`, `Quiz`, `Resources`).
- `/topics/[topicId]/chat`
  - Tutor conversation workspace.
- `/topics/[topicId]/notes`
  - Notes upload and ingestion workspace.

## Generated Content Contract

`POST /api/skills/{skill_id}/resources/generate` returns both persisted text and structured JSON:

- `title`, `summary`, `content`, `relevance_reason`
- `structured_content`:
  - lesson: `title`, `summary`, `learning_objectives[]`, `key_concepts[]`, `sections[]`, `takeaways[]`, `next_steps[]`
  - examples: `title`, `intro`, `examples[]`
  - exercises: `title`, `intro`, `exercises[]`

The frontend renders `structured_content` with dedicated components and only falls back to raw text if the payload is invalid.

Both resource and quiz generation responses include:

- `source`: `stored | generated | regenerated`
- `version`: persisted content version number

## Environment variables

Copy and fill `.env` from `.env.example`:

```bash
cp .env.example .env
```

Required for backend startup:

- `DATABASE_URL` (must be PostgreSQL, `postgresql+psycopg://...`)
- `OPENAI_API_KEY`

Required for external resource endpoint:

- `SEARCH_API_KEY` (Serper)

Recommended defaults are already present in `.env.example`:

- `OPENAI_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `NEXT_PUBLIC_API_BASE_URL`
- `CORS_ORIGINS`

## Local setup

## 1) Start PostgreSQL + pgvector

```bash
cd /Users/jack/Knowledge_Base/knowledge-base
docker compose up -d postgres
```

## 2) Run backend

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
set -a; source ../.env; set +a
uvicorn app.main:app --reload --port 8000
```

Backend startup validates runtime config. If required variables are missing, it fails with explicit errors.

## 3) Run frontend

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/frontend
npm install
set -a; source ../.env; set +a
npm run dev
```

Frontend URL: `http://localhost:3000`  
Backend URL: `http://localhost:8000`

## Optional: seed demo data

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
source .venv/bin/activate
set -a; source ../.env; set +a
python -m scripts.seed_demo
```

## Live end-to-end flow (manual)

1. Create topic (for example, `Python debugging`) from dashboard.
2. Open topic page and confirm generated skill tree nodes.
3. Upload note text or file.
4. Ask tutor a question with a selected skill.
5. Request recommendations.
6. Generate lesson/examples/exercises.
7. Fetch external resources.
8. Generate quiz.
9. Submit quiz answers.
10. Mark lesson complete and exercises complete (each action is idempotent).
11. Refresh skill tree and confirm mastery/status changes.

## Smoke test script

Run against a live backend server:

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
source .venv/bin/activate
python -m scripts.smoke_live_flow
```

Options:

- `--api-base http://localhost:8000/api`
- `--user-id 1`
- `--skip-external` (if `SEARCH_API_KEY` is not set)

The smoke script verifies:

- topic creation
- skill tree retrieval
- note ingestion
- retrieval-backed chat
- recommendations
- lesson generation
- lesson persistence + regenerate
- quiz generation + submission
- quiz persistence + regenerate
- idempotent progression updates
- updated tree retrieval

## API endpoints

- `GET /api/health`
- `GET /api/topics`
- `POST /api/topics`
- `POST /api/topics/{topic_id}/skill-tree/generate`
- `GET /api/topics/{topic_id}/skill-tree`
- `POST /api/topics/{topic_id}/notes/upload`
- `GET /api/topics/{topic_id}/notes`
- `POST /api/topics/{topic_id}/chat`
- `GET /api/topics/{topic_id}/recommendations`
- `POST /api/skills/{skill_id}/resources/generate`
- `GET /api/skills/{skill_id}/resources/external`
- `POST /api/skills/{skill_id}/quiz/generate`
- `POST /api/assessments/{assessment_id}/submit`
- `POST /api/skills/{skill_id}/progress/update`

## Database schema entities

- `User`
- `Topic`
- `SkillNode`
- `SkillEdge`
- `UserSkillState`
- `Document`
- `DocumentChunk` (pgvector embedding)
- `ChatSession`
- `ChatMessage`
- `Recommendation`
- `LearningResource`
- `Assessment`
- `AssessmentAttempt`

## Logging and observability

The backend logs:

- OpenAI chat call start/completion and latency
- OpenAI embedding call start/completion and latency
- retrieval hit counts
- recommendation generation counts
- resource generation/search events
- assessment grading and mastery updates
- provider/configuration errors

## Known limitations

- External search currently uses one provider (`serper`) and requires API key.
- Internal mastery remains heuristic (practical for MVP, not psychometrically calibrated).
- No authentication/authorization yet (single demo user flow by default).
- No background queue yet; all heavy operations run inline in request paths.

## Suggested next steps

1. Add auth and multi-user tenant isolation.
2. Add Alembic migration workflow and CI checks.
3. Add async job queue for ingestion/long generations.
4. Add richer recommendation policy with learning history/spacing.
5. Add evaluation harness for prompt and output quality.
