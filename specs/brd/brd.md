# Business Requirements Document — AI Professional Network

**Project:** ai-professional-network
**Version:** 1.0 (MVP)
**Date:** 2026-06-30
**Status:** Draft — awaiting approval
**Type:** Portfolio + learning project, built to production-grade standards

---

## 1. Executive Summary

An AI-first professional career platform that helps students, recent graduates, and job
seekers present themselves competitively and find well-matched roles. The MVP delivers one
complete, polished vertical — **Sign up → build profile → upload resume → AI Resume Review →
AI Profile Optimization → AI Job Matching** — grounded in a curated retrieval-augmented (RAG)
knowledge base and powered by Claude.

Social-networking capabilities (feed, posts, connections, messaging) and additional AI
features are intentionally deferred to later phases. The system is engineered to production
standards (layered architecture, typed boundaries, ≥80% backend coverage, CI/CD, secure
secret handling) so it can be extended into a real product and showcases full-stack +
AI-engineering competence.

---

## 2. Problem Statement

Students, recent graduates, and job seekers struggle to present themselves effectively in a
competitive market. They produce ATS-unfriendly resumes, leave profiles unoptimized, can't
identify their own skill gaps, and have difficulty discovering roles that match their
experience. Existing professional networks offer connections but little **personalized,
explainable AI guidance** across the early-career journey.

**Cost of not solving it (for the project's purpose):** without a focused, polished vertical,
the work becomes a shallow feature pile that demonstrates neither strong product craft nor real
AI-engineering depth — the two things this portfolio exists to prove.

---

## 3. Target Users

**Primary (v1):** Students, recent graduates, and active job seekers — typically
non-technical, mobile- and desktop-using, motivated to improve their job prospects.

**Secondary (later phases):** Recruiters, hiring managers, and companies (recruiter dashboard,
company pages) — explicitly out of MVP.

---

## 4. Success Metrics

This is a portfolio/learning project; success is measured by **engineering milestones**, not
user growth:

| # | Milestone | Target |
|---|-----------|--------|
| 1 | Production-ready MVP of the core vertical | Auth, profile, resume upload, 3 AI features, job matching all functional end-to-end |
| 2 | AI features integrated | ≥3 (Resume Review, Profile Optimization, Job Matching) with grounded RAG outputs |
| 3 | Public deployment | Deployed with CI/CD pipeline |
| 4 | Backend test coverage | >80% on core backend modules |
| 5 | Documentation & repo polish | Architecture diagrams, comprehensive docs, polished GitHub repo |
| 6 | Non-AI API latency | p95 < 300 ms |

---

## 5. Scope

### In Scope (v1)
- Email/password authentication (JWT access + refresh, Argon2 hashing)
- User onboarding and professional profile management (view/edit)
- Resume upload (PDF/DOCX) with hybrid parsing (local extraction → LLM structuring)
- **AI Resume Review** — RAG-grounded, structured, explainable critique
- **AI Profile Optimization** — RAG-grounded profile improvement guidance
- **AI Job Matching** — vector retrieval over seeded jobs → LLM re-ranking with fit/gap explanation
- Seeded jobs dataset (~500–1000 realistic postings), architected for later real-API swap
- Curated RAG knowledge base (ATS, resume/profile, interview, career material)
- Dashboard hub, Job Details, Settings (incl. data deletion)
- Light + dark theming, fully responsive, WCAG 2.1 AA

### Out of Scope (later phases)
Professional feed · posts · comments · likes · connections · messaging · notifications ·
recruiter dashboard · company pages · advanced search · AI Interview Coach · AI Career Coach ·
AI Networking Assistant · AI Feed Summarizer · admin dashboard · mobile application ·
Google OAuth · background job queues · external jobs API.

---

## 6. MVP Definition

The smallest deployable slice that delivers real value and demonstrates the full technical
story:

> **Sign up → complete professional profile → upload resume → receive AI Resume Review →
> receive AI Profile Optimization → see AI-matched jobs with fit/gap explanations.**

This single vertical exercises authentication, profile management, file upload + parsing,
local embeddings, pgvector retrieval, RAG grounding, structured LLM outputs, and an
end-to-end user journey — deep and polished rather than broad and shallow.

---

## 7. Alternatives Considered

**AI architecture** was the key decision (the rest of the stack is fixed by the manifest).

| Option | Description | Verdict |
|--------|-------------|---------|
| A — Stateless prompt pipelines | One Claude call per feature; matching = pure vector search | Rejected: too shallow to demonstrate RAG/AI-engineering depth |
| **B — RAG-grounded + structured outputs (CHOSEN)** | Retrieval + grounding + citations; two-stage matching (vector top-10 → LLM re-rank with fit/gap); all outputs schema-validated | **Chosen** |
| C — Agentic orchestration | A career agent with tools chaining multi-step workflows | Deferred to Phase 2: high test/eval/latency risk for an MVP |

**Rationale:** Option B proves genuine RAG competence (the stated goal) while staying
deterministic and testable. Feature logic is exposed as **clean service functions**
(parse_resume, structure_resume, embed, retrieve, score_fit, rewrite_section) so an
**Option-C orchestration agent** can be layered on in Phase 2 without refactoring the core.

---

## 8. Technical Architecture

- **Backend:** Python 3.12, FastAPI, uv, ruff, mypy, pytest.
- **Frontend:** TypeScript, React, Vite, npm, eslint, tsc, vitest.
- **Database:** PostgreSQL + pgvector.
- **AI:** Claude (Opus 4.8 / Sonnet 4.6); streaming for long tasks (resume review).
- **Architecture pattern:** strict layered, one-way dependencies — Types → Config →
  Repository → Service → API → UI. LLM/RAG logic lives in the **service layer** only.
- **Resume parsing:** hybrid — deterministic local text extraction (`pypdf` / `python-docx`)
  → LLM normalization into {contact, skills, education, experience, certifications, projects}.
- **Embeddings:** local `BAAI/bge-small-en-v1.5` (sentence-transformers) behind an
  `EmbeddingProvider` abstraction for later provider swap; used for resumes, job descriptions,
  and KB chunks.
- **RAG pipeline:** curated markdown KB → chunk → embed → index in pgvector;
  retrieve-then-generate for grounded, explainable outputs.
- **Job matching:** embed resume → pgvector top-10 retrieval → LLM re-rank with fit/gap
  explanation.
- **Execution model:** synchronous request/response with loading states; streaming where it
  helps. Background jobs/queues deferred.
- **Config:** all values externalized (env vars); centralized LLM config for future token
  budgets and provider switching.

---

## 9. Data Model Overview

Primary entities (to be detailed in `/spec` and `/design`):

| Entity | Purpose |
|--------|---------|
| **User** | Auth identity; email, Argon2 password hash, theme preference |
| **RefreshToken** / session | JWT refresh-token lifecycle |
| **Profile** | Professional profile (headline, summary, skills, education, experience, certifications, projects, completion %) |
| **Resume** | Uploaded file metadata + extracted/structured content; user-deletable |
| **ResumeReview** | AI review result (structured critique, cached by file hash) |
| **ProfileOptimization** | AI profile-improvement result |
| **Job** | Seeded job posting (title, company, description, location, skills, embedding) |
| **JobMatch** | Ranked match result for a user (score, fit explanation, gaps) |
| **KnowledgeChunk** | RAG KB chunk + embedding (pgvector) |
| **AIRequestLog** | Request ID + metadata only (never PII/resume text) |

---

## 10. External Integrations

- **Claude API** (Anthropic) — resume structuring, review, profile optimization, job re-ranking.
  Resume content is processed by this external LLM provider (disclosed to users).
- **Local embedding model** — bundled in-container; no external embeddings API in v1.
- **No external jobs API in v1** — seeded dataset, architected for later swap.
- **No OAuth provider in v1** — auth module designed for later Google OAuth.

---

## 11. Edge Cases & Constraints

**AI guardrails:** schema-validate all LLM outputs · retry once on transient/invalid output ·
safe user-facing errors (no internal detail) · log failures with request IDs + metadata only
(never PII/resume text) · per-user rate limiting on AI endpoints · cache deterministic ops
(unchanged resume → cached review) · centralized LLM config for future token budgets/provider
switch.

**Upload policy:** PDF/DOCX only · ≤5 MB · reject password-protected/corrupt files · reject
files where meaningful text can't be extracted · validate MIME type + extension · treat all
extracted text as untrusted · system instructions always override in-resume prompt-injection.

**Privacy & security:** never log PII/resume text · secure resume storage · Argon2 password
hashing · users can delete resumes + associated AI analyses · HTTPS in deployment · secrets in
env vars only · documented disclosure that resumes are processed by an external LLM provider ·
architecture extensible to GDPR-style compliance.

**Likely failure modes:** complex-layout extraction failures · invalid/incomplete LLM JSON ·
weak matches from a small seed set · embedding cold-start latency · AI provider outages ·
resume-borne prompt injection · misconfiguration (missing keys/env). System fails gracefully
with actionable error messages.

**Operational targets:** non-AI p95 < 300 ms · AI endpoint timeout 60 s · 5 MB uploads ·
PDF/DOCX · ~500–1000 seeded jobs · vector top-10 → LLM re-rank · per-user AI rate limits ·
health-check endpoints · fully externalized config.

---

## 12. UI Context

**Screens (v1):** Landing · Register · Login · Onboarding · Dashboard · Profile View ·
Profile Edit · Resume Upload · AI Resume Review · AI Profile Optimization · Job Matching ·
Job Details · Settings.

**Dashboard hub** surfaces: profile completion, recent AI analyses, matched jobs, recommended
next actions.

**Brand & design identity:** distinctive modern/premium **AI-first SaaS** look (explicitly NOT
a LinkedIn clone) — clean & minimal, spacious layouts, soft rounded corners, professional
typography, card-based UI, subtle gradients, AI-inspired accents, strong visual hierarchy,
smooth micro-interactions, a consistent design system.

**Responsiveness:** fully responsive, desktop-primary, excellent tablet/mobile-browser UX.

**Accessibility:** WCAG 2.1 AA — keyboard navigation, screen-reader support, semantic HTML,
accessible forms, focus indicators, sufficient contrast, ARIA where appropriate.

**Theming:** light + dark mode in v1, OS-default with manual toggle, built into the design
system from the start (not bolted on).

**Design calibration:** consumer-facing profile — design-critic GAN loop, threshold 8,
originality/craft/design-quality weighted 1.5×, up to 10 iterations.

---

## 13. Open Questions

1. **Resume storage backend** — local container volume for v1, or object storage (S3-compatible)?
   (Recommend local volume for MVP; abstract behind a storage interface.)
2. **Embedding model hosting** — in-process within the FastAPI container vs. a separate
   embedding microservice? (Recommend in-process for MVP simplicity; the `EmbeddingProvider`
   abstraction allows extraction later.)
3. **Deployment target** — which host for the public CI/CD deploy (Render / Railway / Fly.io /
   VPS)? Affects `/deploy` artifacts.
4. **Seed job source** — hand-authored vs. generated vs. a public static dataset for the
   ~500–1000 postings? (Affects realism and licensing.)
5. **Streaming scope** — streaming for resume review only, or also profile optimization?

---

*Next step: `/spec` — decompose this BRD into epics, user stories, a dependency graph, and a
machine-readable feature list. Requires human approval of this BRD first.*
