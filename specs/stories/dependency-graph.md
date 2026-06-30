# Dependency Graph — AI Professional Network (MVP)

Stories are grouped by dependency depth. Stories within the same group have no
dependencies on one another and are independently executable in parallel. Foundation
layers (Types, Config, Repository) appear in earlier groups; UI stories appear later.

Validated: no circular dependencies.

---

## Epic Overview (8 epics, 27 stories)

| Epic | Title | Stories |
|------|-------|---------|
| E1 | Foundation | E1-S1 Types · E1-S2 Config · E1-S3 DB/pgvector |
| E2 | Authentication | E2-S1 User/RefreshToken repo · E2-S2 Auth service (JWT/Argon2) · E2-S3 Auth API |
| E3 | Profile Management | E3-S1 Profile repo · E3-S2 Profile service · E3-S3 Profile API |
| E4 | Resume Upload & Parsing | E4-S1 Resume repo/storage · E4-S2 Parsing service · E4-S3 Resume API |
| E5 | RAG Knowledge Base & Embeddings | E5-S1 EmbeddingProvider · E5-S2 KB ingestion · E5-S3 RAG retrieval |
| E6 | AI Features | E6-S1 Claude client · E6-S2 Resume Review · E6-S3 Profile Optimization · E6-S4 AI API |
| E7 | Job Matching | E7-S1 Job repo/seed · E7-S2 Matching service · E7-S3 Job API |
| E8 | Frontend UI & Dashboard | E8-S1 Design system/shell · E8-S2 Auth/onboarding screens · E8-S3 Profile/resume screens · E8-S4 AI feature screens · E8-S5 Dashboard/jobs/settings |

---

## Group A — No dependencies (parallel)

Foundation: shared types, configuration, database/repository scaffolding, and the
embedding provider abstraction. These are pure foundation with no upstream work.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E1-S1 | Define shared domain types and DTOs | Types | — |
| E1-S2 | Centralized configuration and secret loading | Config | — |
| E1-S3 | Database connection, migrations, and pgvector setup | Repository | — |
| E5-S1 | EmbeddingProvider abstraction with local bge-small model | Service | — |

---

## Group B — Depends only on Group A

Core persistence and the authentication service built atop types, config, and the DB.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E2-S1 | User and RefreshToken repositories | Repository | E1-S1, E1-S3 |
| E3-S1 | Profile repository and completion calculation | Repository | E1-S1, E1-S3 |
| E4-S1 | Resume metadata repository and secure file storage | Repository | E1-S1, E1-S2, E1-S3 |
| E5-S2 | KnowledgeChunk ingestion, chunking, and pgvector indexing | Repository | E1-S1, E1-S3, E5-S1 |
| E7-S1 | Job repository, seed dataset, and embedding index | Repository | E1-S1, E1-S3, E5-S1 |

---

## Group C — Depends on Group B (and/or A)

Service-layer business logic: auth, profile, resume parsing, RAG retrieval, and the
centralized Claude LLM client.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E2-S2 | Authentication service (register, login, JWT, refresh) | Service | E2-S1 |
| E3-S2 | Profile service (view, edit, completion) | Service | E3-S1 |
| E4-S2 | Resume parsing service (local extraction + LLM structuring) | Service | E4-S1, E6-S1 |
| E5-S3 | RAG retrieval service (retrieve-then-generate) | Service | E5-S2 |
| E6-S1 | Centralized Claude LLM client with schema validation and guardrails | Service | E1-S2 |

---

## Group D — Depends on Group C

AI feature services that compose parsing, RAG retrieval, and the LLM client.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E6-S2 | AI Resume Review service (RAG-grounded, streaming, cached) | Service | E4-S2, E5-S3, E6-S1 |
| E6-S3 | AI Profile Optimization service (RAG-grounded) | Service | E3-S2, E5-S3, E6-S1 |
| E7-S2 | AI Job Matching service (vector top-10 → LLM re-rank) | Service | E4-S2, E6-S1, E7-S1 |

---

## Group E — Depends on Group D

API layer: HTTP endpoints, rate limiting, error handling, and health checks exposing all services.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E2-S3 | Auth API endpoints and middleware | API | E2-S2 |
| E3-S3 | Profile API endpoints | API | E3-S2 |
| E4-S3 | Resume upload/delete API endpoints | API | E4-S2 |
| E6-S4 | AI feature API endpoints (review, optimization) with rate limiting | API | E6-S2, E6-S3 |
| E7-S3 | Job matching and job details API endpoints | API | E7-S2 |

---

## Group F — Depends on Group E

UI foundation: the design system, theming, and responsive shell that every screen builds on.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E8-S1 | Design system, theming (light/dark), and responsive shell | UI | E2-S3 |

---

## Group G — Depends on Group F

UI screens: auth/onboarding, profile, resume, AI feature, job, and dashboard screens, all built on the design system.

| Story ID | Title | Layer | Depends On |
|----------|-------|-------|------------|
| E8-S2 | Auth and onboarding screens (Landing, Register, Login, Onboarding) | UI | E2-S3, E8-S1 |
| E8-S3 | Profile and resume screens (View, Edit, Upload) | UI | E3-S3, E4-S3, E8-S1 |
| E8-S4 | AI feature screens (Resume Review, Profile Optimization) | UI | E6-S4, E8-S1 |
| E8-S5 | Dashboard hub, Job Matching, Job Details, Settings screens | UI | E6-S4, E7-S3, E8-S1 |
