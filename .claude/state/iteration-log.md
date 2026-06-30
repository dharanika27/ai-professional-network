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
