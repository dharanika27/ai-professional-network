# Amendment 001 — LLM provider abstraction (Groq, not Anthropic)

**Date:** 2026-06-30
**Status:** Approved by user. Supersedes Anthropic/Claude-specific details in
`ai-service-architecture.md`, `system-design.md`, `deployment.md`, and `design-rationale.md`.
**Applies to:** Epic E6 (AI Features) primarily; config in E1-S2.

## Decision

The MVP LLM provider is **Groq** (via `GROQ_API_KEY`), not Anthropic/Claude. The design docs
were authored Claude-centric; this amendment redirects the LLM layer to a provider abstraction
with Groq as the concrete implementation. All Anthropic-specific configuration is **deferred**
(not removed from history, but not implemented in the MVP).

## What changes

1. **Provider abstraction (mirrors `EmbeddingProvider`).** Introduce an `LLMProvider` interface
   in the service layer with the methods the AI services need (e.g. `complete(...)` and a
   streaming `stream(...)` for SSE resume review, returning schema-validatable text/objects).
   - `app/services/ai/llm_provider.py` — the interface (Protocol/ABC).
   - `app/services/ai/groq_provider.py` — the concrete `GroqProvider` (MVP).
   - Rename/repurpose the planned `claude_client.py` → `llm_client.py` (provider-agnostic
     orchestration: guardrails, schema validation, single retry, timeout, metadata-only
     logging) that delegates to the injected `LLMProvider`. Anthropic can be added later as a
     second provider without touching services.

2. **Config (`app/config/llm_config.py`, E1-S2).** Env-driven, no literals:
   - `GROQ_API_KEY` (required for AI groups; not needed for Groups A–B).
   - `LLM_PROVIDER` (default `groq`) to select the provider.
   - Groq model ids per task (structuring / review / optimization / job re-rank) — replace the
     Opus/Sonnet defaults with Groq model names; keep the per-task selection pattern.
   - Keep `LLM_TIMEOUT` (60s), AI rate limit, and token-budget hooks as designed.
   - **Remove the `ANTHROPIC_API_KEY` requirement** from `.env.example`, `Settings`, fail-fast
     validation, deployment secrets, and CI. It becomes optional/future.

3. **Guardrails unchanged.** Schema-validated structured outputs, single bounded retry, safe
   user-facing errors, request-id + metadata-only logging (never PII/resume text), caching of
   deterministic ops, and per-user rate limiting all stay exactly as in `ai-service-architecture.md`
   — they live in the provider-agnostic `llm_client.py`, above the provider.

4. **Docs to reconcile when E6 is built.** Treat every "Claude/Anthropic/`claude_client.py`/
   `ANTHROPIC_API_KEY`" reference in `ai-service-architecture.md`, `system-design.md`,
   `deployment.md`, and `design-rationale.md` as "the configured `LLMProvider` (Groq for MVP)".

## Out of scope for this amendment
- No change to the RAG pipeline, embeddings (`bge-small` stays), data models, API contracts
  (no AI-provider detail leaks into the wire contract), or the LangGraph (Option C) deferral.

## Rationale
Provider independence is good engineering and matches the existing `EmbeddingProvider` pattern;
the user selected Groq. The abstraction keeps the swap localized to the service layer.
