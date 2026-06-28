# UI Visual Polish (S-07) Implementation Plan

> Retrospective plan: the implementation landed during the 2026-06-28 session. Automated
> verification passed; manual visual review is the only open item.

## Overview

A styling-only pass (roadmap S-07) that turns EnvBooker's bare Django output into an
intentionally designed "operations console": one hand-rolled stylesheet — reset → CSS
custom-property design tokens → component classes — served by the existing whitenoise
pipeline. No framework, no build step, no behavior change. The goal is legibility that serves
the PRD's <30-second scan-and-reserve criterion, plus a token seam a future timeline view
inherits.

## Current State Analysis

Before this change (per `research.md`): 12 templates of bare semantic HTML; **no stylesheet
linked**; only two orphan class names (`.warning`, `.badge`) with no CSS; one stray inline
style. Free/busy, in-progress/upcoming, "definition changed", and conflict/next-free messages
all rendered as plain text. Static pipeline was already correct (whitenoise
`CompressedManifestStaticFilesStorage`, `STATICFILES_DIRS=[BASE_DIR/"static"]`).

The one real technical risk is HTMX: `_environment_row.html` and `_reservation_item.html` are
swapped via `hx-swap="outerHTML"`, so styling must key off classes on the **partial roots**,
not the base layout, or swapped fragments lose their look.

## Desired End State

Every page reads as a designed product: coherent palette, legible table row/column structure
with hover states, colored free/busy **state badges**, owner cues, consistent type/spacing,
and styled forms/buttons across booking, my-reservations, auth, and admin surfaces — in both
light and dark themes. Verify: `manage.py test` green (only-presentation guardrail);
`collectstatic` resolves the hashed stylesheet; computed styles confirm tokens apply; an HTMX
swap preserves badge + status-spine styling.

### Key Discoveries

- `templates/base.html` — single stylesheet `<link>` injection point; nav/messages/content skeleton.
- `envbooker/settings.py:147-159` — static/whitenoise config needs no change.
- `_environment_row.html:1` — `<tr>` root is the anchor for the per-row status-spine class.
- `_reservation_item.html:1` — card root; partial reused both standalone and inside admin cells.
- HTMX swap targets: `#env-results`, `#env-row-*`, `#reservation-*` — classes must live on these roots.

## What We're NOT Doing

- No CSS framework, no Node/build step, no per-page CSS files (single stylesheet only).
- No responsive/mobile card layouts (PRD non-goal) — desktop styling pass; wide tables get a
  horizontal-scroll wrapper.
- No markup restructure beyond adding `class` attributes; no view/form/widget/model/settings/
  migration changes.
- No timeline/calendar view (future slice) — only its token seam is built.
- No pixel-regression baseline tooling — candidate follow-up enabler once the design is stable.

## Implementation Approach

Three layers in one file (`static/css/app.css`), then apply the class vocabulary across all
templates. Aesthetic direction ("operations console") came from the `frontend-design` skill:
monospace carries data/labels (versions, times, table headers, badges); the **signature** is a
colored left **status spine** per env row (free=teal, busy=clay) that makes the pool's
free/busy pattern scannable at a glance and is the exact color a future timeline block fills
with. Palette deliberately avoids the three generic AI defaults: console near-white
`#F5F7F9`, ink `#16202A`, indigo accent `#3B3FBF`, free `#0E8C6A`, busy `#B5651D`, danger kept
distinct at `#C2362F`. Tokens are CSS custom properties; the dark theme overrides the
`--color-*` tokens (and the `--shadow-*` tokens, which read differently on a dark canvas)
under `prefers-color-scheme: dark`.

## Critical Implementation Details

- **HTMX-swap styling**: all visual rules live in the stylesheet keyed to classes on the
  partial root elements (`<tr class="env-row env-row--free|busy">`, `<div class="reservation-card">`).
  This is why a re-swapped fragment keeps its styling — verified post-build.
- **`form.as_p` styling**: Django renders each field in a `<p>`; styling element selectors
  scoped under `.form` covers auth/env/booking/edit forms with no widget rewrite.
- **Shared partial in two contexts**: `_reservation_item.html` renders both on my-reservations
  (standalone card) and inside admin env-row cells; `.reservation-card` is acceptable in both.

## Phase 1: Stylesheet foundation (reset + tokens + wiring)

### Overview
Create the design system file and wire it globally.

### Changes Required

#### 1. Design system stylesheet
**File**: `static/css/app.css`
**Intent**: The whole system — modern reset, the design-token layer (semantic CSS custom
properties for color incl. free/busy/owner + spacing/type/radii scales, with a dark override
block), and component classes (nav, tables, badges, forms, buttons, alerts, filter bar,
reservation/auth cards, the env-row status spine).
**Contract**: `:root` token names are the stable contract a future timeline view inherits
(`--color-free`, `--color-busy`, `--color-owner-accent`, spacing/type scales). Dark theme
overrides `--color-*` (and `--shadow-*`) under `@media (prefers-color-scheme: dark)`.

#### 2. Base layout wiring
**File**: `templates/base.html`
**Intent**: Link the stylesheet, add a `viewport` meta and an `extra_head` block, and restyle
nav/messages/content with classes; remove the stray inline logout-form style.
**Contract**: `<link rel="stylesheet" href="{% static 'css/app.css' %}">`; `.site-nav`,
`.site-main`, `.messages` wrappers.

### Success Criteria
#### Automated Verification
- Stylesheet served 200 with non-zero size; referenced in rendered HTML.
- `collectstatic --noinput` succeeds and post-processes `app.css` into the manifest.
#### Manual Verification
- Nav renders as a console header bar; content sits in a centered column.

---

## Phase 2: Component classes applied across all surfaces

### Overview
Apply the class vocabulary (no markup restructure) to the remaining 9 content templates.

### Changes Required

#### 1. Env list, results, row (incl. booking + conflict)
**Files**: `templates/catalog/environment_list.html`, `_environment_results.html`, `_environment_row.html`
**Intent**: `.filters` bar; `.table-scroll > .data-table`; free/busy as `.badge--free|--busy`;
the `env-row env-row--free|busy` status-spine class on the `<tr>` root; owner cue; mono version
cell; conflict/next-free as `.alert--conflict|--info`; booking `.form--inline` + `.btn--primary`.
**Contract**: classes on `#env-row-{{ env.pk }}` and `#env-results` roots survive `hx-swap`.

#### 2. My reservations + reservation item
**Files**: `templates/reservations/my_reservations.html`, `_reservation_item.html`
**Intent**: `.reservation-card` (+`--active`) on the `#reservation-*` root; status as
`.badge--active|--upcoming`; "definition changed" as `.badge--changed`; conflict `.alert--conflict`;
edit/cancel as `.btn`/`.btn--danger`.

#### 3. Auth, admin manage/form/confirm-delete, home
**Files**: `templates/registration/{login,signup}.html`, `templates/catalog/{environment_manage,environment_form,environment_confirm_delete}.html`, `templates/home.html`
**Intent**: `.auth-card .form`; `.data-table` + action `.btn`s on manage; `.alert--warn`
(migrated from `.warning`) on edit/delete callouts; primary/danger buttons; `.form-actions`.

### Success Criteria
#### Automated Verification
- Accessibility snapshot shows free/busy/active/upcoming/changed as discrete badge elements; tables well-formed.
- Computed styles confirm: free badge teal `#0e8c6a`/bg `#dcf3ea`, busy clay `#b5651d`/bg `#fbebd8`, status spine 4px (teal vs clay), primary button indigo `#3b3fbf`, headers monospace+uppercase.
- HTMX busy-filter swap: swapped-in badge keeps monospace+uppercase and the 4px clay spine.
#### Manual Verification
- Free vs busy rows are distinguishable at a glance; the status spine reads down the table's left edge.
- Forms/buttons/alerts look consistent across booking, my-reservations, auth, and admin.

---

## Phase 3: Verification & visual review

### Overview
Prove only-presentation changed and review the design across states and themes.

### Success Criteria
#### Automated Verification
- `manage.py test` stays green (132 tests) — the guardrail that no logic changed.
- `mypy`/`ruff` per standard gates (CSS/templates outside their scope).
#### Manual Verification
- Walk every conditional state: free-vs-busy rows, forced overlap (conflict alert), env edit
  with active reservations (warning callout), blocked delete, "definition changed" badge.
- Toggle `prefers-color-scheme` light/dark on a couple of pages; free/busy stay distinct and
  AA-legible on their `-bg` pairs.
- Spot-check latest Chrome + Firefox (PRD 4-browser commitment).

---

## Testing Strategy

- **Unit/regression**: full Django suite as the only-presentation guardrail (no new tests; CSS
  isn't unit-tested).
- **Structural**: a11y snapshot + computed-style assertions via Playwright MCP.
- **Manual**: state matrix + dark mode + cross-browser, driven from the running dev server.

## Performance Considerations

One small static stylesheet (~17 KB), compressed + hashed by whitenoise; no JS added, no extra
requests beyond the single CSS file. Honors NFR ≤200ms interaction ack (no blocking work);
`prefers-reduced-motion` disables the few transitions.

## Migration Notes

None — no data or schema changes. `collectstatic` picks up the new file on deploy (Railway
start command already runs it).

## References

- Research: `context/changes/ui-visual-polish/research.md`
- Roadmap: `context/foundation/roadmap.md:162-178` (S-07 committed approach + timeline seam)
- PRD success criteria / NFR: `context/foundation/prd.md`
- Stylesheet: `static/css/app.css`; base wiring: `templates/base.html`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Implemented in the 2026-06-28 session (pre-commit;
> sha to append on landing). Manual items await the user's visual review.

### Phase 1: Stylesheet foundation
#### Automated
- [x] 1.1 Stylesheet served 200 and referenced in HTML — 74ae95c
- [x] 1.2 collectstatic post-processes app.css into the manifest — 74ae95c
#### Manual
- [x] 1.3 Nav renders as console header bar; centered content column — 74ae95c

### Phase 2: Component classes applied across all surfaces
#### Automated
- [x] 2.1 Badges render as discrete elements; tables well-formed (a11y snapshot) — 74ae95c
- [x] 2.2 Computed styles match token values (badges, spine, button, headers) — 74ae95c
- [x] 2.3 HTMX swap preserves badge + status-spine styling — 74ae95c
#### Manual
- [x] 2.4 Free/busy rows distinguishable at a glance; status spine scannable — 74ae95c, b166d76
- [x] 2.5 Forms/buttons/alerts consistent across all surfaces — 74ae95c, d607838

### Phase 3: Verification & visual review
#### Automated
- [x] 3.1 Full Django suite green (132 tests) — 74ae95c
- [x] 3.2 mypy + ruff gates clean — 74ae95c
#### Manual
- [x] 3.3 State matrix walked (conflict, warning, blocked delete, changed badge) — 74ae95c
- [x] 3.4 Dark mode legible; free/busy distinct in both themes — 74ae95c, d607838
- [x] 3.5 Chrome + Firefox spot-check — 74ae95c

## Addendum (2026-06-28) — user-requested deviations

Two changes landed during manual review that diverge from the plan body above;
both were user-requested and are also recorded in `change.md`. Noted here so the
plan matches the shipped reality:

- **Dark-mode toggle (supersedes "no JS added", Performance Considerations).** Plan
  committed dark via `prefers-color-scheme` only. Added a nav `◐ Theme` toggle: a
  small vanilla-JS snippet (no build step) that sets `data-theme` on `<html>` and
  persists to `localStorage`, plus a no-FOUC head script; a manual choice overrides
  the OS default. `base.html:8-18,52-70`. Still no framework/build step.
- **Env-list table slimmed (supersedes "no markup restructure beyond classes").**
  Dropped the Version and Owner columns (neither is a filter axis) and moved Status
  beside Name to cut horizontal scroll. Env owner still shows in the admin Manage
  table; Duration pinned to 5.5rem. `b166d76`.
