# Filter Env List Implementation Plan

## Overview

Add structured, no-reload filtering to the environment list (dashboard) so a signed-in user can narrow it by **availability (free now / busy now)**, **purpose / use-case tag**, and **project**. Filter state lives in the URL as GET query params (shareable / bookmarkable), and results update via htmx without a full page reload. This is roadmap slice **S-03** and closes the PRD's primary "<30 second find-and-reserve" success criterion (FR-009, US-01) that S-02 deliberately left open.

## Current State Analysis

- The dashboard is a single view, `catalog.views.environment_list` (`catalog/views.py:11-26`): it builds an `Environment` queryset with `select_related("owner")` + a 24h reservation prefetch, then loops to build one row-context dict per env and renders `catalog/environment_list.html`.
- Row-building and the prefetch live in `catalog/services.py` (`build_row_context`, `prefetch_reservations_for_list`). `build_row_context` computes `is_busy` in Python as "a reservation has `during.lower <= now < during.upper`".
- `Environment` (`catalog/models.py:5-21`) has `name`, `version`, `purpose` (indexed), `project` (indexed), `use_case_tag` (indexed), `owner`. Project / purpose / use_case_tag are plain indexed `CharField`s — direct DB filters.
- "Free now / busy now" is **not** a column; it is the existence of a `Reservation` whose `during` contains `now`. `Reservation.during` is a `DateTimeRangeField` (`reservations/models.py:19`), so `reservations__during__contains=now` (or an `Exists` subquery) expresses it at the DB level, consistent with the Python `is_busy` already shown per row.
- htmx is already loaded globally (`templates/base.html:7`) and the booking flow already uses `hx-post` → row `outerHTML` swap (`templates/catalog/_environment_row.html:29-31`). Filtering reuses this pattern with `hx-get`.
- The list template currently has no swappable wrapper; the `<table>` is inline in `environment_list.html`, and the empty state is a single `No environments found.` message that does not distinguish "no envs exist" from "no matches".

## Desired End State

The dashboard shows a filter form above the env table with three controls: an **availability** select (Any / Free now / Busy now), a **project** select, and a **purpose / use-case tag** select — the project and tag selects are populated from the distinct values currently in the catalog. Choosing any value issues an `hx-get` that swaps just the results region and pushes the filter state into the URL (e.g. `/?availability=free&project=billing`). Loading that URL directly reproduces the same filtered list. A **Clear filters** link resets to `/`. When filters match nothing, the results region shows "No environments match these filters." (distinct from the empty-catalog message). Combining filters narrows with AND semantics.

Verify by: applying each filter and combinations, confirming the table updates without a full reload, confirming the URL reflects the filters and is reproducible on refresh, and confirming the clear link and no-match message behave correctly.

### Key Discoveries:

- htmx `hx-get` + `hx-push-url="true"` gives shareable URL state with no JS; the bundled htmx supports it (`templates/base.html:7`, `static/vendor/htmx.min.js`).
- `Reservation.during` is a `DateTimeRangeField`, so `during__contains=now` filters "covers this instant" — matching the existing `is_busy` definition in `build_row_context` (`catalog/services.py:30-33`). Availability filtering must use the same `now` the row build uses, so pass a single `now` through.
- The booking row partial expects a `booking_form` per row (`catalog/views.py:23`); the results partial must keep emitting rows the same way so the existing booking flow and its row-swap target (`#env-row-{{ env.pk }}`) keep working.

## What We're NOT Doing

- No filtering by owner or version (FR-009 names only availability, purpose/use-case, project). Deferred.
- No free-text / name search box (PRD explicitly kept filtering structured, not free-text — FR-009 note).
- No saved filters, no per-user default filters, no multi-select within one attribute (each select is single-value).
- No data-model changes, no migrations, no new dependencies.
- No change to the booking flow, reservation overlap logic, or the 24h upcoming column.
- No pagination (out of scope for this slice; catalog is small).

## Implementation Approach

Two phases. Phase 1 puts the filtering logic in `catalog/services.py` and threads it through the view: parse the three GET params, narrow the `Environment` queryset (availability via `during__contains=now`, project/tag via exact match), and expose the distinct dropdown values. Phase 2 extracts the results region into a partial that htmx can swap, adds the filter form (dropdowns from distinct values), wires `hx-get` with `hx-push-url`, and adds the clear link + no-match state. Tests accompany each phase.

The view stays a single GET endpoint at `name="home"`. A normal request renders the full page; an htmx request (detected via the `HX-Request` header) renders only the results partial. Both paths run identical filtering, so the URL and the htmx swap always agree.

## Critical Implementation Details

- **Single `now` per request.** Availability filtering and `build_row_context` must use the *same* `now` value, or an env could be filtered as "busy" but render as "free" (or vice versa) within one request. Compute `now = timezone.now()` once in the view and pass it into both the filter helper and `build_row_context` (the latter already accepts `now`).
- **Unknown/blank filter values are "no filter".** A missing param, an empty string, or a value not in the allowed set (for availability) must mean "don't constrain on this attribute" — never an error and never a forced empty result. Project/tag values that don't match any env legitimately yield zero rows (the no-match state), which is correct.

## Phase 1: Filtering logic (service + view)

### Overview

Add filter parsing and queryset narrowing in the service layer and wire it into `environment_list`, plus expose the distinct values used to populate the dropdowns. No template changes yet; correctness is proven by unit tests against the view's resulting `rows` and context.

### Changes Required:

#### 1. Filtering + distinct-values helpers

**File**: `catalog/services.py`

**Intent**: Add a helper that applies the three filters to an `Environment` queryset, and a helper that returns the distinct project and use_case_tag values for the dropdowns. Keep availability consistent with the existing `is_busy` definition by filtering on a reservation whose range contains `now`.

**Contract**:
- `filter_environments(queryset, *, availability=None, project=None, use_case_tag=None, now)` → filtered queryset. `availability` is one of `"free"`, `"busy"`, or falsy (no constraint). `project` / `use_case_tag` apply exact-match only when truthy. AND semantics across the three. Availability uses an `Exists` subquery on `Reservation.objects.filter(environment=OuterRef("pk"), during__contains=now)` — `busy` keeps rows where it exists, `free` keeps rows where it does not. (Snippet justified: the `Exists`/`OuterRef` + `during__contains` form is the non-obvious core of the change.)

```python
from django.db.models import Exists, OuterRef

def filter_environments(queryset, *, availability=None, project=None, use_case_tag=None, now):
    if project:
        queryset = queryset.filter(project=project)
    if use_case_tag:
        queryset = queryset.filter(use_case_tag=use_case_tag)
    if availability in ("free", "busy"):
        busy = Reservation.objects.filter(environment=OuterRef("pk"), during__contains=now)
        queryset = queryset.annotate(_busy=Exists(busy))
        queryset = queryset.filter(_busy=(availability == "busy"))
    return queryset
```

- `filter_options()` → dict like `{"projects": [...distinct sorted...], "use_case_tags": [...distinct sorted...]}`, each from `Environment.objects.values_list(field, flat=True).distinct().order_by(field)`.

#### 2. Parse params and apply filters in the view

**File**: `catalog/views.py`

**Intent**: Read the three GET params, compute one `now`, narrow the queryset via `filter_environments`, pass the active filter values and `filter_options()` into the template context so the form can render current selections. (Template branching for htmx vs full page lands in Phase 2; Phase 1 keeps rendering the existing template so the suite stays green.)

**Contract**: View reads `request.GET.get("availability")`, `request.GET.get("project")`, `request.GET.get("use_case_tag")`. `now = timezone.now()` computed once, passed to both `filter_environments(...)` and each `build_row_context(env, now=now)`. Context gains `filters` (the three active values) and `options` (from `filter_options()`) alongside `rows`. The prefetch + `select_related("owner")` + `order_by("name")` chain is preserved; `filter_environments` is applied to that queryset.

### Success Criteria:

#### Automated Verification:

- Test suite passes: `uv run python manage.py test catalog`
- New unit tests cover: filter by project, filter by use_case_tag, availability=free, availability=busy, AND-combination of two filters, blank/unknown param = no constraint, and `filter_options()` returns distinct sorted values.

#### Manual Verification:

- Hitting `/?availability=free`, `/?project=<x>`, `/?use_case_tag=<x>`, and combinations returns the expected subset (verified via runserver before the UI exists, using the URL directly).
- No regression: unfiltered `/` still lists all envs with correct Busy/Free badges.

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Filter UI (htmx partial)

### Overview

Surface the filters in the template: extract the results region into a swappable partial, add the filter form with dropdowns populated from `options`, wire `hx-get` with URL push, and add the Clear-filters link plus a distinct no-match empty state. Make the view render only the partial for htmx requests so the swap and the URL stay in sync.

### Changes Required:

#### 1. Results partial

**File**: `templates/catalog/_environment_results.html` (new)

**Intent**: Hold the `<table>` (or the no-match / empty message) currently inline in `environment_list.html`, wrapped in a single element htmx can target and swap. Keep emitting rows via the existing `_environment_row.html` include so the booking flow is untouched.

**Contract**: A wrapper element with a stable id (e.g. `id="env-results"`). Three render states: rows present → table as today; filters active but zero rows → "No environments match these filters."; no envs at all → existing "No environments found." Distinguish "filters active" using the `filters` context (any truthy value).

#### 2. Filter form + page shell

**File**: `templates/catalog/environment_list.html`

**Intent**: Add the filter form above the results and include the new partial. The form GETs to the dashboard, targets the results wrapper, and pushes filter state to the URL. Selects show the current selection from `filters` and options from `options`. Add a Clear-filters link to the bare dashboard URL.

**Contract**: A `<form>` with `hx-get="{% url 'home' %}"`, `hx-target="#env-results"`, `hx-swap="outerHTML"`, `hx-push-url="true"`. Controls: `availability` select (Any / Free now / Busy now), `project` select (blank "Any" + `options.projects`), `use_case_tag` select (blank "Any" + `options.use_case_tags`); each marks the value from `filters` as selected. A "Clear filters" `<a href="{% url 'home' %}">`. The page body includes `_environment_results.html`. (`method="get"` on the form as a no-JS fallback so the form still works if htmx is absent.)

#### 3. Render partial for htmx requests

**File**: `catalog/views.py`

**Intent**: When the request is an htmx request, render only the results partial so the swap target matches; otherwise render the full page. Same filtering either way.

**Contract**: Branch on `request.headers.get("HX-Request")`. htmx → render `catalog/_environment_results.html` with `rows` + `filters`; non-htmx → render `catalog/environment_list.html` with `rows` + `filters` + `options`. No change to filtering or `now` handling.

### Success Criteria:

#### Automated Verification:

- Test suite passes: `uv run python manage.py test catalog`
- New tests cover: full-page GET renders the filter form with options; an `HX-Request` GET returns only the results partial (no `<html>`/nav chrome); a filtered htmx GET returns the narrowed rows; zero-match filtered request renders the "No environments match" message; an unfiltered request with envs still renders the table.

#### Manual Verification:

- Selecting a filter updates the table without a full page reload (network shows a partial swap, no flash).
- The URL reflects the active filters and reloading that URL reproduces the filtered list.
- "Clear filters" returns to the full list and resets the URL to `/`.
- Booking an env from a filtered list still works (row swap via the existing `hx-post` is unaffected).
- Browser back/forward moves between filter states correctly.

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation. This phase closes the change.

---

## Testing Strategy

### Unit Tests:

- `filter_environments`: each filter in isolation (project, use_case_tag, availability=free, availability=busy), AND-combination, and blank/unknown values = no constraint. Availability tests create reservations whose `during` contains / does not contain the test `now` (reuse the `make_dt` / `make_range` helpers in `catalog/tests.py`).
- `filter_options`: returns distinct, sorted project and use_case_tag values across several envs.

### Integration Tests:

- View-level (Django test client) for both phases' criteria: full-page vs `HX-Request` rendering, filtered results, and the no-match state. Use a logged-in client (the view is `@login_required`).

### Manual Testing Steps:

1. Seed a few envs across ≥2 projects and ≥2 tags, with one env holding a reservation covering "now".
2. Filter by availability=Free now → busy env disappears; =Busy now → only it remains.
3. Filter by a project, then add a tag → AND narrowing; confirm URL shows both params.
4. Copy the filtered URL into a fresh tab → same filtered list renders.
5. Click Clear filters → full list, URL back to `/`.
6. Filter to an empty result → "No environments match these filters."
7. Book an env while filtered → row updates in place.

## Performance Considerations

Catalog is small; filters hit indexed columns (`project`, `use_case_tag` are `db_index=True`) and the availability `Exists` subquery uses the reservation FK. `filter_options()` runs two cheap `DISTINCT` queries per full-page render (not on htmx swaps if options aren't re-sent). No pagination needed at this scale.

## Migration Notes

None — no model or schema changes.

## References

- Roadmap slice: `context/foundation/roadmap.md` S-03 (`filter-env-list`), lines ~107-118
- PRD: FR-009, US-01, Success Criteria §Primary (`context/foundation/prd.md`)
- Existing htmx swap pattern: `templates/catalog/_environment_row.html:29-31`
- Existing row/availability logic: `catalog/services.py:8-40`, `catalog/views.py:11-26`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Filtering logic (service + view)

#### Automated

- [ ] 1.1 Test suite passes: `uv run python manage.py test catalog`
- [ ] 1.2 Unit tests cover project / use_case_tag / availability=free / availability=busy / AND-combination / blank-unknown=no-constraint / `filter_options()` distinct-sorted

#### Manual

- [ ] 1.3 URL-param filtering returns expected subsets via runserver
- [ ] 1.4 No regression: unfiltered `/` lists all envs with correct Busy/Free badges

### Phase 2: Filter UI (htmx partial)

#### Automated

- [ ] 2.1 Test suite passes: `uv run python manage.py test catalog`
- [ ] 2.2 Tests cover full-page form render, `HX-Request` partial-only render, filtered htmx results, zero-match message, unfiltered table render

#### Manual

- [ ] 2.3 Selecting a filter updates the table without full page reload
- [ ] 2.4 URL reflects active filters and reloads reproduce the filtered list
- [ ] 2.5 Clear filters resets list and URL to `/`
- [ ] 2.6 Booking from a filtered list still works (row swap unaffected)
- [ ] 2.7 Browser back/forward moves between filter states correctly
