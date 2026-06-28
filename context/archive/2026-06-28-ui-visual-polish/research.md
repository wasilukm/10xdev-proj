---
date: 2026-06-28T22:41:11+02:00
researcher: Mariusz Wasiluk
git_commit: 5497b43897a12e56bbb930baecae61d4db2f6c36
branch: main
repository: 10xdev-proj
topic: "S-07 UI visual polish — current template/static state and the path to a design-token CSS layer"
tags: [research, codebase, ui, css, templates, htmx, design-tokens]
status: complete
last_updated: 2026-06-28
last_updated_by: Mariusz Wasiluk
---

# Research: S-07 UI Visual Polish

**Date**: 2026-06-28T22:41:11+02:00
**Researcher**: Mariusz Wasiluk
**Git Commit**: 5497b43897a12e56bbb930baecae61d4db2f6c36
**Branch**: main
**Repository**: 10xdev-proj

## Research Question

For the `ui-visual-polish` change (roadmap S-07): what is the current state of templates,
static-file wiring, and per-page markup across every user-facing surface, and what is the
concrete path to the committed hand-rolled design-token CSS layer (no framework, no build
step) — including the forward-compat seam for a future timeline view?

## Summary

The app is functionally complete (S-01–S-06 done) but visually **unstyled**: 12 templates
of bare semantic HTML, **no stylesheet linked**, only two orphan class names
(`.warning`, `.badge`) with no CSS backing them, and one stray inline style. State that
should read as colored badges (free/busy, in-progress/upcoming, "definition changed") and
the conflict/next-free messages all render as plain text.

The static pipeline is **ready as-is**: whitenoise `CompressedManifestStaticFilesStorage`,
`STATICFILES_DIRS=[BASE_DIR/"static"]`, `STATIC_ROOT=staticfiles/`. A single stylesheet
dropped into `static/css/` and linked from `base.html` needs no config change and is served
hashed in prod.

The roadmap has already **committed the approach** (no framework, no build step; three
layers: reset → design tokens as CSS custom properties → component classes) and a
**forward-compat contract**: define tokens as custom properties and pick free/busy/owner
colors that read as a filled timeline block, since a future timeline view inherits them.

The single real technical risk is **HTMX**: `_environment_row.html` and
`_reservation_item.html` are swapped in via `hx-swap="outerHTML"`, so styling must live in
the stylesheet keyed off classes placed on the **partials' own root elements**, not in the
base layout — otherwise re-swapped fragments lose their styling.

Two scope forks were resolved with the user during this change: **full light + dark** token
sets (`prefers-color-scheme`), and **desktop-only** (no responsive card fallback; the wide
env-list table gets a horizontal-scroll wrapper). Responsive is a PRD non-goal.

## Detailed Findings

### Base layout & static pipeline

- `templates/base.html` — `<head>` linked only `vendor/htmx.min.js`; no stylesheet, no
  extra-head block. Bare `<nav>` (pipe-delimited links + a logout `<form>` carrying the only
  inline style, `style="display:inline"`), bare `<ul>` messages list, `{% block title %}` +
  `{% block content %}`.
- `envbooker/settings.py:147-159` — `STATIC_URL="static/"`, `STATIC_ROOT=BASE_DIR/"staticfiles"`,
  `STATICFILES_DIRS=[BASE_DIR/"static"]`; whitenoise `CompressedManifestStaticFilesStorage`;
  whitenoise middleware at `settings.py:67`. `static/` held only `vendor/htmx.min.js`.

### Templates inventory (12 files, 3 HTMX partials)

```
templates/
  base.html · home.html
  registration/login.html · registration/signup.html
  catalog/environment_list.html · _environment_results.html · _environment_row.html
          environment_manage.html · environment_form.html · environment_confirm_delete.html
  reservations/my_reservations.html · _reservation_item.html
```
Partials are `_`-prefixed; each has a stable `id` root for HTMX targeting
(`#env-row-{{ env.pk }}`, `#reservation-{{ reservation.pk }}`, `#env-results`). Only
`.warning` (`environment_form.html`) and `.badge` (`_reservation_item.html`) existed, both
unstyled.

### State rendered as plain text (the badge / alert candidates)

- `_environment_row.html:8` — `Busy` (in `<strong>`) vs plain `Free` → free/busy badges.
- `_environment_row.html:41-42` — conflict message + "Next free:" as plain `<p>` → alerts.
- `_reservation_item.html:6` — `In progress` vs `Upcoming` → status badges.
- `_reservation_item.html:8` — `<span class="badge">Definition changed…</span>` → real badge.
- `environment_form.html:9` `.warning` div; `environment_confirm_delete.html:11` blocking
  list → warning callouts.

### Per-surface markup & view mapping

| Surface | Template(s) | View |
|---|---|---|
| Env list + filters | `environment_list.html`, `_environment_results.html`, `_environment_row.html` | `catalog.views.environment_list` (catalog/views.py:28-79) |
| Booking + conflict | booking form inside `_environment_row.html:39-51` | `reservations.views.reservation_create` (reservations/views.py:141-177) |
| My reservations | `my_reservations.html`, `_reservation_item.html` | `reservations.views.my_reservations` (reservations/views.py:181-193) |
| Auth | `registration/login.html` (LoginView + `EmailAuthenticationForm`), `signup.html` (`SignUpView`) | accounts/views.py:12-20 |
| Manage envs | `environment_manage.html` (7-col table) | `catalog.views.environment_manage` (catalog/views.py:83-88) |
| Env create/edit | `environment_form.html` (`EnvironmentForm.as_p`, warn-on-confirm) | catalog/views.py:92-150 |
| Confirm delete | `environment_confirm_delete.html` (blocked + unblocked) | catalog/views.py:154-170 |
| Home | `home.html` (h1 + p) | — |

The env-list results table is **10 columns** (Name, Version, Project, Purpose, Tag, Owner,
Status, Current reservation, Upcoming 24h, Book) — the only surface where table→cards would
be a meaningful responsive decision, and the one tied to the <30s scan criterion. The
manage table is 7 columns (admin-only). All other surfaces are already single-column and
narrow-viewport-safe. Forms render via `{{ form.as_p }}` everywhere (auth, env, booking,
edit-duration), so element-selector styling scoped under a form class covers them without a
widget rewrite.

### HTMX swap behavior (the technical risk)

- Filter: `environment_list.html` form `hx-get` → swaps `#env-results` (`_environment_results.html`).
- Book: `_environment_row.html` form `hx-post reservations:create` → swaps `#env-row-*` (the row).
- Edit/cancel: `_reservation_item.html` forms → swap the row (admin, via `row_env_pk`) or the
  card (`#reservation-*`).
Conclusion: classes must sit on the partial roots and all visual rules in the stylesheet, so
swapped fragments keep styling. (Verified post-implementation: a busy-filter swap preserved
badge font/uppercase and the 4px clay spine.)

## Code References

- `templates/base.html` — global head/nav/messages; the single stylesheet `<link>` injection point.
- `envbooker/settings.py:147-159` — static/whitenoise config (no change needed).
- `templates/catalog/_environment_row.html:1,8,41-49` — row root (status-spine class anchor),
  free/busy text, conflict/next-free, booking form.
- `templates/reservations/_reservation_item.html:1,6,8,11` — card root, status text, badge, conflict.
- `templates/catalog/environment_form.html:9` — `.warning` callout to migrate.

## Architecture Insights

- **Single source of truth ordering:** land reset + tokens before per-page component classes
  so every surface shares one token layer (roadmap S-07 risk note). One stylesheet, no
  per-page CSS files.
- **Token-as-custom-property seam is load-bearing**, not cosmetic: it is simultaneously the
  dark-mode mechanism and the future-timeline inheritance contract. Free/busy must be
  saturated enough to fill a time-block, not only tint a pill.
- **Styling-only blast radius:** the entire change is a CSS file + `class="..."` attributes +
  one `<link>`. No views/forms/services/models/settings/migrations. The Django test suite is
  the guardrail that only presentation changed.

## Historical Context (from prior changes)

- `context/foundation/roadmap.md:162-178` (S-07) — committed approach, rejected alternatives
  (Tailwind = Node build vs uv-only stack; Pico/Water = templated look, no help for
  row/column + badge work), and the timeline-view forward-compat note.
- `context/foundation/prd.md` — Primary success criterion (<30s find-and-reserve;
  legibility-bound), Secondary (24h horizon), NFR (≤200ms interaction ack; latest-two of
  Chrome/Firefox/Safari/Edge), and responsive listed as a **non-goal**.
- Prereqs S-02–S-06 all archived under `context/archive/` (booking, filter, edit-own,
  admin-catalog, admin-override) — the pages S-07 restyles.

## Decisions locked (this change)

- **Theme:** full light + dark via `prefers-color-scheme`.
- **Responsive:** desktop-only; env-list + manage tables stay tables; env-list wrapped in a
  horizontal-scroll container. No card fallback.
- **Aesthetic direction (via `frontend-design`):** "operations console" — monospace carries
  data/labels; the signature is a colored left **status spine** per env row (free=teal,
  busy=clay) that doubles as the future timeline-block color; palette avoids the three
  generic AI defaults (console near-white `#F5F7F9`, ink `#16202A`, indigo `#3B3FBF`,
  free `#0E8C6A`, busy `#B5651D`, danger kept distinct at `#C2362F`).
- **Pixel-regression:** out of scope for this first-ever styling pass (no baseline to
  regress against); a candidate follow-up enabler once the design is stable.

## Related Research

- Plan file (this change, working location): `/home/mariusz/.claude/plans/ui-visual-polish-shiny-lake.md`
  — approved implementation plan derived from this research.

## Process note

This research ran under harness **plan mode**, which blocked writing this `research.md` at
the time, so the findings were first captured in the approved plan file and the change
proceeded into implementation. This artifact back-fills the canonical research record;
`change.md` advanced `new → preparing`. The implementation (CSS + 12 templates) is kept.

## Open Questions

- Whether to add a pixel-regression / visual-baseline enabler as a follow-up once S-07 lands.
- Whether a future timeline-reservations view will use a hand-built CSS-grid or a themed
  calendar lib (out of scope here; the token seam serves either).
