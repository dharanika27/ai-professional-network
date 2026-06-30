# Design Rationale — AI Professional Network (MVP)

**Project:** ai-professional-network
**Version:** 1.0 (MVP)
**Status:** Decision log. Consistent with the canonical contracts
(`data-models.md`, `api-contracts.md`, `folder-structure.md`, `component-map.md`) and
`system-design.md`. Introduces no new entities, fields, or endpoints.
**Date:** 2026-06-30

This is an architecture decision log. Each entry records **options considered**, the
**decision**, the **rationale**, **trade-offs accepted**, and **future revisit triggers** —
the conditions under which we would reopen the decision.

| ID | Decision | Status |
|----|----------|--------|
| D1 | AI architecture: Option B (RAG-grounded + structured outputs) | Accepted |
| D2 | Embeddings: local bge-small behind `EmbeddingProvider` | Accepted |
| D3 | Auth: in-memory JWT access + rotating refresh in an HttpOnly cookie (vs sessions / localStorage) | Accepted |
| D4 | Execution: synchronous + SSE streaming (vs background queue) | Accepted |
| D5 | Jobs: seeded dataset behind `JobLoader` (vs external API) | Accepted |
| D6 | Vector store: PostgreSQL + pgvector (vs dedicated vector DB) | Accepted |
| D7 | Strict layered architecture, machine-enforced | Accepted |
| D8 | snake_case on the wire (request + response) | Accepted |

---

## D1 — AI architecture: Option B (RAG-grounded + structured outputs)

**Options considered**
- **A — Stateless prompt pipelines:** one Claude call per feature; job matching is pure vector
  search. Simplest, lowest latency.
- **B — RAG-grounded + structured outputs (CHOSEN):** curated KB retrieval + grounding +
  citations; two-stage matching (vector top-10 → LLM re-rank with fit/gap); **all** outputs
  schema-validated against Pydantic types.
- **C — Agentic orchestration:** a Career Assistant agent chaining multi-step tool workflows.

**Decision:** Adopt **B now**; defer **C to Phase 2**; reject **A**.

**Rationale**
- The project's stated goal is to demonstrate genuine **RAG/AI-engineering depth**; A is too
  shallow to prove that (`brd.md` §7).
- B is **deterministic and testable**: grounded context + schema validation + single retry make
  outputs reproducible enough for the `>80%` backend coverage target and design-eval loop.
- B yields **explainability for free**: every `ReviewItem.source_id` cites a retrieved
  `Citation`, which the UI surfaces — a concrete product differentiator over a LinkedIn clone.
- C carries high test/eval/latency/cost risk for an MVP; deferring it avoids non-determinism
  while we harden the foundation.

**Trade-offs accepted**
- Higher latency and token cost than A (extra retrieval + larger grounded prompts; mitigated by
  60 s timeout, hash caching, and rate limits).
- A curated KB must be authored and ingested (`kb/*.md`, `scripts/ingest_kb.py`).
- Schema-validation + retry adds service complexity in `claude_client`.

**Future revisit triggers**
- Foundation is stable and tests/evals are green → **promote to C** by layering a LangGraph
  agent over the existing service functions (`system-design.md` §9) — purely additive.
- Grounded outputs prove low-value for a feature → selectively fall back toward A for that
  feature only (the service boundary localizes the change).

---

## D2 — Embeddings: local bge-small behind an `EmbeddingProvider` abstraction

**Options considered**
- **Hosted embeddings API** (e.g. a vendor endpoint): no model to ship, easy updates.
- **Local `BAAI/bge-small-en-v1.5` in-process (CHOSEN):** 384-dim, bundled in the container.
- **Separate embedding microservice:** isolated scaling from day one.

**Decision:** **Local bge-small, in-process**, hidden behind the `EmbeddingProvider` interface
(`services/ai/embedding_provider.py`).

**Rationale**
- **No external embeddings dependency or per-call cost/latency** — privacy-friendly for resume
  text (one fewer third party touching PII) and consistent with "no external embeddings API in
  v1" (`brd.md` §10).
- **Deterministic, offline-capable** local verification (manifest `verification.mode = local`).
- 384-dim is small/fast and is the **fixed contract** across `resumes`, `jobs`,
  `knowledge_chunks` (`data-models.md` §0: `vector(384)`; any mismatch is a defect).
- The **abstraction** keeps the option open: swapping providers touches one module.

**Trade-offs accepted**
- Model weights inflate the image and add cold-start/memory cost (mitigated: lazy
  process-lifetime singleton).
- Embedding CPU competes with request handling in a single process (see scalability path).
- Re-embedding everything is required if we ever change the model/dimension.

**Future revisit triggers**
- Embedding latency/memory dominates → **extract to a dedicated embedding service** behind the
  same interface (`system-design.md` §8).
- A clearly superior hosted/larger model emerges → swap the impl (plan a full re-embed + a
  migration if dimension changes from 384).

---

## D3 — Authentication: JWT access + rotating refresh (vs server sessions)

**Options considered**
- **Server-side sessions** (cookie + session store): easy revocation, stateful.
- **JWT access + rotating refresh tokens (CHOSEN):** stateless access, refresh persisted as a
  SHA-256 hash with rotation/revocation.

**Decision:** **Short-lived JWT access (15 min)** + **opaque rotating refresh token**; only the
refresh token's hash is stored (`refresh_tokens.token_hash`), with `revoked` + `rotated_to`
for the rotation chain.

**Token transport (security hardening):** the **access token** is returned in the JSON body and
held by the SPA **in memory only**; the **refresh token is transported solely as an
`HttpOnly; Secure; SameSite=Strict` cookie** scoped to `Path=/api/v1/auth`. It never appears in
any request/response body and is never readable by JavaScript. (This supersedes the earlier
MVP idea of storing the refresh token in `localStorage`.)

**Rationale**
- **Stateless access tokens** let the API scale horizontally with no shared session store
  (`system-design.md` §8) — a deliberate enabler of the scalability story.
- Rotation + revocation give a **practical security posture**: short access TTL limits blast
  radius; refresh rotation detects reuse; logout/rotation set `revoked`.
- Storing only the **hash** means a DB leak does not expose usable tokens (mirrors password
  handling). Argon2id for passwords (`data-models.md` §2.1).
- **HttpOnly cookie for the refresh token removes the XSS token-theft vector** — JS cannot read
  it — which is the single biggest reason to prefer it over `localStorage`. `Secure` forces
  HTTPS-only transmission; `SameSite=Strict` + the scoped `Path` provide the CSRF mitigation,
  and keeping the access token in memory means a stolen access token dies within 15 minutes.
- Matches the canonical contract exactly: `AuthSessionResponse` (no `refresh_token` in body),
  `/auth/refresh` rotation via cookie, `expires_in: 900` (`api-contracts.md` §2,
  `security-architecture.md`).

**Trade-offs accepted**
- Access-token revocation is not instant (valid until TTL); acceptable given 15-min TTL.
- Refresh-rotation bookkeeping (`rotated_to`, `revoked`) adds repository logic.
- Client must implement transparent refresh (handled in `frontend/api/client.ts`).
- Cookie transport requires **credentialed CORS** (`credentials: 'include'` + a strict allowed
  origin) and a `SameSite=Strict` posture; cross-site embedding of the auth flow is not
  supported in the MVP. If that becomes necessary, add an explicit CSRF token (double-submit).

**Future revisit triggers**
- Need for **instant global logout / token revocation** → add a short-TTL deny-list (Redis) or
  move to sessions for sensitive operations.
- Adding **Google OAuth** (deferred, `brd.md` §10) → the auth module is designed to accommodate
  an additional credential source without changing the token model.

---

## D4 — Execution model: synchronous + SSE streaming (vs background queue)

**Options considered**
- **Background job queue** (Celery/RQ + worker): durable long tasks, instant API return.
- **Synchronous request/response + SSE streaming (CHOSEN):** AI endpoints run inline with a
  60 s timeout; resume review can stream via `text/event-stream`.

**Decision:** **Synchronous** AI calls with **SSE streaming** where it helps (resume review),
loading states elsewhere. Background queues explicitly **deferred** (`brd.md` §5).

**Rationale**
- **Drastically simpler MVP**: no broker, no worker fleet, no result-store, no async status
  endpoints — fewer moving parts to deploy and test locally.
- **Streaming covers the worst UX case** (long resume review) by emitting `meta`/`delta`/
  `result` events, so users get progressive feedback without a queue
  (`api-contracts.md` §5).
- Bounded by a **60 s timeout** + per-user rate limit + hash caching, keeping inline execution
  safe for MVP traffic.
- Keeps the **service functions delivery-agnostic** (they return typed DTOs), so adding a queue
  later changes only the API delivery shape.

**Trade-offs accepted**
- A long LLM call **occupies a worker** for its duration (concurrency cost).
- A dropped connection loses an in-flight (non-cached) result; the user retries.
- Streaming adds SSE handling on both ends (`useStream`, `lib/sse.ts`).

**Future revisit triggers**
- Sustained concurrency exhausts workers, or tasks routinely approach 60 s → introduce a
  **background queue** returning a job id + status; the unchanged services become the worker
  body (`system-design.md` §8).
- A multi-step Option-C agent (D1) makes single-request latency untenable → queue the
  orchestration.

---

## D5 — Jobs: seeded dataset behind a `JobLoader` (vs external jobs API)

**Options considered**
- **External jobs API** (live postings): realistic, fresh, but adds a vendor, rate limits,
  licensing, and flakiness.
- **Seeded ~500–1000 postings behind a `JobLoader` interface (CHOSEN):** `source='seed'` now,
  `source='api'` later.

**Decision:** **Seed** the dataset (`seeds/jobs/jobs_seed.json` via `seeds/loaders/job_loader.py`),
architected for a later real-API swap. No external jobs API in v1 (`brd.md` §10). The seed is a
**curated, realistic dataset that combines hand-authored and AI-generated job descriptions
spanning multiple industries and experience levels** (entry → senior), so vector matching is
exercised across diverse roles rather than a narrow slice. (Resolves `brd.md` §13.4 open
question.)

**Rationale**
- **Deterministic, offline, license-clean** data for local verification, tests, and the demo —
  no third-party dependency to break the vertical.
- A realistic seed (~500–1000) is **enough to exercise** embed → pgvector top-10 → LLM re-rank
  end to end (`brd.md` §6).
- The **`JobLoader` + `jobs.source` enum** (`data-models.md` §2.7) make the swap a localized,
  additive change — matching logic is untouched.

**Trade-offs accepted**
- Postings can be **stale/limited**; weak matches are expected → matching returns **honest low
  scores** rather than failing (E7-S2 AC4).
- Authoring/curating realistic seed data is upfront effort (`brd.md` §13.4 open question).

**Future revisit triggers**
- Product needs **live postings** → add an API-backed `JobLoader` (`source='api'`), reuse the
  embed/index pipeline.
- Corpus grows large enough to pressure pgvector recall → see **D6**.

---

## D6 — Vector store: PostgreSQL + pgvector (vs a dedicated vector DB)

**Options considered**
- **Dedicated vector DB** (e.g. a managed ANN store): purpose-built recall/scale.
- **PostgreSQL + pgvector (CHOSEN):** vectors as `vector(384)` columns with HNSW indexes,
  co-located with relational data.

**Decision:** **PostgreSQL + pgvector** for all embeddings (`resumes`, `jobs`,
`knowledge_chunks`), HNSW indexes (`data-models.md` §2.4/§2.7/§2.10). This is fixed by the
manifest stack and reaffirmed here.

**Rationale**
- **One datastore** for relational + vector data: single connection, single backup, **atomic
  transactions** spanning rows and their embeddings; no cross-store consistency problem.
- **Operationally trivial** for the MVP corpus (~500–1000 jobs + KB chunks); HNSW gives fast
  recall at low write volume (ivfflat is an acceptable alternative after `ANALYZE`).
- **No extra service** to deploy/learn — keeps local verification and docker-compose minimal.
- Repository methods (`retrieve_top_jobs`, KB top-k) **encapsulate** the similarity query, so
  the store is swappable without touching services.

**Trade-offs accepted**
- pgvector won't match a specialized engine at **very large scale** or extreme QPS.
- Index tuning (HNSW params / ivfflat `lists`) is a manual operational concern.

**Future revisit triggers**
- Corpus reaches **millions of vectors** or recall/latency targets slip under load → migrate
  the similarity methods in `knowledge_repository`/`job_repository` to a **dedicated vector DB**;
  the repository interface is the seam (`system-design.md` §8).

---

## D7 — Strict layered architecture, machine-enforced

**Options considered**
- **Pragmatic/loose layering:** convention only, faster to write, drifts over time.
- **Strict one-way layering, enforced in CI (CHOSEN):** Types → Config → Repository → Service →
  API → UI; LLM/RAG only in services.

**Decision:** **Strict layering with machine enforcement** (import-linter contract in CI + mypy
`--strict` over `app/types/`), matching `folder-structure.md`.

**Rationale**
- **Clean, HTTP-free service seams are the explicit prerequisite** for the deferred Option-C
  agent (D1) and for swapping a synchronous call to a queue (D4) — the layering *is* the
  extensibility strategy.
- Keeping **LLM/RAG strictly in services** means repositories stay pure data access and the API
  stays thin, which makes each layer independently unit-testable (supports `>80%` coverage).
- **Enforcement prevents architectural drift** under time pressure; a violating import fails CI,
  not a code review.

**Trade-offs accepted**
- More files and explicit DTO mapping (no shortcut from API straight to DB).
- Some boilerplate passing typed objects across layers.
- Contributors must learn the dependency rule.

**Future revisit triggers**
- The rule blocks a genuinely necessary pattern → introduce a documented, narrowly-scoped
  exception in the import-linter contract rather than abandoning enforcement.

---

## D8 — snake_case on the wire (request + response)

**Options considered**
- **camelCase JSON** (JS-idiomatic frontend) with a translation layer at the boundary.
- **snake_case everywhere (CHOSEN):** request and response bodies match DB columns and Pydantic
  fields exactly.

**Decision:** **snake_case on the wire**, stated explicitly so frontend and backend never
disagree (`data-models.md` §0, `api-contracts.md` §0). The frontend's `api/types.ts` uses
snake_case DTOs.

**Rationale**
- **Eliminates a whole class of bugs** and a translation layer: DB column → Pydantic field →
  JSON key → TS type are **identical names** end to end.
- Makes the **OpenAPI ↔ data-model lock-step** trivial to verify (the two schema companions
  mirror the same names).
- Reduces mapping code and review overhead; the contract is unambiguous for both teams.

**Trade-offs accepted**
- Slightly **non-idiomatic for TypeScript/JS** consumers (snake_case keys in the frontend).
- If a third-party client ever expects camelCase, an adapter would be needed at that edge.

**Future revisit triggers**
- A public/partner API with strong camelCase expectations is introduced → add a **boundary
  adapter for that surface only**, leaving the internal contract snake_case.

---

## Cross-cutting consequences

- **Privacy** (D1/D2/D3): local embeddings keep resume text off a second vendor; metadata-only
  `ai_request_logs`; hashed credentials; hard-delete cascades (`data-models.md` §4–§5).
- **Testability** (D1/D4/D7): deterministic grounded outputs + pure layers + delivery-agnostic
  services underpin the `>80%` coverage target.
- **Extensibility** (D1/D4/D5/D6/D7): every deferred capability — Option-C agent, background
  queue, real jobs API, dedicated vector DB, hosted embeddings — sits behind an existing
  interface or is a purely additive layer, so none requires refactoring the core.
