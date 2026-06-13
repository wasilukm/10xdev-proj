<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Typing & Type-Check Gate (Q-01)

- **Plan**: context/changes/typing-and-type-check-gate/plan.md
- **Scope**: Phases 1–3 of 3 (full plan)
- **Date**: 2026-06-13
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

Success-criteria verification (this session): `uv run mypy .` green (mypy 2.1.0,
0 issues, 46 files); pre-commit hook installed and references lefthook; hook
blocks on a staged type error (exit 1, surfaced the message) and passes on a
clean tree. Criterion 2.3 (Django test suite) was not re-run — local Postgres
was down — but was green at commit f710699 and the change is non-behavioral.

## Findings

### F1 — build_row_context returns dict[str, Any], not the planned TypedDict

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: catalog/services.py:15
- **Detail**: Phase 2's contract named a TypedDict (env, is_busy: bool, current_reservation: Reservation | None, upcoming_reservations: list[Reservation]) as build_row_context's return shape. Implementation returned a plain dict[str, Any]; no TypedDict was defined. Module IS a strict island, so the def was typed — but the Any-valued dict defeated the structural typing the plan asked for, and the return crosses into reservations.views.
- **Fix**: Define a RowContext TypedDict with the four planned keys, use it as build_row_context's return type, and have call sites copy into dict[str, Any] before adding render-only keys.
  - Strength: Delivers the structural typing the plan specified; catches key typos at the cross-module boundary.
  - Tradeoff: A few lines; one spot diverges from the "context dicts are dict[str, Any]" convention.
  - Confidence: HIGH — mypy already green; adding a TypedDict over a known-shaped dict is low-risk.
  - Blind spot: Template/HTMX partial key usage not exhaustively checked.
- **Decision**: FIXED — 76f8c28

### F2 — reservations/admin.py:during_local left unannotated

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: reservations/admin.py:13
- **Detail**: Phase 2's goal was "annotate every callable in the four packages." during_local(self, obj) had no annotations and the file lacked `from __future__ import annotations`. admin.py is not a strict island, so it passed under lenient defaults — but it was the lone first-party callable the "annotate all" goal missed.
- **Fix**: Annotate during_local(self, obj: Reservation) -> str, add the future-import, and use cast(datetime, ...) for the range bounds (mirroring the services-layer pattern).
- **Decision**: FIXED — 76f8c28

### F3 — *.tests.* override misses flat accounts/tests.py & catalog/tests.py

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture (config)
- **Location**: pyproject.toml:27-29
- **Detail**: The override `*.tests.*` matched the reservations.tests package but not the flat modules accounts.tests / catalog.tests (nothing follows "tests"). Faithful to the plan's literal pattern, but those two files weren't carved out — a future typed-test error there would unexpectedly hit the gate.
- **Fix**: Add module pattern `*.tests` alongside `*.tests.*` in the ignore_errors override.
- **Decision**: FIXED — 76f8c28

### F4 — Effectively-dead defensive branches added for stub nullability

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: reservations/forms.py:45-46,88-91; reservations/services.py:55
- **Detail**: `if cleaned_data is None: return` guards and `assert custom_hours is not None` were added to narrow django-stubs' nullable return types. In practice super().clean() returns the dict and the form already blocks the custom-hours-missing path, so the branches are dead. No behavior change. The assert is stripped under `python -O`, but the form guard makes that path unreachable.
- **Fix**: Optional — replace with cast()/narrowing if you'd rather not carry dead runtime branches; otherwise leave as-is.
- **Decision**: SKIPPED — harmless typing scaffolding, no behavior change.
