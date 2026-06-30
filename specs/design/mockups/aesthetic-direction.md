# Aesthetic Direction — "Aurora" Design Language

**Project:** AI Professional Network (MVP)
**Status:** Visual contract. Every mockup and later production code references these tokens.
**Note:** Mockups render fully offline — no CDN. Fonts use a curated system stack with strong
fallbacks; distinctiveness comes from scale, weight, tracking, gradient accents, and spatial
language rather than a webfont download.

---

## 1. Personality

A premium, AI-first career platform — explicitly **NOT a LinkedIn clone**. The feel is closer
to a modern developer-tools SaaS (Linear / Vercel / Raycast lineage) blended with the warmth of
a consumer product. Calm, spacious, confident. Intelligence is signalled through a single
recurring **aurora gradient** (indigo → violet → cyan) used sparingly on AI-touched surfaces:
scores, AI actions, active states, and brand marks.

Tone words: **luminous, precise, generous, trustworthy.**

## 2. Typography

Distinctive pairing using widely-available faces with robust fallbacks (offline-safe):

- **Display / headings:** `"Fraunces", "Georgia", "Times New Roman", serif` — a characterful
  high-contrast serif for hero and section headers. Used at large sizes, tight tracking,
  optical weight 600–800. This is the signature move that separates us from default-Tailwind
  sans-everywhere SaaS.
- **Body / UI:** `"Plus Jakarta Sans", "Segoe UI", system-ui, -apple-system, sans-serif` — a
  clean humanist geometric sans for all UI text, labels, and data.
- **Mono / data accents:** `"JetBrains Mono", "SF Mono", ui-monospace, monospace` — for scores,
  request IDs, API-call labels, and metric chips.

Type scale (1.250 major-third): 12 / 13 / 14 / 16 / 18 / 22 / 28 / 36 / 48 / 60.
Body line-height 1.6; headings 1.1. Numerals use `font-variant-numeric: tabular-nums` for data.

## 3. Color tokens (semantic, theme-driven via CSS variables)

Two themes from one source. Aurora brand ramp is shared.

**Brand / AI accent ramp (shared):**
- `--brand-1` indigo `#5B5BF5`
- `--brand-2` violet `#8B5CF6`
- `--brand-3` cyan  `#22D3EE`
- `--aurora` = `linear-gradient(120deg, #5B5BF5 0%, #8B5CF6 45%, #22D3EE 100%)`

**Light ("Porcelain"):**
- `--bg` `#F7F8FC` (soft off-white, never pure white)
- `--surface` `#FFFFFF`
- `--surface-2` `#F1F2F9`
- `--text` `#15161D` · `--text-muted` `#5A5E72` · `--text-subtle` `#8A8FA3`
- `--border` `#E6E8F2` · `--ring` `#5B5BF5`
- `--accent` `#5B5BF5` · `--accent-weak` `#EEF0FE`

**Dark ("Ink"):**
- `--bg` `#0A0B12` (near-black indigo, never pure black)
- `--surface` `#12131F`
- `--surface-2` `#1A1C2B`
- `--text` `#ECEDF5` · `--text-muted` `#A2A7BE` · `--text-subtle` `#6E7390`
- `--border` `#262A3E` · `--ring` `#8B5CF6`
- `--accent` `#8B5CF6` · `--accent-weak` `#1C1B33`

**Status (both themes, tuned per theme):** success `#16A34A`/`#34D399`,
warning `#D97706`/`#FBBF24`, danger `#DC2626`/`#F87171`, info = brand.

All text/background pairings meet WCAG 2.1 AA (≥4.5:1 body, ≥3:1 large/UI).

## 4. Spacing, radius, shadow

- **Spacing scale (4px base):** 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 56 / 80.
- **Radius:** `--r-sm` 8px · `--r-md` 14px · `--r-lg` 20px · `--r-xl` 28px · `--r-full` 999px.
  Soft, generous rounding everywhere — cards default to `--r-lg`.
- **Shadow (light):** layered, low-spread, tinted with indigo —
  `--shadow-1` `0 1px 2px rgba(18,19,31,.06), 0 1px 3px rgba(18,19,31,.04)`,
  `--shadow-2` `0 8px 24px -8px rgba(35,30,90,.18)`,
  `--shadow-glow` `0 0 0 1px rgba(91,91,245,.25), 0 8px 30px -6px rgba(91,91,245,.35)`.
- **Dark shadows:** rely on borders + faint brand glow rather than drop shadows.

## 5. Spatial language & motion

- Spacious, card-based, max content width ~1180px, centered.
- App shell: persistent left sidebar (desktop) → bottom tab/sheet (mobile), top bar with
  brand mark, theme toggle, account.
- Micro-interactions: 150–220ms ease-out transforms; cards lift 2px on hover; focus rings are
  2px `--ring` offset. Aurora gradient subtly animates only on AI-active elements.
- `prefers-reduced-motion` respected (animations disabled).

## 6. Component inventory (defined in E8-S1 style guide)

Buttons (primary aurora / secondary / ghost / danger), inputs + textarea + select with
floating-style labels, cards, badges/chips (skill, status, score), nav shell, modal/dialog,
toast, skeleton loader, progress ring (profile completion / fit score), citation chip,
empty/error/loading states.

## 7. Accessibility commitments

Semantic landmarks (`header`/`nav`/`main`/`footer`), labelled forms, `aria-live` for async AI
results and toasts, visible focus on every interactive element, keyboard-operable toggles,
contrast-checked tokens, theme persisted to `localStorage` and defaulted from
`prefers-color-scheme`.

## 8. API-call labelling convention

Interactive elements that trigger network calls carry a small mono `data-api` chip, e.g.
`POST /api/v1/auth/register`, `GET /api/v1/jobs/match`, so the generator and evaluator can map
UI → contract directly. All mock data uses **snake_case** field names exactly matching
`data-models.md` / `api-contracts.md`.
