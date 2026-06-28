# Admin Reservation Override — Plan Brief

> Full plan: `context/changes/admin-reservation-override/plan.md`

## What & Why

Staff/superusers need to manage bookings they don't own — to free or reschedule environments held by other users. Today every mutating reservation view is hard-scoped to `owner=request.user`, so no one can touch another user's booking. This adds an admin override for **cancel and edit**, surfaced in the existing app UI.

## Starting Point

The access boundary is a single ORM filter — `get_object_or_404(Reservation, pk=pk, owner=request.user)` in `reservation_edit` and `reservation_cancel` — plus a past-block (`during.upper <= now → 404`). The env-row template already lists other users' reservations as plain text, and a reusable `_reservation_item.html` partial already provides the edit/cancel controls used on *My Reservations*.

## Desired End State

A staff/superuser browsing the environments list sees "Update duration" / "Cancel reservation" controls inline on other users' current and upcoming reservations and can act on them in place via HTMX. Normal users see the row exactly as today and still 404 on direct POSTs to others' reservations. Already-ended reservations remain off-limits to everyone.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Capability | Cancel + edit others' bookings | Frees/reschedules stuck environments; no force-book or owner-reassign | Plan |
| Surface | Inline in the env row (app HTMX UI) | Reuses the row that already shows others' bookings + the existing item partial | Plan |
| Who is an admin | `is_staff or is_superuser` | No new model state; consistent with Django auth | Plan |
| Time scope | Same as users (`during.upper > now`) | Consistent rule, minimal change | Plan |
| Audit trail | None | Keeps scope tight; no migration | Plan |

## Scope

**In scope:** relax owner-scoping in edit/cancel views for admins; inline edit/cancel controls in the env row gated on `user.is_staff`; tests.

**Out of scope:** force-booking over conflicts, owner reassignment, editing past reservations, audit trail/logging, Django admin changes, object-level (env-owner) permissions, fixing the stale Busy/Free badge after inline cancel.

## Architecture / Approach

A single predicate `is_reservation_admin(user)` gates a relaxed lookup in the two mutating views (drop the `owner` filter for admins, keep it otherwise; past-block unchanged). For the UI, both row-rendering paths (`catalog.views.environment_list` and `reservations.views._row_response`) attach per-reservation item contexts for admin viewers, and `_environment_row.html` renders the existing `_reservation_item.html` controls when `user.is_staff`. Because that partial is keyed `#reservation-<pk>` and the edit/cancel responses target it with `outerHTML`, swap semantics match the established flow for free.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Backend authz relaxation | Admins can edit/cancel any not-yet-ended reservation; non-admins unchanged | Accidentally loosening the boundary for non-admins |
| 2. Inline admin controls | Edit/cancel controls in the env row for staff, in both render paths | Missing one render path → controls absent after a booking; table-cell layout of the partial |

**Prerequisites:** none — no schema changes, no dependency on the uncommitted `admin-env-catalog` work.
**Estimated effort:** ~1-2 sessions across 2 phases.

## Open Risks & Assumptions

- Stale Busy/Free badge after an inline cancel (single-div swap doesn't re-render the row) — accepted as a known limitation.
- `_reservation_item.html` repeats the environment name; rendered inside a table cell this is slightly redundant but acceptable.
- Assumes `user.is_staff`/`is_superuser` is the desired admin definition (confirmed).

## Success Criteria (Summary)

- Staff can cancel and edit other users' not-yet-ended reservations from the browse page; normal users cannot (404 on direct POST).
- Already-ended reservations remain non-editable/cancelable for everyone.
- Full test suite green; mypy and ruff clean.
