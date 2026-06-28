# Admin Reservation Override Implementation Plan

## Overview

Allow staff/superusers to **cancel and edit any user's reservation** through the existing HTMX app UI (not the Django admin). Today both mutating reservation views are hard-scoped to `owner=request.user`, so a user can only touch their own bookings. This change relaxes that scoping for admins and surfaces per-reservation edit/cancel controls inline in the environment row for admin viewers. Admins are bound by the same time rule as users (only reservations that have not yet ended, `during.upper > now`). No audit trail is added.

## Current State Analysis

- **Authz is per-view, via the ORM filter.** `reservation_edit` and `reservation_cancel` both call `get_object_or_404(Reservation, pk=pk, owner=request.user)` (`reservations/views.py:140`, `reservations/views.py:175`), then enforce a past-block (`reservation.during.upper <= now → Http404`). A non-owner hitting either URL already gets a 404 — that is the entire access boundary.
- **The env row already displays other users' bookings as plain text.** `_environment_row.html:10-23` renders `current_reservation` and `upcoming_reservations` (owner label + time range) with no controls. The data is built by `catalog.services.build_row_context` (`catalog/services.py:24`), which returns plain `Reservation` objects (`current_reservation`, `upcoming_reservations`).
- **Edit/cancel controls already exist as a reusable partial.** `_reservation_item.html` renders the `hours` edit form and cancel form, keyed by `#reservation-{{ pk }}`, with `hx-swap="outerHTML"`. It is built from `_item_context` (`reservations/views.py:43`), which supplies `form` (a `ReservationEditForm`), `is_editable` (`during.upper > now`), and `is_active`. Edit returns `_item_response` (the same partial); cancel returns `HttpResponse("")`.
- **Two code paths render env rows:** the browse/list view `catalog.views.environment_list` (`catalog/views.py:48-51`, uses a 24h prefetch to avoid N+1) and the post-create/edit partial `reservations.views._row_response` (`reservations/views.py:23`). Both build a row context dict and pass selected vars into `_environment_row.html` via `{% with %}` in `_environment_results.html:20`.
- **Template can see the viewer.** `envbooker/settings.py:84-86` enables both the `request` and `auth` context processors, so `user.is_staff` / `user.is_superuser` are available in templates without passing a flag.
- **Tests** live in `reservations/tests/` (a package). `test_views.py` uses `_helpers.py` (`_FIXED_NOW`, `_dt`, `_range`) and `mock.patch` on `timezone.now` to keep "future start" checks deterministic (fixed anchor 2024-01-01 08:00 UTC).

### Key Discoveries:

- Access boundary is exactly the `owner=request.user` filter at `reservations/views.py:140` and `:175` — relaxing it for admins is the whole backend change.
- `_reservation_item.html` is keyed `#reservation-{{ reservation.pk }}` and the edit/cancel responses target that id with `outerHTML` — so reusing it inline in the env row gives identical HTMX swap semantics to the `my_reservations` page, for free.
- `_item_context` (`reservations/views.py:43`) already computes everything `_reservation_item.html` needs; the only gap is that `build_row_context` returns bare `Reservation` objects, not item contexts.
- The env-row "Busy/Free" badge and booking cell are NOT re-rendered when a single reservation div is swapped out by an inline cancel — so a stale badge is an expected, acceptable limitation (flag in manual verification).

## Desired End State

A logged-in staff or superuser browsing the environments list sees, next to each listed current/upcoming reservation (including those owned by other users), the same "Update duration" and "Cancel reservation" controls that owners see on *My Reservations*. Acting on them edits/cancels that reservation in place via HTMX. A non-staff user sees the row exactly as today (plain text, no controls) and cannot edit/cancel another user's reservation even by POSTing directly to the URL (still 404). The time rule is unchanged: already-ended reservations are not editable/cancelable by anyone.

Verified by: the new automated tests pass; manually, an admin can cancel/edit another user's booking from the browse page, and a normal user cannot.

## What We're NOT Doing

- No force-booking over a conflict / bumping a conflicting reservation (the no-overlap exclusion constraint is untouched; admin edits still respect it).
- No reassigning a reservation's owner.
- No editing/cancelling already-ended (past) reservations.
- No audit trail, audit model, or override logging.
- No changes to the Django admin (`ReservationAdmin`).
- No object-level permissions (environment-owner-based control); admin = `is_staff or is_superuser` only.
- No fix for the stale Busy/Free badge after an inline cancel (out of scope; documented limitation).

## Implementation Approach

Two phases, each independently testable. Phase 1 relaxes the backend access boundary so admins can mutate any not-yet-ended reservation, leaving everyone else's behavior identical. Phase 2 adds the UI surface: enrich the row context with per-reservation item contexts for admin viewers and render the existing `_reservation_item.html` controls inline, gated on `user.is_staff` in the template. Reusing the existing partial keeps HTMX swap semantics identical to the established *My Reservations* flow.

## Phase 1: Backend authz relaxation

### Overview

Introduce a single admin predicate and use it to drop the `owner` filter in the edit and cancel views for admins, keeping owner-scoping for everyone else and preserving the existing past-block and conflict handling.

### Changes Required:

#### 1. Admin predicate helper

**File**: `reservations/services.py`

**Intent**: Add one small, testable predicate that defines who may manage any reservation, so the rule lives in one place rather than being duplicated inline in two views.

**Contract**: `def is_reservation_admin(user) -> bool` returning `True` when the user is authenticated and `user.is_staff or user.is_superuser`. Pure function of the user; no DB access.

#### 2. Relax owner-scoping in edit and cancel views

**File**: `reservations/views.py`

**Intent**: For admins, look up the reservation by pk alone; for everyone else, keep the `owner=request.user` filter so non-admins still 404 on others' bookings. Preserve the `during.upper <= now → Http404` past-block and all existing conflict/IntegrityError handling unchanged.

**Contract**: In `reservation_edit` (`:139`) and `reservation_cancel` (`:174`), replace the `get_object_or_404(Reservation, pk=pk, owner=request.user)` lookup with a lookup that conditionally includes the `owner` filter based on `services.is_reservation_admin(request.user)`. Behavior for non-admins, and the past-block, are byte-for-byte equivalent to today. A short shared helper inside `views.py` (e.g. `_reservation_for_request(request, pk)`) is acceptable to avoid duplicating the branch.

### Success Criteria:

#### Automated Verification:

- Type checking passes: `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .`
- Linting passes: `uv run ruff check . && uv run ruff format --check .`
- New + existing reservation view tests pass: `uv run python manage.py test reservations.tests.test_views`
- New service test passes: `uv run python manage.py test reservations.tests.test_services`

#### Manual Verification:

- As a staff user, POSTing to `/reservations/<pk>/cancel/` for another user's not-yet-ended reservation removes it.
- As a normal user, the same POST still returns 404.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Inline admin controls in the environment row

### Overview

Surface the existing edit/cancel partial inline in the env row for admin viewers, by enriching the row context with per-reservation item contexts in both row-rendering code paths and gating the controls on `user.is_staff` in the template. Non-admins see the unchanged plain-text listing.

### Changes Required:

#### 1. Expose the item-context builder

**File**: `reservations/views.py`

**Intent**: Make the per-reservation item context (form, `is_editable`, `is_active`) reusable from the catalog list view so admin controls can be rendered for each listed reservation, not just on *My Reservations*. The current `_item_context` already produces exactly this.

**Contract**: Promote `_item_context` to an importable helper (rename to `build_reservation_item` or re-export; keep the existing signature `(reservation, form=None, conflict_message=None) -> dict`). Existing callers (`my_reservations`, `_item_response`) updated to the new name. No behavior change.

#### 2. Enrich row context for admin viewers

**Files**: `catalog/views.py` (`environment_list`, `:47-51`) and `reservations/views.py` (`_row_response`, `:23`)

**Intent**: When the viewer is an admin, attach item contexts for the row's `current_reservation` and `upcoming_reservations` so the template can render controls; for non-admins, add nothing (template falls back to plain text). Both row-rendering paths must do this so controls appear on first browse load and after a booking re-renders the row.

**Contract**: After building the row dict, when `services.is_reservation_admin(request.user)`, add keys `current_item` (item context for `current_reservation`, or `None`) and `upcoming_items` (list of item contexts for `upcoming_reservations`). Pass these vars into `_environment_row.html` via the `{% with %}` in `_environment_results.html` (list path) and the `render` context (`_row_response` path). `catalog/views.py` already imports from `reservations`; importing the helper + predicate is consistent with the existing cross-module usage.

#### 3. Render inline controls in the row, gated on staff

**File**: `templates/catalog/_environment_row.html`

**Intent**: For staff viewers, render the reusable `_reservation_item.html` controls for the current and each upcoming reservation in place of (or beneath) the plain-text entries; for non-staff, render today's plain text unchanged.

**Contract**: In the "Current reservation" cell (`:10-16`) and "Upcoming" cell (`:17-24`), branch on `{% if user.is_staff %}`: when true, `{% include "reservations/_reservation_item.html" %}` with the matching item context (`current_item` / each of `upcoming_items`); else keep the existing plain-text markup. The included partial is keyed `#reservation-{{ pk }}`, so the Phase 1 edit/cancel responses swap it correctly inside the row.

#### 4. Pass viewer vars through the results include

**File**: `templates/catalog/_environment_results.html`

**Intent**: Ensure the new `current_item` / `upcoming_items` row vars reach `_environment_row.html`.

**Contract**: Extend the `{% with %}` at `:20` to include `current_item=row.current_item upcoming_items=row.upcoming_items`. (`user` is already globally available via the auth context processor.)

### Success Criteria:

#### Automated Verification:

- Type checking passes: `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .`
- Linting passes: `uv run ruff check . && uv run ruff format --check .`
- View/template tests pass: `uv run python manage.py test reservations.tests.test_views`
- Full suite passes: `uv run python manage.py test`

#### Manual Verification:

- As a staff user, the browse page shows "Update duration" / "Cancel reservation" controls on another user's current and upcoming reservations; using them edits/cancels in place.
- As a normal user, the browse page shows the unchanged plain-text reservation listing with no controls.
- Known limitation confirmed acceptable: after an inline admin cancel, the row's Busy/Free badge may be stale until the next filter/refresh.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful.

---

## Testing Strategy

### Unit Tests:

- `is_reservation_admin`: staff → True, superuser → True, regular user → False, anonymous/unauthenticated → False (`reservations/tests/test_services.py`).

### Integration Tests (`reservations/tests/test_views.py`):

- Admin (staff) can cancel another user's not-yet-ended reservation → reservation deleted, 200 + empty body.
- Admin can edit another user's reservation duration → `during` updated, partial re-rendered.
- Non-admin POSTing edit/cancel for another user's reservation → 404 (regression guard for the boundary).
- Admin cancelling/editing an already-ended reservation → 404 (time rule preserved).
- Owner can still edit/cancel their own reservation (no regression).
- Env-row rendering: a staff request to the list view yields edit/cancel controls (e.g. the cancel URL / `#reservation-<pk>` form) for another user's reservation; a normal-user request does not.

### Manual Testing Steps:

1. Log in as a superuser; create reservations as two different users; from the browse page, cancel and edit the other user's reservation.
2. Log in as a normal user; confirm no controls appear and direct POSTs 404.
3. Confirm an already-ended reservation offers no controls and 404s on direct POST.

## Performance Considerations

The list view already prefetches the 24h reservation window per env (`prefetch_reservations_for_list`) and `select_related("owner")`, so building item contexts for admins iterates already-loaded objects — no new queries per row. `is_reservation_admin` is a pure attribute check. No N+1 introduced.

## Migration Notes

None — no model or schema changes.

## References

- Access boundary: `reservations/views.py:140`, `reservations/views.py:175`
- Reusable controls partial: `templates/reservations/_reservation_item.html`, built by `reservations/views.py:43` (`_item_context`)
- Row context: `catalog/services.py:24` (`build_row_context`); row render paths `catalog/views.py:47` and `reservations/views.py:23`
- Context processors enabling `user.is_staff` in templates: `envbooker/settings.py:84`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Backend authz relaxation

#### Automated

- [x] 1.1 Type checking passes (mypy) — cba4f86
- [x] 1.2 Linting passes (ruff check + format --check) — cba4f86
- [x] 1.3 reservation view tests pass — cba4f86
- [x] 1.4 service test for is_reservation_admin passes — cba4f86

#### Manual

- [x] 1.5 Staff can cancel another user's not-yet-ended reservation via direct POST — cba4f86
- [x] 1.6 Normal user still 404s on the same POST — cba4f86

### Phase 2: Inline admin controls in the environment row

#### Automated

- [x] 2.1 Type checking passes (mypy)
- [x] 2.2 Linting passes (ruff check + format --check)
- [x] 2.3 View/template tests pass
- [x] 2.4 Full test suite passes

#### Manual

- [x] 2.5 Staff sees and can use edit/cancel controls on others' reservations in the browse page
- [x] 2.6 Normal user sees unchanged plain-text listing, no controls
- [ ] 2.7 Stale Busy/Free badge after inline cancel confirmed acceptable (superseded by Phase 3)
