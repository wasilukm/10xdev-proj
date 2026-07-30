---
title: "EnvBooker — Invariant & Aggregate Refactor Plan"
created: 2026-07-30
type: refactor-plan
---

# EnvBooker — Invariant & Aggregate Refactor Plan

This is a **plan document**. No production code is modified here.

## Step 0 — Context discovery

Documents read: `context/foundation/prd.md`, `context/domain/01-domain-distillation.md`
(prior distillation — Ubiquitous Language, subdomain map, and aggregate candidates
1–4 are reused as a starting point rather than re-derived). No new foundation doc
existed beyond what `01-domain-distillation.md` already catalogued.

Stack/layers (confirmed by reading source directly, not assumed): Django 6.0.5 /
Python 3.14. Three apps — `accounts`, `catalog`, `reservations` — each following
`models.py` → `services.py` → `views.py` (thin) → `forms.py`. Business rules live
in `catalog/services.py` and `reservations/services.py`; `reservations/models.py`
additionally carries two **database-level** invariants (`ExclusionConstraint`,
`CheckConstraint`) that have no application-layer equivalent because Postgres
enforces them directly. This matters for Step 2: some invariants in this codebase
are already guarded at the strongest possible layer (the DB), which changes where
the "weakest enforcement" analysis should point.

## Step 1 — Identified invariants

| # | Invariant | Source (doc) | Source (code) |
|---|---|---|---|
| I1 | No two reservations for the same environment may have overlapping `during` ranges. | "No double-booking... at any layer" (`prd.md:42`) | `reservations/models.py:26-33` (`ExclusionConstraint reservation_no_overlap`) |
| I2 | A reservation's `during` range must be non-empty and bounded (no open-ended ranges). | Implicit — FR-011 requires "a specific time window" (`prd.md:94`) | `reservations/models.py:34-41` (`CheckConstraint reservation_during_bounded`) |
| I3 | A reservation may only be modified/cancelled by its owner, except an admin may act on any reservation. | "Reservation ownership is respected" (`prd.md:43`) | `reservations/views.py:46-55` (`_reservation_for_request`) |
| I4 | An environment may be **deleted** only when it has no active or upcoming reservations. | FR-007 (`prd.md:80`) | `catalog/services.py:123-149` (`delete_environment`) |
| I5 | An environment may be **edited** while it has active/upcoming reservations, but only after the admin has been shown which reservations are affected and has explicitly confirmed. | FR-006 (`prd.md:78-79`) — Socrates note: "do not block; notify-only... admin sees warning before save" | `catalog/views.py:114-150` (`environment_edit`) |
| I6 | A reservation whose environment definition changed after it was created must be flagged to its owner. | FR-006, second half (`prd.md:78`) | `reservations/views.py:89-91` (`definition_changed`) |
| I7 | Sign-up is restricted to allow-listed email domains, matched case-insensitively, when any allow-list rows exist. | FR-001 (`prd.md:65`) | `accounts/models.py:52-60`, `accounts/forms.py` |

## Step 2 — Classification and selection of #1

| # | (a) How core | (b) Spread across layers | (c) Enforcement status |
|---|---|---|---|
| I1 | **Highest.** This is literally the guardrail the product exists to satisfy (`prd.md:42`). | Single layer: DB constraint, with a service-layer translator (`reservations/services.py:106-128`) that only turns the DB error into a message — it adds no independent enforcement. | **Enforced, strongly, once.** Postgres `GIST` exclusion constraint — cannot be bypassed by any code path, including future ones. |
| I2 | Medium — a precondition of I1, not independently product-critical. | Single layer: DB `CheckConstraint`. | **Enforced, strongly, once.** |
| I3 | High — a named guardrail (`prd.md:43`). | Single layer: one function, `_reservation_for_request`, used by both `reservation_edit` and `reservation_cancel` (`reservations/views.py:199,245`). | **Enforced, consistently, in one place.** No duplication, no bypass found. |
| I4 | High — protects the trust of the metadata-driven catalog that the Vision section names as the product's differentiator (`prd.md:24`). | Single layer: `catalog/services.py:delete_environment`, called once from `catalog/views.py:159`. | **Enforced, atomically.** Check-then-delete is wrapped in one `transaction.atomic()` block, and even a race is caught by the DB's own `PROTECT` FK → `ProtectedError` (`catalog/services.py:130-133,145-148`). Belt-and-suspenders. |
| I5 | High — same underlying concern as I4 (an environment's committed metadata must not go stale under a live reservation) applied to edit instead of delete; directly tied to the same Vision-level differentiator (`prd.md:24`) as I4. | **Spread.** No `catalog/services.py` function exists for it at all — the check-then-act logic is written inline in the view (`catalog/views.py:114-150`), duplicating a query (`active_or_upcoming_reservations`) that `catalog/views.py` also calls independently for I4 at two other call sites (`catalog/views.py:121,156,164`). | **Enforced, but weakly and inconsistently vs. I4.** No `transaction.atomic()` wraps the check-then-save; the "confirmed" path (`request.POST.get("confirm")`) skips the affected-reservations check entirely rather than re-verifying it; the confirmation itself is a client-supplied hidden field trusted at face value. See Step 3. |
| I6 | Medium — a read-model/display concern, not a write invariant. | Single layer: one comparison in `reservations/views.py:89-91`. | Enforced but coarse (any `updated_at` bump trips it) — a precision gap, not a violability gap; already noted in `01-domain-distillation.md` Candidate 4. |
| I7 | Low — Generic subdomain, not core (per `01-domain-distillation.md` Step 2). | Single layer. | Enforced consistently. |

**Selected: I5 — "an environment may be edited under live reservations only with
an explicit, re-verified admin acknowledgement."**

I1 is more core than I5, but it is already enforced at the one layer nothing can
bypass (the database), so there is no refactor to make there. I5 ties for
"most core, weakly enforced": it protects the same Vision-level guarantee as I4
(environment metadata stays trustworthy against live reservations), it is the
*only* invariant in this table that is genuinely smeared across layers (view-inline
logic duplicating a query also used elsewhere, with no dedicated service function),
and it is the only one whose enforcement is provably weaker than its nearest
sibling (I4) despite guarding the same class of risk. That combination — high
centrality, real spread, inconsistent enforcement relative to a proven-good
pattern sitting right next to it in the same file — is what KROK 2 asks to find.

## Step 3 — Diagnosis of I5

Where the rule lives today, across layers:

1. **View layer, first branch** — `catalog/views.py:120-121`: `active_or_upcoming_reservations(env)` is called directly from the view (not from `catalog/services.py`), immediately after `form.is_valid()`.
2. **View layer, gating condition** — `catalog/views.py:125`: `if not request.POST.get("confirm") and affected.exists():` — the *entire* enforcement of "admin must see the warning" is this one inline boolean. There is no server-side record of what was shown; the "warning was seen" fact is encoded only in a hidden form field the client echoes back.
3. **View layer, unconditional save** — `catalog/views.py:140`: `env = form.save()` runs whenever either branch above is false — i.e. either no reservations are affected, **or** `confirm` was already set. On the confirmed path, `affected` is never recomputed.
4. **No transaction boundary** — unlike I4's `delete_environment` (`catalog/services.py:138`, `with transaction.atomic():`), nothing here wraps the check (step 1) and the save (step 3) in one atomic block. Between them, another request can create a new reservation for the same environment; that reservation is never shown to the admin, yet the edit proceeds anyway on the strength of the earlier, now-stale check.
5. **No DB backstop** — I4's DB-level `PROTECT` FK gives it a second line of defense (`ProtectedError`) even if the application-level check races. I5 has no equivalent: `Environment` carries no constraint tied to its reservations, so a race here fails silently rather than raising.
6. **Duplication** — the same `active_or_upcoming_reservations` query that I5 calls once (step 1) is called again, separately, for I4 at `catalog/views.py:156` and `catalog/views.py:164`. Two invariants about "does this environment have live reservations" independently query the same fact from the view layer instead of sharing one guarded entry point.

Net effect: I5 is not unenforced — `test_edit_with_active_upcoming_warns_and_does_not_save` (`catalog/tests.py:578-590`) and `test_resubmit_with_confirm_saves` (`catalog/tests.py:592-598`) prove the happy path works — but the guarantee only holds for the single-request, no-concurrency case. There is no test exercising the race (a reservation created between the warning and the confirm), and the current implementation has no mechanism that would make such a test pass even if written.

## Step 4 — Aggregate design

**Aggregate root:** `Environment` (already the natural root — it owns the
metadata whose staleness is the thing being protected; `Reservation` rows are
read as *evidence* the aggregate consults, not absorbed as child entities, since
I1/I2/I3 remain `Reservation`'s own invariants and must stay enforced where they
already are, at the DB).

**Value object:** `ReservationImpact` — the set of active/upcoming reservations
an edit or delete would affect, computed once and carried through the whole
operation instead of re-queried ad hoc per call site.

**Domain errors** (named, not silent state updates):

- `UnconfirmedReservationImpact(impact: ReservationImpact)` — raised by `apply_edit` when live reservations exist and the caller has not acknowledged *this exact* impact.
- `EnvironmentHasLiveReservations(impact: ReservationImpact)` — raised by `delete` unconditionally when live reservations exist (I4 has no override, unlike I5).

**Domain methods on `Environment` (pseudocode):**

```python
class ReservationImpact:
    reservations: list[Reservation]

    def fingerprint(self) -> str:
        # Stable hash of the reservation pks the admin was actually shown.
        # Used to detect "impact changed since you were warned" — see apply_edit.
        return hash(tuple(sorted(r.pk for r in self.reservations)))

    def is_empty(self) -> bool:
        return not self.reservations


class Environment(models.Model):
    ...  # existing fields unchanged

    def assess_reservation_impact(self, now=None) -> ReservationImpact:
        """Single source of truth for 'does this env have live reservations',
        replacing the three independent call sites in catalog/views.py."""
        return ReservationImpact(
            reservations=list(active_or_upcoming_reservations(self, now))
        )

    def apply_edit(
        self, changes: EnvironmentChanges, acknowledged_impact_fingerprint: str | None
    ) -> None:
        """FR-006: notify-only, override allowed — but the override must match
        the impact actually shown, not just any prior confirmation."""
        impact = self.assess_reservation_impact()
        if not impact.is_empty():
            if acknowledged_impact_fingerprint != impact.fingerprint():
                raise UnconfirmedReservationImpact(impact)
        changes.apply_to(self)
        self.save()

    def delete_guarded(self) -> None:
        """FR-007: hard block, no override — mirrors today's delete_environment."""
        impact = self.assess_reservation_impact()
        if not impact.is_empty():
            raise EnvironmentHasLiveReservations(impact)
        active_or_upcoming_reservations... # past reservations cascade unchanged
        self.delete()
```

The `fingerprint()` check is the fix for Step 3's race: instead of a bare
`confirm=1` flag, the client echoes back which impact it was shown (e.g. a hash
embedded as a hidden field), and `apply_edit` recomputes impact fresh and
compares. If a new reservation arrived after the warning was rendered, the
fingerprint no longer matches, `UnconfirmedReservationImpact` fires again with
the *updated* list, and the admin re-confirms against current reality — closing
the race without turning I5 into a hard block (preserving FR-006's deliberate
notify-only resolution).

**Repository / transaction boundary:**

```python
def load_environment_for_mutation(pk: int) -> Environment:
    """Row-lock the environment for the duration of the guarded operation, so
    the impact check and the save/delete observe a consistent snapshot instead
    of racing against a concurrent reservation_create."""
    return Environment.objects.select_for_update().get(pk=pk)


# in the view:
with transaction.atomic():
    env = load_environment_for_mutation(pk)
    try:
        env.apply_edit(changes, acknowledged_impact_fingerprint=form_fingerprint)
    except UnconfirmedReservationImpact as exc:
        return render_warning(exc.impact)  # re-renders with the CURRENT impact
```

`select_for_update()` inside `transaction.atomic()` is the pragmatic Django
adapter for "the whole check-then-act goes in one transaction" that KROK 4 asks
for — it also closes I4's already-narrow race window on the same code path for
free, since `delete_guarded` reuses the same locked load.

**Thin route:** `environment_edit`/`environment_delete` views shrink to: parse
form → `load_environment_for_mutation` → call the one aggregate method → catch
its named domain error → map to the existing warning/blocked templates. All
three of `catalog/views.py:121,156,164`'s direct calls to
`active_or_upcoming_reservations` are removed; only `assess_reservation_impact`
remains, and only inside the aggregate.

## Step 5 — Before/after, phased plan, tests

### Before/after

| Site | Before | After |
|---|---|---|
| `catalog/views.py:120-140` (`environment_edit`) | Inline check, no transaction, `confirm` flag trusted blindly | `env.apply_edit(...)` inside `transaction.atomic()` + `select_for_update()`; domain error carries fresh impact |
| `catalog/services.py:123-149` (`delete_environment`) | Standalone function, its own `transaction.atomic()`, `ProtectedError` catch as backstop | Becomes `Environment.delete_guarded()`; `ProtectedError` catch kept as a defense-in-depth backstop, no longer the primary guard |
| `catalog/views.py:156,164` (`environment_delete`) | Calls `active_or_upcoming_reservations` directly, twice | Calls `env.assess_reservation_impact()` once via the loaded aggregate |

### Phased plan (test-first where the project's existing discipline supports it —
`catalog/tests.py` already covers I4/I5's happy paths with `TestCase`)

- **Phase 1 (test-first).** Add the race-condition test that today's code cannot pass: two overlapping requests where a reservation is created for the env *between* the initial warning and the confirmed resubmit. Assert the confirmed save is rejected (impact re-shown) rather than silently succeeding. This requires `TransactionTestCase` (not plain `TestCase`) so the two writes are genuinely separate transactions.
- **Phase 2.** Implement `ReservationImpact`, `UnconfirmedReservationImpact`, `EnvironmentHasLiveReservations`, `Environment.assess_reservation_impact` / `apply_edit` / `delete_guarded`, and `load_environment_for_mutation`.
- **Phase 3.** Migrate `environment_edit` to the aggregate; run Phase 1's test — should now pass.
- **Phase 4.** Migrate `environment_delete` to `delete_guarded()`; retire the standalone `delete_environment` service function (or keep it as a one-line wrapper if external callers exist — none found outside `catalog/views.py:159` and `catalog/tests.py`).
- **Phase 5.** Full regression: existing `catalog/tests.py` (`EnvironmentEditViewTest`, `DeleteEnvironmentServiceTest`, `EnvironmentDeleteViewTest`) plus the new race test, all green.

### Test cases for the invariant (legal / illegal transitions)

1. Edit with zero affected reservations → saves immediately, no confirm required. *(legal — existing `test_edit_without_reservations_saves_one_step`)*
2. Edit with affected reservations, no acknowledgement → blocked, impact shown, not saved. *(illegal without ack — existing `test_edit_with_active_upcoming_warns_and_does_not_save`)*
3. Edit with affected reservations, fingerprint matches current impact → saves. *(legal override — existing `test_resubmit_with_confirm_saves`, adapted to fingerprint)*
4. Edit with affected reservations, admin confirms, but a *new* reservation was created after the warning was rendered and before the confirm lands → rejected, fresh impact re-shown; admin must re-confirm. *(new — the race case; illegal to silently accept a stale acknowledgement)*
5. Delete with zero reservations → deletes. *(legal — existing `test_delete_when_no_reservations`)*
6. Delete with active or upcoming reservations → always blocked, no confirm parameter accepted. *(illegal, no override — existing `test_blocked_when_upcoming_exists`, `test_blocked_when_active_exists`)*
7. Delete where a reservation is created concurrently between load and delete → still blocked. *(illegal — existing `test_post_blocked_re_renders_with_blocking_list` as a regression; now provable directly via the locked load instead of relying solely on `ProtectedError`)*
8. Past-reservation cascade on delete is unaffected by this refactor. *(regression — existing `test_cascade_past_reservations`)*

### New load-bearing names to register (if this project keeps a contracts registry)

- `Environment.assess_reservation_impact`
- `Environment.apply_edit`
- `Environment.delete_guarded`
- `ReservationImpact` (incl. `fingerprint()`)
- `UnconfirmedReservationImpact`
- `EnvironmentHasLiveReservations`
- `load_environment_for_mutation`

## Summary

I5 — "an environment may be edited under live reservations only with an
explicit, re-verified admin acknowledgement" (FR-006) — was selected over the
more product-central I1 (no double-booking) because I1 is already enforced at
the one layer nothing can bypass, the database, while I5 is the only invariant
in this codebase that is both genuinely core (it protects the same
metadata-trustworthiness guarantee the Vision section names as the product's
differentiator) and demonstrably weaker than its nearest sibling, I4
(delete-guard), despite guarding the same class of risk. The diagnosis traced
I5 to inline, unwrapped, duplicated logic in `catalog/views.py` with no
transaction boundary and a client-trusted confirmation flag that is never
re-verified against current reservation state — a real, currently-untested race
window. The proposed fix makes `Environment` the aggregate root for both FR-006
and FR-007, introduces a `ReservationImpact` value object with a fingerprint so
confirmations are checked against the *current* impact rather than blindly
trusted, and moves both edit and delete onto one row-locked, atomically-loaded
path (`load_environment_for_mutation` + `select_for_update`) — closing the race
for I5 while also tightening I4's already-strong guard for free. The phased
plan is test-first: the race test that today's code cannot pass is written
before any implementation change, per this project's existing test discipline.
