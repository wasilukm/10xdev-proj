# No-overlap Hardening (Risk #1) — Plan Brief

> Full plan: `context/changes/testing-no-overlap-hardening/plan.md`
> Research: `context/changes/testing-no-overlap-hardening/research.md`

## What & Why

Phase 1 of the project's test rollout, covering Risk #1: *two reservations overlap on the
same environment because the app layer fails to cleanly translate the DB exclusion-constraint
violation into a rejection.* The violation **is** translated cleanly today — but by
string-matching the constraint name in the error text, a fragile seam where a future rename
silently regresses into an unhandled 500. This phase pins that coupling with tests and, as the
test-plan §6 first sub-phase, converts `reservations/tests.py` into the `tests/` package layout.

## Starting Point

Both write paths (`reservation_create`, `reservation_edit`) already catch `IntegrityError`
inside `transaction.atomic()` and render a named-conflict message — never a 500, never a silent
second row. Existing tests cover the model and most of the view layer in a single 559-line
`reservations/tests.py` (42 tests, 8 classes).

## Desired End State

`reservations/tests/` is a by-surface package (`_helpers.py` + `test_models/services/forms/views.py`)
with 44 passing tests. A model test fails if the `reservation_no_overlap` constraint is renamed
(pointing the author at the `views.py` string-match), and the edit path now asserts a genuine
overlap returns 200-not-500 — matching the guarantee the create path already had.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Concurrency test | Deferred | A `TransactionTestCase` mostly re-verifies Postgres's GiST guarantee; app outcome equals the tested sequential loss. | Research |
| Coupling lock strength | Behavioral + structural pin | Edit not-500 test fills the flagged gap; the name-pin fails loudly on a rename before it ships a 500. | Plan |
| Shared helpers | One `_helpers.py` module | Single source of truth; removes the existing `make_range` vs `_range` duplication. | Plan |
| Bounded-constraint branch | Out of scope | It is form-unreachable from the view; a test would need to mock the DB write (over-mocking anti-pattern). | Plan |
| Phase order | Convert first, then add tests | Test-plan §6 names conversion as the first sub-phase; avoids writing new tests into the soon-moved monolith. | Plan |

## Scope

**In scope:** package conversion of `reservations` tests; `_helpers.py` extraction;
constraint-name pin test; edit-path not-500 test; test-plan §6 cookbook update.

**Out of scope:** any production-code change; `TransactionTestCase`/concurrency;
bounded-constraint hardening; converting `catalog`/`accounts` tests; model `full_clean()`.

## Architecture / Approach

Two additive phases, no production code touched. Phase 1 is a pure reorganization verified by
an unchanged passing test count (42 → 42). Phase 2 authors two new tests directly into the new
layout (42 → 44) and updates the cookbook. The constraint-name pin is the load-bearing new
idea: it converts an invisible string-coupling into a test that breaks on rename.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Convert tests to package | `reservations/tests/` package, 42 tests still pass | A dropped/renamed test during the move (mitigated: count + name spot-check) |
| 2. Lock coupling + cookbook | Constraint-name pin + edit not-500 test (44 tests); §6 updated | Name-pin reads as a redundant model check (mitigated: docstring + rename-verify step) |

**Prerequisites:** local Postgres running (`docker compose up -d`); the three env vars set;
existing suite green.
**Estimated effort:** ~1 session, 2 phases.

## Open Risks & Assumptions

- Assumes the constraint name remains the chosen coupling key (rather than refactoring the
  view to a non-string-based detection) — this plan hardens the current design, not redesigns it.
- The `tests.py`-must-be-deleted-for-package-discovery step is easy to forget; called out in
  Critical Implementation Details.

## Success Criteria (Summary)

- `uv run python manage.py test reservations` reports 44 passing tests; full suite green.
- A local rename of `reservation_no_overlap` fails a test (verified once, reverted).
- `reservations/tests.py` is gone; the `tests/` package holds the five files; test-plan §6 has
  no dangling "until then" references.
