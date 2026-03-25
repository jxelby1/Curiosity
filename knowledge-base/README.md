# Knowledge Base (Authenticated MVP)

`knowledge-base` is a locally runnable multi-agent learning platform:

- create topics and LLM-generated skill trees
- ingest source documents + personal notes
- chat with a tutor using retrieval context
- generate lessons/examples/exercises/resources
- run mixed-type assessments (not only MCQ)
- update progression and unlock nodes over time
- persist everything per authenticated user

## Stack

- Frontend: Next.js + React + TypeScript + Tailwind
- Backend: FastAPI + Python
- DB: PostgreSQL
- Vector: pgvector
- ORM: SQLAlchemy
- LLM/Embeddings: OpenAI API
- External search: Serper API

## Repo structure

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
    scripts/
      init_db.py
      seed_demo.py
      smoke_auth_isolation.py
      smoke_live_flow.py
  frontend/
    app/
      login/page.tsx
      signup/page.tsx
      topics/...
    components/
    lib/
  docker/
  .env.example
  docker-compose.yml
```

## Authentication model

Implemented auth is JWT-based with backend-issued bearer tokens.

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

Passwords are hashed with `passlib` (`pbkdf2_sha256`).

### User profile fields

`User` includes:

- `id`, `email`, `hashed_password`, `display_name`
- `onboarding_state`, `subscription_tier`
- `xp`, `level`
- `preferences`, `current_goal_summary`
- `created_at`, `updated_at`

### User-scoped data

All core entities are user-scoped in runtime access:

- topics/skill trees
- user skill states
- documents/notes/chunks
- chat sessions/messages
- recommendations
- generated resources
- assessments + attempts + responses + feedback

Frontend protected routing is handled by an auth provider + auth gate.
Unauthenticated users are redirected to `/login`.

## Assessment architecture

Assessment moved from simple MCQ quiz to mixed-type evaluation.

### Supported question types

- `multiple_choice`
- `short_answer`
- `explain`
- `scenario`
- `error_spotting`
- `reflection`

### Data model

- `Assessment`
- `AssessmentQuestion`
- `AssessmentAttempt`
- `AssessmentResponse`
- `AssessmentFeedback`

### Generation

`AssessmentAgent` generates structured assessments using OpenAI:

- node-scoped
- learner-level aware
- mixed question types
- rubric/expected-concept aware
- persisted and versioned per user + skill node

### Reliability safeguards

- type-specific validation for MCQ/open-response/reflection fields
- schema-aware payload normalization before final validation
- automatic repair for missing `expected_concepts`/rubric gaps
- fallback path when structured output still fails:
1. narrower constrained regeneration
2. deterministic valid assessment fallback
- observability logs for validation failures, repaired fields, fallback usage, and final question composition

### Scoring

- MCQ: deterministic scoring against answer index
- Free-text: rubric-based LLM evaluation against expected concepts
- Mastery updates are based on assessment performance (confidence input is not required in the user flow)

### Feedback returned

- overall score
- per-question scores and feedback
- strengths
- weaknesses
- review focus
- suggested follow-up
- mastery delta
- updated node state

## Topic initialization flow

Topic creation now supports a dedicated initialization flow with a progress screen.

Blocking stage before entry:

1. create topic record
2. build/reuse skill tree
3. compute unlock states
4. prepare first unlocked node content:
   - lesson
   - examples
   - exercises
   - assessment draft
5. generate recommendations

After that, user is routed directly to the first ready skill node.
Readiness only completes once all required starter content above exists for the first node.
Then additional content preparation continues for nearby nodes in priority order:

1. unlocked nodes
2. likely-to-unlock nodes
3. remaining high-priority neighbors (bounded set)

Initialization progress is persisted in `topic_initialization_jobs`.

## Key APIs

### Topics / learning flow

- `GET /api/topics`
- `POST /api/topics`
- `POST /api/topics/create-and-initialize`
- `POST /api/topics/{topic_id}/initialize`
- `GET /api/topics/{topic_id}/initialization-status`
- `DELETE /api/topics/{topic_id}?confirm=true`
- `GET /api/topics/{topic_id}/skill-tree`
- `POST /api/topics/{topic_id}/skill-tree/generate`
- `POST /api/skills/{skill_id}/resources/generate`
- `GET /api/skills/{skill_id}/resources/external`
- `GET /api/topics/{topic_id}/recommendations`
- `POST /api/skills/{skill_id}/progress/update`
- `POST /api/skills/{skill_id}/deep-dive`

### Chat / notes

- `POST /api/topics/{topic_id}/chat`
- `GET /api/topics/{topic_id}/notes`
- `POST /api/topics/{topic_id}/notes`
- `PUT /api/notes/{note_id}`
- `DELETE /api/notes/{note_id}`
- `POST /api/topics/{topic_id}/documents/upload`
- `GET /api/topics/{topic_id}/documents`
- `DELETE /api/topics/{topic_id}/documents/{document_id}`

Tutor chat includes topic-relevance guardrails:
- relevant/related questions are answered normally
- clearly unrelated questions are gently redirected back to the selected topic

### Assessments

- `POST /api/assessments/generate`
- `GET /api/assessments/{assessment_id}`
- `POST /api/assessments/{assessment_id}/submit`
- `GET /api/assessment-attempts/{attempt_id}`
- `GET /api/topics/{topic_id}/progress`
- `GET /api/users/me/progress-summary`

Compatibility endpoints still exist for legacy UI flows:

- `POST /api/skills/{skill_id}/quiz/generate`
- `POST /api/assessments/{assessment_id}/submit-quiz`

## Environment

Copy env file:

```bash
cp .env.example .env
```

Required:

- `DATABASE_URL` (PostgreSQL + psycopg URL)
- `OPENAI_API_KEY`
- `JWT_SECRET_KEY`

Required for web resource retrieval:

- `SEARCH_API_KEY`

## Local setup

### 1) Start PostgreSQL + pgvector

```bash
cd /Users/jack/Knowledge_Base/knowledge-base
docker compose up -d postgres
```

### 2) Run backend

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
set -a; source ../.env; set +a
uvicorn app.main:app --reload --port 8000
```

### 3) Run frontend

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/frontend
npm install
set -a; source ../.env; set +a
npm run dev
```

Open:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

## DB init / migration note

Startup runs `init_db()`:

- creates missing tables from SQLAlchemy models
- applies lightweight `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` migrations

For production, replace this with full Alembic migration workflow.

## Auth + assessment smoke flow

Run:

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
source .venv/bin/activate
python -m scripts.smoke_live_flow --skip-external
```

Smoke script validates:

1. register + `auth/me`
2. topic creation
3. skill tree load
4. note ingestion
5. chat response
6. recommendations
7. lesson generation
8. mixed assessment generation
9. mixed assessment submission (including free-text)
10. attempt retrieval
11. topic/user progress summary endpoints

## Topic initialization UX test

1. Sign in and open `/topics`
2. Create a new topic
3. Confirm redirect to `/topics/{id}/initializing`
4. Wait for progress to reach ready state
5. Confirm auto-redirect to `/topics/{id}/skills/{firstReadySkillId}`
6. Open `Lesson`, `Exercises`, and `Assessment` tabs to verify first-node content is already available/stored

Auth/isolation smoke:

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
source .venv/bin/activate
python -m scripts.smoke_auth_isolation
```

Validates:

1. unauthenticated protected-route rejection
2. registration for two users
3. per-user topic visibility
4. cross-user access denial for topic detail endpoints

## Tests

Backend quick tests:

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
source .venv/bin/activate
pytest -q
```

Live integration tests (against a running backend):

```bash
cd /Users/jack/Knowledge_Base/knowledge-base/backend
source .venv/bin/activate
LIVE_API_BASE_URL=http://localhost:8000/api pytest -q -m integration
```

## Frontend UX changes in this refactor

- Added `/login` and `/signup`
- Added auth provider + protected app shell + logout
- Removed default `user_id` hacks in frontend API calls
- Upgraded skill assessment tab to mixed-type assessment UI:
  - MCQ + free-text inputs
  - detailed results/feedback rendering

## Known limitations

- No refresh-token/session rotation yet (access token only).
- No email verification/password reset yet.
- LLM-based free-text scoring quality depends on model behavior.
- Lightweight migration bootstrap is practical for MVP but not enough for production release management.
