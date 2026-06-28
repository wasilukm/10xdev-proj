# UI Visual Polish (S-07) — Plan Brief

> Full plan: `context/changes/ui-visual-polish/plan.md`
> Research: `context/changes/ui-visual-polish/research.md`

## What & Why

Restyle every EnvBooker page from raw Django output into an intentionally designed
"operations console" — a coherent palette, legible tables, colored free/busy state badges,
and consistent forms/buttons. Legibility is load-bearing: the PRD's primary success criterion
is a <30-second scan-and-reserve, which bare unstyled HTML undermines. Styling only — no new
capability, no behavior change.

## Starting Point

The app is functionally complete (S-01–S-06 done) but visually unstyled: 12 templates of bare
semantic HTML, no stylesheet linked, two orphan class names with no CSS, state shown as plain
text. The static pipeline (whitenoise, manifest storage) was already correct and needed no
change.

## Desired End State

One hand-rolled stylesheet (`static/css/app.css`) gives every surface — env list, booking,
my-reservations, auth, and admin — a shared design language in both light and dark themes.
Free/busy read as colored badges plus a left **status spine** down each env row, so the whole
pool's availability is scannable at a glance. CSS custom-property tokens leave a clean seam for
a future timeline view.

## Key Decisions Made

| Decision            | Choice                                          | Why (1 sentence)                                                        | Source   |
| ------------------- | ----------------------------------------------- | ---------------------------------------------------------------------- | -------- |
| Styling tech        | Hand-rolled CSS, no framework/build step        | Keeps the deliberately uv-only, build-free stack; whitenoise serves it | Research |
| Token architecture  | CSS custom properties (3 layers)                | Single source of truth + the seam dark mode and a timeline both inherit| Research |
| Theme               | Full light + dark (`prefers-color-scheme`)      | User asked for both, not just a seam                                    | Plan     |
| Responsive          | Desktop-only; wide tables get scroll wrapper    | PRD lists responsive as a non-goal                                     | Plan     |
| Aesthetic direction | "Operations console": mono data + status spine  | Subject-grounded, avoids the three generic AI defaults (`frontend-design`)| Plan  |
| Pixel-regression    | Out of scope (no baseline yet)                  | First-ever styling pass has nothing to diff; revisit as a follow-up    | Plan     |

## Scope

**In scope:** one stylesheet + `class` attributes on 12 templates + one `<link>` in base; light
+ dark themes; free/busy badges, owner cues, status spine, alerts, styled forms/buttons.

**Out of scope:** CSS framework / build step; responsive card layouts; markup restructure;
any view/form/model/settings/migration change; the timeline view; pixel-regression tooling.

## Architecture / Approach

Three layers in `static/css/app.css`: (1) reset, (2) design tokens as `:root` CSS custom
properties (dark overrides only the `--color-*` set), (3) component classes. All visual rules
key off classes placed on the HTMX partial roots (`env-row`, `reservation-card`, `#env-results`)
so `hx-swap="outerHTML"` fragments keep their styling. Forms styled via element selectors
scoped under `.form`, so Django's `form.as_p` needs no widget rewrite.

## Phases at a Glance

| Phase                          | What it delivers                                  | Key risk                                   |
| ------------------------------ | ------------------------------------------------- | ------------------------------------------ |
| 1. Stylesheet foundation       | `app.css` (reset+tokens+components) wired in base | Token seam must be right for dark/timeline |
| 2. Component classes applied   | All 12 templates restyled, no markup restructure  | HTMX swaps stripping styling (mitigated)   |
| 3. Verification & visual review| Tests green + structural checks + visual sign-off | Visual/dark-mode judgment still pending    |

**Prerequisites:** S-02–S-06 done (all archived). **Estimated effort:** delivered in one
session; remaining work is the user's manual visual review.

## Open Risks & Assumptions

- Pixel-level visual quality and dark mode are **verified structurally but not visually** in
  this session (the MCP browser couldn't surface screenshots) — they await the user's eyeball.
- This plan is retrospective: the code already landed, so Progress reflects what's verified vs.
  what's pending review rather than work-to-start.

## Success Criteria (Summary)

- Every page reads as a designed product; free/busy distinguishable at a glance via badge + spine.
- 132-test suite stays green — proof only presentation changed.
- Both light and dark themes legible, free/busy distinct in each.
