# Filter Env List — Plan Brief

> Full plan: `context/changes/filter-env-list/plan.md`

## What & Why

Add structured, no-reload filtering to the env-list dashboard so a signed-in user can narrow it by **availability (free now / busy now)**, **purpose / use-case tag**, and **project**. This is roadmap slice S-03 (FR-009, US-01) and closes the PRD's primary "<30 second find-and-reserve" success criterion that S-02 deliberately left open — filtering is what turns "find an available env that fits this purpose" into a self-serve action a new joiner completes in seconds.

## Starting Point

The dashboard (`catalog.views.environment_list`) lists every `Environment` with a 24h reservation prefetch and a Busy/Free badge per row. htmx is already loaded and the booking flow already does `hx-post` → row swap. There is no filtering today, and the table is inline in the template with a single ambiguous empty state.

## Desired End State

A filter form sits above the table with three dropdowns (availability, project, purpose/use-case tag). Project/tag options come from the catalog's distinct values. Choosing any value issues an `hx-get` that swaps just the results region and pushes the filters into the URL (e.g. `/?availability=free&project=billing`) — so a filtered list is shareable and survives refresh. A "Clear filters" link resets to `/`, and a distinct "No environments match these filters." message appears when nothing matches.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Filter state location | URL GET query params (htmx push-url) | Shareable/bookmarkable pre-filtered links serve the new-joiner onboarding goal; resolves the roadmap's open unknown | Plan |
| Filter control style | Dropdowns from distinct DB values | Structured, typo-free, discoverable — matches the PRD's "kept structured, not free-text" resolution on FR-009 | Plan |
| "Free/busy now" meaning | At this instant (`during__contains=now`) | Matches the existing per-row Busy/Free badge for one consistent mental model | Plan |
| Filterable attributes | Exactly FR-009's three | Keeps the slice plannable in one pass and avoids scope creep (no owner/version/name search) | Plan |
| Clear / empty UX | Clear-filters link + distinct no-match message | Distinguishes "no matches" from "empty catalog" and gives an easy reset | Plan |

## Scope

**In scope:** availability + project + purpose/use-case-tag filters; htmx partial swap; URL-param state; clear link; no-match state; unit + view tests.

**Out of scope:** owner/version filters, free-text/name search, saved filters, multi-select, pagination, any data-model change.

## Architecture / Approach

One GET endpoint (`name="home"`). The view computes a single `now`, narrows the `Environment` queryset via a new `filter_environments` service helper (project/tag = exact match on indexed columns; availability = `Exists` subquery on a `Reservation` whose `during` contains `now`), and renders the full page normally — but renders only a results partial when the request carries the `HX-Request` header. The same filtering runs on both paths, so the swapped DOM and the URL always agree.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Filtering logic (service + view) | `filter_environments` + `filter_options`, view wires params + single `now`; unit tests | Availability filter must use the same `now` as row-build or badge/filter disagree |
| 2. Filter UI (htmx partial) | Results partial, filter form, `hx-get` + push-url, clear link + no-match state; view tests | htmx partial vs full-page branch must keep booking row-swap working |

**Prerequisites:** S-02 (browse-and-reserve) — done.
**Estimated effort:** ~1 session across 2 phases.

## Open Risks & Assumptions

- Assumes the bundled htmx supports `hx-push-url` (standard in current htmx; verified present locally).
- Availability filtering depends on `DateTimeRangeField` `__contains` matching the `[)` row-build semantics — confirmed equivalent.
- Catalog is small, so distinct-value dropdowns and the `Exists` subquery need no pagination/caching.

## Success Criteria (Summary)

- A user can filter by availability, project, and tag (and combine them) and the list updates without a full page reload.
- The filtered state is in the URL and reproduces on refresh / when shared.
- Clear filters and the no-match message behave correctly, and booking from a filtered list still works.
