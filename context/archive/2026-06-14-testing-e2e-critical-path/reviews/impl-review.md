<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Critical-path E2E Harness

- **Plan**: context/changes/testing-e2e-critical-path/plan.md
- **Scope**: Phases 1–2 of 2
- **Date**: 2026-06-16
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

All automated criteria re-verified green: 3 e2e tests pass on two consecutive runs,
`ruff check tests/` clean, no `wait_for_timeout` in the e2e tree, existing 89-test
unittest suite still OK (earlier failure was just unset env vars — the standing project
requirement — not a regression), test DB created and dropped cleanly. Manual items
1.6/1.7/2.7/2.8 honestly left unchecked in Progress — pending, not rubber-stamped.

## Findings

### F1 — Unplanned pytest-env dependency + env config block

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: pyproject.toml:20, 70-79
- **Detail**: Phase 1's contract listed only `pytest-playwright` + `pytest-django` as deps, and the pytest config contract listed only DJANGO_SETTINGS_MODULE / testpaths / python_files / marker. The implementation also added `pytest-env` and a 4-key `env = [...]` block (DJANGO_SECRET_KEY, DATABASE_URL, PLAYWRIGHT_HOST_PLATFORM_OVERRIDE, DJANGO_ALLOW_ASYNC_UNSAFE). Genuinely necessary scope discovered at implementation time (Ubuntu 26.04 / Playwright 1.60 ABI; Django async guard) and documented in test-plan §6.3/§6.6.
- **Fix**: Accept; optionally note in the plan as an addendum that pytest-env + the env block were added to make the harness runnable without manual secret export.
- **Decision**: ACCEPTED — plan addendum added (plan.md Phase 1 config contract).

### F2 — DJANGO_ALLOW_ASYNC_UNSAFE applied suite-wide

- **Severity**: ◽ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: pyproject.toml:78
- **Detail**: The flag disables Django's sync-from-async guard for the entire pytest session (incl. test_db_sanity.py), not just Playwright tests. Acceptable because testpaths is scoped to tests/e2e and the guard fires falsely under Playwright's loop, but a future non-Playwright pytest test would inherit the relaxed guard.
- **Fix**: Leave as-is; if pure-ORM pytest tests are later added outside tests/e2e, scope the flag to the e2e tests instead.
- **Decision**: ACCEPTED as-is (revisit if pytest scope widens beyond tests/e2e).

### F3 — _dt/_range duplicated instead of reusing _helpers.py

- **Severity**: ◽ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/e2e/conftest.py:17-22
- **Detail**: Plan contract said "reusing the _range()/_dt()/_FIXED_NOW idiom from reservations/tests/_helpers.py". The implementation re-defines _dt/_range locally with a different signature and doesn't reference _FIXED_NOW. The pattern is reused but not the code — fair, since cross-package import into tests/e2e is awkward.
- **Fix**: Accept the local copy; optionally add a comment pointing at _helpers.py as the idiom's origin.
- **Decision**: FIXED — origin/sync comment added above _dt in conftest.py.

### F4 — Redundant django_db marker + transactional_db param

- **Severity**: ◽ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/e2e/test_smoke.py:13-15, 22-23
- **Detail**: Each test both decorates @pytest.mark.django_db(transaction=True) and takes `transactional_db` as a param (and the fixtures already pull transactional_db). All three request the same behavior; one is redundant. Plan contract specified the param form, so the decorator is the extra.
- **Fix**: Drop the @pytest.mark.django_db(transaction=True) decorator and keep the `transactional_db` param to match the plan's stated signature.
- **Decision**: FIXED — decorators removed from both tests (and the now-unused `import pytest`); ruff clean, smoke test still green.
