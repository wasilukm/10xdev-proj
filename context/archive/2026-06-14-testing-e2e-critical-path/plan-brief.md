# Critical-path E2E Harness — Plan Brief

> Full plan: `context/changes/testing-e2e-critical-path/plan.md`
> Research: `context/changes/testing-e2e-critical-path/research.md`

## What & Why

Build the Playwright **Python** e2e harness for EnvBooker so the
find → filter → reserve → appears-without-reload flow (test-plan **Risk #2**) can be
driven in a real browser. Today every partial-render view-test passes even if the HTMX
`hx-target`/`hx-swap`/JS wiring is broken — the primary <30s success criterion could
silently fail. This change delivers the *infrastructure* that makes a real browser
assertion possible; it does not write the risk test itself.

## Starting Point

Zero browser/e2e infrastructure exists (no `pytest-playwright`/`pytest-django`, no
`conftest.py`, no `tests/e2e/`). The `/10x-e2e` skill — already adapted to Playwright
Python in this repo — *discovers* such a harness and **STOPs** if it's missing; it only
creates `test_seed.py` + the E2E rules file. So the harness must be built first, by this
change.

## Desired End State

`DJANGO_DEBUG=True uv run pytest tests/e2e/test_smoke.py` boots headless Chromium against
the real app on the Postgres test DB via `live_server`, arrives authenticated with no
login form driven, and sees a seeded environment row on the dashboard — green and
deterministic. At that point `/10x-e2e testing-e2e-critical-path` passes its setup gate
and is ready to generate the Risk #2 test.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Language binding | Playwright Python (`pytest-playwright` + `pytest-django`) | One Python/uv toolchain; seed via the Django ORM. | Research |
| App start + test DB | `live_server` + `transactional_db` on Postgres, `DJANGO_DEBUG=True` | Live-server thread sees committed rows; test DB auto-managed; avoids `SECURE_SSL_REDIRECT` 301s. | Research |
| Auth | Inject server-side `sessionid` cookie via fixture | No UI login; DB-native and simplest. | Research |
| Seeding | pytest fixtures via the Django ORM, unique-suffixed | Reuses existing `_range()`/`_helpers` idiom; test-DB reset handles teardown. | Research |
| Handoff boundary | Harness + smoke test here; risk test owned by `/10x-e2e` | Matches the skill's discover-don't-build contract; keeps the risk test under its review/break-check loop. | Plan |
| <30s timing | Assert behavior; capture timing as a logged observation | A hard wall-clock assertion is flaky; 30s is a UX target, not an SLA. | Plan |
| Visual review | Behavior only; dashboard snapshot deferred | test-plan marks visual "optional, dashboard only". | Plan |
| Conflict locator | `getByText` against verified string; a11y noted as follow-up | Avoids a production-template change inside a test-infra phase. | Plan |
| Risk coverage (for `/10x-e2e`) | Happy path **+** conflict rejection | Research: both hops + the in-page reject are core to Risk #2. | Plan |

## Scope

**In scope:** dev deps + Chromium; pytest↔Django config; `live_server`+`transactional_db`
wiring; session-cookie auth fixture; ORM seed fixture; one harness smoke test; test-plan
§6.3/§6.6 cookbook + handoff note.

**Out of scope:** the Risk #2 critical-path test, `tests/e2e/test_seed.py` + the E2E
rules file (both owned by `/10x-e2e`), CI wiring (Phase 5), visual/pixel snapshots, the
`role="alert"` template change, edit/cancel coverage.

## Architecture / Approach

Two additive phases. Phase 1 sets the dependency + config floor (pytest discovers Django,
Postgres test DB auto-created). Phase 2 adds the no-UI auth fixture and the unique-suffixed
ORM seed fixture, then proves all three parts (`live_server` + auth cookie + seeded row)
cooperate in one smoke test, and documents the run command + `/10x-e2e` handoff. The
existing `manage.py test` unittest suite is untouched and runs independently of pytest.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Harness install & config | dev deps, Chromium, `[tool.pytest.ini_options]` Django wiring | pytest-django ↔ Postgres test-DB config not booting Django cleanly |
| 2. Fixtures, smoke test & handoff | auth + seed fixtures, `live_server` smoke test, cookbook + handoff docs | session cookie dropped (domain/port mismatch) → silent login redirect |

**Prerequisites:** Postgres running locally (`docker compose up -d`); `DJANGO_DEBUG=True`
in the environment for every pytest run.
**Estimated effort:** ~1–2 sessions across 2 phases.

## Open Risks & Assumptions

- Session-cookie injection must use `live_server`'s hostname (not host:port) and be added
  before the first `page.goto`, or auth silently fails — called out in the plan.
- `live_server` requires `transactional_db` (not the default `db`) for the browser thread
  to see seed rows — paired explicitly in the fixtures.
- The smoke test deliberately proves only boot+auth+seed; a green harness is not yet proof
  the HTMX flow works (that's the `/10x-e2e` test that follows).

## Success Criteria (Summary)

- `DJANGO_DEBUG=True uv run pytest tests/e2e/test_smoke.py` is green and deterministic on
  repeated runs.
- `/10x-e2e testing-e2e-critical-path` would pass its setup gate (deps + `tests/e2e/test_*.py`
  + `conftest.py` auth fixture all discovered) instead of STOPping.
- The existing `manage.py test` suite still passes unchanged.
