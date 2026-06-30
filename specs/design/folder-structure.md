# Folder Structure — AI Professional Network (MVP)

**Status:** Canonical. `component-map.md` references these exact paths.
Reflects the strict layered architecture: **Types → Config → Repository → Service → API → UI**
(one-way dependencies). LLM/RAG logic lives only in the service layer.

---

## Repository root

```
ai-professional-network/
├── backend/                      # FastAPI service (Python 3.12, uv)
├── frontend/                     # React + TypeScript + Vite app
├── specs/                        # BRD, stories, design (this folder lives here)
├── docs/                         # Architecture diagrams, ADRs, README assets
├── docker-compose.yml            # Local stack: app + postgres(pgvector)
├── .github/workflows/            # CI/CD pipelines (lint, type, test, deploy)
└── README.md                     # Repo overview, setup, screenshots
```

---

## Backend — `backend/`

```
backend/
├── pyproject.toml                # uv project, deps, ruff + mypy + pytest config
├── uv.lock                       # Locked dependency versions
├── .env.example                  # Documented env vars (no real secrets)
├── Dockerfile                    # Bundles bge-small model in-container
├── alembic.ini                   # Migration framework config
│
├── migrations/                   # Alembic migration scripts (incl. pgvector enable)
│   ├── env.py                    # Alembic runtime (loads Settings, target metadata)
│   └── versions/                 # Timestamped migration revisions
│
├── src/app/                      # Application package (import root)
│   │
│   ├── types/                    # LAYER 1: shared domain types & DTOs (no deps)
│   │   ├── __init__.py
│   │   ├── domain.py             # Entity models: User, Profile, Resume, Job, etc.
│   │   ├── dto.py                # Request/response DTOs (no internal fields exposed)
│   │   ├── structured.py         # StructuredResume, ContactInfo, *Item, ReviewItem, Citation
│   │   ├── ai.py                 # AI content schemas: ResumeReviewContent, ProfileOptimizationContent
│   │   └── enums.py              # ParseStatus, ThemePreference, AIFeature, etc.
│   │
│   ├── config/                   # LAYER 2: centralized config & secret loading
│   │   ├── __init__.py
│   │   ├── settings.py           # pydantic-settings Settings; fail-fast validation
│   │   └── llm_config.py         # Model id, max tokens, 60s timeout, AI rate limit
│   │
│   ├── db/                       # LAYER 3a: persistence substrate
│   │   ├── __init__.py
│   │   ├── session.py            # Engine + scoped session factory (single import point)
│   │   ├── base.py               # SQLAlchemy declarative base / metadata
│   │   ├── models.py             # ORM table mappings incl. pgvector vector(384) columns
│   │   └── health.py             # SELECT 1 health-check function
│   │
│   ├── repositories/             # LAYER 3b: data access (no HTTP, no business rules)
│   │   ├── __init__.py
│   │   ├── user_repository.py    # create_user, get_user_by_email (case-insensitive)
│   │   ├── refresh_token_repository.py  # store/revoke/validate refresh tokens
│   │   ├── profile_repository.py # get/update profile, completion calculation
│   │   ├── resume_repository.py  # save/get/delete metadata, get-by-hash cache lookup
│   │   ├── knowledge_repository.py  # KnowledgeChunk persist + top-k similarity query
│   │   ├── job_repository.py     # seed persist, retrieve_top_jobs(k=10), get_job_by_id
│   │   ├── resume_review_repository.py   # persist/fetch reviews, cache by file hash
│   │   ├── profile_optimization_repository.py  # persist/fetch latest optimization
│   │   ├── job_match_repository.py  # persist runs + matches, fetch latest run
│   │   └── ai_log_repository.py  # AIRequestLog metadata-only writes
│   │
│   ├── storage/                  # Storage interface (local volume now, S3 later)
│   │   ├── __init__.py
│   │   ├── base.py               # StorageBackend protocol (save/read/delete)
│   │   └── local_storage.py      # Local non-web-served volume implementation
│   │
│   ├── services/                 # LAYER 4: business logic (LLM/RAG live here only)
│   │   ├── __init__.py
│   │   ├── auth_service.py       # register, login, refresh, logout; Argon2 + JWT
│   │   ├── security.py           # Argon2 hashing + JWT encode/decode helpers
│   │   ├── profile_service.py    # view/edit, skill normalization, incomplete sections
│   │   ├── resume_service.py     # upload policy, hybrid parse orchestration
│   │   ├── parsing/              # Resume text extraction
│   │   │   ├── __init__.py
│   │   │   ├── extractor.py      # pypdf / python-docx local extraction
│   │   │   └── structurer.py     # LLM normalization → StructuredResume (untrusted text)
│   │   ├── ai/                   # AI/RAG service modules
│   │   │   ├── __init__.py
│   │   │   ├── claude_client.py  # Centralized Claude client: complete_structured, stream, retry, guardrails
│   │   │   ├── embedding_provider.py  # EmbeddingProvider interface + bge-small singleton impl
│   │   │   ├── rag_retrieval.py  # retrieve(query, k) → context block + citations (no LLM call)
│   │   │   ├── kb_ingestion.py   # chunk + embed + idempotent index of KB markdown
│   │   │   ├── resume_review_service.py  # RAG-grounded review, streaming, hash cache
│   │   │   ├── profile_optimization_service.py  # RAG-grounded profile suggestions
│   │   │   └── prompts/          # Versioned prompt templates (system-instruction-first)
│   │   └── job_matching_service.py  # embed resume → top-10 → Claude re-rank → JobMatch
│   │
│   ├── api/                      # LAYER 5: HTTP boundary
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app factory, router mounting, /api/v1 prefix
│   │   ├── deps.py               # get_current_user, get_session DI dependencies
│   │   ├── errors.py             # Exception handlers → standard error envelope
│   │   ├── rate_limit.py         # Per-user AI rate-limit middleware/dependency
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── health.py         # GET /health
│   │       ├── auth.py           # register/login/refresh/logout
│   │       ├── profile.py        # GET/PUT /profile
│   │       ├── resume.py         # POST/GET/DELETE /resume
│   │       ├── ai.py             # resume-review, profile-optimization (+ latest reads)
│   │       └── jobs.py           # match, list, detail
│   │
│   └── __init__.py
│
├── seeds/                        # Seed data (loader-abstracted)
│   ├── jobs/                     # ~500–1000 job postings (JSON/CSV source)
│   │   └── jobs_seed.json
│   └── loaders/
│       └── job_loader.py         # JobLoader interface impl reading seeds/jobs
│
├── kb/                           # Curated RAG knowledge base (markdown source)
│   ├── ats_best_practices.md     # category: ats
│   ├── resume_writing.md         # category: resume
│   ├── profile_optimization.md   # category: profile
│   ├── interview_prep.md         # category: interview
│   └── career_guidance.md        # category: career
│
├── scripts/
│   ├── seed_jobs.py              # CLI: load + embed + index jobs
│   └── ingest_kb.py              # CLI: chunk + embed + index kb/ markdown
│
└── tests/                        # pytest, ≥80% coverage on core modules
    ├── conftest.py               # Fixtures: test DB, client, auth tokens
    ├── unit/                     # Per-layer unit tests
    │   ├── test_repositories/
    │   ├── test_services/
    │   └── test_types/
    ├── integration/              # API + DB integration tests
    │   ├── test_auth_api.py
    │   ├── test_profile_api.py
    │   ├── test_resume_api.py
    │   ├── test_ai_api.py
    │   └── test_jobs_api.py
    └── fixtures/
        ├── sample_resume.pdf
        ├── sample_resume.docx
        └── prompt_injection_resume.pdf   # E4-S2 injection test fixture
```

---

## Frontend — `frontend/`

```
frontend/
├── package.json                  # npm scripts: dev, build, lint, type-check, test
├── tsconfig.json                 # Strict TS config
├── vite.config.ts                # Vite + vitest config
├── .eslintrc.cjs                 # eslint rules
├── index.html
│
├── public/                       # Static assets (favicon, og image)
│
└── src/
    ├── main.tsx                  # App entry; mounts router + theme provider
    ├── App.tsx                   # Route tree, layout shell
    │
    ├── design-system/            # E8-S1: tokens, theming, primitives
    │   ├── tokens.ts             # Color, spacing, radii, typography (single source)
    │   ├── theme.tsx             # ThemeProvider, OS-default + persisted manual toggle
    │   ├── globals.css           # Reset, CSS variables for light/dark
    │   └── components/           # Button, Card, Input, Select, Badge, Spinner, Toast
    │
    ├── components/               # Shared composite components
    │   ├── shell/                # AppShell, NavBar, Sidebar (responsive)
    │   ├── forms/                # Accessible form fields, inline validation
    │   ├── ai/                   # ReviewSection, CitationBadge, StreamingPanel
    │   └── feedback/             # ErrorState, LoadingState, EmptyState, RetryButton
    │
    ├── pages/                    # Screen-level components
    │   ├── Landing.tsx           # E8-S2
    │   ├── Register.tsx          # E8-S2
    │   ├── Login.tsx             # E8-S2
    │   ├── Onboarding.tsx        # E8-S2
    │   ├── ProfileView.tsx       # E8-S3
    │   ├── ProfileEdit.tsx       # E8-S3
    │   ├── ResumeUpload.tsx      # E8-S3 (LLM disclosure)
    │   ├── ResumeReview.tsx      # E8-S4 (streaming display)
    │   ├── ProfileOptimization.tsx  # E8-S4
    │   ├── Dashboard.tsx         # E8-S5 (hub)
    │   ├── JobMatching.tsx       # E8-S5
    │   ├── JobDetails.tsx        # E8-S5
    │   └── Settings.tsx          # E8-S5 (data deletion, theme toggle)
    │
    ├── api/                      # Typed API client (mirrors api-contracts)
    │   ├── client.ts             # fetch wrapper, auth header, token refresh, error map
    │   ├── auth.ts               # register/login/refresh/logout calls
    │   ├── profile.ts            # get/update profile
    │   ├── resume.ts             # upload/get/delete
    │   ├── ai.ts                 # resume-review (SSE), profile-optimization
    │   ├── jobs.ts               # match/list/detail
    │   └── types.ts              # Generated/handwritten DTO types (snake_case)
    │
    ├── hooks/                    # useAuth, useProfile, useResume, useStream, useTheme
    ├── store/                    # Auth/session state (context or lightweight store)
    ├── lib/                      # Formatters, validators, sse parser
    └── tests/                    # vitest component/unit tests
```

---

## Where key assets live (quick reference)

| Asset | Location |
|-------|----------|
| Migrations (incl. pgvector enable) | `backend/migrations/versions/` |
| KB markdown (RAG source) | `backend/kb/*.md` |
| Job seed data | `backend/seeds/jobs/jobs_seed.json` |
| Seed/ingest CLIs | `backend/scripts/seed_jobs.py`, `backend/scripts/ingest_kb.py` |
| bge-small model | bundled in `backend/Dockerfile`, loaded by `services/ai/embedding_provider.py` |
| Env var documentation | `backend/.env.example` |
| Prompt templates | `backend/src/app/services/ai/prompts/` |
| Stored resume files | local volume via `storage/local_storage.py` (non-web-served) |
