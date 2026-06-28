# Admin Env-Catalog UI (S-05) — Plan Brief

> Full plan: `context/changes/admin-env-catalog/plan.md`

## What & Why

Ship a first-class admin UI to manage the environment catalog — create, modify, and delete env
definitions — retiring the Django `/admin/` fallback. Closes PRD FR-005/006/007: admins maintain the
catalog with guardrails (a pre-save warning + change-badge on modify, a delete block while reservations
are live) so catalog edits never silently break in-flight bookings.

## Starting Point

`Environment` CRUD today happens only through Django `/admin/` (`catalog/admin.py`). The booking list,
filters, and own-reservation editing already ship (S-02/03/04). `Environment` has no timestamp and
`Reservation.environment` is `on_delete=PROTECT`. `accounts.User` extends `AbstractUser`, so `is_staff`
is available as the admin flag.

## Desired End State

A staff user gets a "Manage environments" nav link to `/manage/environments/` and can create envs (owner
selectable, default self), edit them (a two-step "Save anyway" warning lists affected active/upcoming
reservations), and delete them (blocked while active/upcoming reservations exist; otherwise env + its past
reservations are removed together). Affected reservation owners see a "definition changed" badge in *My
reservations*. `Environment` is gone from Django `/admin/`; non-staff get 403 on manage routes.

## Key Decisions Made

| Decision | Choice | Why | Source |
| --- | --- | --- | --- |
| Admin gate | `User.is_staff` | No schema change; superusers already qualify; PRD wants a wide informal admin pool | Plan |
| Change badge | Derived `env.updated_at > reservation.created_at` | No per-reservation writes / ack state; persists until reservation ends | Plan |
| Badge surface | My reservations only | Targets the owner who needs to know; one template touch | Plan |
| Delete rule | Block active/upcoming; cascade past in a txn | Honors FR-007 literally; delete stays useful after historical bookings; PROTECT is race backstop | Plan |
| Edit warning | Two-step confirm, literal affected list (owner+window, cap ~5) | True pre-save warning per FR-006; shows blast radius | Plan |
| Django admin | Unregister `EnvironmentAdmin` | Single guarded write path; retires the fallback | Plan |
| UI placement | Dedicated `/manage/environments/` page | Clean access boundary; keeps booking list uncluttered | Plan |
| Env owner | Selectable dropdown, default current admin | Full FR-005 fidelity; the catalog admin often isn't the env's real owner | Plan |

## Scope

**In scope:** `Environment.updated_at` + migration; staff-gated CRUD views/forms/templates; manage nav link;
two-step edit warning; derived change-badge in My reservations; active/upcoming delete guard with past-cascade;
unregister Django admin for Environment; tests.

**Out of scope:** S-06 admin reservation override; badge acknowledgement / env-list badge; soft-delete /
history retention; any change to booking/filter/edit-own flows.

## Architecture / Approach

Mirror the app's thin-view + `services.py` + template convention. A `staff_required` decorator (anon → login,
non-staff → 403) gates four function-based views under `/manage/environments/` (flat URL names — no
`app_name`, which would break `home`). Server-rendered form/confirm pages keep the two-step edit warning and
delete-confirm simple. Reservation-window queries (`active_or_upcoming_reservations`) live in
`reservations/services.py` and are reused by the edit-warning and delete paths.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Data model + access | `updated_at` field + migration, `staff_required`, unregister admin, reservation-window service | auto_now field needs a one-off default on existing rows |
| 2. Create + list + nav (FR-005) | Manage page, create form, staff nav link | owner dropdown over all users |
| 3. Edit + badge (FR-006) | Two-step warning, derived change-badge in My reservations | warning must list the right active/upcoming set |
| 4. Delete guard (FR-007) | Active/upcoming block + past-cascade delete | check-then-delete race (handled via txn + PROTECT) |

**Prerequisites:** F-01 + S-01 (both done). Local Postgres (`docker compose up -d`).
**Estimated effort:** ~2–3 sessions across 4 phases (small, well-bounded surface).

## Open Risks & Assumptions

- "Active/upcoming" = `during.upper > now`; past = `upper <= now`. Cascade hard-deletes past reservations
  (acceptable — no analytics/history requirement).
- Badge persists until the reservation ends (no acknowledgement) and won't appear on the shared env list.
- Editing a reservation after an env change does not clear the badge (`created_at` is `auto_now_add`).

## Success Criteria (Summary)

- A staff user can create, edit (with the warning), and delete (guarded) envs from the dedicated page.
- A reservation owner sees the "definition changed" badge after a staff edit of their env.
- `Environment` is no longer writable via Django `/admin/`; non-staff get 403 on manage routes.
