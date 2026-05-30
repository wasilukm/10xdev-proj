<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Env + Reservation Data Model (F-01)

- **Plan**: context/changes/env-and-reservation-data-model/plan.md
- **Scope**: All 4 phases (full plan)
- **Date**: 2026-05-30
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 2 observations (all fixed during triage)

> Note: `accounts` reviewed at its F-01 commit (f6367b0); `catalog`/`reservations` reviewed at HEAD (unchanged since F-01). A later change (org-restricted-auth) rewrote `accounts/models.py` and the test user-creation calls afterward — not F-01 drift.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING (F1 — fixed) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS (check + migrate clean, 25 tests pass) |

## Findings

### F1 — Exclusion constraint doesn't block empty/unbounded ranges

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: reservations/models.py:18-30
- **Detail**: The GiST `&&` exclusion constraint enforces no-overlap for normal windows, but Postgres treats an `empty` range as overlapping nothing, and unbounded ranges (`[x,)`, `(,y]`) slip through too. A caller could persist a zero-duration `[x,x)` or open-ended reservation that bypasses overlap protection. Half-open `[start,end)` semantics lived only in caller/test code, not as a model-level guarantee. Consistent with the plan (create-path validation deferred to S-02) — not drift, but a latent data-safety gap.
- **Fix**: Added `CheckConstraint("reservation_during_bounded")` on `Reservation.Meta` enforcing `during__isempty=False, during__lower_inf=False, during__upper_inf=False`. New migration `0002_reservation_reservation_during_bounded`. Two regression tests added (`test_empty_range_rejected`, `test_unbounded_range_rejected`).
  - Strength: Closes the gap at the same DB layer as the no-overlap guarantee; survives any future caller including S-02 before its own validation exists.
  - Tradeoff: A few lines + one migration now.
  - Confidence: HIGH — verified: migration applies on PG17, all 25 tests pass.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix now

### F2 — DATABASE_URL default silently falls back to SQLite

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture (Reliability)
- **Location**: envbooker/settings.py:99-103
- **Detail**: `dj_database_url.config(default="sqlite:///…")` meant an unset `DATABASE_URL` silently used SQLite, where `btree_gist` / `ExclusionConstraint` / `contrib.postgres` cannot exist — `migrate` then failed with a confusing low-level error.
- **Fix**: Dropped the SQLite default; raise `ImproperlyConfigured` when `DATABASE_URL` is unset or the engine is not PostgreSQL. Verified the clear error fires when `DATABASE_URL` is unset.
- **Decision**: FIXED via Fix now

### F3 — Stale Django version in settings.py header

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: envbooker/settings.py:4-10
- **Detail**: Header comment / docs links referenced "Django 5.2.9" and `/en/5.2/` while the project runs Django 6.0.5.
- **Fix**: Updated the header docstring version note and docs URLs to `/en/6.0/`.
- **Decision**: FIXED via Fix now
