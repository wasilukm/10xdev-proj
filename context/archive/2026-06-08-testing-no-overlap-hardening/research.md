---
date: 2026-06-08T23:40:57+02:00
researcher: Mariusz Wasiluk
git_commit: 25bf1917f32396ed72e7666b34dec33039da1f22
branch: main
repository: 10xdev-proj
topic: "Phase 1 — No-overlap hardening (Risk #1): create/edit write paths, constraint-violation translation, concurrency-test feasibility"
tags: [research, codebase, reservations, no-overlap, exclusion-constraint, integrityerror]
status: complete
last_updated: 2026-06-08
last_updated_by: Mariusz Wasiluk
---

# Research: Phase 1 — No-overlap hardening (Risk #1)

**Date**: 2026-06-08T23:40:57+02:00
**Researcher**: Mariusz Wasiluk
**Git Commit**: 25bf1917f32396ed72e7666b34dec33039da1f22
**Branch**: main
**Repository**: 10xdev-proj

## Research Question

Ground Risk #1 from `context/foundation/test-plan.md` against current code, per the
§2 Risk Response Guidance brief: the create and edit write entry points; how the
Postgres exclusion-constraint violation surfaces (IntegrityError) and where it is
translated to a form/user error; and whether a true concurrent test
(`TransactionTestCase`) is warranted vs. simulating the integrity error.

Risk #1 (verbatim): *"Two reservations overlap on the same environment under
concurrent requests — the exact collision the product exists to prevent — because
the app layer does not cleanly translate the database exclusion-constraint violation
into a rejection."*

## Summary

The risk's stated cause is **largely already mitigated**. Both write paths
(`reservation_create`, `reservation_edit`) wrap the DB write in
`transaction.atomic()` and catch `IntegrityError`, translating the no-overlap
violation into an in-page conflict message that names the other owner and window —
never a silent second row, and (for the two known constraints) never a 500. This is
covered by existing tests at both the model layer (`ReservationNoOverlapTest`) and
the view layer (overlap-names-owner, not-500, edit-conflict-names-other-not-self,
extend-without-self-conflict).

Two genuine residual surfaces remain:

1. **Brittle translation coupling (the real Risk-#1 surface today).** The
   create/edit handlers decide "is this an overlap?" by **string-matching the
   constraint name** in `str(e.__cause__)`: `"reservation_no_overlap" in cause`. If
   the constraint were ever renamed in a migration, or psycopg changed its error
   text, the match fails and control falls to `else: raise` — an **unhandled 500**,
   i.e. exactly the Risk-#1 failure mode, reintroduced silently. No test locks the
   constraint-name ↔ message coupling. (Echoes `lessons.md`: verify a named
   mechanism actually exists and is matched, rather than assuming it.)

2. **Untested true-concurrent race.** All existing overlap tests are sequential
   under `TestCase`. No `TransactionTestCase` exists anywhere in the repo; there is
   no threading/connection-level concurrency test. **Decision (user, 2026-06-08):
   defer.** A concurrent test would chiefly re-verify Postgres's own GiST guarantee,
   and the app-layer outcome under a concurrent loss is identical to the
   already-tested sequential loss (the loser's INSERT raises `IntegrityError`, caught
   and rolled back by the `transaction.atomic()` wrapper). Cost × signal does not
   justify the `TransactionTestCase` + threading + separate-connection + barrier
   infrastructure for Phase 1. Recorded as deferred negative-space, revisitable if
   the constraint or write path changes shape.

**Cheapest layer with real signal for Phase 1:** integration/view tests on the
translation coupling, plus the mechanical cookbook conversion of
`reservations/tests.py` into the `tests/` package. No e2e, no concurrency infra.

## Detailed Findings

### Create write path

- View `reservation_create` — `reservations/views.py:51-85`. Decorated
  `@login_required` + `@require_POST`; route `reservations/create/`
  (`reservations/urls.py:8`, mounted at `envbooker/urls.py:23`). HTMX-style: re-renders
  the row partial `catalog/_environment_row.html`.
- Form `ReservationForm` (plain `forms.Form`) — `reservations/forms.py:20-66`. Fields:
  hidden `environment`, `start` (`datetime-local`), `duration` choice, optional
  `custom_hours`. Local→aware conversion at `forms.py:53-55`
  (`timezone.make_aware(start, get_current_timezone())`). End computed via
  `services.compute_end(...)`; range built half-open at `forms.py:65`:
  `cleaned_data["during"] = Range(start, end, "[)")`.
- Persistence — `reservations/views.py:68-74`, `Reservation.objects.create(...)`
  inside `with transaction.atomic():`. Owner forced to `request.user`. **No
  `full_clean()` / `validate_constraints()`**, and **no Python-level overlap
  pre-check** — the DB GiST constraint is the sole enforcement.
- Translation — `reservations/views.py:75-83`:
  `cause = str(getattr(e, "__cause__", "") or e)`;
  `if "reservation_no_overlap" in cause:` → `services.describe_overlap_conflict(env, during)`
  + `services.next_free_window(env, start)`; `elif "reservation_during_bounded" in cause:`
  → static range-invalid message; `else: raise`.

### Edit write path

- View `reservation_edit` — `reservations/views.py:105-137`. Route
  `reservations/<int:pk>/edit/` (`reservations/urls.py:10`), `@login_required` +
  `@require_POST`. **Ownership via queryset filter**:
  `get_object_or_404(Reservation, pk=pk, owner=request.user)` (`views.py:108`) → a
  non-owner gets **404** (not 403). Already-ended reservations are non-editable:
  `if reservation.during.upper <= now: raise Http404` (`views.py:110-111`).
- Form `ReservationEditForm` — `reservations/forms.py:69-99`. **Start is immutable**
  (passed in via `__init__(start=...)`, stored on `self._start`); only `hours` moves
  the end. View instantiates with `start=reservation.during.lower` (`views.py:113`).
  Range rebuilt at `forms.py:98`: `Range(self._start, end, "[)")`.
- Translation — `reservations/views.py:121-135`: **same** `transaction.atomic()` +
  `IntegrityError` + constraint-name-string-match shape as create. On conflict it
  restores `reservation.during = original_during` (`views.py:126`) and builds the
  message with **self-exclusion**:
  `describe_overlap_conflict(env, during, exclude_pk=reservation.pk)`
  (`views.py:129-131`; `.exclude(pk=...)` at `services.py:62-63`) so the message
  never names the user's own row. Self-row overlap is a non-issue because the
  UPDATE replaces the row's own range in place.

### Model-layer constraint

- `reservations/models.py:8-44`. `during = DateTimeRangeField()` (`models.py:19`).
  `ExclusionConstraint(name="reservation_no_overlap", expressions=[("environment",
  EQUAL), ("during", OVERLAPS)], index_type="GIST")` (`models.py:24-31`) — scoped
  **per environment** (`=` on the FK, `&&` on the range); requires `btree_gist`.
  Second constraint `reservation_during_bounded` (`CheckConstraint`,
  `models.py:32-39`) rejects empty/unbounded ranges. **No model `clean()` /
  `validate_constraints()` override** — all enforcement is at the DB layer, surfaced
  as `IntegrityError`, translated in the views.

### Existing overlap coverage (the baseline to build on)

In `reservations/tests.py` (single 559-line file; all classes use `TestCase`, **no
`TransactionTestCase`**):

- Model layer — `ReservationNoOverlapTest` (`tests.py:24-105`):
  `test_overlap_rejected` (`42-47`, `assertRaises(IntegrityError)` in
  `transaction.atomic()`), `test_back_to_back_allowed` (`49-53`, asserts count==2),
  `test_cross_env_allowed` (`55-59`, count==2), `test_contained_window_rejected`
  (`61-66`), plus `reservation_during_bounded` cases (`68-85`).
- View layer — `ReservationCreateViewTest.test_overlap_rejection_names_owner_and_window`
  (`tests.py:269-280`, status 200, count stays 1, owner name in HTML),
  `test_overlap_rejection_is_not_500` (`282-291`);
  `ReservationEditViewTest.test_overlap_conflict_names_other_owner_not_self`
  (`451-468`, names Bob, not self, original window intact after rollback),
  `test_extend_own_window_no_self_conflict` (`470-478`).

All assert **observable side effects** (raised error, row count, HTTP status,
owner-name presence/absence) — none mirror the production overlap query, so the
oracle-problem anti-pattern the test plan warns about is already avoided.

### Concurrency-test feasibility

- Runner: plain Django `manage.py test` unittest runner; **no pytest** (no
  `pytest.ini`/conftest; `pyproject.toml:1-14` has no pytest config). Postgres is
  mandatory — `ImproperlyConfigured` guards at `envbooker/settings.py:104-113`.
- **Zero `TransactionTestCase`** repo-wide; zero threading / `select_for_update` /
  raw-connection usage in tests. `transaction.atomic()` appears only to isolate
  expected `IntegrityError`s (`tests.py:46,65,71,82`) and in the views.
- A true concurrent test would require `TransactionTestCase` + `threading` +
  per-thread DB connections + a `Barrier` to align INSERTs — net-new infra that
  mostly exercises Postgres's GiST guarantee, not app code. **Deferred** per the
  cost × signal decision above.

## Code References

- `reservations/views.py:51-85` — `reservation_create`; constraint translation at `75-83`
- `reservations/views.py:105-137` — `reservation_edit`; ownership 404 at `108`, translation at `125-135`, self-exclusion message at `129-131`
- `reservations/models.py:24-31` — `reservation_no_overlap` ExclusionConstraint (per-environment GiST)
- `reservations/models.py:32-39` — `reservation_during_bounded` CheckConstraint
- `reservations/forms.py:53-55` — local→aware conversion; `forms.py:65` / `forms.py:98` — `Range(..., "[)")`
- `reservations/services.py:54-71` — `describe_overlap_conflict` (`.exclude(pk=...)` at `62-63`); `74-94` — `next_free_window`
- `reservations/tests.py:24-105` — model overlap tests; `269-291` / `451-478` — view overlap tests
- `envbooker/settings.py:104-113` — Postgres-mandatory guard

## Architecture Insights

- **DB-as-arbiter** pattern: no app-level overlap pre-check; the GiST exclusion
  constraint is the single source of truth, made request-safe by the
  `transaction.atomic()` wrapper that rolls back the failed INSERT.
- **Translation by error-string introspection** is the one fragile seam: behavior
  is correct today but coupled to the literal constraint names
  (`reservation_no_overlap`, `reservation_during_bounded`) appearing in
  `e.__cause__`. This is the highest-signal, lowest-cost place for Phase 1 to add a
  regression test.
- Create and edit share the same translation shape, differing only in
  `objects.create` vs `save(update_fields=["during"])` and the message's
  `exclude_pk` — a test for one informs the other.

## Recommended Phase 1 test surface (for `/10x-plan`)

1. **Lock the constraint-name ↔ message coupling.** An integration/view test that a
   genuine overlap on create *and* on edit yields status 200 + the named-conflict
   message + no extra row — explicitly guarding that a future constraint rename or
   psycopg message change cannot regress into the `else: raise` 500. (The single
   highest-signal addition.)
2. **Confirm/extend edit-path parity** with create (the edit conflict test exists;
   ensure the not-500 guarantee is asserted on the edit path too, mirroring
   `test_overlap_rejection_is_not_500`).
3. **Cookbook package conversion (first sub-phase, per test-plan §6).** Move
   `reservations/tests.py` (559 lines, 8 classes) into `reservations/tests/`
   split by surface: `test_models.py` ← `ReservationNoOverlapTest`;
   `test_services.py` ← `ComputeEndTest`, `NextReservationAfterTest`,
   `NextFreeWindowTest`; `test_forms.py` ← `ReservationEditFormTest`;
   `test_views.py` ← `ReservationCreateViewTest`, `ReservationEditViewTest`,
   `ReservationCancelViewTest`. Mechanical move; default runner auto-discovers
   `test_*.py`; no config change.

## Negative space (deferred for Phase 1)

- **True concurrent-insert test** — deferred (user decision 2026-06-08). Re-evaluate
  only if the write path stops relying on the DB constraint or the constraint is
  re-scoped.
- **Model `full_clean()`/`validate_constraints()`** — not used and not proposed; the
  DB-as-arbiter pattern is intentional.

## Historical Context (from prior changes)

- `context/archive/2026-05-28-env-and-reservation-data-model/` — established the
  `Reservation` model, `DateTimeRangeField`, and the `reservation_no_overlap`
  exclusion constraint (DB-only enforcement decision).
- `context/archive/2026-05-31-browse-and-reserve/` — built `reservation_create` and
  the HTMX row-partial flow + the IntegrityError translation.
- `context/archive/2026-06-04-edit-own-reservation/` — built `reservation_edit`,
  ownership-404, immutable-start edit form, and the `exclude_pk` self-exclusion
  message.

## Related Research

- None prior under `context/changes/**/research.md`. This is the first research
  artifact for the testing rollout.

## Open Questions

- None blocking. The constraint-name coupling test and the package conversion are
  ready to hand to `/10x-plan`.
