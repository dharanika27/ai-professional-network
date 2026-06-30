# ai-professional-network

An AI-powered professional networking platform inspired by LinkedIn that helps users build professional profiles, connect with other professionals, share content, discover jobs, and receive AI-powered career assistance. Integrates Agentic AI, LLMs, RAG, and intelligent workflows for resume review, profile optimization, interview preparation, job matching, and career coaching.

## Quick Reference

**Backend:** `cd backend && uv run pytest -x -q` | `uv run ruff check --fix .` | `uv run mypy src/`
**Frontend:** `cd frontend && npm test` | `npm run lint` | `npm run typecheck`
**Full stack:** Start backend + frontend (see init.sh)

## Architecture

Strict layered architecture: Types → Config → Repository → Service → API → UI.
One-way dependencies only. See `.claude/architecture.md` for full rules.

## Where to Find Things

| What | Where |
|------|-------|
| Architecture rules | `.claude/architecture.md` |
| Quality principles | `.claude/skills/code-gen/SKILL.md` |
| Testing patterns | `.claude/skills/testing/SKILL.md` |
| Evaluation rubric | `.claude/skills/evaluation/SKILL.md` |
| Sprint contract format | `.claude/skills/evaluation/references/contract-schema.json` |
| Playwright patterns | `.claude/skills/evaluation/references/playwright-patterns.md` |
| Human control knobs | `.claude/program.md` |
| Session recovery | `claude-progress.txt` |
| Feature tracking | `features.json` |
| Learned rules | `.claude/state/learned-rules.md` |

## Pipeline Commands

| Command | Purpose |
|---------|---------|
| `/brd` | Socratic interview → BRD |
| `/spec` | BRD → stories + features.json |
| `/design` | Architecture + schemas + mockups |
| `/build` | Full 8-phase pipeline |
| `/auto` | Autonomous ratcheting loop |
| `/implement` | Code gen with agent teams |
| `/evaluate` | Run app, verify contract |
| `/review` | Evaluator + security review |
| `/test` | Test plan + Playwright E2E |
| `/deploy` | Docker Compose + init.sh |

## Code Style

- TDD mandatory: test first, then implement
- 100% meaningful coverage target, 80% floor
- Functions < 50 lines, files < 300 lines
- Static typing everywhere (zero `any`)
- See `.claude/skills/code-gen/SKILL.md` for full rules

## AI / LLM Integration

- **LLM provider is Groq** (`GROQ_API_KEY`), behind an `LLMProvider` abstraction — NOT Anthropic.
  See `specs/design/amendments/001-llm-provider-abstraction.md`. Anthropic config is deferred.
- Embeddings: local `bge-small` (384-dim) behind `EmbeddingProvider`. RAG retrieval uses
  `pgvector` on PostgreSQL.
- Treat prompts, providers, and chains as **service-layer** concerns — never call LLM/embedding
  APIs from the UI or repository layers. Keep all guardrails (schema validation, retry, safe
  errors, metadata-only logging) in the provider-agnostic `llm_client.py`.
- See `.claude/skills/code-gen/SKILL.md` for LLM integration patterns.

## Git

Branch: `<type>/<description>` (e.g., `feat/user-auth`)
Commits: conventional format (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`)
