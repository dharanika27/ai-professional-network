# Component Map — AI Professional Network (MVP)

**Status:** Canonical routing instruction for the build phase. Maps every story (E1-S1 … E8-S5)
to the concrete files/modules that implement it. Paths are relative to the repository root and
consistent with `folder-structure.md`. Schemas/contracts referenced are in this `specs/design/` folder.

Backend import root is `backend/src/app/` (shown below as `app/`).

---

## Epic E1 — Foundation

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E1-S1** | Shared domain types & DTOs | `app/types/domain.py`, `app/types/dto.py`, `app/types/structured.py`, `app/types/ai.py`, `app/types/enums.py`; validated against `specs/design/data-models.schema.json`; mypy --strict over `app/types/` |
| **E1-S2** | Centralized config & secrets | `app/config/settings.py`, `app/config/llm_config.py`, `backend/.env.example` |
| **E1-S3** | DB, migrations, pgvector | `app/db/session.py`, `app/db/base.py`, `app/db/models.py` (vector(384) columns + HNSW indexes), `app/db/health.py`, `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/` |

## Epic E2 — Authentication

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E2-S1** | User & RefreshToken repos | `app/repositories/user_repository.py`, `app/repositories/refresh_token_repository.py` |
| **E2-S2** | Auth service (JWT/Argon2) | `app/services/auth_service.py`, `app/services/security.py` (Argon2 + JWT helpers) |
| **E2-S3** | Auth API + middleware + health | `app/api/routers/auth.py`, `app/api/routers/health.py`, `app/api/deps.py` (get_current_user), `app/api/errors.py`, `app/api/main.py`; contract: `api-contracts.md` §1–2 |

## Epic E3 — Profile Management

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E3-S1** | Profile repo + completion calc | `app/repositories/profile_repository.py` |
| **E3-S2** | Profile service | `app/services/profile_service.py` (skill normalization, incomplete_sections) |
| **E3-S3** | Profile API | `app/api/routers/profile.py`; contract: `api-contracts.md` §3 |

## Epic E4 — Resume Upload & Parsing

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E4-S1** | Resume repo + secure storage | `app/repositories/resume_repository.py`, `app/storage/base.py`, `app/storage/local_storage.py` |
| **E4-S2** | Parsing service (extract + LLM structure) | `app/services/resume_service.py`, `app/services/parsing/extractor.py`, `app/services/parsing/structurer.py`, `app/services/ai/prompts/` (system-first); injection fixture `backend/tests/fixtures/prompt_injection_resume.pdf` |
| **E4-S3** | Resume API | `app/api/routers/resume.py`; contract: `api-contracts.md` §4 (disclosure surfaced) |

## Epic E5 — RAG Knowledge Base & Embeddings

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E5-S1** | EmbeddingProvider (bge-small) | `app/services/ai/embedding_provider.py` (interface + lazy singleton, 384-dim) |
| **E5-S2** | KB ingestion + pgvector index | `app/services/ai/kb_ingestion.py`, `app/repositories/knowledge_repository.py`, `backend/scripts/ingest_kb.py`, KB source `backend/kb/*.md` |
| **E5-S3** | RAG retrieval service | `app/services/ai/rag_retrieval.py` (retrieve → context + citations, no LLM call) |

## Epic E6 — AI Features

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E6-S1** | Centralized Claude client | `app/services/ai/claude_client.py` (complete_structured, streaming, single retry, timeout, request-id logging), `app/repositories/ai_log_repository.py` (metadata-only) |
| **E6-S2** | Resume Review service | `app/services/ai/resume_review_service.py`, `app/repositories/resume_review_repository.py` (hash cache), `app/services/ai/prompts/resume_review.*` |
| **E6-S3** | Profile Optimization service | `app/services/ai/profile_optimization_service.py`, `app/repositories/profile_optimization_repository.py`, `app/services/ai/prompts/profile_optimization.*` |
| **E6-S4** | AI API + rate limiting | `app/api/routers/ai.py`, `app/api/rate_limit.py`; contract: `api-contracts.md` §5 (SSE streaming, 429/503/504) |

## Epic E7 — Job Matching

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E7-S1** | Job repo + seed + embedding index | `app/repositories/job_repository.py`, `backend/seeds/loaders/job_loader.py`, `backend/seeds/jobs/jobs_seed.json`, `backend/scripts/seed_jobs.py` |
| **E7-S2** | Job Matching service | `app/services/job_matching_service.py`, `app/repositories/job_match_repository.py` (top-10 → Claude re-rank → JobMatch) |
| **E7-S3** | Job API | `app/api/routers/jobs.py`; contract: `api-contracts.md` §6 |

## Epic E8 — Frontend UI & Dashboard

| Story | Title | Implementing files/modules |
|-------|-------|----------------------------|
| **E8-S1** | Design system + theming + shell | `frontend/src/design-system/tokens.ts`, `theme.tsx`, `globals.css`, `design-system/components/*`, `frontend/src/components/shell/*` |
| **E8-S2** | Auth/onboarding screens | `frontend/src/pages/{Landing,Register,Login,Onboarding}.tsx`, `frontend/src/api/auth.ts`, `frontend/src/hooks/useAuth.ts`, `frontend/src/components/forms/*` |
| **E8-S3** | Profile/resume screens | `frontend/src/pages/{ProfileView,ProfileEdit,ResumeUpload}.tsx`, `frontend/src/api/{profile,resume}.ts`, `frontend/src/hooks/{useProfile,useResume}.ts` |
| **E8-S4** | AI feature screens | `frontend/src/pages/{ResumeReview,ProfileOptimization}.tsx`, `frontend/src/api/ai.ts`, `frontend/src/hooks/useStream.ts`, `frontend/src/components/ai/*`, `frontend/src/lib/sse.ts` |
| **E8-S5** | Dashboard/jobs/settings screens | `frontend/src/pages/{Dashboard,JobMatching,JobDetails,Settings}.tsx`, `frontend/src/api/jobs.ts`, `frontend/src/components/feedback/*` |

---

## Cross-cutting modules (touched by multiple stories)

| Module | Used by |
|--------|---------|
| `app/types/*` | every backend layer (imports only downward) |
| `app/config/settings.py` | E2-S2, E4-S2, E6-S1, all services needing secrets |
| `app/db/session.py` | every repository (E2-S1, E3-S1, E4-S1, E5-S2, E7-S1, review/opt/match repos) |
| `app/services/ai/claude_client.py` | E4-S2 (structuring), E6-S2, E6-S3, E7-S2 |
| `app/services/ai/embedding_provider.py` | E5-S2, E5-S3, E7-S1, E7-S2, E6-S2 (resume embedding) |
| `app/services/ai/rag_retrieval.py` | E6-S2, E6-S3 |
| `app/api/deps.py` (auth dependency) | all authenticated routers (E3-S3, E4-S3, E6-S4, E7-S3) |
| `app/api/rate_limit.py` | E6-S4, E7-S3 (AI endpoints) |
| `frontend/src/design-system/*` | every E8 screen (E8-S2..S5 depend on E8-S1) |
| `frontend/src/api/client.ts` | every frontend api module (token refresh, error mapping) |

---

## Story → primary API endpoint(s)

| Story | Endpoint(s) |
|-------|-------------|
| E2-S3 | `POST /api/v1/auth/register`, `/login`, `/refresh`, `/logout`, `GET /api/v1/health` |
| E3-S3 | `GET /api/v1/profile`, `PUT /api/v1/profile` |
| E4-S3 | `POST /api/v1/resume`, `GET /api/v1/resume`, `DELETE /api/v1/resume/{resume_id}` |
| E6-S4 | `POST /api/v1/ai/resume-review` (+`/latest`), `POST /api/v1/ai/profile-optimization` (+`/latest`) |
| E7-S3 | `POST /api/v1/jobs/match`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{job_id}` |
