# Authorization & Endpoint Access Tests (Phase 2) Implementation Plan

## Overview

This is rollout Phase 2 of the project test plan (`context/foundation/test-plan.md` §3),
covering **Risk #3**: a user reaches or mutates a reservation or endpoint they are
not authorized for. The goal is to prove — by observable behavior, route by route —
that every gated route enforces authentication, that the one ownership-*filtered*
GET (`reservations:mine`) does not leak another user's data, and to systematically
guard against a *future* view forgetting its `@login_required` decorator (the named
anti-pattern: "one guarded view implies the siblings are guarded too").

This phase is test-only and documentation-only. It adds no production code and
changes no view behavior.

## Current State Analysis

**Gated route inventory** (every one decorated `@login_required`):

| Route name | View | Method | Ownership filter |
|------------|------|--------|------------------|
| `home` (`catalog:home`) | `catalog.views.environment_list` | GET | none |
| `reservations:create` | `reservations.views.reservation_create` | POST (`@require_POST`) | none |
| `reservations:mine` | `reservations.views.my_reservations` | GET | `filter(owner=request.user)` |
| `reservations:edit` | `reservations.views.reservation_edit` | POST (`@require_POST`) | `get_object_or_404(..., owner=request.user)` |
| `reservations:cancel` | `reservations.views.reservation_cancel` | POST (`@require_POST`) | `get_object_or_404(..., owner=request.user)` |

Public routes (must stay reachable, not in scope to positively assert this phase):
`login`, `logout`, `signup` (`accounts/urls.py`).

**Existing coverage** (already strong on the write paths):

- `reservations/tests/test_views.py::ReservationEditViewTest` — `test_auth_required`, `test_non_owner_404`, `test_nonexistent_pk_404`.
- `reservations/tests/test_views.py::ReservationCancelViewTest` — same three.
- `reservations/tests/test_views.py::ReservationCreateViewTest::test_auth_required`.
- `catalog/tests.py::DashboardAuthTest::test_anonymous_redirects_to_login` (the `home` route).

**The gaps this phase closes:**

1. **`reservations:mine` has zero tests** — and it is the only ownership-*filtered*
   GET. Nothing proves it doesn't render another user's reservations. This is the
   IDOR-shaped exposure Risk #3 names directly.
2. **No systematic guard** that a *newly added* view carries `@login_required`.
   Today each route is covered by a hand-written one-off; a new view is invisible
   until someone remembers to add its test. Risk #3's anti-pattern is exactly this
   "siblings are guarded too" assumption.
3. **The admin-vs-non-admin boundary has no first-party surface.** S-05
   (admin-env-catalogue UI) and S-06 (admin-reservation-override) are both
   `proposed`, not built (`context/foundation/roadmap.md` lines 37–38). Admin today
   is Django's built-in `/admin/`, which test-plan §7 explicitly excludes from
   testing. There is nothing first-party to assert.

### Key Discoveries:

- **The Django runner ignores `tests/e2e/`.** `manage.py test` ran the full suite
  (89 tests, OK) without touching the pytest function-style e2e tests — unittest
  only collects `TestCase` subclasses, and bare `def test_*(live_server, ...)`
  functions are silently skipped. Verified 2026-06-23. A new
  `tests/test_authorization.py` with a `TestCase` **will** be discovered and run by
  `manage.py test`. The project-level `tests/` package already exists with
  `tests/__init__.py`, so no package scaffolding is needed.
- **`login_required` is the outermost decorator** on the write paths (declared
  above `@require_POST` in `reservations/views.py:80,121,137,172`). An anonymous
  request — regardless of HTTP method — hits the auth check first and gets a 302 to
  login *before* `require_POST` can return a 405. This is why the inventory's
  GET-then-POST fallback is robust: the auth redirect fires either way.
- **`get_object_or_404(Reservation, pk=pk, owner=request.user)`** is the ownership
  guard on edit/cancel — a non-owner gets a 404 (not a 403), because the queryset
  filter makes the row invisible. Tests assert the observable 404, never the filter.
- **`my_reservations` uses `filter(owner=request.user)`** (`reservations/views.py:129`)
  with no `get_object_or_404`, so a non-owner sees an empty/own-only list, never a
  403/404. The isolation test must assert *absence of B's data in A's rendered list*,
  not a status code.
- **Test seed pattern**: `User.objects.create_user(email=..., password=..., first_name=..., last_name=...)`;
  `self.client.login(email=..., password=...)`; reservation ranges via
  `reservations/tests/_helpers.py` (`_range`, `_dt`, `_FIXED_NOW`) with
  `@mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)`.
- **Settings**: `LOGIN_URL = "login"`, `AUTH_USER_MODEL = "accounts.User"`. Run the
  suite with `DJANGO_DEBUG=True` or every request 301s on `SECURE_SSL_REDIRECT`
  before reaching the view (test-plan §6.6 Phase 1 note).

## Desired End State

- `manage.py test` (run with `DJANGO_DEBUG=True`) covers, by observable behavior:
  - every gated route denies anonymous access (one data-driven test that fails the
    moment a new gated route is added without `@login_required` — provided the route
    is registered in the inventory);
  - `reservations:mine` requires auth **and** shows only the requesting user's
    reservations, never another user's;
  - a recorded, skipped marker test naming the S-06 dependency for the
    admin-vs-non-admin boundary (so the open clause is visible in test output, not
    silently absent).
- Test-plan §6.4 and §6.5 cookbook sections are filled from "TBD" to real,
  reference-pointing patterns; a §6.5-area per-rollout-phase note records the
  admin-defer decision; the §3 Phase 2 Status cell reads `complete`.

**Verification**: `DJANGO_DEBUG=True uv run python manage.py test` is green;
`tests/test_authorization.py` and the new `mine/` tests appear in the count; mypy
clean; the route-inventory test fails if you temporarily remove `@login_required`
from any inventoried view (a manual spot-check).

## What We're NOT Doing

- **Not building S-05 or S-06.** No admin-override view, no first-class admin UI.
  The admin-vs-non-admin boundary is *deferred and documented*, not implemented.
- **Not testing Django's `/admin/`** — §7 excludes re-testing framework built-ins.
- **Not changing any view, decorator, or production behavior.** This phase asserts
  the current guards; it does not add or move them.
- **Not auto-discovering URL patterns by reflection.** The inventory is an explicit,
  hand-maintained list (parameterized routes need synthetic pks and an exemption
  list anyway); reflection was considered and rejected as fragile for a 5-route set.
- **Not positively asserting public-route reachability** (login/signup/logout return
  200 for anonymous). Scoped out this phase; the focus is the exposure direction
  (a gated route losing its guard), not the over-gating direction.
- **Not adding full behavioral coverage of `my_reservations`** (past-reservation
  exclusion, ordering, `select_related`). Those are functional concerns outside the
  Risk #3 authorization lens.
- **Not converting `catalog/tests.py` or `accounts/tests.py`** to the package
  layout. Per §6.2 "convert when a phase touches them" — this phase adds no auth
  tests *inside* those apps (the cross-cutting test lives at project level), so they
  stay flat.

## Implementation Approach

Three independently-verifiable phases, smallest blast radius first:

1. **Fill the one concrete gap** (`mine/` isolation) in the app that owns the
   surface — `reservations/tests/test_views.py`, already a package. This is the
   highest-signal single test in the phase.
2. **Add the cross-cutting guard** as a new project-level `tests/test_authorization.py`
   — a data-driven inventory test plus the skipped admin-boundary marker. It spans
   `catalog` + `reservations` routes, so per §6.2 it has no single owning app and
   belongs at project level.
3. **Close the loop in documentation** — fill the cookbook's reserved §6.4/§6.5
   placeholders, record the admin-defer decision, flip the phase status.

## Phase 1: `mine/` Ownership Isolation

### Overview

Add the missing tests for `reservations:mine` — the only untested gated route and
the only ownership-filtered GET. Prove auth is required and that one user's list
never contains another user's reservations.

### Changes Required:

#### 1. `MyReservationsViewTest`

**File**: `reservations/tests/test_views.py` (append a new `TestCase` class)

**Intent**: Cover the `my_reservations` view for Risk #3. Two users each own a
reservation on the same environment (non-overlapping windows); assert (a) anonymous
GET redirects to login, and (b) when user A is logged in, the rendered page contains
A's reservation and does **not** contain B's. The assertion is on observable rendered
output (presence/absence of an owner name or environment-specific marker), never on
the view's internal `filter(owner=...)`.

**Contract**: New class `MyReservationsViewTest(TestCase)` in the existing module.
Reuses `_helpers._range` / `_FIXED_NOW` and the `@mock.patch("django.utils.timezone.now", ...)`
idiom for any future-windowed reservations (so `upper_bound__gt=now` keeps them in
the list). URL via `reverse("reservations:mine")`. Methods (at least):
`test_auth_required` (302 → `reverse("login")`), `test_lists_only_own_reservations`
(A present, B absent). To disambiguate A from B in the HTML, give the two owners
distinct `first_name`/`last_name` and assert on `get_full_name()` strings, mirroring
`test_overlap_conflict_names_other_owner_not_self`.

### Success Criteria:

#### Automated Verification:

- New tests pass: `DJANGO_DEBUG=True uv run python manage.py test reservations.tests.test_views`
- Full suite still green: `DJANGO_DEBUG=True uv run python manage.py test`
- Type check clean: `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .`
- Lint/format clean: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Temporarily comment out the `filter(owner=request.user)` clause in
  `my_reservations` and confirm `test_lists_only_own_reservations` fails (proves the
  test actually exercises the isolation, not a tautology). Restore after.

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 2: Cross-Cutting Authorization Module

### Overview

Add a project-level `tests/test_authorization.py` containing (a) a data-driven
route-inventory test that asserts every gated route denies anonymous access, killing
the "siblings are guarded too" anti-pattern for any route added to the inventory,
and (b) a skipped marker test recording that the admin-vs-non-admin boundary awaits
S-06.

### Changes Required:

#### 1. Route-inventory authentication guard

**File**: `tests/test_authorization.py` (new; project-level `tests/` package already
has `__init__.py`)

**Intent**: One `TestCase` holding an explicit inventory of every gated route. For
each, issue an anonymous request and assert it is denied — redirect to login (302
whose `Location` contains `reverse("login")`), or 403/404. Use a per-route helper
that tries **GET first and retries with POST on a 405**, so method-constrained
(`@require_POST`) routes are handled without the inventory needing a per-route method
column. A separate test asserts the inventory is non-empty (guards against an empty
list silently passing).

**Contract**: New `tests/test_authorization.py` with e.g.
`class GatedRouteAuthTest(TestCase)`. The inventory is a list of
`(reverse-able name, kwargs)` entries:
`home`, `reservations:create`, `reservations:mine`,
`(reservations:edit, {pk: <synthetic>})`, `(reservations:cancel, {pk: <synthetic>})`.
A synthetic pk (e.g. `1`) is fine — auth is checked before the object lookup, so the
anonymous request never reaches the 404. A module/class comment must tie the
inventory to `reservations/urls.py` + `catalog/urls.py` and instruct: "add every new
`@login_required` route here." Helper sketch (the one non-obvious bit — method
fallback):

```python
def _anon_denied(self, url):
    resp = self.client.get(url)
    if resp.status_code == 405:
        resp = self.client.post(url)
    # auth denial: redirect to login, or hard deny
    if resp.status_code in (301, 302):
        self.assertIn(reverse("login"), resp["Location"])
    else:
        self.assertIn(resp.status_code, (403, 404))
```

#### 2. Admin-boundary deferral marker

**File**: `tests/test_authorization.py` (same module)

**Intent**: Record the deferred "admin-only actions reject non-admins" clause of
Risk #3 as an explicit `@unittest.skip` test whose reason names the S-06 dependency,
so the open item surfaces in test output (`s` in verbose runs) rather than being
silently absent. When S-06 lands, this test is the obvious home to fill.

**Contract**: A skipped method, e.g.
`@skip("admin-vs-non-admin boundary lands with roadmap S-06 (admin-reservation-override); no first-party admin surface exists yet — see test-plan §7")`
`def test_admin_only_action_rejects_non_admin(self): ...`. Body may be a bare `pass`
or a `self.fail` guarded by the skip.

### Success Criteria:

#### Automated Verification:

- New module discovered and runs: `DJANGO_DEBUG=True uv run python manage.py test tests.test_authorization`
- Full suite green, count increased: `DJANGO_DEBUG=True uv run python manage.py test`
- Skipped marker shows as skipped (not error/fail): `DJANGO_DEBUG=True uv run python manage.py test tests.test_authorization -v 2`
- Type check clean: `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .`
- Lint/format clean: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Temporarily remove `@login_required` from `catalog.views.environment_list` and
  confirm the inventory test fails for the `home` route (proves the guard bites).
  Restore after.
- Confirm an anonymous POST-only route (e.g. `reservations:create`) is reported
  denied via the GET→405→POST fallback path, not a spurious pass on the 405 itself.

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 3: Cookbook & Test-Plan Documentation

### Overview

Fill the test-plan cookbook placeholders this phase was reserved to fill, record the
admin-defer decision as a per-rollout-phase note, and mark Phase 2 complete.

### Changes Required:

#### 1. Cookbook §6.4 — new endpoint/view test pattern

**File**: `context/foundation/test-plan.md` (§6.4, currently "TBD — see §3 Phase 2")

**Intent**: Replace the TBD with the concrete pattern: where a view test lives
(`<app>/tests/test_views.py` for the owning surface; project-level
`tests/test_authorization.py` for cross-cutting route guards), and the reference
tests produced by this phase.

**Contract**: Prose + bullet list pointing at `MyReservationsViewTest` and
`tests/test_authorization.py::GatedRouteAuthTest`. Mention the inventory-maintenance
rule (every new `@login_required` route gets an inventory entry).

#### 2. Cookbook §6.5 — authorization/ownership test pattern

**File**: `context/foundation/test-plan.md` (§6.5)

**Intent**: Replace the seed-only stub with the full pattern: assert the observable
`302`/`403`/`404` (never copy the view's permission check); test the non-owner and
the anonymous cases, not just the happy-path owner; for ownership-filtered list views
assert absence of other users' data.

**Contract**: Updated bullets citing `ReservationEditViewTest::test_non_owner_404`,
`MyReservationsViewTest::test_lists_only_own_reservations`, and
`GatedRouteAuthTest`.

#### 3. Per-rollout-phase note — admin-defer decision

**File**: `context/foundation/test-plan.md` (§6.6, add a "Phase 2" note block)

**Intent**: Record that the admin-vs-non-admin boundary is deferred to S-06 with a
skipped marker, why (no first-party admin surface; §7 excludes `/admin/`), and where
it will be filled. Also note the `tests/test_authorization.py` route-inventory
location and the GET→POST-on-405 helper convention.

**Contract**: New dated note under §6.6 in the same style as the existing Phase 1 /
Phase 3 notes.

#### 4. Phase status flip

**File**: `context/foundation/test-plan.md` (§3 table, row 2)

**Intent**: Change the Phase 2 Status cell from `change opened` to `complete`.

**Contract**: Single-cell edit in the §3 Phased Rollout table.

#### 5. Change identity update

**File**: `context/changes/testing-auth-and-endpoint-access/change.md`

**Intent**: Set `status: planned` → (on completion) reflect progress; update
`updated:` date. (The plan step sets `planned`; implementation closes it out.)

**Contract**: Frontmatter `status` and `updated` fields.

### Success Criteria:

#### Automated Verification:

- No TBD remains in the two filled sections: `grep -n "TBD" context/foundation/test-plan.md` shows §6.4/§6.5 are no longer TBD.
- Phase 2 status updated: `grep -n "Authorization & endpoint access" context/foundation/test-plan.md` row shows `complete`.
- Full suite still green: `DJANGO_DEBUG=True uv run python manage.py test`

#### Manual Verification:

- Read §6.4/§6.5/§6.6 and confirm the references resolve to tests that actually
  exist after Phases 1–2.

**Implementation Note**: Final phase — confirm the whole suite is green and the
test-plan reads coherently before closing the change.

---

## Testing Strategy

### Unit / Integration Tests:

- `MyReservationsViewTest` — auth required; cross-user list isolation (the IDOR gap).
- `GatedRouteAuthTest` — data-driven anonymous-denial across all gated routes;
  non-empty-inventory guard.
- Skipped admin-boundary marker — records the S-06-deferred clause.

### What is deliberately not added here:

- Re-asserting edit/cancel non-owner 404 (already covered in
  `ReservationEditViewTest` / `ReservationCancelViewTest`) — the inventory covers the
  *auth* layer; ownership on the write paths is already tested. Avoid duplicating.

### Manual Testing Steps:

1. Remove `@login_required` from one inventoried view → inventory test fails →
   restore.
2. Comment out `filter(owner=request.user)` in `my_reservations` → isolation test
   fails → restore.
3. Run `... test -v 2` and confirm the admin marker is reported skipped.

## Performance Considerations

Negligible — a handful of additional `TestCase` methods. The inventory test issues
~5 anonymous requests with no DB writes.

## Migration Notes

None — no schema or data changes.

## References

- Test plan: `context/foundation/test-plan.md` (§3 Phase 2, §2 Risk #3, §6.2/§6.4/§6.5/§6.6, §7)
- Roadmap S-05/S-06 (proposed, not built): `context/foundation/roadmap.md` lines 37–38, 135–157
- Reference tests: `reservations/tests/test_views.py` (`ReservationEditViewTest`, `ReservationCancelViewTest`)
- Gated views: `reservations/views.py:80,121,137,172`; `catalog/views.py:21`
- Shared fixtures: `reservations/tests/_helpers.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: `mine/` Ownership Isolation

#### Automated

- [x] 1.1 New tests pass: `manage.py test reservations.tests.test_views` — ab26586
- [x] 1.2 Full suite still green: `manage.py test` — ab26586
- [x] 1.3 Type check clean (mypy) — ab26586
- [x] 1.4 Lint/format clean (ruff) — ab26586

#### Manual

- [x] 1.5 Removing `filter(owner=...)` makes `test_lists_only_own_reservations` fail (anti-tautology check) — ab26586

### Phase 2: Cross-Cutting Authorization Module

#### Automated

- [x] 2.1 New module discovered and runs: `manage.py test tests.test_authorization` — 4d1ae4c
- [x] 2.2 Full suite green, count increased — 4d1ae4c
- [x] 2.3 Skipped admin marker shows as skipped, not error/fail — 4d1ae4c
- [x] 2.4 Type check clean (mypy) — 4d1ae4c
- [x] 2.5 Lint/format clean (ruff) — 4d1ae4c

#### Manual

- [x] 2.6 Removing `@login_required` from `environment_list` fails the inventory test — 4d1ae4c
- [x] 2.7 POST-only route reported denied via GET→405→POST fallback (not a 405 false-pass) — 4d1ae4c

### Phase 3: Cookbook & Test-Plan Documentation

#### Automated

- [x] 3.1 No TBD remains in §6.4/§6.5: `grep -n "TBD" context/foundation/test-plan.md`
- [x] 3.2 Phase 2 status reads `complete` in §3 table
- [x] 3.3 Full suite still green: `manage.py test`

#### Manual

- [x] 3.4 §6.4/§6.5/§6.6 references resolve to tests that exist after Phases 1–2
