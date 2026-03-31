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
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`

Passwords are hashed with `passlib` (`pbkdf2_sha256`).

Forgot/reset flow uses single-use reset tokens stored in `password_reset_tokens` with expiry.
Reset emails are sent via Resend when enabled.
In local development, you can keep email sending disabled and use the optional debug token flow.

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
- Reflection questions are recorded with attempts but excluded from grading and score calculations

### Assessment readiness guardrail

Assessment generation is now grounded to in-app taught material:

- lesson/examples are ensured before assessment generation
- assessment prompts include explicit taught-concept coverage context
- non-reflection expected concepts are normalized to taught concepts
- out-of-scope concept drift is repaired toward taught coverage

Rule of thumb: a diligent learner should be able to pass from lesson + examples without external reading.

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

When new nodes unlock during progression, the same starter bundle (lesson/examples/exercises/assessment) is prepared automatically in the background.

Initialization progress is persisted in `topic_initialization_jobs`.

## Course personalization and skill-tree navigation

Topic creation now includes learner-configurable course settings:

- `course_depth`: `light | standard | deep_dive`
- `starting_skill_level`: `beginner | intermediate | advanced`
- `assessment_styles`: multi-select allowed styles

Supported assessment styles in this release:

- open text
- short answer
- multiple choice
- flashcard recall
- scenario reasoning
- coding assessment
- debugging
- code completion
- code interpretation
- math problem solving

These settings materially influence generation:

- skill-graph depth and breadth (node count target ranges)
- progression ramp-up from selected starting level
- assessment style sequencing and question composition

The skill constellation now supports:

- drag-to-pan navigation
- wheel/trackpad zoom
- reset view control
- auto-keeping selected nodes in view

## Retention loop (new)

Topic pages now prioritize guided momentum instead of a large standalone growth card.

Backend now computes a retention payload per topic with:

- daily/weekly learning plan
- next 3 actions (clickable skill + tab targets)
- unlock anticipation ("coming next" with required steps)
- compact progress signals (unlock/verified/completed/mastery)
- inactivity reminder generation after threshold inactivity
- milestone celebrations for meaningful events

### Plan generation logic

Plan items are generated from real user state:

- unlocked node status
- lesson/examples/exercises/assessment completion signals
- weak assessment performance (review/retry suggestions)
- recommendation ranking signals
- upcoming unlock dependencies

Cadence is adaptive:

- `daily` for recently active learners
- `weekly` for re-entry / less recent activity

### Unlock anticipation logic

The system ranks locked nodes by distance-to-unlock and returns:

- the likely next unlock
- why it is still locked
- concrete steps to unlock it
- a direct next-step target node/tab

### Inactivity reminders

If a learner has been inactive past threshold, a reminder object is created and persisted.
The reminder includes re-entry context:

- what to do next
- what is close to unlocking
- a direct resume target

Reminder delivery is currently in-app (banner on return), with backend persistence ready for email/push extensions.

### Milestone celebrations

Milestones are persisted with dedupe keys to avoid repeat spam.
Current triggers include:

- first verified node
- first optional branch unlocked
- topic growth stage milestones
- strong assessment pass on an important node
- topic completion

Users can acknowledge milestones, and acknowledged events are hidden from celebration UI.

## Exercise progress + topic project journal

Exercises now use per-item completion tracking (not all-or-nothing):

- each module is capped at 2 exercises
- each exercise can be completed independently
- optional proof upload (image/PDF) can be attached per exercise completion
- module exercise progress is derived from per-exercise completions

Notes now include a richer topic project journal view:

- chronological record of notes
- exercise completions (+ proof artifacts)
- module completion events
- assessment attempts/results
- milestones

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
- `GET /api/skills/{skill_id}/exercises/completions`
- `POST /api/skills/{skill_id}/exercises/{exercise_index}/complete`
- `GET /api/exercise-completions/{completion_id}/proof`
- `POST /api/skills/{skill_id}/progress/update`
- `POST /api/skills/{skill_id}/deep-dive`
- `GET /api/users/me/progress-summary` (includes per-topic tree stage for Garden)
- `GET /api/topics/{topic_id}/retention-loop`
- `POST /api/topics/{topic_id}/milestones/{milestone_id}/seen`
- `POST /api/topics/{topic_id}/reminders/{reminder_id}/dismiss`

### Chat / notes

- `POST /api/topics/{topic_id}/chat`
- `GET /api/topics/{topic_id}/notes`
- `GET /api/topics/{topic_id}/journal`
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
- password-reset settings:
  - `PASSWORD_RESET_TOKEN_TTL_MINUTES`
  - `PASSWORD_RESET_BASE_URL`
  - `PASSWORD_RESET_DEBUG_EXPOSE_TOKEN`
  - `PASSWORD_RESET_ALLOW_USER_DISCOVERY`
  - `PASSWORD_RESET_SEND_EMAIL`
  - `PASSWORD_RESET_EMAIL_SUBJECT`
- email provider settings (Resend):
  - `EMAIL_PROVIDER` (`resend`)
  - `RESEND_API_KEY`
  - `RESEND_FROM_EMAIL`
  - `RESEND_REPLY_TO` (optional)
  - `RESEND_BASE_URL`

Required for web resource retrieval:

- `OPENAI_WEB_SEARCH_MODEL` (defaults to `gpt-4.1-mini` if omitted)
- media cache (recommended defaults):
  - `MEDIA_CACHE_STORAGE_DIR`
  - `MEDIA_CACHE_MAX_MB`
  - `MEDIA_CACHE_TIMEOUT_SECONDS`
  - `MEDIA_CACHE_TOKEN_TTL_SECONDS`
  - `MEDIA_CACHE_MIN_IMAGE_PIXELS`
  - `MEDIA_CACHE_MIN_IMAGE_LONG_EDGE`
  - `MEDIA_CACHE_DOMAIN_BLOCK_TTL_SECONDS`

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

### Password reset email (Resend)

To send real reset emails:

1. Set these values in `.env`:
   - `PASSWORD_RESET_SEND_EMAIL=true`
   - `EMAIL_PROVIDER=resend`
   - `RESEND_API_KEY=<your-resend-api-key>`
   - `RESEND_FROM_EMAIL=Knowledge Base <no-reply@your-domain.com>`
   - `PASSWORD_RESET_BASE_URL=http://localhost:3000/reset-password`
2. Restart backend.
3. Use `Forgot password` from `/login` and check inbox.

For local-only debug flow without email:

- `PASSWORD_RESET_SEND_EMAIL=false`
- `PASSWORD_RESET_DEBUG_EXPOSE_TOKEN=true`

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
6. Open `Lesson`, `Examples`, `Exercises`, and `Assessment` tabs to verify first-node content is already available/stored

## Garden and tree stages

- `frontend/public/assets/tree-growth/` stores per-stage tree assets.
- `frontend/lib/tree-growth.ts` defines stage mapping and asset resolution.
- `frontend/scripts/slice_tree_growth_sheet.py` slices a 6-stage source sheet into stage assets when a sheet is provided.
- Growth stages are mapped from topic progress signals (mastery, verified-node ratio, unlocked-node ratio) into 6 stages.
- `/garden` shows all topics as tree cards and links back to each topic.
- `/topics/{id}` shows the current topic tree stage.

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
- Added forgot/reset password pages
- Added Garden tab/page with per-topic tree growth cards
- Removed confidence sliders from assessment UI
- Removed user-facing “mastery delta” wording from assessment results

## Known limitations

- No refresh-token/session rotation yet (access token only).
- No email verification/password reset yet.
- LLM-based free-text scoring quality depends on model behavior.
- Lightweight migration bootstrap is practical for MVP but not enough for production release management.
