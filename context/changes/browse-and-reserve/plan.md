# Browse & Reserve (S-02) Implementation Plan

## Overview

EnvBooker's north-star slice (roadmap **S-02**, `context/foundation/roadmap.md:92`). A signed-in user
opens the env list, sees every env's current free/reserved state plus the owners and time windows of
current + upcoming reservations, picks a free env, enters a time window, and confirms. The reservation
appears immediately **without a manual page reload**. Overlapping windows are rejected with a message
naming the conflicting reservation's owner + window and suggesting the next free window.

This is the **validation milestone**: if it lands and the no-overlap guarantee holds end-to-end under
realistic concurrent use, the core product hypothesis is proven.

PRD refs: FR-008, FR-010, FR-011, FR-015, US-01.

## Current State Analysis

- `catalog.Environment` (`catalog/models.py:5`) and `reservations.Reservation` (`reservations/models.py:8`)
  exist (F-01 done). `Reservation.during` is a `DateTimeRangeField` (tstzrange) guarded by a Postgres GiST
  `ExclusionConstraint` (`reservation_no_overlap`) — the race-safe source of truth — plus a bounded
  `CheckConstraint` (`reservation_during_bounded`).
- `catalog/views.py` and `reservations/views.py` are empty stubs; neither app has a `urls.py`.
- `envbooker/urls.py:25` routes `/` to a `login_required` placeholder `TemplateView` (`home.html`).
- Templates are minimal hand-rolled HTML. `base.html:20` already renders `{% for message in messages %}`;
  owner display idiom is `user.get_full_name|default:user.email` (`base.html:10`). **No JS / HTMX / CSS
  framework today.**
- `settings.py`: `USE_TZ=True`, `TIME_ZONE="UTC"`, `LOGIN_REDIRECT_URL="home"`, whitenoise
  `CompressedManifestStaticFilesStorage`, `STATIC_ROOT=staticfiles/`. No `STATICFILES_DIRS` yet.
- Established patterns: Django generic CBVs + Django forms (`accounts/views.py`, `accounts/forms.py`).
- Prerequisites F-01 + S-01 are both `done` (roadmap "Done" section).

## Desired End State

`/` is the env-list dashboard. Each env row shows its descriptive attributes, a free/busy-now badge, the
current reservation (if any), and upcoming reservations within the next 24h — each with owner identity and
localized time window. A booking form per row lets the user pick a start + duration (incl. "until next
reservation", capped at 4h) and confirm; the row updates live via HTMX with no full page reload. Overlap
attempts are rejected inline with a message naming the conflict and suggesting the next free window. The
no-overlap guarantee is enforced at the DB layer (the exclusion constraint is correct by construction) and
verified by tests covering constraint-violation handling — a deliberately overlapping save is caught and
surfaced inline, not 500'd.

### Key Discoveries
- DB exclusion constraint already exists (`reservations/models.py:24`) — app code must treat it as the
  authority, not re-implement the guarantee.
- Half-open ranges `[start, end)`: adjacency (`end == next.start`) is NOT an overlap — enables a clean
  "until next reservation" fill.
- `base.html` already wires the messages framework and the owner-display idiom to reuse.

## What We're NOT Doing

- Filtering the env list (S-03) — separate slice; closes the <30s criterion later.
- Editing / cancelling own reservations (S-04).
- Admin override of any reservation (S-06) and admin catalog UI (S-05).
- Per-user timezones, notifications, analytics (PRD Non-Goals).

## Implementation Approach

Server-rendered Django (CBVs + forms + templates) augmented with **HTMX** for partial updates — one
vendored `<script>`, no build step, consistent with the whitenoise static setup. The env row is an
includable partial that doubles as the HTMX swap target, so both successful booking and overlap rejection
re-render the same fragment. Gap-finding logic lives in one `reservations/services.py` module, reused by
both the "until next reservation" duration and the rejection's next-free-window suggestion.

## Critical Implementation Details

- **Race-safe create**: the exclusion constraint raises `IntegrityError` on overlap. Wrap the save in
  `transaction.atomic()` and catch `IntegrityError`; on catch, re-query the conflicting reservation to
  build the message. The DB constraint — not a pre-check — is the guarantee; a pre-check query exists only
  to produce the friendly message / suggestion.
- **Two constraints, not one**: the model also has `reservation_during_bounded` (rejects empty/unbounded
  ranges; it does **not** cap duration). The `IntegrityError` handler must **branch on the constraint
  name** (inspect `e.__cause__` / the DB diagnostic) and only run the conflict + next-window path for
  `reservation_no_overlap`. A bounded violation (e.g. an empty range when "until next reservation" lands on
  a booking that starts at `start`) would otherwise re-query for a conflict, find none, and 500 / show a
  misleading "conflicts with (none)" message. Belt-and-suspenders: form `clean()` rejects empty/zero ranges
  (see Phase 2 §2) so the bounded check should not fire from valid user input.
- **datetime-local parsing**: HTML `datetime-local` submits `YYYY-MM-DDTHH:MM` (naive). Add
  `%Y-%m-%dT%H:%M` to the form field `input_formats`, then `timezone.make_aware(value, get_current_timezone())`.
  Template auto-localization (USE_TZ) renders aware datetimes back in `settings.TIME_ZONE`.
- **MAX_DURATION**: `timedelta(hours=4)` as a single module constant in `services.py`, reused as the preset
  default and the "until next reservation" ceiling.

---

## Phase 1: Read-only env list dashboard + HTMX wiring

### Overview
Stand up the dashboard at `/` showing every env with free/busy state, current reservation, and upcoming
reservations within 24h (owner + window). Vendor HTMX and configure static. No booking yet.

### Changes Required:

#### 1. HTMX vendor asset
**File**: `static/vendor/htmx.min.js` (new)
**Intent**: Vendor HTMX (~14KB) so whitenoise serves it; no CDN dependency.
**Contract**: referenced via `{% static 'vendor/htmx.min.js' %}`.

#### 2. Settings
**File**: `envbooker/settings.py`
**Intent**: Enable a project-level static dir and set the single org display timezone.
**Contract**: add `STATICFILES_DIRS = [BASE_DIR / "static"]`; set `TIME_ZONE` to the org zone (confirm exact
value at implementation time, e.g. `"Europe/Warsaw"`); keep `USE_TZ=True`.

#### 3. Base template
**File**: `templates/base.html`
**Intent**: Load HTMX globally.
**Contract**: `{% load static %}` + `<script src="{% static 'vendor/htmx.min.js' %}"></script>` in `<head>`.

#### 4. Dashboard view
**File**: `catalog/views.py`
**Intent**: List all envs with current + next-24h reservations, auth-gated.
**Contract**: `login_required` view; queries `Environment`s; attaches current reservation
(`during__contains=now`) + upcoming reservations overlapping `[now, now+24h]` ordered by lower bound, via a
filtered `Prefetch` to avoid N+1. Per-env row context (attributes, free/busy badge, current + upcoming) is
produced by a shared `build_row_context(env, now=None)` helper (new, `catalog/services.py`) so the create
view in Phase 2 can render the identical row fragment from one source of truth.

#### 5. URL wiring
**File**: `catalog/urls.py` (new), `envbooker/urls.py`
**Intent**: Serve the dashboard at `/`, replacing the placeholder TemplateView, keeping `name="home"`.
**Contract**: `LOGIN_REDIRECT_URL="home"` continues to resolve.

#### 6. Templates
**File**: `templates/catalog/environment_list.html` (new), `templates/catalog/_environment_row.html` (new)
**Intent**: Render the list and a per-env row partial.
**Contract**: row has `id="env-row-{{ env.pk }}"` (HTMX swap target); shows attributes, free/busy badge,
current + upcoming reservations with owner (`get_full_name|default:email`) and localized windows. Booking
form added in Phase 2.

#### 7. Admin registration
**File**: `catalog/admin.py`, `reservations/admin.py`
**Intent**: `Environment` and `Reservation` are not currently registered in Django admin; register them so
data can be seeded/inspected via `/admin/` for manual verification (no fixtures or seed command needed).
**Contract**: both models appear and are editable under `/admin/`.

### Success Criteria:
#### Automated Verification:
- No unintended model changes: `uv run python manage.py makemigrations --check --dry-run`
- Anonymous request to `/` redirects to login
- Dashboard groups current vs upcoming-within-24h reservations correctly
#### Manual Verification:
- `/` shows envs with owners + windows; free/busy state correct against seeded data
- Times display in the configured org timezone
- `Environment` and `Reservation` are editable under `/admin/` (for seeding QA data)

**Implementation Note**: After Phase 1 automated verification passes, pause for manual confirmation before Phase 2.

---

## Phase 2: Reservation booking flow (create + overlap rejection)

### Overview
Add the booking form to each env row, the create view (HTMX), the gap-finder, race-safe creation, and the
named-conflict + suggested-next-window rejection.

### Changes Required:

#### 0. Reuse the shared row-context builder
**File**: `catalog/services.py` (`build_row_context`, introduced in Phase 1 §4)
**Intent**: The create view renders the same `_environment_row.html` swap target as the dashboard, so it
must call `build_row_context(env)` for the saved/attempted env — never hand-roll a parallel context.
**Contract**: on success the rebuilt row reflects the new reservation; on rejection it shows the existing
reservations + the error. One source of truth for the partial's context.

#### 1. Gap-finder services
**File**: `reservations/services.py` (new)
**Intent**: Centralize duration/gap computation reused by booking and rejection.
**Contract**: `MAX_DURATION = timedelta(hours=4)`; `next_reservation_after(env, start)`;
`compute_end(env, start, duration_choice, custom_hours=None)` (presets, custom hours, and "until next
reservation" → `min(next.start, start+MAX)`, fallback `start+MAX`); `next_free_window(env, after)`. Pure
functions over querysets, unit-testable.

#### 2. Reservation form
**File**: `reservations/forms.py` (new)
**Intent**: Validate input and build the `during` range.
**Contract**: fields `environment` (hidden PK), `start` (datetime-local, `input_formats` incl.
`%Y-%m-%dT%H:%M`), `duration` (ChoiceField: 1h/2h/4h/custom/until-next), optional `custom_hours`. `clean()`
makes `start` aware, computes `end` via services, returns a `DateTimeTZRange`; rejects past-start and
zero/negative ranges with field errors.

#### 3. Create view
**File**: `reservations/views.py`
**Intent**: Create the reservation race-safely and return the updated row fragment.
**Contract**: POST, `login_required`; sets `owner=request.user`; saves inside `transaction.atomic()`;
catches `IntegrityError` and **branches on the constraint name** — for `reservation_no_overlap`, re-queries
conflict + next free window and re-renders the row partial with the named-conflict message; for
`reservation_during_bounded` (or any other), re-renders with a generic validation error (no conflict
re-query). Always returns `templates/catalog/_environment_row.html` (consistent HTMX swap target),
rebuilding its context via the shared `build_row_context` helper (§0) so the swapped row reflects current
state on both success and rejection.

#### 4. URL wiring
**File**: `reservations/urls.py` (new), `envbooker/urls.py`
**Intent**: Expose the create endpoint under `reservations/` with namespace `reservations`.
**Contract**: `reservations:create`.

#### 5. Booking form in row partial
**File**: `templates/catalog/_environment_row.html`
**Intent**: Wire the form to HTMX.
**Contract**: `<form hx-post="{% url 'reservations:create' %}" hx-target="#env-row-{{ env.pk }}" hx-swap="outerHTML">`
with `{% csrf_token %}` inside the form (HTMX serializes form fields, so the token is sent — same idiom as
the logout form in `base.html`); render form errors + conflict/suggestion message inline.

### Success Criteria:
#### Automated Verification:
- Happy-path booking creates a reservation; response fragment shows it
- Overlapping window rejected; message names conflicting owner + window
- Constraint-violation handling: an overlapping save (exclusion constraint) is caught and surfaced, not a 500
- `compute_end` "until next reservation" caps at MAX and stops at the next booking's start (adjacency allowed)
- `next_free_window` returns a correct opening
- Create view requires auth
#### Manual Verification:
- Booking a free env updates only that row, no full page reload (HTMX)
- Rejection shows named conflict + suggested next window inline, no reload
- "Until next reservation" fills the gap up to the next booking, capped at 4h
- Round-trip from landing to confirmed reservation feels well under 30s

**Implementation Note**: After Phase 2 automated verification passes, pause for manual confirmation before Phase 3.

---

## Phase 3: Automated test suite (core behavior + overlap focus)

### Overview
Round out tests per the chosen depth: core behavior with an overlap/race focus.

### Changes Required:

#### 1. Reservation tests
**File**: `reservations/tests.py`
**Intent**: Cover services and the create view.
**Contract**: service tests (`compute_end` presets/custom/until-next + adjacency, `next_reservation_after`,
`next_free_window`); view tests (happy path, overlap rejection message, IntegrityError constraint-violation
handling via a direct overlapping create — **wrap that deliberately-overlapping save in
`transaction.atomic()`** so the `IntegrityError` doesn't poison the test's outer transaction — auth
required). Note: this exercises the constraint-violation *handler*, not literal cross-connection
concurrency; the exclusion constraint itself is the race guarantee, correct by construction. Append to the
existing `reservations/tests.py` (which already holds F-01 constraint tests) — do not overwrite it.

#### 2. Catalog tests
**File**: `catalog/tests.py`
**Intent**: Cover the dashboard.
**Contract**: auth redirect, current vs upcoming-within-24h grouping, owner visibility, free/busy badge.
Use a small fixture of users + envs + reservations around a frozen `now`.

### Success Criteria:
#### Automated Verification:
- Full suite passes: `uv run python manage.py test`
- New tests cover overlap rejection, the DB race path, gap/until-next logic, the 24h horizon query, and access control
#### Manual Verification:
- Test names clearly map to FR-015 / US-01 acceptance criteria

---

## Testing Strategy

### Unit Tests:
- `compute_end` across all duration choices incl. "until next reservation" cap + adjacency
- `next_reservation_after` / `next_free_window` gap math
- Form `clean()` rejects past-start and zero/negative ranges

### Integration Tests:
- Booking happy path returns the row fragment with the new reservation
- Overlap rejection returns the row fragment with named conflict + suggestion (no 500 on the DB race path)
- Dashboard auth gating + 24h horizon grouping

### Manual Testing Steps:
1. Seed envs + reservations via `/admin/`; sign in.
2. Confirm dashboard lists envs with owners + 24h horizon and correct free/busy state.
3. Book a free env → row updates live, no reload.
4. Attempt an overlapping window → inline named conflict + suggested next window.
5. Use "until next reservation" → fills the gap, capped at 4h.

## Performance Considerations

The dashboard must avoid N+1 across envs — use a single filtered `Prefetch` for the `[now, now+24h]`
window. Env count is small (20–50 per PRD), QPS low; no caching needed for v1. NFR: acknowledge within
200ms — HTMX partial swaps keep payloads to a single row.

## Migration Notes

No model changes — F-01's schema is reused as-is. `makemigrations --check` should report nothing.

## References

- Roadmap slice: `context/foundation/roadmap.md:92` (S-02)
- PRD: `context/foundation/prd.md` (FR-008/010/011/015, US-01)
- Models: `catalog/models.py:5`, `reservations/models.py:8`
- Pattern reuse: `accounts/views.py`, `accounts/forms.py`, `templates/base.html`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Read-only env list dashboard + HTMX wiring

#### Automated
- [x] 1.1 No unintended model changes (`makemigrations --check --dry-run`) — 9eb7cfe
- [x] 1.2 Anonymous request to `/` redirects to login — 9eb7cfe
- [x] 1.3 Dashboard groups current vs upcoming-within-24h reservations correctly — 9eb7cfe

#### Manual
- [x] 1.4 `/` shows envs with owners + windows; free/busy state correct against seeded data
- [x] 1.5 Times display in the configured org timezone
- [x] 1.6 `Environment` and `Reservation` are editable under `/admin/` (for seeding QA data)

### Phase 2: Reservation booking flow (create + overlap rejection)

#### Automated
- [x] 2.1 Happy-path booking creates a reservation; response fragment shows it
- [x] 2.2 Overlapping window rejected; message names conflicting owner + window
- [x] 2.3 Constraint-violation handling: overlapping save caught and surfaced, not a 500
- [x] 2.4 `compute_end` "until next reservation" caps at MAX and stops at next booking's start (adjacency allowed)
- [x] 2.5 `next_free_window` returns a correct opening
- [x] 2.6 Create view requires auth

#### Manual
- [x] 2.7 Booking a free env updates only that row, no full page reload (HTMX)
- [x] 2.8 Rejection shows named conflict + suggested next window inline, no reload
- [x] 2.9 "Until next reservation" fills the gap up to the next booking, capped at 4h
- [x] 2.10 Round-trip from landing to confirmed reservation feels well under 30s

### Phase 3: Automated test suite (core behavior + overlap focus)

#### Automated
- [ ] 3.1 Full suite passes (`uv run python manage.py test`)
- [ ] 3.2 New tests cover overlap rejection, DB race path, gap/until-next logic, 24h horizon query, access control

#### Manual
- [ ] 3.3 Test names clearly map to FR-015 / US-01 acceptance criteria
