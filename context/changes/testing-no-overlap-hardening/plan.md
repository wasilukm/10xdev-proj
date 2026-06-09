# No-overlap Hardening (Risk #1) Implementation Plan

## Overview

Phase 1 of the project's test rollout (`context/foundation/test-plan.md` §3, Risk #1).
Two pieces of work:

1. **Lock the no-overlap translation coupling.** Both reservation write paths
   (`reservation_create`, `reservation_edit`) translate the Postgres exclusion-constraint
   violation into a clean in-page conflict message by **string-matching the constraint
   name** (`"reservation_no_overlap" in cause`). If the constraint were ever renamed, that
   match fails and control falls to `else: raise` — an unhandled 500, i.e. exactly the
   Risk-#1 failure mode, reintroduced silently. Add tests that pin the coupling.
2. **Convert `reservations/tests.py` to the `tests/` package layout** — the first
   sub-phase of test-plan §6 (the file is the largest in the project and grows next).

## Current State Analysis

The risk's stated cause is **largely already mitigated** (see `research.md`):

- `reservation_create` (`reservations/views.py:51-85`) and `reservation_edit`
  (`reservations/views.py:105-137`) both wrap the DB write in `transaction.atomic()`,
  catch `IntegrityError`, and translate the no-overlap violation into a conflict message
  naming the other owner/window — never a silent second row, never a 500 (for the two
  known constraints).
- The one fragile seam is **translation by error-string introspection**:
  `cause = str(getattr(e, "__cause__", "") or e)` then `if "reservation_no_overlap" in cause`
  (`views.py:77`, `views.py:128`). A constraint rename in a future migration, or a psycopg
  message-text change, drops control to `else: raise` → unhandled 500.
- Existing coverage in `reservations/tests.py` (single 559-line file, 8 classes, all
  `TestCase`): model-layer overlap (`ReservationNoOverlapTest`), create-path overlap
  (`test_overlap_rejection_names_owner_and_window`, `test_overlap_rejection_is_not_500`),
  edit-path overlap (`test_overlap_conflict_names_other_owner_not_self`,
  `test_extend_own_window_no_self_conflict`).
- **Two real gaps**: (a) the create path is *accidentally* guarded against a constraint
  rename by `test_overlap_rejection_is_not_500` (`tests.py:282-291`), but the **edit path has
  no equivalent not-500 assertion** — its overlap test only asserts the named message;
  (b) nothing pins the constraint *name* itself, so a rename passes all model tests (which
  don't reference the name) while breaking the view string-match.

### Key Discoveries:

- Constraint defined at `reservations/models.py:24-31`,
  `ExclusionConstraint(name="reservation_no_overlap", …)` — the literal the views depend on.
- View string-match seam: `reservations/views.py:77` (create), `reservations/views.py:128` (edit).
- The `reservation_during_bounded` branch (`views.py:80`, `views.py:132`) shares the same
  seam but is **out of scope** (decision below) — it is unreachable from the view via real
  form input: `ReservationForm.clean()` (`forms.py:62`) and `ReservationEditForm.clean()`
  (`forms.py:90`) both reject `end <= start` and always build a concrete bounded
  `Range(start, end, "[)")`, so a bounded `IntegrityError` never surfaces to the view.
- Shared test helpers in `tests.py`: `make_range` (`tests.py:16-21`), and a near-duplicate
  pair `_dt`/`_range` (`tests.py:95-101`), plus `_FIXED_NOW` (`tests.py:92`). The conversion
  consolidates these into one `_helpers.py`.
- Test-plan §6 prescribes the split axis (**by surface**: `test_models.py`,
  `test_services.py`, `test_forms.py`, `test_views.py`) and names this conversion as the
  first sub-phase of Phase 1. The default Django runner auto-discovers `test_*.py` in a
  package; no config change.
- Concurrency (`TransactionTestCase`) is **deferred** per the recorded user decision
  (2026-06-08) — not in this plan.

## Desired End State

- `reservations/tests/` is a package: `_helpers.py` + `test_models.py`, `test_services.py`,
  `test_forms.py`, `test_views.py`. `reservations/tests.py` no longer exists.
- The full suite passes with the **same test count after conversion as before** (42 in
  `reservations`), then **44** after the two new tests land.
- A model test asserts the `reservation_no_overlap` constraint exists by that exact name —
  so a rename fails a test and points the author at the `views.py` string-match.
- An edit-path view test asserts a genuine overlap yields **status 200, not 500** (mirroring
  the create path's existing guarantee).
- Test-plan §6 references are updated to drop the "in `tests.py` until then" language, and
  §6.6 records what this phase taught.

Verify: `uv run python manage.py test reservations` is green; the run reports 44 tests;
`reservations/tests.py` is gone and `reservations/tests/` holds the five files.

## What We're NOT Doing

- **No `TransactionTestCase` / true concurrent-insert test** — deferred (user decision
  2026-06-08); a concurrent test mostly re-verifies Postgres's GiST guarantee and the
  app-layer outcome is identical to the already-tested sequential loss.
- **No bounded-constraint hardening** — out of scope (decision: no-overlap only). The
  `reservation_during_bounded` branch is form-unreachable from the view, and a behavioral
  test would require mocking the DB write to raise a synthetic error (the over-mocking
  anti-pattern). Its model-layer reach-tests (`test_empty_range_rejected`,
  `test_unbounded_range_rejected`) stay as-is.
- **No model `full_clean()`/`validate_constraints()`** — the DB-as-arbiter pattern is
  intentional; not changing it.
- **No converting `catalog`/`accounts` tests** — they convert when a phase next touches them
  (test-plan §6).
- **No production-code changes** — `models.py`, `views.py`, `forms.py`, `services.py` are
  untouched. This phase only adds/moves tests and updates the cookbook.

## Implementation Approach

Conversion first (Phase 1), then the two new coupling tests authored directly into the new
layout (Phase 2). This honors test-plan §6 ("conversion is the first sub-phase") and avoids
writing new tests into the old monolith only to move them a step later. Phase 1 is a pure
reorganization verifiable by an unchanged passing test count; Phase 2 is additive.

## Critical Implementation Details

- **Test discovery requires deleting `tests.py`.** A package `reservations/tests/` and a
  module `reservations/tests.py` cannot coexist — Python resolves one and the runner will
  silently stop discovering the other. The old file must be removed in the same phase the
  package is created.
- **Helper consolidation must not change fixture semantics.** `make_range` (used by
  `ReservationNoOverlapTest`) and `_range`/`_dt` (used by the service/view/form classes)
  produce equivalent UTC ranges but via different signatures. Keep both helper names in
  `_helpers.py` so no call site changes; only their definitions move. `_FIXED_NOW` moves
  verbatim.

## Phase 1: Convert `reservations` tests to the package layout

### Overview

Mechanically split `reservations/tests.py` into a `tests/` package, by surface, with shared
helpers extracted to `_helpers.py`. No test logic changes; the same 42 tests pass.

### Changes Required:

#### 1. Shared helpers module

**File**: `reservations/tests/_helpers.py` (new)

**Intent**: Single home for the fixtures every test file needs, eliminating the existing
`make_range` vs `_dt`/`_range` duplication. Leading underscore keeps the runner from treating
it as a test module.

**Contract**: Exports `make_range(start_hour, end_hour)`, `_dt(h, m=0, d=1)`, `_range(sh, eh)`,
and the `_FIXED_NOW` constant — moved verbatim from `tests.py:16-21`, `tests.py:92`,
`tests.py:95-101`. Same signatures and return values; no behavior change.

#### 2. Model tests

**File**: `reservations/tests/test_models.py` (new)

**Intent**: House model/constraint-layer tests.

**Contract**: Contains `ReservationNoOverlapTest` (moved from `tests.py:24-85`). Imports
`make_range` from `._helpers`. No assertion changes.

#### 3. Service tests

**File**: `reservations/tests/test_services.py` (new)

**Intent**: House service-function tests.

**Contract**: Contains `ComputeEndTest`, `NextReservationAfterTest`, `NextFreeWindowTest`
(moved from `tests.py:108-216`). Imports `_dt`, `_range` from `._helpers`.

#### 4. Form tests

**File**: `reservations/tests/test_forms.py` (new)

**Intent**: House form-layer unit tests.

**Contract**: Contains `ReservationEditFormTest` (moved from `tests.py:298-351`). Imports
`_dt` from `._helpers`.

#### 5. View tests

**File**: `reservations/tests/test_views.py` (new)

**Intent**: House integration tests for the HTMX write endpoints.

**Contract**: Contains `ReservationCreateViewTest`, `ReservationEditViewTest`,
`ReservationCancelViewTest` (moved from `tests.py:223-559`). Imports `_dt`, `_range`,
`_FIXED_NOW` from `._helpers`.

#### 6. Package init + remove old file

**File**: `reservations/tests/__init__.py` (new, empty) and delete `reservations/tests.py`

**Intent**: Make `tests/` a package; remove the monolith so discovery resolves the package.

**Contract**: Empty `__init__.py`. `reservations/tests.py` deleted (use `git mv`-style move so
history follows where practical, but a delete + new files is acceptable).

### Success Criteria:

#### Automated Verification:

- Suite passes with unchanged count: `uv run python manage.py test reservations` reports
  **42 tests, all passing** (same as before the move).
- Full suite still green: `uv run python manage.py test`.
- `reservations/tests.py` no longer exists and `reservations/tests/` contains
  `__init__.py`, `_helpers.py`, `test_models.py`, `test_services.py`, `test_forms.py`,
  `test_views.py`.

#### Manual Verification:

- Spot-check that no test was dropped or silently renamed during the move (class/method
  names match the originals).

**Implementation Note**: After completing this phase and all automated verification passes,
pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Lock the no-overlap translation coupling + update cookbook

### Overview

Add the two tests that pin the constraint-name ↔ view string-match coupling, then update
test-plan §6 to reflect the completed conversion.

### Changes Required:

#### 1. Structural constraint-name pin

**File**: `reservations/tests/test_models.py`

**Intent**: Fail loudly if the `reservation_no_overlap` constraint is renamed, because
`reservations/views.py` translates the violation by string-matching that exact name — a
rename would silently regress the create/edit paths into a 500. A clear docstring must state
this is a coupling guard, not a redundant model assertion.

**Contract**: A new test (e.g. `ReservationConstraintNameTest` or a method on the existing
class) asserting that a constraint named `"reservation_no_overlap"` is present in
`Reservation._meta.constraints`. Reads `c.name for c in Reservation._meta.constraints`; no DB
write. The docstring names `views.py:77`/`views.py:128` as the dependent code.

#### 2. Edit-path not-500 guarantee

**File**: `reservations/tests/test_views.py`

**Intent**: Close the gap research flagged (recommendation #2): the create path asserts a
genuine overlap returns 200-not-500 (`test_overlap_rejection_is_not_500`), but the edit path
only asserts the named message. Mirror the create guarantee on edit so a rename that breaks
the edit string-match (→ `else: raise` → 500) is caught.

**Contract**: A new method on `ReservationEditViewTest` (e.g.
`test_overlap_conflict_is_not_500`) that drives a real overlapping edit against an existing
sibling reservation and asserts `response.status_code == 200` (and `!= 500`). Reuse the
existing fixture/`_post` pattern from `test_overlap_conflict_names_other_owner_not_self`
(`tests/test_views.py`, formerly `tests.py:451-468`) — shorten own reservation, create a
sibling owned by `other_user`, edit into overlap.

#### 3. Cookbook §6 update

**File**: `context/foundation/test-plan.md`

**Intent**: The conversion is done, so the §6 references that say "in `tests/…` after
Phase 1's conversion; in `tests.py` until then" are now simply the `tests/` paths. Record what
this phase taught in §6.6.

**Contract**: Edit §6.1 and §6.2 *Reference test* lines and the *Test file layout* paragraph
to drop the "until then" conditional and point at `reservations/tests/test_*.py`. Add a §6.6
bullet noting the `reservations` conversion landed, the `_helpers.py` consolidation pattern,
and the constraint-name-pin coupling-guard pattern (so future phases reuse it). Do not alter
§1–§5 (frozen strategy).

### Success Criteria:

#### Automated Verification:

- New tests present and passing: `uv run python manage.py test reservations` reports
  **44 tests, all passing**.
- The constraint-name pin actually guards: a temporary local rename of the constraint in
  `models.py` makes `test_models.py` fail (verify once, then revert — do not commit the
  rename).
- Full suite green: `uv run python manage.py test`.

#### Manual Verification:

- Read the new test docstrings: the constraint-name pin clearly explains it guards the
  `views.py` string-match (not a redundant model check).
- Test-plan §6 reads correctly with no dangling "until then" references; §6.6 note is
  accurate; §1–§5 unchanged.

**Implementation Note**: After completing this phase and all automated verification passes,
pause for manual confirmation. This completes Phase 1 of the test rollout — mark test-plan §3
row 1 `complete`.

---

## Testing Strategy

### Unit Tests:

- Constraint-name pin (`test_models.py`) — structural assertion on
  `Reservation._meta.constraints`, no DB write.

### Integration Tests:

- Edit-path overlap → 200-not-500 (`test_views.py`) — real Postgres, real view, asserts
  observable HTTP status (no mocking of the DB write).

### Manual Testing Steps:

1. Run `uv run python manage.py test reservations` and confirm 44 tests pass.
2. Temporarily rename `reservation_no_overlap` in `models.py`; confirm `test_models.py`
   fails; revert.
3. Read the two new test docstrings for clarity on intent.

## Migration Notes

No schema or data changes. Production code (`models.py`, `views.py`, `forms.py`,
`services.py`) is untouched — no `makemigrations` needed.

## References

- Research: `context/changes/testing-no-overlap-hardening/research.md`
- Test plan: `context/foundation/test-plan.md` (§2 Risk #1, §3 Phase 1, §6 cookbook)
- Constraint: `reservations/models.py:24-31`
- View string-match seam: `reservations/views.py:77` (create), `reservations/views.py:128` (edit)
- Existing create not-500 reference: `reservations/tests.py:282-291`
- Existing edit overlap reference: `reservations/tests.py:451-468`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Convert `reservations` tests to the package layout

#### Automated

- [x] 1.1 Suite passes with unchanged count (42 tests): `uv run python manage.py test reservations` — 5fcb337
- [x] 1.2 Full suite still green: `uv run python manage.py test` — 5fcb337
- [x] 1.3 `reservations/tests.py` removed; `reservations/tests/` holds `__init__.py`, `_helpers.py`, `test_models.py`, `test_services.py`, `test_forms.py`, `test_views.py` — 5fcb337

#### Manual

- [x] 1.4 Spot-check no test was dropped or silently renamed (class/method names match originals) — 5abcbfd

### Phase 2: Lock the no-overlap translation coupling + update cookbook

#### Automated

- [x] 2.1 New tests present and passing (44 tests): `uv run python manage.py test reservations`
- [x] 2.2 Constraint-name pin guards: a temporary local rename makes `test_models.py` fail (revert, do not commit)
- [x] 2.3 Full suite green: `uv run python manage.py test`

#### Manual

- [x] 2.4 New test docstrings clearly explain the coupling guard and the edit not-500 intent
- [x] 2.5 Test-plan §6 has no dangling "until then" references; §6.6 note accurate; §1–§5 unchanged
