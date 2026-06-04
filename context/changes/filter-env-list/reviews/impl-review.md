<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Filter Env List

- **Plan**: context/changes/filter-env-list/plan.md
- **Scope**: Phase 1 & 2 of 2 (full plan)
- **Date**: 2026-06-04
- **Verdict**: APPROVED
- **Findings**: 0 critical, 0 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Notes

- Test suite: 26 passed (`uv run python manage.py test catalog`, DJANGO_DEBUG=True).
- Single-`now` consistency, `@login_required`, `select_related`/prefetch reuse, and the read-only nature were all verified — genuine strengths.
- Unknown/blank filter params are silently treated as "no filter" — this is per-spec ("Critical Implementation Details"), not a defect.

## Findings

### F1 — No test pins the self-replacing swap contract (id="env-results")

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency / Success Criteria
- **Location**: templates/catalog/_environment_results.html:1; catalog/tests.py (FilterUITest)
- **Detail**: The filter form swaps `#env-results` with `hx-swap="outerHTML"`, and the partial's root re-emits `id="env-results"`, making the swap self-replacing. Correct today, but no test asserts the htmx partial response contains `id="env-results"`. If a future edit drops the wrapper id, the first swap still works but every subsequent swap silently breaks.
- **Fix**: In the existing HX-Request partial test, add an assertion that the response body contains `id="env-results"`.
- **Decision**: FIXED (assertion added to test_htmx_request_returns_partial_only)

### F2 — Function-local import in filter_options breaks module convention

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: catalog/services.py:57
- **Detail**: `filter_options()` imports `Environment` inside the function body, while sibling code imports `Reservation` at module top (services.py:5) and views.py already imports `Environment` at module level — no circular-import reason for the local import. Harmless but inconsistent.
- **Fix**: Hoist `from .models import Environment` to the module top.
- **Decision**: FIXED (import hoisted to module top)
