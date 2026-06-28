<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Admin Env-Catalog UI (S-05)

- **Plan**: context/changes/admin-env-catalog/plan.md
- **Scope**: Phases 1–4 of 4 (full plan)
- **Date**: 2026-06-28
- **Verdict**: REJECTED
- **Findings**: 1 critical 2 warnings 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | FAIL |

Re-verified this run: `makemigrations --check` clean, `ruff check`/`format` clean, `mypy` clean (57 files). BUT `manage.py test catalog reservations` FAILS — the uncommitted backfill migration 0003 crashes test-DB creation (see F1).

## Findings

### F1 — Backfill migration 0003 crashes on any fresh database

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: catalog/migrations/0003_backfill_environment_updated_at.py:16
- **Detail**: 0003 (the uncommitted fix the prior review added for its own F1) annotates `Min("reservations__created_at")` — a cross-app reverse relation into the reservations app — but declares only `dependencies = [("catalog", "0002_environment_updated_at")]`. It never depends on a reservations migration. On a fresh build the migration executor can run catalog/0003 before the Reservation FK exists in the historical project state, so the reverse accessor is unknown: `FieldError: Cannot resolve keyword 'reservations' into field`. This breaks `create_test_db` (entire suite cannot run) and a fresh `migrate` on CI/prod would fail identically. It passed the prior review's "migrate clean" check only because that ran against an already-migrated dev DB (single-pending-node state masks the missing dependency). The prior review reported "93 tests pass" but did not re-run tests after creating 0003.
- **Fix**: Add the reservations FK migration to the dependency list: `dependencies = [("catalog", "0002_environment_updated_at"), ("reservations", "0001_initial")]`.
  - Strength: Standard Django remedy for data migrations reading a sibling app's model; deterministic ordering; restores a buildable test DB.
  - Tradeoff: None of substance — only constrains ordering.
  - Confidence: HIGH — exact match for the FieldError reproduced on a clean test DB.
  - Blind spot: Whether 0003 should be committed at all vs. accepting spurious badges (original F1 tradeoff). Crash must be fixed regardless; if 0003 is dropped, the plan's Migration Notes still need correcting.
- **Decision**: FIXED via Fix now — added `("reservations", "0001_initial")` to dependencies; fresh-DB `test catalog reservations` now green (93 tests OK).

### F2 — "+N more" count is capped at 1 regardless of true overflow

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: catalog/views.py:124
- **Detail**: Edit warning fetches `affected[: _AFFECTED_PREVIEW + 1]` (≤6) and computes `more = len(preview) - _AFFECTED_PREVIEW`, so `more` can never exceed 1. With 20 affected reservations it shows "+1 more" instead of "+15 more". Plan said "first ~5 + '+N more'". No test covers >6 affected. Carried PENDING from the prior review.
- **Fix**: Compute the remainder from a real count: `affected_more = max(active_or_upcoming_reservations(env).count() - _AFFECTED_PREVIEW, 0)`, keep slicing preview to 5.
- **Decision**: FIXED via Fix now — catalog/views.py now slices preview to 5 and derives `more` from `affected.count()`; ruff/mypy clean, edit/delete view tests green.

### F3 — reservations/admin.py modified despite "stay untouched" guardrail

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: reservations/admin.py:18
- **Detail**: "What We're NOT Doing" says Reservation/User/AllowedEmailDomain admin registrations "stay untouched", but retiring EnvironmentAdmin forces ReservationAdmin.autocomplete_fields to drop "environment" (else admin.E039 fires). The change is correct and necessary; the plan didn't foresee the coupling. Carried PENDING from the prior review.
- **Fix**: No code change — record a plan addendum so the guardrail matches the discovered, mandatory scope.
- **Decision**: SKIPPED — code change is already correct and committed; user opted not to amend the plan.
