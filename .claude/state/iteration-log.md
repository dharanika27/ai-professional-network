# Iteration Log
<!-- Append-only. Do not edit or delete entries. -->

<!-- ENTRY FORMAT — Append one block per group iteration:

## Group {ID} — {Group Name}
- **Date:** {ISO 8601}
- **Status:** PASS | FAIL (attempt {N} of 3) | BLOCKED
- **Stories:** [{story IDs}]
- **Mode:** full | lean | solo | turbo
- **Summary:** {1-2 sentence description of what happened}
- **Checks:** {N} API, {N} Playwright, {N} design passed
- **Coverage:** {N}% (baseline: {N}%)
- **Learned Rules Applied:** [{rule numbers}]

### Micro-DAG (if agent team was used)
- Phase 1 (Independent): [{teammate IDs}]
- Phase 2 (Depends on Phase 1): [{teammate IDs}]
- Phase 3 (Integrators): [{teammate IDs}] (shared files: [{paths}])

-->

## Group B — Repository Substrate
- **Date:** 2026-06-30
- **Status:** IN PROGRESS (attempt 1 of 3)
- **Stories:** [E2-S1, E3-S1, E4-S1, E5-S2, E7-S1]
- **Mode:** full (5 parallel teammates)
- **Summary:** Implementing repositories (user/refreshtoken/profile/resume/knowledge/job), secure storage backend, KB ingestion, job seed (500-1000 postings), pgvector top-k search.

### Micro-DAG
- Phase 1 (All Independent — parallel): [teammate-E2, teammate-E3, teammate-E4, teammate-E5, teammate-E7]
  - teammate-E2: user_repository.py, refresh_token_repository.py
  - teammate-E3: profile_repository.py
  - teammate-E4: resume_repository.py, storage/base.py, storage/local_storage.py
  - teammate-E5: services/ai/kb_ingestion.py, repositories/knowledge_repository.py, scripts/ingest_kb.py, kb/*.md
  - teammate-E7: repositories/job_repository.py, seeds/loaders/job_loader.py, seeds/jobs/jobs_seed.json, scripts/seed_jobs.py
- Phase 2 (Integration): Generator wires repositories/__init__.py, runs tests + coverage gate

## Group A — Foundation
- **Date:** 2026-06-30
- **Status:** PASS (attempt 1 of 3)
- **Stories:** [E1-S1, E1-S2, E1-S3, E5-S1]
- **Mode:** full
- **Summary:** Backend foundation — Pydantic types/DTOs, env-driven Settings (Groq, no Anthropic key), SQLAlchemy models + Alembic migration with pgvector(384), local bge-small EmbeddingProvider. Independently verified by orchestrator.
- **Checks:** 0 API, 0 Playwright, 0 design (no API/UI in Group A); 34 contract checks; 172 unit/integration tests
- **Coverage:** 99% (baseline: 0% -> 99%)
- **Learned Rules Applied:** none
- **Gate fixes:** ruff --fix/format on migrations/ (5 lint + 2 format) auto-corrected before commit

## Group B — Repository & Data-Seeding Substrate
- **Date:** 2026-06-30
- **Status:** PASS (attempt 1 of 3) — RESUMED after interruption; implementation was on disk uncommitted, verified & completed by orchestrator
- **Stories:** [E2-S1, E3-S1, E4-S1, E5-S2, E7-S1]
- **Mode:** full
- **Summary:** 6 repositories (user, refresh_token, profile, resume, knowledge, job), secure LocalStorage (opaque keys, non-web-served, path-traversal-safe), KB ingestion (chunk->embed->pgvector, idempotent on content_hash, 5 KB markdown docs), job repo + curated 600-job seed (hand-authored + AI-generated, idempotent on external_ref) + embedding index. Repos are data-access only (no commit/rollback, injected session).
- **Checks:** 0 API, 0 Playwright, 0 design; 39 contract checks; 335 unit/integration tests
- **Coverage:** 100% (baseline: 99%, kept at 99 to avoid brittleness)
- **Learned Rules Applied:** none
- **Self-heal:** 1 fix — test_get_resume_by_id mock omitted parse_error/updated_at (test-mock bug, not production); completed the mock. Also ruff-format on 2 test files.
