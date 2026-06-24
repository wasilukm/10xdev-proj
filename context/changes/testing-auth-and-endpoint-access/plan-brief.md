# Authorization & Endpoint Access Tests (Phase 2) — Plan Brief

> Full plan: `context/changes/testing-auth-and-endpoint-access/plan.md`

## What & Why

Rollout Phase 2 of the project test plan, covering **Risk #3**: a user reaches or
mutates a reservation or endpoint they are not authorized for. We prove — by
observable behavior, route by route — that every gated route enforces authentication,
that the one ownership-filtered list view doesn't leak another user's data, and we
systematically guard against a future view forgetting its `@login_required`.

## Starting Point

Five gated routes exist (`home`, `reservations:create/mine/edit/cancel`), all
`@login_required`. Edit/cancel already have auth + non-owner-404 + bad-pk-404 tests;
`home` and `create` have auth tests. Two gaps remain: `reservations:mine` (the only
ownership-*filtered* GET) has **zero** tests, and there is no systematic guard that a
*new* view carries its auth decorator.

## Desired End State

`manage.py test` (with `DJANGO_DEBUG=True`) covers a data-driven inventory that
denies anonymous access to every gated route, a cross-user isolation test proving
`mine/` shows only the requester's reservations, and a skipped marker recording that
the admin-vs-non-admin boundary awaits S-06. The test-plan cookbook's reserved
§6.4/§6.5 placeholders are filled and Phase 2 is marked complete.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Admin-vs-non-admin clause | Defer + document (skipped marker) | S-05/S-06 are `proposed`, no first-party admin surface; §7 excludes testing `/admin/`. | Plan |
| Guard against future ungated views | Data-driven route-inventory test | Directly kills the "siblings are guarded too" anti-pattern for any inventoried route. | Plan |
| `mine/` depth | Auth + cross-user isolation | Closes the actual IDOR question by asserting observable output, not the internal queryset. | Plan |
| Test file placement | Per-app for `mine/`, project-level for inventory | §6.2 files by owning surface; the inventory spans apps so it has no single owner. | Plan |
| Public-route reachability | Not asserted this phase | Focus on the exposure direction (a route losing its guard), not over-gating. | Plan |
| Method-constrained routes | GET first, retry POST on 405 | Lets the inventory skip a per-route method column; auth redirect fires regardless. | Plan |

## Scope

**In scope:** `mine/` auth + isolation tests; data-driven route-inventory auth guard;
skipped admin-boundary marker; fill cookbook §6.4/§6.5 + a §6.6 phase note; flip
Phase 2 status.

**Out of scope:** building S-05/S-06; testing Django `/admin/`; any production/guard
change; URL-reflection auto-discovery; public-route reachability assertions; full
behavioral coverage of `my_reservations`; converting `catalog`/`accounts` tests.py.

## Architecture / Approach

Three independently-verifiable, test-only phases, smallest blast radius first:
(1) fill the concrete `mine/` gap in `reservations/tests/test_views.py`; (2) add a
project-level `tests/test_authorization.py` with the inventory + admin marker —
discovered by the Django runner (which ignores the pytest-based `tests/e2e/`);
(3) close the loop in the test-plan cookbook.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. `mine/` isolation | Auth + cross-user list-isolation tests | Tautological assertion that doesn't actually exercise the filter (mitigated by anti-tautology manual check) |
| 2. Authorization module | Data-driven inventory + skipped admin marker | Inventory is hand-maintained — a new route not added is uncovered (mitigated by a tying comment) |
| 3. Documentation | Cookbook §6.4/§6.5 filled, status flipped | Doc references drift from real test names |

**Prerequisites:** Postgres up (`docker compose up -d`); run tests with `DJANGO_DEBUG=True`.
**Estimated effort:** ~1 session across 3 phases.

## Open Risks & Assumptions

- The route inventory is explicit and hand-maintained; it only protects routes added
  to it. A class comment ties it to the URLconfs and instructs adding new
  `@login_required` routes — but discipline, not automation, enforces this.
- The admin clause of Risk #3 stays formally open until S-06 ships; the skipped
  marker keeps it visible in test output.

## Success Criteria (Summary)

- Every gated route is proven to deny anonymous access by a single test that bites
  when a guard is removed.
- `mine/` is proven not to leak another user's reservations.
- The deferred admin boundary is recorded (skipped marker + §6.6 note), not silently
  absent; cookbook §6.4/§6.5 are filled; Phase 2 reads `complete`.
