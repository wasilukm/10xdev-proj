# Edit Own Reservation (S-04) Implementation Plan

## Overview

Let a signed-in user **modify the duration/end of their own reservation** and **cancel it**, surfaced on a new **"My reservations"** page. Modifications are subject to the same no-overlap rejection (FR-015) as creation; users cannot touch reservations they do not own (FR-012, FR-013, Access Control). The start of a reservation is immutable — editing changes only the duration (and thus the end). Admin override of others' reservations is **out of scope** (that is S-06).

This slice reuses the established HTMX row-swap pattern and the overlap-detection / conflict-decoding logic already shipped in S-02 (`browse-and-reserve`). The edit form is intentionally minimal — a single numeric **hours** field prefilled with the reservation's current duration. The create form's richer duration presets (`1h/2h/4h/custom/until_next`) are *not* reused for editing; a raw value keeps the edit UI simple.

## Current State Analysis

- **Reservation model** (`reservations/models.py`): `owner` FK, `environment` FK, `during DateTimeRangeField`, `created_at`. A Postgres GiST `ExclusionConstraint` (`reservation_no_overlap`) guarantees no two reservations on the same env overlap; a `CheckConstraint` (`reservation_during_bounded`) rejects empty/unbounded ranges. No `status` field, no per-row ownership gating anywhere yet.
- **Create flow** (`reservations/views.py:27` `reservation_create`): `@login_required @require_POST`, validates `ReservationForm`, creates inside `transaction.atomic()`, and on `IntegrityError` decodes the constraint name to produce a named-owner conflict message + `next_free_window`. Returns the `catalog/_environment_row.html` partial swapped into `#env-row-{pk}` (`_row_response`).
- **Form** (`reservations/forms.py`): `ReservationForm` has `environment` (hidden), `start`, `duration` (choice of `1h/2h/4h/custom/until_next`), `custom_hours`. `clean()` makes `start` aware, rejects past starts, calls `services.compute_end(env, start, duration, custom_hours)`, and stores `during = Range(start, end, "[)")`.
- **Services** (`reservations/services.py`): `compute_end` resolves the end; `until_next` calls `next_reservation_after(env, start)` (via `_qs_starting_at_or_after`, a `lower()`-annotated query). `next_free_window` follows contiguous blocks. **None of these accept a "reservation to exclude" — they will see the row being edited as a sibling.**
- **Surface gap**: the env list (`catalog/views.py` + `catalog/services.py:build_row_context`) only renders each env's *current* reservation + *upcoming-24h*. A user's reservations beyond 24h are not shown anywhere — hence a dedicated "My reservations" page.
- **Routing**: `reservations/urls.py` has only `create/` (`app_name = "reservations"`). Root urls include it under `reservations/`.
- **Nav** (`templates/base.html`): a single `<nav>` with auth links; no app navigation links yet.
- **Tests** (`reservations/tests.py`, 290 lines): model-constraint tests, service tests (`ComputeEndTest`, `NextReservationAfterTest`, `NextFreeWindowTest`), and `ReservationCreateViewTest` (auth-required, happy path, overlap-rejection-names-owner, not-500) — `@patch`-ing `timezone.now` where needed.

## Desired End State

A signed-in user opens **My reservations** (`/reservations/mine/`), sees a list of their own active + upcoming reservations (env, time window, status), and for each can:

- **Edit the duration** via an inline form — a single hours field, prefilled with the current window length (start is shown read-only and never changes); the new end is `start + hours`. Saving either updates the window in place (row re-renders) or, on overlap, re-renders the row with a named-owner conflict message — without false-positiving against the row's own pre-edit window in the conflict lookup.
- **Cancel** via a button guarded by a native `hx-confirm` prompt; on confirm the reservation is hard-deleted and the row disappears.

A non-owner (or non-existent id) requesting edit/cancel receives **404**. Past reservations (already ended) are not editable/cancelable. A "My reservations" nav link appears for authenticated users.

Verify: `uv run python manage.py test reservations` passes (including new tests); manual walkthrough on the running app confirms edit, cancel, overlap-on-edit, and the 404 guard.

### Key Discoveries:

- **Self-exclusion is required in exactly one place: the conflict-report query.** After an in-place `save()` raises `IntegrityError`, the transaction rolls back, so the row still holds its *old* window. The conflict lookup `filter(environment=env, during__overlap=new_during)` (`views.py:53-58`) can therefore match the row itself (e.g. when extending an existing window) and must `.exclude(pk=reservation.pk)`. Because the edit form does **not** offer `until_next`, the `compute_end` / `next_reservation_after` "row sees itself as its own successor" problem never arises — so the services need no `exclude_pk` and stay untouched. The DB `ExclusionConstraint` itself is fine on an in-place `UPDATE` (a row never conflicts with itself).
- **Start is immutable; duration is a raw hours value** (confirmed decisions): edit changes only the duration, entered as a single number. This sidesteps the "past start rejected by `ReservationForm.clean()`" problem entirely, makes in-progress edits coherent (only the end moves), and avoids reconstructing the original preset/`until_next` choice (which isn't stored anyway).
- **`end > now` is the binding edit validation.** For a future reservation `now < start`, so `end > start` already implies it; for an in-progress reservation (`start < now`) the reservation must still have a future tail, so `end > now` is what prevents shrinking it into the past (which would be a disguised cancel).
- **HTMX outerHTML-swap of a per-item partial** is the established interaction model; cancel returns empty content to make the row vanish.
- **Hard delete** (confirmed) — no `status` field, no migration; matches PRD Non-Goals (no notifications/audit).

## What We're NOT Doing

- **Not** allowing the start time or environment to change (booked the wrong start/env → cancel + rebook).
- **Not** implementing admin override of others' reservations (FR-014 / S-06).
- **Not** adding soft-delete, audit trail, undo, or cancellation notifications (PRD Non-Goals).
- **Not** adding edit/cancel controls inline on the env-list rows (the "My reservations" page is the single surface for this slice).
- **Not** touching the DST/calendar edge-case hardening deferred to SPIKE-01 (`timezone-calendar-edge-cases`).
- **Not** rendering past (ended) reservations as editable; they may be shown read-only or omitted (see Phase 2).

## Implementation Approach

Build bottom-up: first add a minimal hours-based edit form (pure, unit-testable). Then add the three views + URLs + the "My reservations" page and its inline item partial, reusing the create view's conflict-decoding logic with the single self-exclusion. Finally, add view/integration tests matching the existing suite's depth and do a manual pass.

## Critical Implementation Details

- **Single self-exclusion site.** The edit view's conflict-report query must `.exclude(pk=reservation.pk)`. That is the only place self-exclusion is needed — the ordering services are not touched (see Key Discoveries).
- **Edit validation ordering.** Compute `end = start + timedelta(hours=hours)`, then reject if `end <= timezone.now()` (would leave no future window). Overlap is enforced by the DB `ExclusionConstraint`: the in-place `Reservation.save(update_fields=["during"])` inside `transaction.atomic()` raises `IntegrityError` with `reservation_no_overlap` on conflict, decoded exactly as in create.
- **Editable gating.** A reservation is editable/cancelable iff `during.upper > now` (active or future). Enforce server-side in the view (return 404 or a refreshed read-only row) — not just by hiding the control.

## Phase 1: Edit Form Foundation

### Overview

Introduce a minimal hours-based edit form that computes a new end from the reservation's fixed start. Pure logic, fully unit-testable, no user-facing change yet. The ordering services (`compute_end`, `next_reservation_after`, `next_free_window`) are intentionally **not** modified — the edit form doesn't use `until_next`, so no `exclude_pk` threading is needed.

### Changes Required:

#### 1. Hours-based edit form

**File**: `reservations/forms.py`

**Intent**: Provide a form for editing a reservation's duration as a single raw hours value while holding its start fixed.

**Contract**: New `ReservationEditForm(forms.Form)` with one field — `hours` (`DecimalField`, `min_value=0.25`, `max_digits=5`, `decimal_places=2`, `required=True`). It does **not** include `start`, `environment`, or a duration choice. Pass the fixed `start` via `__init__(self, *args, start, **kwargs)` and store it on the instance. Its `clean()` computes `end = start + timedelta(hours=float(hours))`, rejects `end <= timezone.now()` ("New end must be in the future — increase the hours or cancel instead.") and (defensively) `end <= start`, and stores `cleaned_data["during"] = Range(start, end, "[)")`. Overlap is left to the DB constraint at save time (Phase 2).

### Success Criteria:

#### Automated Verification:

- New edit-form unit tests pass: `uv run python manage.py test reservations.tests.ReservationEditFormTest`
- No regression in existing create-path / service tests: `uv run python manage.py test reservations`

#### Manual Verification:

- (none — pure form logic; covered by the automated form tests)

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding.

---

## Phase 2: Views, URLs, Templates, Nav

### Overview

Add the user-facing feature: the "My reservations" page listing the user's active/upcoming reservations, with an inline duration-edit form and a cancel button, plus the three views, routes, and a nav link.

### Changes Required:

#### 1. Edit, cancel, and listing views

**File**: `reservations/views.py`

**Intent**: Add `my_reservations` (list), `reservation_edit` (apply a duration change), and `reservation_cancel` (hard-delete), all owner-scoped, reusing the create view's conflict-decoding logic.

**Contract**:
- `my_reservations(request)` — `@login_required`. Lists `request.user.reservations` with `during.upper > now` (active + future), `select_related("environment")`, ordered by lower bound; renders `templates/reservations/my_reservations.html`. Each reservation's `ReservationEditForm` is seeded with `initial={"hours": <current window length in hours>}` (compute `(during.upper - during.lower).total_seconds() / 3600`, rounded to 2dp) so the form opens at the current duration.
- `reservation_edit(request, pk)` — `@login_required @require_POST`. `reservation = get_object_or_404(Reservation, pk=pk, owner=request.user)`; 404 also if `reservation.during.upper <= now` (not editable). Builds `ReservationEditForm(request.POST, start=reservation.during.lower)`. On invalid form, re-render the item partial with form errors. On valid: inside `transaction.atomic()`, set `reservation.during = cleaned_data["during"]` and `reservation.save(update_fields=["during"])`; on `IntegrityError` decode `reservation_no_overlap` → named-owner conflict message using the conflict query `filter(environment=..., during__overlap=...).exclude(pk=reservation.pk)`. Returns the `_reservation_item.html` partial (updated row or conflict message).
- `reservation_cancel(request, pk)` — `@login_required @require_POST`. Owner-scoped 404 (and `during.upper <= now` → 404). Deletes the reservation; returns an empty `HttpResponse("")` so the HTMX `outerHTML` swap removes the row.
- Factor a small `_item_response(request, reservation, form=None, conflict_message=None)` helper mirroring `_row_response`.

**Contract note**: The conflict-decoding block (`IntegrityError` → `__cause__` string → constraint-name branch) is duplicated logic from `reservation_create`; extract a shared helper (e.g. `services.describe_overlap_conflict(env, during, exclude_pk=None)` returning the message) so create and edit share one implementation. Update `reservation_create` to use it.

#### 2. Routes

**File**: `reservations/urls.py`

**Intent**: Expose the three new endpoints under the existing `reservations:` namespace.

**Contract**: Add `path("mine/", views.my_reservations, name="mine")`, `path("<int:pk>/edit/", views.reservation_edit, name="edit")`, `path("<int:pk>/cancel/", views.reservation_cancel, name="cancel")`.

#### 3. My-reservations page + item partial

**File**: `templates/reservations/my_reservations.html`, `templates/reservations/_reservation_item.html`

**Intent**: Render the list and the per-reservation inline edit/cancel controls using the HTMX outerHTML-swap pattern.

**Contract**:
- `my_reservations.html` extends `base.html`, iterates the reservations into `_reservation_item.html`, and handles the empty case ("You have no upcoming reservations.").
- `_reservation_item.html` renders one reservation inside a uniquely-id'd container (e.g. `id="reservation-{{ reservation.pk }}"`) showing env name, start (read-only), current end, and status. It contains: an edit `<form>` (`hx-post="{% url 'reservations:edit' reservation.pk %}"`, `hx-target="#reservation-{{ reservation.pk }}"`, `hx-swap="outerHTML"`) rendering the `ReservationEditForm`; a cancel `<form>` (`hx-post="{% url 'reservations:cancel' reservation.pk %}"`, same target/swap, `hx-confirm="Cancel this reservation?"`); and an optional `{{ conflict_message }}` block. The edit form is shown only when the reservation is editable (`during.upper > now`).

#### 4. Navigation link

**File**: `templates/base.html`

**Intent**: Give authenticated users a way to reach their reservations (and the env list).

**Contract**: In the authenticated `<nav>` branch, add links to `{% url 'home' %}` ("Environments") and `{% url 'reservations:mine' %}` ("My reservations").

### Success Criteria:

#### Automated Verification:

- Django check passes: `uv run python manage.py check`
- URL reversing works (covered by the Phase 3 view tests): `uv run python manage.py test reservations`

#### Manual Verification:

- "My reservations" link appears when signed in and lists the user's upcoming reservations.
- The edit form opens pre-populated with the reservation's current duration in hours, not a blank default.
- Editing a future reservation's duration updates its window in place without a full page reload.
- Editing into an overlap re-renders the row with a named-owner conflict message and leaves the original window intact.
- Editing an in-progress reservation can shorten/extend the end (start stays put); cannot set an end in the past.
- Cancel shows the confirm prompt and removes the row on confirm.
- Another user's reservation id on `/edit/` or `/cancel/` returns 404.

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding.

---

## Phase 3: Tests & Manual QA

### Overview

Add view/integration tests matching the depth of the existing `ReservationCreateViewTest`, covering ownership, overlap-with-self-exclusion, time-gating, and cancel.

### Changes Required:

#### 1. Edit/cancel view tests

**File**: `reservations/tests.py`

**Intent**: Lock in the authorization, overlap, and time-gating behavior so regressions surface.

**Contract**: New `ReservationEditViewTest` and `ReservationCancelViewTest` (mirroring `ReservationCreateViewTest`'s `setUp` + `@patch` of `timezone.now` where needed) covering:
- auth required (redirect when anonymous);
- non-owner / non-existent pk → 404 for both edit and cancel;
- happy future edit changes `during` and re-renders the item;
- in-progress edit changes only the end, keeps the original start, rejects an end `<= now`;
- edit into an overlapping window → conflict message names the other owner and does **not** false-positive against the row's own pre-edit window (the `.exclude(pk=...)` self-exclusion in the conflict query);
- extending an existing window (overlaps only its own old range) succeeds rather than reporting a self-conflict;
- cancel deletes the row and returns empty content;
- past (ended) reservation → edit and cancel both 404.

#### 2. Form/service unit tests (if not already added in Phase 1)

**File**: `reservations/tests.py`

**Intent**: Directly exercise `ReservationEditForm`.

**Contract**: `ReservationEditFormTest` covering a valid hours change (correct `during` Range from the fixed start), `end <= now` rejection, and the `min_value` bound on `hours`.

### Success Criteria:

#### Automated Verification:

- Full reservations suite passes: `uv run python manage.py test reservations`
- Full project suite passes: `uv run python manage.py test`
- Django check passes: `uv run python manage.py check`

#### Manual Verification:

- End-to-end manual walkthrough on the running dev server (`uv run python manage.py runserver`) confirms all Phase 2 manual criteria together with a second user account for the 404 ownership path.

**Implementation Note**: After completing this phase and all automated verification passes, pause for final manual confirmation.

---

## Testing Strategy

### Unit Tests:

- `ReservationEditForm`: valid hours change → correct `during` Range from the fixed start, `end <= now` rejection, `hours` `min_value` bound.

### Integration Tests:

- Edit and cancel views end-to-end via the test client (HTMX POSTs), asserting status codes, DB state, rendered partials, ownership 404s, and the self-exclusion overlap behavior.

### Manual Testing Steps:

1. Sign in as user A; create two future reservations on the same env back-to-back.
2. Open "My reservations"; edit the first to extend up to (not into) the second — succeeds.
3. Edit the first to overlap the second — rejected with a named-owner conflict message; original window unchanged.
4. Edit a reservation that is currently in progress: shorten the end (start unchanged); attempt an end in the past — rejected.
5. Cancel a reservation — confirm prompt appears; on confirm the row disappears.
6. As user B, POST to user A's `/reservations/<pk>/edit/` and `/cancel/` — both 404.

## Performance Considerations

Negligible. The list query is a single owner-scoped `select_related("environment")`. Edit/cancel touch one row inside a short transaction. No N+1 (no per-row reservation re-query as in the env list).

## Migration Notes

No schema changes — no migration. Cancellation is a hard delete; existing data is unaffected.

## References

- Roadmap: `context/foundation/roadmap.md` (S-04)
- PRD: `context/foundation/prd.md` (FR-012, FR-013, FR-015, Access Control)
- Reuses create flow: `reservations/views.py:27`, `reservations/forms.py`, `reservations/services.py`
- Sibling slice (patterns): `context/archive/2026-05-31-browse-and-reserve/`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Edit Form Foundation

#### Automated

- [x] 1.1 New edit-form unit tests pass (ReservationEditFormTest)
- [x] 1.2 No regression in existing create-path / service tests (reservations)

### Phase 2: Views, URLs, Templates, Nav

#### Automated

- [ ] 2.1 Django check passes
- [ ] 2.2 URL reversing works (via reservations test suite)

#### Manual

- [ ] 2.3 "My reservations" link appears and lists upcoming reservations
- [ ] 2.4 Edit form opens pre-populated with the current duration in hours
- [ ] 2.5 Editing a future reservation's duration updates in place without reload
- [ ] 2.6 Editing into an overlap re-renders with a named conflict, original window intact
- [ ] 2.7 In-progress edit shifts the end only; end-in-past rejected
- [ ] 2.8 Cancel shows confirm prompt and removes the row
- [ ] 2.9 Another user's reservation id on edit/cancel returns 404

### Phase 3: Tests & Manual QA

#### Automated

- [ ] 3.1 Full reservations suite passes
- [ ] 3.2 Full project suite passes
- [ ] 3.3 Django check passes

#### Manual

- [ ] 3.4 End-to-end manual walkthrough with a second user account confirms all criteria
