# Sequence Diagrams — AI Professional Network (MVP)

**Project:** ai-professional-network
**Version:** 1.0 (MVP)
**Status:** Canonical-consistent. Endpoints, request/response fields, status codes, and entity
names are taken verbatim from `api-contracts.md` and `data-models.md`. Layer participants follow
`folder-structure.md` (Types → Config → Repository → Service → API → UI; LLM/RAG only in services).

---

## Participant legend

These participants recur across the diagrams below. Each maps to a real module from
`folder-structure.md`.

| Participant | Maps to |
|-------------|---------|
| `SPA` | Browser / React app (`frontend/src/api/*`, `hooks/useStream`) |
| `API` | FastAPI boundary (`api/routers/*`, `api/deps.py`, `api/errors.py`, `api/rate_limit.py`) |
| `AuthSvc` | `services/auth_service.py` + `services/security.py` (Argon2 + JWT) |
| `ProfileSvc` | `services/profile_service.py` |
| `ResumeSvc` | `services/resume_service.py` + `services/parsing/{extractor,structurer}.py` |
| `ReviewSvc` | `services/ai/resume_review_service.py` |
| `OptSvc` | `services/ai/profile_optimization_service.py` |
| `MatchSvc` | `services/job_matching_service.py` |
| `RAG` | `services/ai/rag_retrieval.py` |
| `Embed` | `services/ai/embedding_provider.py` (local `bge-small`, `vector(384)`) |
| `Claude` | `services/ai/claude_client.py` → Anthropic API |
| `Repo` | `repositories/*` (data access only) |
| `Storage` | `storage/local_storage.py` (non-web-served volume) |
| `DB` | PostgreSQL + pgvector |
| `AILog` | `repositories/ai_log_repository.py` → `ai_request_logs` (metadata only, never PII) |

> Note: the `Authorization: Bearer <access_token>` header and the `get_current_user`
> dependency (`api/deps.py`) are implied on every authenticated call and omitted from
> per-step labels for readability except where the auth result is the subject of the flow.

---

## 1. Registration

New user creates an account; an empty `profiles` row (completion 0) is created. The
`access_token` is returned in the `AuthSessionResponse` body and the rotating refresh token is
set as an HttpOnly cookie via `Set-Cookie` (never in the body) per `POST /api/v1/auth/register`.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant AuthSvc as Auth service
    participant URepo as user_repository
    participant PRepo as profile_repository
    participant RTRepo as refresh_token_repository
    participant DB as PostgreSQL

    SPA->>API: POST /api/v1/auth/register {email, password}
    API->>API: validate body (email format, password ≥ 8) — 422 on fail
    API->>AuthSvc: register(email, password)
    AuthSvc->>URepo: get_user_by_email(lower(email))
    URepo->>DB: SELECT 1 user by email
    alt email already exists
        DB-->>URepo: row found
        URepo-->>AuthSvc: existing user
        AuthSvc-->>API: EmailTaken
        API-->>SPA: 409 {error.code: "email_already_registered"}
    else email free
        DB-->>URepo: none
        AuthSvc->>AuthSvc: security.hash_password (Argon2id)
        AuthSvc->>URepo: create_user(email, password_hash, theme="system")
        URepo->>DB: INSERT users
        AuthSvc->>PRepo: create_empty_profile(user_id) completion=0
        PRepo->>DB: INSERT profiles
        AuthSvc->>AuthSvc: issue access JWT (15 min) + opaque refresh token
        AuthSvc->>RTRepo: store(token_hash=sha256(refresh), expires_at)
        RTRepo->>DB: INSERT refresh_tokens
        AuthSvc-->>API: AuthSessionResponse (no password_hash; refresh not in body)
        API-->>SPA: 201 Set-Cookie: refresh_token=<opaque>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth
        API-->>SPA: body {user, access_token, token_type:"bearer", expires_in:900}
    end
```

---

## 2. Login

Existing user authenticates; Argon2 verify is timing-safe and credential errors are generic per
`POST /api/v1/auth/login`.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant AuthSvc as Auth service
    participant URepo as user_repository
    participant RTRepo as refresh_token_repository
    participant DB as PostgreSQL

    SPA->>API: POST /api/v1/auth/login {email, password}
    API->>AuthSvc: login(email, password)
    AuthSvc->>URepo: get_user_by_email(lower(email))
    URepo->>DB: SELECT user
    alt user missing OR Argon2 verify fails
        AuthSvc->>AuthSvc: security.verify_password (always runs to stay timing-safe)
        AuthSvc-->>API: InvalidCredentials
        API-->>SPA: 401 {error.code: "invalid_credentials"}  (never reveals if email exists)
    else credentials valid
        AuthSvc->>AuthSvc: issue access JWT (15 min) + opaque refresh
        AuthSvc->>RTRepo: store(token_hash, expires_at)
        RTRepo->>DB: INSERT refresh_tokens
        AuthSvc-->>API: AuthSessionResponse
        API-->>SPA: 200 Set-Cookie: refresh_token=<opaque>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth
        API-->>SPA: body {user, access_token, token_type:"bearer", expires_in:900}
    end
```

---

## 3. Token refresh with rotation, plus the 401 → refresh → retry path

A protected call hits an expired access token; the SPA client (`api/client.ts`) transparently
refreshes (rotating the refresh token — old revoked, `rotated_to` set) and retries the original
request once.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant AuthSvc as Auth service
    participant RTRepo as refresh_token_repository
    participant DB as PostgreSQL

    Note over SPA,API: User triggers any protected request (e.g. GET /api/v1/profile)
    SPA->>API: GET /api/v1/profile  (Authorization: Bearer <expired access>)
    API->>API: get_current_user decodes JWT → expired
    API-->>SPA: 401 {error.code: "unauthorized"}

    Note over SPA: client.ts intercepts 401, attempts single refresh
    SPA->>API: POST /api/v1/auth/refresh (no body; credentials: 'include' → browser sends HttpOnly refresh_token cookie)
    API->>AuthSvc: refresh(refresh_token from cookie)
    AuthSvc->>RTRepo: get_by_hash(sha256(refresh_token))
    RTRepo->>DB: SELECT refresh_tokens
    alt token unknown / revoked / expired
        AuthSvc-->>API: InvalidRefreshToken
        API-->>SPA: 401 {error.code: "invalid_refresh_token"}
        Note over SPA: client clears session → redirect to Login
    else token valid (revoked=false AND expires_at>now)
        AuthSvc->>AuthSvc: mint new access JWT + new opaque refresh
        AuthSvc->>RTRepo: rotate(old_id → revoked=true, rotated_to=new_id; INSERT new)
        RTRepo->>DB: UPDATE old + INSERT new refresh_token
        AuthSvc-->>API: TokenRefreshResponse
        API-->>SPA: 200 Set-Cookie: refresh_token=<rotated>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth
        API-->>SPA: body {access_token, token_type:"bearer", expires_in:900}
        Note over SPA: retry original request with fresh access token (refresh token stays in cookie)
        SPA->>API: GET /api/v1/profile (Authorization: Bearer <new access>)
        API-->>SPA: 200 ProfileResponse
    end
```

---

## 4. Resume upload → local extraction → LLM structuring → embedding → persistence

`POST /api/v1/resume` (multipart `file`). Validation rejects bad MIME (415), oversized (>5 MB,
422), and empty-extraction/corrupt (422 `file_unreadable`) before any LLM call. On success the
file is stored at an opaque `storage_key`, structured by Claude, embedded locally, and persisted
with `parse_status="parsed"`.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant ResumeSvc as Resume service
    participant Storage as file storage
    participant Extractor as parsing.extractor
    participant Claude as Claude client
    participant Embed as EmbeddingProvider
    participant RRepo as resume_repository
    participant AILog as ai_request_log
    participant DB as PostgreSQL

    SPA->>API: POST /api/v1/resume  (multipart/form-data: file)
    API->>API: check extension + MIME (pdf/docx)
    alt MIME/extension not allowed
        API-->>SPA: 415 {error.code: "unsupported_file_type"}  (stores nothing)
    else size > 5 MB
        API-->>SPA: 422 {error.code: "file_too_large"}  (stores nothing)
    else accepted
        API->>ResumeSvc: parse_and_store(user_id, upload)
        ResumeSvc->>ResumeSvc: compute file_hash = sha256(bytes)
        ResumeSvc->>RRepo: get_by_user_and_hash(user_id, file_hash)
        RRepo->>DB: SELECT resumes
        alt identical file already parsed (cache)
            RRepo-->>ResumeSvc: existing parsed resume
            ResumeSvc-->>API: ResumeResponse (existing)
            API-->>SPA: 201 ResumeResponse (no storage_key/embedding)
        else new file
            ResumeSvc->>Extractor: extract_text(bytes, mime)  (pypdf / python-docx)
            alt password-protected / corrupt / no meaningful text
                Extractor-->>ResumeSvc: empty/insufficient text
                ResumeSvc-->>API: FileUnreadable
                API-->>SPA: 422 {error.code: "file_unreadable"}  (stores nothing)
            else text extracted
                ResumeSvc->>Storage: save(bytes) → storage_key
                ResumeSvc->>RRepo: insert(parse_status="pending", storage_key, file_hash, mime, size)
                RRepo->>DB: INSERT resumes
                ResumeSvc->>Claude: complete_structured(system-first prompt, untrusted text) → StructuredResume
                Note over Claude: in-resume instructions treated as data; system prompt overrides
                Claude-->>ResumeSvc: validated StructuredResume JSON
                ResumeSvc->>AILog: write(feature="resume_structuring", outcome, latency, tokens)  (no PII)
                AILog->>DB: INSERT ai_request_logs
                ResumeSvc->>Embed: embed(resume_text) → vector(384)
                Embed-->>ResumeSvc: embedding
                ResumeSvc->>RRepo: update(structured_content, embedding, parse_status="parsed")
                RRepo->>DB: UPDATE resumes
                ResumeSvc-->>API: ResumeResponse + disclosure
                API-->>SPA: 201 {parse_status:"parsed", structured_content, disclosure, ...}
            end
        end
    end
```

---

## 5. AI Resume Review (RAG retrieve → grounded generate → schema-validate → SSE stream); cache-hit branch

`POST /api/v1/ai/resume-review`. AI hourly rate limit (10/hr/user) checked first — on 429 the LLM
is never invoked. A cache hit by `resume_file_hash` returns the prior completed review
(`cached: true`) without an LLM call and without consuming rate limit. Streaming path emits
`meta` → `delta`* → `result` SSE events.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant RL as rate_limit
    participant ReviewSvc as Resume Review service
    participant RRRepo as resume_review_repository
    participant RAG as RAG retrieval
    participant Embed as EmbeddingProvider
    participant KRepo as knowledge_repository
    participant Claude as Claude client
    participant AILog as ai_request_log
    participant DB as PostgreSQL

    SPA->>API: POST /api/v1/ai/resume-review  (Accept: text/event-stream)
    API->>RL: check AI hourly limit (user)
    alt rate limit exceeded
        RL-->>API: blocked
        API-->>SPA: 429 {error.code:"rate_limited", request_id} + Retry-After  (LLM NOT invoked)
    else allowed
        API->>ReviewSvc: review_resume(user_id, resume_id?)
        ReviewSvc->>RRRepo: get_current_resume(user_id)
        alt no uploaded resume
            ReviewSvc-->>API: ResumeNotFound
            API-->>SPA: 404 {error.code:"resume_not_found", request_id}
        else resume exists
            ReviewSvc->>RRRepo: get_completed_review_by_hash(resume_file_hash)
            RRRepo->>DB: SELECT resume_reviews WHERE status='completed'
            alt cache hit
                RRRepo-->>ReviewSvc: completed review
                Note over ReviewSvc: cache hit — exempt from rate-limit consumption, no LLM call
                ReviewSvc-->>API: ResumeReviewResponse (cached=true)
                API-->>SPA: SSE meta → result {cached:true}  (or 200 JSON if not streaming)
            else cache miss
                API-->>SPA: SSE event: meta {request_id, resume_id}
                ReviewSvc->>RAG: retrieve(resume context, categories=[ats,resume], k)
                RAG->>Embed: embed(query)
                RAG->>KRepo: top_k similarity (pgvector cosine)
                KRepo->>DB: SELECT knowledge_chunks ORDER BY embedding <=> query
                KRepo-->>RAG: chunks
                RAG-->>ReviewSvc: context block + [Citation{source_id, source_file, snippet}]
                ReviewSvc->>Claude: stream(system-first, grounded prompt + context)
                loop streamed tokens
                    Claude-->>ReviewSvc: partial text
                    ReviewSvc-->>API: SSE event: delta {text}
                    API-->>SPA: delta {text}
                end
                Claude-->>ReviewSvc: full JSON
                ReviewSvc->>ReviewSvc: schema-validate ResumeReviewContent; assert each source_id ∈ sources
                ReviewSvc->>RRRepo: persist(status="completed", content, sources, model_id)
                RRRepo->>DB: INSERT resume_reviews
                ReviewSvc->>AILog: write(feature="resume_review", outcome="success", tokens, latency)
                AILog->>DB: INSERT ai_request_logs
                ReviewSvc-->>API: ResumeReviewResponse (cached=false)
                API-->>SPA: SSE event: result {full ResumeReviewResponse}
            end
        end
    end
```

---

## 6. AI Profile Optimization (RAG-grounded)

`POST /api/v1/ai/profile-optimization`. Operates on the user's current profile, RAG-grounded
against the `profile`/`resume` KB categories, schema-validated, persisted, and re-fetchable via
`GET /api/v1/ai/profile-optimization/latest` without a new LLM call.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant RL as rate_limit
    participant OptSvc as Profile Optimization service
    participant PRepo as profile_repository
    participant RAG as RAG retrieval
    participant Embed as EmbeddingProvider
    participant KRepo as knowledge_repository
    participant Claude as Claude client
    participant PORepo as profile_optimization_repository
    participant AILog as ai_request_log
    participant DB as PostgreSQL

    SPA->>API: POST /api/v1/ai/profile-optimization
    API->>RL: check AI hourly limit
    alt rate limited
        API-->>SPA: 429 {error.code:"rate_limited", request_id} + Retry-After
    else allowed
        API->>OptSvc: optimize_profile(user_id)
        OptSvc->>PRepo: get_profile(user_id)
        PRepo->>DB: SELECT profiles
        alt profile too sparse
            OptSvc-->>API: ProfileInsufficient
            API-->>SPA: 409 {error.code:"profile_insufficient", request_id}  (actionable message)
        else profile usable
            OptSvc->>RAG: retrieve(profile context, categories=[profile,resume], k)
            RAG->>Embed: embed(query)
            RAG->>KRepo: top_k similarity (pgvector)
            KRepo->>DB: SELECT knowledge_chunks
            RAG-->>OptSvc: context block + [Citation]
            OptSvc->>Claude: complete_structured(system-first, grounded prompt + context)
            Claude-->>OptSvc: JSON
            OptSvc->>OptSvc: schema-validate ProfileOptimizationContent; check source_id grounding
            OptSvc->>PORepo: persist(status="completed", content, sources, model_id)
            PORepo->>DB: INSERT profile_optimizations
            OptSvc->>AILog: write(feature="profile_optimization", outcome="success")
            OptSvc-->>API: ProfileOptimizationResponse
            API-->>SPA: 200 {id, status:"completed", content, sources, model_id, request_id, created_at}
        end
    end

    Note over SPA,DB: Later re-display (no LLM)
    SPA->>API: GET /api/v1/ai/profile-optimization/latest
    API->>OptSvc: get_latest(user_id)
    OptSvc->>PORepo: latest completed
    PORepo->>DB: SELECT ... ORDER BY created_at DESC
    alt none
        API-->>SPA: 404 {error.code:"optimization_not_found"}
    else found
        API-->>SPA: 200 ProfileOptimizationResponse
    end
```

---

## 7. Job Matching (embed resume → pgvector top-10 → LLM re-rank → persist run + matches)

`POST /api/v1/jobs/match`. Two-stage: deterministic pgvector top-10 retrieval (no LLM) then a
single Claude re-rank producing `fit_score`/`fit_explanation`/`gaps`. A `job_match_run` parents
the per-job `job_match` rows; results return as `JobSummary` (no `description`/`embedding`),
ordered by descending `fit_score`. Weak matches yield honest low scores, not errors.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant RL as rate_limit
    participant MatchSvc as Job Matching service
    participant RRepo as resume_repository
    participant Embed as EmbeddingProvider
    participant JRepo as job_repository
    participant Claude as Claude client
    participant JMRepo as job_match_repository
    participant AILog as ai_request_log
    participant DB as pgvector

    SPA->>API: POST /api/v1/jobs/match
    API->>RL: check AI hourly limit
    alt rate limited
        API-->>SPA: 429 {error.code:"rate_limited", request_id} + Retry-After
    else allowed
        API->>MatchSvc: match_jobs(user_id)
        MatchSvc->>RRepo: get_current_resume(user_id)
        RRepo->>DB: SELECT resumes
        alt no parsed resume
            MatchSvc-->>API: ResumeNotParsed
            API-->>SPA: 409 {error.code:"resume_not_parsed", request_id}  (actionable, not 500)
        else parsed resume present
            MatchSvc->>JMRepo: create_run(user_id, resume_id, status="pending")
            JMRepo->>DB: INSERT job_match_runs
            MatchSvc->>Embed: ensure resume embedding (reuse stored vector(384))
            MatchSvc->>JRepo: retrieve_top_jobs(resume_embedding, k=10)  (no LLM)
            JRepo->>DB: SELECT jobs ORDER BY embedding <=> query LIMIT 10
            JRepo-->>MatchSvc: top-10 candidate jobs
            MatchSvc->>Claude: complete_structured(re-rank prompt: resume + 10 jobs → fit/gaps)
            Claude-->>MatchSvc: ranked JSON [{job_id, fit_score, fit_explanation, gaps, rank}]
            MatchSvc->>MatchSvc: schema-validate; clamp scores 0–100; sort desc; assign 1-based rank
            MatchSvc->>JMRepo: persist matches + run.status="completed"
            JMRepo->>DB: INSERT job_matches (UNIQUE run_id,job_id) + UPDATE job_match_runs
            MatchSvc->>AILog: write(feature="job_matching", outcome="success")
            MatchSvc-->>API: JobMatchResponse (matches as JobSummary)
            API-->>SPA: 200 {run_id, resume_id, model_id, request_id, matches[≤10], created_at}
        end
    end
```

---

## 8. Representative failure flow — Claude timeout / invalid output → single retry → safe error envelope

Applies uniformly to every `/ai/*` and `/jobs/match` call via `claude_client.py` guardrails:
one retry on a transient/invalid response, schema validation, a 60 s timeout, metadata-only
logging, and a safe error envelope carrying `request_id` (never internal detail or PII). Shown
here for resume review; the same guardrail wraps optimization and matching.

```mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser/SPA
    participant API
    participant ReviewSvc as Resume Review service
    participant Claude as Claude client
    participant Anthropic as Anthropic API
    participant AILog as ai_request_log
    participant DB as PostgreSQL

    SPA->>API: POST /api/v1/ai/resume-review
    API->>ReviewSvc: review_resume(user_id) (rate limit already passed, request_id minted)
    ReviewSvc->>Claude: complete_structured(prompt, schema, timeout=60s)
    Claude->>Anthropic: request (attempt 1)
    alt timeout or invalid/unparseable JSON (attempt 1)
        Anthropic-->>Claude: timeout / malformed output
        Claude->>Claude: classify transient; retry_count=1
        Claude->>Anthropic: request (attempt 2 — single retry)
        alt attempt 2 succeeds + schema-valid
            Anthropic-->>Claude: valid JSON
            Claude-->>ReviewSvc: validated content (retry_count=1)
            ReviewSvc->>AILog: write(outcome="retry_success", retry_count=1)
            AILog->>DB: INSERT ai_request_logs (metadata only)
            ReviewSvc-->>API: ResumeReviewResponse
            API-->>SPA: 200 ResumeReviewResponse
        else attempt 2 also fails
            alt timeout
                Claude-->>ReviewSvc: AITimeout
                ReviewSvc->>AILog: write(outcome="timeout", retry_count=1)
                AILog->>DB: INSERT ai_request_logs
                ReviewSvc-->>API: AITimeout
                API-->>SPA: 504 {error.code:"ai_timeout", message:"safe", request_id}
            else provider error / still invalid schema
                Claude-->>ReviewSvc: AIProviderUnavailable | InvalidSchema
                ReviewSvc->>AILog: write(outcome="failed"|"invalid_schema", retry_count=1)
                AILog->>DB: INSERT ai_request_logs
                ReviewSvc-->>API: AIProviderUnavailable
                API-->>SPA: 503 {error.code:"ai_provider_unavailable", message:"safe", request_id}
            end
            Note over SPA: if streaming, this is delivered as SSE event: error {code, message, request_id}
        end
    end
```

> **Guardrail summary (per BRD §11 and `claude_client.py`):** schema-validate every LLM output ·
> single retry on transient/invalid output (`retry_count` ∈ {0,1}) · 60 s timeout · safe
> user-facing messages with no internal detail · `request_id` correlation in every AI error ·
> `ai_request_logs` stores metadata only, never PII or prompt/resume text.
