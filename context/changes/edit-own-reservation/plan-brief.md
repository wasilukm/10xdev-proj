# Edit Own Reservation (S-04) — Plan Brief

> Full plan: `context/changes/edit-own-reservation/plan.md`

## What & Why

Signed-in users can currently create reservations but cannot change or cancel them — a basic gap (PRD FR-012/FR-013). This slice lets a user modify the **duration/end** of their own reservation and **cancel** it, with the same no-overlap rejection as creation (FR-015) and no ability to touch others' reservations.

## Starting Point

S-02 (`browse-and-reserve`) shipped reservation creation via an HTMX row-swap: `ReservationForm` + `compute_end`/overlap services + an `IntegrityError`-decoding view that names the conflicting owner. There is no edit/cancel path, no per-row ownership gating, and the env list only shows each env's current + next-24h reservations — so a user's later reservations are unreachable today.

## Desired End State

A new **"My reservations"** page (`/reservations/mine/`) lists the user's active + upcoming reservations. Each has an inline edit form — a single hours field prefilled with the current duration (start shown read-only, never changes) — and a cancel button guarded by a native confirm prompt. Edits re-render the row in place; overlaps re-render with a named conflict and leave the original window intact. Non-owners get 404; past reservations are locked.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Surface for controls | New "My reservations" page | Env list only shows a 24h window, so later reservations need their own reachable surface | Plan |
| Cancel data model | Hard delete | Simplest; matches PRD Non-Goals (no audit/notifications) and frees the slot immediately | Plan |
| What's editable | Future + in-progress | More forgiving for the "I'm done early / need longer" case | Plan |
| Cancel friction | Native `hx-confirm` prompt | One-line guard against accidental data loss, consistent with existing HTMX flow | Plan |
| Edit semantics | Duration/end only; start immutable | User-confirmed: the elapsed/booked start can't move — wrong start ⇒ cancel + rebook | Plan |
| Edit input | Single raw hours field (no presets/`until_next`) | User-confirmed: preset-vs-custom distinction makes the edit UI needlessly complex | Plan |
| In-progress edit | Lock start, move end only (`end > now`) | Honest model — time already spent can't be rewritten | Plan |
| Auth failure | 404 (owner-scoped lookup) | Never reveals another user's reservation exists | Plan |

## Scope

**In scope:** "My reservations" page; edit duration (future + in-progress); cancel (hard delete + confirm); owner-scoped 404; overlap rejection with self-exclusion; nav link; tests.

**Out of scope:** changing start/environment; admin override (S-06); soft-delete/audit/undo/notifications; inline controls on the env list; DST/calendar hardening (SPIKE-01).

## Architecture / Approach

Bottom-up reuse of the S-02 machinery. Phase 1 adds a minimal hours-based `ReservationEditForm` (start fixed, `end = start + hours`); the ordering services are untouched. Phase 2 adds three owner-scoped views (`my_reservations`, `reservation_edit`, `reservation_cancel`), routes, the page + an HTMX `_reservation_item.html` partial, and a nav link; the `IntegrityError`→named-conflict logic is factored into a shared helper (with `.exclude(pk=...)` self-exclusion) used by both create and edit. Phase 3 adds view/integration tests.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Edit form foundation | Hours-based `ReservationEditForm` | Edit validation must reject an end `<= now` (disguised cancel) |
| 2. Views, URLs, templates, nav | Working "My reservations" page with edit/cancel | The conflict query must `.exclude(pk=...)`; time-gating (`during.upper > now`) enforced server-side, not just hidden |
| 3. Tests & manual QA | View/integration tests + manual pass | Forgetting the self-overlap false-positive / extend-own-window test (the subtle bug) |

**Prerequisites:** S-02 (`browse-and-reserve`) done — it is. Local Postgres running for tests.
**Estimated effort:** ~2–3 sessions across 3 phases.

## Open Risks & Assumptions

- **Self-exclusion** is needed at exactly one site — the edit view's conflict-report query (`.exclude(pk=...)`); the plan's tests target this (the "extend own window" case) explicitly.
- The edit form is a single raw hours value (`during.upper - during.lower`), prefilled with the current duration; the original preset/`until_next` choice isn't reconstructed (and isn't stored anyway) — a deliberate UI simplification.
- "My reservations" page intentionally lists only active/upcoming; ended reservations are not shown as actionable.

## Success Criteria (Summary)

- A user can shorten/extend/cancel their own future or in-progress reservation from "My reservations" without a full reload.
- Editing into someone else's window is rejected with a named conflict; the original reservation is unchanged.
- A user cannot edit or cancel a reservation they don't own (404).
