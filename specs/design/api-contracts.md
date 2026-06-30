# API Contracts — AI Professional Network (MVP)

**Project:** ai-professional-network
**Version:** 1.0 (MVP)
**Base path:** `/api/v1`
**Status:** Canonical. The OpenAPI companion (`api-contracts.schema.json`) mirrors this file.

---

## 0. Conventions

| Concern | Rule |
|---------|------|
| **Casing** | All JSON request/response bodies use **snake_case**, matching `data-models.md`. No camelCase on the wire. |
| **Base path** | Every endpoint is prefixed `/api/v1`. The stories' shorthand (`/api/auth/...`) maps to `/api/v1/auth/...`. |
| **Auth** | Bearer JWT access token: `Authorization: Bearer <access_token>`. Short TTL (15 min); the client holds it **in memory**. The refresh token is opaque and is carried **only as an HttpOnly cookie** (`Set-Cookie: refresh_token=<opaque>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=<refresh TTL>`). It is **never** in any request/response body and **never** readable by JS; the browser attaches it automatically only on `/auth/refresh` and `/auth/logout`. Auth requests use credentialed CORS so the cookie is set/sent. |
| **Content type** | `application/json` except resume upload (`multipart/form-data`) and streaming review (`text/event-stream`). |
| **IDs** | UUID v4 strings. |
| **Timestamps** | ISO-8601 UTC. |
| **DTO safety** | Response DTOs NEVER include `password_hash`, `token_hash`, `storage_key`, or raw `embedding` vectors. |
| **Correlation** | AI endpoints return `request_id` (UUID) in error bodies for support/log correlation (no PII). |

> **Why the refresh token is an HttpOnly cookie (rationale).** The refresh token is the
> long-lived credential. Putting it in an `HttpOnly` cookie means JavaScript cannot read it, so
> an XSS payload cannot steal it; `Secure` keeps it HTTPS-only; `SameSite=Strict` + the scoped
> `Path=/api/v1/auth` mitigate CSRF on the auth endpoints (the cookie is never sent cross-site
> and only on auth paths). The access token stays in the JSON body (held in memory) so the API
> remains a stateless Bearer API. See `security-architecture.md` 1.2.

### Standard error envelope

All non-2xx responses (except 422 validation, which uses FastAPI's field-level shape) use:

```json
{
  "error": {
    "code": "string_machine_code",
    "message": "Human-readable, safe message with no internal detail.",
    "request_id": "uuid (present on AI endpoints)"
  }
}
```

`422` validation errors use the FastAPI/Pydantic shape:
```json
{ "detail": [ { "loc": ["body", "email"], "msg": "value is not a valid email address", "type": "value_error.email" } ] }
```

### Common status codes

`200 OK` · `201 Created` · `204 No Content` · `401 Unauthorized` (missing/invalid token) ·
`403 Forbidden` (authenticated but not owner) · `404 Not Found` · `409 Conflict` ·
`415 Unsupported Media Type` · `422 Unprocessable Entity` (validation) ·
`429 Too Many Requests` (rate limit) · `503 Service Unavailable` / `504 Gateway Timeout` (AI provider).

### Rate-limit policy

| Scope | Limit | Headers on response |
|-------|-------|---------------------|
| Global non-AI | 120 req/min/user (soft) | — |
| AI endpoints (`/ai/*`, `/jobs/match`) | **10 requests / hour / user**, configurable via `AI_RATE_LIMIT_PER_HOUR` | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`; `Retry-After` (seconds) on 429 |

When an AI rate limit is hit, the LLM is **not** invoked; a `429` is returned immediately.

---

## Endpoint template

> **Method & Path** · **Auth** · **Story**
> Request: headers / path / query / body
> Success: status + body
> Errors: status + code
> Rate limit · Notes

---

## 1. Health

### GET `/api/v1/health`
- **Auth:** none. **Story:** E2-S3 (AC5), E1-S3 (AC4).
- **Request:** no params, no body.
- **Success `200`:**
  ```json
  { "status": "healthy", "database": "up", "version": "1.0.0", "time": "2026-06-30T10:00:00Z" }
  ```
- **Failure `503`:** body `{ "status": "unhealthy", "database": "down", "version": "1.0.0", "time": "..." }` when the `SELECT 1` DB check fails.
- **Rate limit:** none. **Notes:** liveness+readiness combined for MVP.

---

## 2. Authentication — `/api/v1/auth`

### POST `/api/v1/auth/register`
- **Auth:** none. **Story:** E2-S2, E2-S3 (AC1).
- **Body** (`RegisterRequest`):
  ```json
  { "email": "asha.rao@example.com", "password": "S3curePass!" }
  ```
  Constraints: valid email; password length ≥ 8.
- **Response headers:** `Set-Cookie: refresh_token=<opaque>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=<refresh TTL>` (sets the rotating refresh cookie).
- **Success `201`** (`AuthSessionResponse`):
  ```json
  {
    "user": { "id": "uuid", "email": "asha.rao@example.com", "theme_preference": "system", "created_at": "..." },
    "access_token": "jwt...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```
  The refresh token is **not** in the body — it is delivered only via the `Set-Cookie` header above.
- **Errors:** `409` `email_already_registered`; `422` validation (email/password).
- **Rate limit:** global. **Notes:** creates the user's empty `profiles` row (completion 0). `password_hash` and the refresh token are never returned in the body.

### POST `/api/v1/auth/login`
- **Auth:** none. **Story:** E2-S2, E2-S3 (AC2).
- **Body** (`LoginRequest`): `{ "email": "...", "password": "..." }`
- **Response headers:** `Set-Cookie: refresh_token=<opaque>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=<refresh TTL>`.
- **Success `200`** (`AuthSessionResponse`): same body shape as register (`user`, `access_token`, `token_type`, `expires_in`) — **no** `refresh_token` in the body; it is set via `Set-Cookie`.
- **Errors:** `401` `invalid_credentials` (generic — never reveals whether the email exists); `422` validation.
- **Rate limit:** global (login attempts throttled). **Notes:** Argon2 verify; timing-safe.

### POST `/api/v1/auth/refresh`
- **Auth:** none. The refresh token is read **from the HttpOnly cookie** (sent automatically by the browser on the `/api/v1/auth` path); the request takes **no body**. **Story:** E2-S2, E2-S3 (AC3).
- **Request:** no body. Requires the `refresh_token` cookie. Browser clients must send credentials (`credentials: 'include'`).
- **Response headers:** `Set-Cookie: refresh_token=<opaque-new>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=<refresh TTL>` (the rotated cookie).
- **Success `200`** (`TokenRefreshResponse`):
  ```json
  { "access_token": "jwt...", "token_type": "bearer", "expires_in": 900 }
  ```
  The rotated refresh token is delivered only via `Set-Cookie`, never in the body.
- **Errors:** `401` `invalid_refresh_token` (revoked/expired/unknown/missing cookie).
- **Rate limit:** global. **Notes:** rotates the refresh token — old token revoked, `rotated_to` set to the new one, new cookie set.

### POST `/api/v1/auth/logout`
- **Auth:** Bearer (access token). The refresh token is read **from the HttpOnly cookie**. **Story:** E2-S3.
- **Request:** no body. Requires credentials so the `refresh_token` cookie is sent.
- **Response headers:** `Set-Cookie: refresh_token=; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=0` (clears the cookie).
- **Success `204`:** no body. Revokes the server-side refresh token **and** clears the cookie.
- **Errors:** `401` `unauthorized` (no/invalid access token).
- **Rate limit:** global. **Notes:** idempotent; revoking an already-revoked token (or with no cookie) still returns 204 and clears the cookie.

---

## 3. Profile — `/api/v1/profile`

### GET `/api/v1/profile`
- **Auth:** Bearer. **Story:** E3-S2, E3-S3 (AC1).
- **Request:** no params.
- **Success `200`** (`ProfileResponse`):
  ```json
  {
    "id": "uuid", "user_id": "uuid",
    "full_name": "Asha Rao",
    "headline": "Aspiring Backend Engineer",
    "summary": "...",
    "skills": ["Python", "FastAPI"],
    "education": [ { "institution": "PSG Tech", "degree": "B.E. CS", "field": "CS", "start_year": 2022, "end_year": 2026, "grade": "8.7" } ],
    "experience": [ { "company": "Acme", "title": "Intern", "start_date": "2025-05", "end_date": "2025-08", "current": false, "description": "..." } ],
    "certifications": [ { "name": "AWS CP", "issuer": "AWS", "issued_date": "2025-03" } ],
    "projects": [ { "name": "ResumeRAG", "description": "...", "url": "https://...", "technologies": ["Python"] } ],
    "completion_percentage": 80,
    "incomplete_sections": ["certifications"],
    "updated_at": "..."
  }
  ```
- **Errors:** `401` `unauthorized`.
- **Rate limit:** global. **Notes:** `incomplete_sections` drives dashboard "recommended next actions" (E3-S2 AC4). p95 < 300 ms target.

### PUT `/api/v1/profile`
- **Auth:** Bearer. **Story:** E3-S2, E3-S3 (AC2, AC3).
- **Body** (`ProfileUpdateRequest`) — all fields optional; provided fields replace stored values:
  ```json
  {
    "full_name": "Asha Rao",
    "headline": "Backend Engineer | Python · FastAPI",
    "summary": "...",
    "skills": ["Python", " python ", "FastAPI"],
    "education": [ ... ], "experience": [ ... ], "certifications": [ ... ], "projects": [ ... ]
  }
  ```
  Constraints: `headline` ≤ 160; `summary` ≤ 2000; `full_name` ≤ 120; skills trimmed+deduped server-side (case-preserved).
- **Success `200`** (`ProfileResponse`): updated profile incl. recomputed `completion_percentage`.
- **Errors:** `401`; `422` field-level (e.g. headline too long).
- **Rate limit:** global. **Notes:** atomic update; never mutates another user's profile.

---

## 4. Resume — `/api/v1/resume`

### POST `/api/v1/resume`
- **Auth:** Bearer. **Story:** E4-S2, E4-S3 (AC1, AC2, AC5).
- **Request:** `multipart/form-data`, field `file` (PDF or DOCX, ≤ 5 MB).
- **Success `201`** (`ResumeResponse`):
  ```json
  {
    "id": "uuid", "user_id": "uuid",
    "original_filename": "asha_rao_resume.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 184320,
    "file_hash": "b94d27b9...",
    "parse_status": "parsed",
    "structured_content": { "contact": { "full_name": "Asha Rao", "email": "...", "phone": null, "location": null, "links": [] }, "skills": ["Python"], "education": [], "experience": [], "certifications": [], "projects": [] },
    "parse_error": null,
    "disclosure": "Your resume content is processed by an external LLM provider (Anthropic Claude) to extract and structure it.",
    "created_at": "..."
  }
  ```
- **Errors:**
  - `415` `unsupported_file_type` (extension/MIME not PDF/DOCX) — stores nothing.
  - `422` `file_too_large` (> 5 MB) or `file_unreadable` (password-protected/corrupt/no extractable text) — stores nothing.
  - `401` `unauthorized`.
- **Rate limit:** global (parsing uses one LLM structuring call; not counted against the AI hourly limit, but the LLM client guardrails apply). **Notes:** `storage_key` and `embedding` are never returned. Replacing an existing resume supersedes the prior one. Disclosure (E4-S3 AC5) surfaced in the response and OpenAPI description.

### GET `/api/v1/resume`
- **Auth:** Bearer. **Story:** E4-S3 (AC3).
- **Success `200`** (`ResumeResponse`): the authenticated user's current resume + structured content.
- **Errors:** `404` `resume_not_found` (none uploaded); `401`.
- **Rate limit:** global.

### DELETE `/api/v1/resume/{resume_id}`
- **Auth:** Bearer. **Story:** E4-S1, E4-S3 (AC4).
- **Path param:** `resume_id` (UUID).
- **Success `204`:** no body. Removes the stored file, metadata, and cascaded `resume_reviews` + `job_match_runs`/`job_matches`.
- **Errors:** `404` `resume_not_found`; `403` `forbidden` (resume owned by another user — return 404-style opacity acceptable, but spec uses 403/404); `401`.
- **Rate limit:** global. **Notes:** satisfies privacy/data-deletion requirement.

---

## 5. AI Features — `/api/v1/ai`

> All `/ai/*` endpoints: **Bearer auth**, **AI hourly rate limit (10/hr/user)**, single-retry LLM guardrails, 60 s timeout. On 429 the LLM is not invoked. Errors carry `request_id`.

### POST `/api/v1/ai/resume-review`
- **Auth:** Bearer. **Story:** E6-S2, E6-S4 (AC1, AC3, AC4).
- **Headers:** optional `Accept: text/event-stream` to request streaming.
- **Body:** none (operates on the user's current resume) — optional `{ "resume_id": "uuid" }` to target a specific resume.
- **Success `200` (JSON, default)** (`ResumeReviewResponse`):
  ```json
  {
    "id": "uuid", "resume_id": "uuid", "status": "completed",
    "content": {
      "overall_summary": "...",
      "strengths": [ { "text": "...", "source_id": "ats-1" } ],
      "weaknesses": [ { "text": "...", "source_id": "resume-3" } ],
      "ats_issues": [ { "text": "...", "source_id": "ats-2" } ],
      "suggestions": [ { "text": "...", "source_id": "resume-5" } ]
    },
    "sources": [ { "source_id": "ats-1", "source_file": "ats_best_practices.md", "snippet": "..." } ],
    "cached": false,
    "model_id": "claude-opus-4-8",
    "request_id": "uuid",
    "created_at": "..."
  }
  ```
- **Success `200` (streaming, `Accept: text/event-stream`):** Server-Sent Events. Event sequence:
  - `event: meta` → `data: {"request_id":"uuid","resume_id":"uuid"}`
  - repeated `event: delta` → `data: {"text":"...partial content..."}`
  - terminal `event: result` → `data: { full ResumeReviewResponse JSON }`
  - on error mid-stream: `event: error` → `data: {"code":"...","message":"...","request_id":"uuid"}`
- **Errors:** `404` `resume_not_found` (no uploaded resume); `429` `rate_limited` (`Retry-After` header); `503` `ai_provider_unavailable`; `504` `ai_timeout`; `401`.
- **Rate limit:** AI hourly. **Notes:** Cached by `resume_file_hash` — an unchanged resume returns the prior completed review with `cached: true` and **does not** consume an LLM call (still counts toward rate limit unless served from cache; cache hits are exempt from rate-limit consumption). Each item references a `source_id` present in `sources` (explainability, E6-S2 AC2).

### POST `/api/v1/ai/profile-optimization`
- **Auth:** Bearer. **Story:** E6-S3, E6-S4 (AC2, AC3, AC4).
- **Body:** none (operates on the user's current profile).
- **Success `200`** (`ProfileOptimizationResponse`):
  ```json
  {
    "id": "uuid", "status": "completed",
    "content": {
      "headline_suggestions": [ { "text": "...", "source_id": "profile-2" } ],
      "summary_suggestion": { "text": "...", "source_id": "profile-2" },
      "missing_skills": ["CI/CD", "Kubernetes"],
      "section_suggestions": [ { "text": "Add measurable outcomes to experience bullets.", "source_id": "resume-4" } ]
    },
    "sources": [ { "source_id": "profile-2", "source_file": "profile_optimization.md", "snippet": "..." } ],
    "model_id": "claude-sonnet-4-6",
    "request_id": "uuid",
    "created_at": "..."
  }
  ```
- **Errors:** `409` `profile_insufficient` (profile too sparse to optimize — actionable message, E6-S3 AC3); `429` `rate_limited`; `503`/`504`; `401`.
- **Rate limit:** AI hourly. **Notes:** result persisted and re-fetchable (see GET below) without re-invoking the LLM.

### GET `/api/v1/ai/profile-optimization/latest`
- **Auth:** Bearer. **Story:** E6-S3 (AC5).
- **Success `200`** (`ProfileOptimizationResponse`): most recent completed optimization.
- **Errors:** `404` `optimization_not_found`; `401`.
- **Rate limit:** global (no LLM call). **Notes:** read-only re-fetch for display.

### GET `/api/v1/ai/resume-review/latest`
- **Auth:** Bearer. **Story:** E6-S2 (AC3 cache surfacing), E8-S4.
- **Success `200`** (`ResumeReviewResponse`): most recent completed review for the current resume.
- **Errors:** `404` `review_not_found`; `401`.
- **Rate limit:** global. **Notes:** read-only.

---

## 6. Jobs — `/api/v1/jobs`

### POST `/api/v1/jobs/match`
- **Auth:** Bearer. **Story:** E7-S2, E7-S3 (AC1, AC3, AC4). **AI rate-limited.**
- **Body:** none (matches the user's current parsed resume).
- **Success `200`** (`JobMatchResponse`):
  ```json
  {
    "run_id": "uuid",
    "resume_id": "uuid",
    "model_id": "claude-sonnet-4-6",
    "request_id": "uuid",
    "matches": [
      {
        "rank": 1,
        "fit_score": 82,
        "fit_explanation": "Strong Python/FastAPI alignment with the required backend stack.",
        "gaps": ["Kubernetes exposure", "Production on-call experience"],
        "job": {
          "id": "uuid", "title": "Junior Backend Engineer", "company": "Nimbus Cloud",
          "location": "Bengaluru (Hybrid)", "employment_type": "full_time", "seniority": "entry",
          "skills": ["Python", "FastAPI"]
        }
      }
    ],
    "created_at": "..."
  }
  ```
  `matches` is ordered by descending `fit_score`, up to 10 items.
- **Errors:** `409` `resume_not_parsed` (no parsed resume — actionable, not 500; E7-S3 AC3); `429` `rate_limited`; `503`/`504`; `401`.
- **Rate limit:** AI hourly. **Notes:** two-stage — pgvector top-10 retrieval (no LLM) → Claude re-rank. Honest low scores returned for weak matches rather than failing (E7-S2 AC4). The embedded `job` is a `JobSummary` (no `description`/`embedding`).

### GET `/api/v1/jobs`
- **Auth:** Bearer. **Story:** E7-S3 (job list — supports dashboard/browse).
- **Query params:** `limit` (default 20, max 50), `offset` (default 0), optional `q` (title/company substring).
- **Success `200`** (`JobListResponse`):
  ```json
  { "items": [ { "id": "uuid", "title": "...", "company": "...", "location": "...", "employment_type": "full_time", "seniority": "entry", "skills": ["Python"] } ], "total": 742, "limit": 20, "offset": 0 }
  ```
- **Errors:** `401`; `422` (bad pagination).
- **Rate limit:** global. **Notes:** returns `JobSummary` items (no `embedding`).

### GET `/api/v1/jobs/{job_id}`
- **Auth:** Bearer. **Story:** E7-S3 (AC2).
- **Path param:** `job_id` (UUID).
- **Success `200`** (`JobDetailResponse`):
  ```json
  {
    "id": "uuid", "title": "Junior Backend Engineer", "company": "Nimbus Cloud",
    "location": "Bengaluru (Hybrid)", "employment_type": "full_time", "seniority": "entry",
    "description": "Full posting text...", "skills": ["Python", "FastAPI", "PostgreSQL"],
    "source": "seed", "created_at": "..."
  }
  ```
- **Errors:** `404` `job_not_found`; `401`.
- **Rate limit:** global. **Notes:** `embedding` never exposed.

---

## 7. Endpoint summary (14 operations)

| # | Method | Path | Auth | AI-limited | Story |
|---|--------|------|------|-----------|-------|
| 1 | GET | `/api/v1/health` | none | no | E1-S3, E2-S3 |
| 2 | POST | `/api/v1/auth/register` | none | no | E2-S3 |
| 3 | POST | `/api/v1/auth/login` | none | no | E2-S3 |
| 4 | POST | `/api/v1/auth/refresh` | none | no | E2-S3 |
| 5 | POST | `/api/v1/auth/logout` | bearer | no | E2-S3 |
| 6 | GET | `/api/v1/profile` | bearer | no | E3-S3 |
| 7 | PUT | `/api/v1/profile` | bearer | no | E3-S3 |
| 8 | POST | `/api/v1/resume` | bearer | no | E4-S3 |
| 9 | GET | `/api/v1/resume` | bearer | no | E4-S3 |
| 10 | DELETE | `/api/v1/resume/{resume_id}` | bearer | no | E4-S3 |
| 11 | POST | `/api/v1/ai/resume-review` | bearer | yes | E6-S4 |
| 12 | GET | `/api/v1/ai/resume-review/latest` | bearer | no | E6-S2 |
| 13 | POST | `/api/v1/ai/profile-optimization` | bearer | yes | E6-S4 |
| 14 | GET | `/api/v1/ai/profile-optimization/latest` | bearer | no | E6-S3 |
| 15 | POST | `/api/v1/jobs/match` | bearer | yes | E7-S3 |
| 16 | GET | `/api/v1/jobs` | bearer | no | E7-S3 |
| 17 | GET | `/api/v1/jobs/{job_id}` | bearer | no | E7-S3 |

17 operations total (the "14" headline refers to core distinct screens-facing operations; full count above is 17 including read-back/list helpers).

---

## 8. Service-boundary note (Option-C readiness)

Each endpoint maps 1:1 to a service function (`auth_service.register`, `profile_service.get_profile`,
`resume_service.parse_and_store`, `resume_review_service.review_resume`,
`profile_optimization_service.optimize_profile`, `job_matching_service.match_jobs`, etc.).
Services take typed inputs and return typed DTOs with no HTTP coupling, so a later LangGraph
agent can call these functions directly as tools without going through HTTP. No agent endpoints
are part of the MVP contract.
