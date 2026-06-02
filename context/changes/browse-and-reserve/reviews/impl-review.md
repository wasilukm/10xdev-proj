<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Browse & Reserve (S-02)

- **Plan**: context/changes/browse-and-reserve/plan.md
- **Scope**: All 3 phases (full plan)
- **Date**: 2026-06-03
- **Verdict**: NEEDS ATTENTION (all findings resolved during triage)
- **Findings**: 0 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

Automated success criteria verified: `makemigrations --check --dry-run` reports no changes; full suite passes (50 tests) before and after triage fixes.

## Findings

### F1 — N+1: build_row_context ignores the prefetch cache

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (Performance)
- **Location**: catalog/services.py:20-25
- **Detail**: `build_row_context` re-queried `env.reservations.filter(during__overlap=window)` per env, bypassing the `Prefetch` built in `prefetch_reservations_for_list`. The Prefetch loaded a cache that was never read → 1 query per env (the exact N+1 the plan's filtered Prefetch was meant to prevent). 20-50 extra queries per dashboard load.
- **Fix**: Read the prefetch cache (`"reservations" in env._prefetched_objects_cache`) in the list path; fall back to the filtered query only for the single-env create path.
- **Decision**: FIXED

### F2 — IntegrityError else-branch swallows unexpected errors

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: reservations/views.py:50-66
- **Detail**: Code matched only `reservation_no_overlap` and routed everything else (the bounded check, FK violations, future renamed constraints) into one `else` that reported "Invalid reservation range" to the user. The plan's "Two constraints, not one" section called for branching on the constraint name and naming `reservation_during_bounded` explicitly. Unknown IntegrityErrors were masked as user input error, never logged.
- **Fix**: Added explicit `elif "reservation_during_bounded" in cause` for the generic message; `else: raise` so unknown IntegrityErrors surface as bugs instead of being masked.
- **Decision**: FIXED

### F3 — Conflict message can name an arbitrary reservation

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (Correctness)
- **Location**: reservations/views.py:52-57
- **Detail**: The "Conflicts with X" lookup used `.filter(...).first()` with no ordering; with multiple overlapping reservations Postgres returns an arbitrary row, so the named owner/window may not be the most relevant conflict.
- **Fix**: Added `.order_by("during")` before `.first()` for a deterministic, earliest-conflict message.
- **Decision**: FIXED

### F4 — Dead function _now_horizon

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: catalog/services.py:8-9
- **Detail**: `_now_horizon(now)` was never called (both real functions inline `now + timedelta(hours=24)`); Pylance flagged it as not accessed.
- **Fix**: Deleted `_now_horizon`.
- **Decision**: FIXED

### F5 — make_aware can 500 on a DST-gap local time

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (Reliability)
- **Location**: reservations/forms.py:51-52
- **Detail**: `timezone.make_aware(start, get_current_timezone())` for `Europe/Warsaw` raises on a DST gap/fold datetime (twice a year), producing a 500 rather than a form error.
- **Decision**: DEFERRED → roadmap SPIKE-01 (`timezone-calendar-edge-cases`). User wants a broader analysis of DST/leap-year/calendar corner cases before patching the single symptom.
