# Critical-path E2E Harness Implementation Plan

## Overview

Build the Playwright **Python** end-to-end test harness for EnvBooker so the
find → filter → reserve → appears-without-reload flow (test-plan **Risk #2**) can
be driven in a real browser. This change delivers the **infrastructure** — dev
dependencies + browser, a pytest↔Django configuration, app-start under
`live_server`+`transactional_db` against the Postgres test DB, a no-UI session-cookie
auth fixture, and unique-suffixed ORM seed fixtures — verified end-to-end by a thin
smoke test. The Risk #2 critical-path test itself is **out of scope here**: it is
owned by the `/10x-e2e` skill, which *discovers* the harness this plan builds and
then generates, reviews, and hardens the risk-tied test.

## Current State Analysis

- **Zero browser/e2e infrastructure** (whole-repo search, research §5/§7): no
  `pytest-playwright`/`pytest-django`, no Node/`package.json`, no `conftest.py`, no
  `tests/e2e/`, no `LiveServerTestCase`. Confirmed directly: `pyproject.toml` has an
  empty `[dependency-groups]`; no top-level `tests/`.
- **The `/10x-e2e` skill will STOP on this repo today.** It is adapted to Playwright
  Python (`.claude/skills/10x-e2e/SKILL.md`): it asserts `pytest-playwright` +
  `pytest-django` are installed and that `tests/e2e/test_*.py` / a `conftest.py` auth
  fixture exist; if absent it stops and tells the user to set it up first
  (`SKILL.md:50-61, 113-122`). It **creates only** `tests/e2e/test_seed.py` and the
  E2E rules file — never the runner/config. So the harness must pre-exist.
- **Postgres-only, even in tests** (research §5 correction, `CLAUDE.md`,
  `test-plan.md:91`): the `btree_gist` exclusion constraint is Postgres-only and
  `settings.py` raises `ImproperlyConfigured` on a non-Postgres `DATABASE_URL`. The
  harness boots against Postgres; `DJANGO_DEBUG=True` must be set or
  `SECURE_SSL_REDIRECT` 301s requests before they reach the view
  (`test-plan.md:179-180`).
- **The flow under future test is a two-hop HTMX targeted swap** (research §1): filter
  (`hx-get` → `#env-results` outerHTML) then reserve (`hx-post` → `#env-row-{pk}`
  outerHTML). "Appears" is emergent from a re-query on the create path, not an OOB swap.
- **Existing test idiom to reuse** (research §6): the reservation view tests seed via
  the ORM (`User.objects.create_user`, `Environment.objects.create`,
  `Reservation.objects.create(during=_range(...))`) with helpers in
  `reservations/tests/_helpers.py` (`_FIXED_NOW = 2024-01-01 08:00 UTC`, `_dt()`,
  `_range()`).
- **The four hardest architecture questions are already resolved** (research Open Qs
  4–7): Python binding, `live_server`+`transactional_db`, ORM seed fixtures,
  session-cookie auth.

## Desired End State

A developer can run a single command —
`DJANGO_DEBUG=True uv run pytest tests/e2e/test_smoke.py` — and a headless Chromium
boots the real EnvBooker app via `live_server` against the Postgres test DB, arrives
authenticated (no login form driven), sees a seeded environment row on the dashboard,
and the test passes deterministically. At that point `/10x-e2e testing-e2e-critical-path`
no longer STOPs: it discovers `pytest-playwright` + `pytest-django` + the `conftest.py`
auth/seed fixtures + `tests/e2e/test_*.py`, and is ready to generate the Risk #2 test.

**Verification**: `uv run pytest --collect-only` lists the e2e tests; the smoke test is
green; `uv run pip` is irrelevant (uv-managed venv); the `/10x-e2e` setup gate passes
its discovery check (manually confirmed by reading what it probes for, not by running
the skill in this change).

### Key Discoveries:

- Harness ownership boundary is the load-bearing fact: **this change builds the
  runner/config/fixtures; `/10x-e2e` builds the two levers and the risk test**
  (`SKILL.md:50-63, 113-122`; research §7).
- `live_server` + `transactional_db` lets the live-server thread see committed rows and
  auto-creates/migrates/tears down `test_envbooker` — no `webServer`, no `dev.sh` at
  test time (research §7 "App-start under Postgres").
- Auth without the UI: create the `User` via ORM, mint a server-side session
  (`django.contrib.sessions`), and inject the `sessionid` cookie with
  `context.add_cookies([...])` (research §7 "Auth without the UI";
  `accounts/urls.py` login route exists but is never driven).
- Duplicate-auto-id hazard (`{{ booking_form.as_p }}` per row) means future reserve
  interactions must be row-scoped via `#env-row-{pk}` — recorded here so the seed
  fixture and smoke test model the addressable shape, even though the reserve hop is
  the skill's job (research top hazard, §Concrete locator candidates).

## What We're NOT Doing

- **The Risk #2 critical-path browser test** (filter → reserve → appears, plus the
  conflict-rejection hop). Owned by `/10x-e2e`; this plan only proves the harness can
  carry it. The decided risk coverage (happy path **+** conflict rejection) is recorded
  in the handoff note so the skill scopes correctly.
- **`tests/e2e/test_seed.py` and the E2E rules file** — created by `/10x-e2e` from its
  `references/`. Do **not** pre-build them; the skill's first-run setup owns them.
- **CI wiring** — the e2e gate enters CI in **Phase 5** (`test-plan.md:112`). Keep the
  smoke test CI-ready (headless, deterministic) but author no workflow YAML.
- **Visual / pixel snapshots** — behavior-only this phase; the optional dashboard
  snapshot is logged as a follow-up (decision: visual deferred).
- **The `role="alert"`/`aria-live` template change** — out of scope for a test-infra
  phase; logged as an a11y follow-up. The future conflict locator uses `getByText`.
- **Edit/cancel (`my_reservations`) coverage** — secondary surface, research-scoped out.
- **Converting `catalog/tests.py` to a package** — unrelated to the harness.

## Implementation Approach

Two phases, each independently verifiable. Phase 1 stands up the dependency + config
floor so pytest discovers Django and the Postgres test DB. Phase 2 adds the two
fixtures the harness (and `/10x-e2e`) depend on — no-UI auth and ORM seed — and proves
all three moving parts (`live_server` + auth cookie + seeded row) cooperate via one
smoke test, then documents the run command, the cookbook entry, and the `/10x-e2e`
handoff. The smoke test is deliberately **not** the risk test: it asserts the harness
boots and authenticates, nothing about the HTMX swap behavior.

## Critical Implementation Details

- **Timing & lifecycle** — `live_server` requires `transactional_db` (not the default
  `db`) so the browser thread sees committed seed rows; pairing them is non-negotiable
  for this harness. The session cookie must be added to the browser context **before**
  the first `page.goto`, and its domain/port must match `live_server.url` (use
  `urlparse(live_server.url).hostname`), or the cookie is silently dropped and the app
  redirects to login.
- **Debug & observability** — every pytest invocation in this harness needs
  `DJANGO_DEBUG=True` in the environment; without it `SECURE_SSL_REDIRECT` returns a 301
  before the view runs and the smoke test fails with a redirect, not an auth error
  (`test-plan.md:179-180`). Document this on the run command so the next developer
  doesn't chase a phantom 301.

## Phase 1: Harness install & config

### Overview

Add the e2e toolchain to dev dependencies, install the Chromium browser binary, and
wire pytest to Django so test collection and a database-touching test run against the
Postgres test DB.

### Changes Required:

#### 1. Dev dependencies + browser

**File**: `pyproject.toml` (and `uv.lock`)

**Intent**: Add the Playwright Python toolchain to a dev dependency group so it is
isolated from runtime deps and reproduced from the lockfile, then install the browser
binary the harness drives.

**Contract**: `pytest-playwright` and `pytest-django` added under `[dependency-groups]`
`dev`, installed via `uv add --group dev pytest-playwright pytest-django`; Chromium
installed via `uv run playwright install chromium`. No runtime (`[project]`)
dependencies change.

#### 2. pytest ↔ Django configuration

**File**: `pyproject.toml`

**Intent**: Tell pytest how to bootstrap Django and where the e2e tests live, so
`uv run pytest` discovers the suite and the Postgres test DB is created/migrated
automatically.

**Contract**: a `[tool.pytest.ini_options]` table setting
`DJANGO_SETTINGS_MODULE = "envbooker.settings"`, `testpaths` including `tests/e2e`, a
`python_files`/`python_functions` convention consistent with `test_*.py`/`test_*`, and a
registered marker for e2e tests. No change to the Django test runner used by
`manage.py test` (the existing unittest suite keeps working unchanged).

**Addendum (2026-06-16, impl-review F1)**: implementation also added `pytest-env`
(dev group) and a `[tool.pytest.ini_options].env` block providing `D:`-default
`DJANGO_SECRET_KEY` + `DATABASE_URL` (so pytest runs without manual secret export),
plus two discovered workarounds — `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64`
(Ubuntu 26.04 / Playwright 1.60 ABI) and `DJANGO_ALLOW_ASYNC_UNSAFE=true` (Playwright
event loop trips Django's sync-from-async guard). `DJANGO_DEBUG=True` is deliberately
*not* baked in and stays on the run command. Documented in test-plan §6.3/§6.6.

### Success Criteria:

#### Automated Verification:

- Dependencies resolve and lock: `uv sync` succeeds with the new dev group.
- Browser installed: `uv run playwright install chromium` completes.
- pytest discovers Django + the suite: `DJANGO_DEBUG=True uv run pytest --collect-only`
  exits 0 with no Django-setup error.
- A trivial DB-touching pytest-django test (using `transactional_db`) passes against the
  Postgres test DB: `DJANGO_DEBUG=True uv run pytest tests/e2e -k <trivial>`.
- Existing unittest suite still green: `DJANGO_DEBUG=True uv run python manage.py test`.

#### Manual Verification:

- The Postgres test database (`test_envbooker`) is created and torn down by the run (no
  leftover DB; no manual `docker compose` step needed beyond the running Postgres).
- `uv.lock` diff contains only the intended additions and their transitive deps.

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human before proceeding to Phase 2.
Phase blocks use plain bullets — the `- [ ]` checkboxes live in `## Progress`.

---

## Phase 2: Fixtures, smoke test & handoff

### Overview

Add the two fixtures the harness and `/10x-e2e` depend on — a no-UI session-cookie auth
fixture and a unique-suffixed ORM seed fixture — and prove the whole harness with one
`live_server` smoke test. Then document the single-test run command, fill the test-plan
cookbook, and record the `/10x-e2e` handoff (including the decided risk coverage and the
deferred follow-ups).

### Changes Required:

#### 1. Auth + seed fixtures

**File**: `tests/e2e/conftest.py` (new)

**Intent**: Provide reusable pytest fixtures so any e2e test arrives authenticated
without driving the login form and with deterministic, collision-free seed data. The
auth fixture mints a server-side Django session for an ORM-created user and yields the
cookie payload; the seed fixture creates a user/environment (and, for the future
conflict path, an existing reservation) through the ORM under `transactional_db`.

**Contract**: an auth fixture that creates a `User` via
`User.objects.create_user(email=..., password=..., first_name=..., last_name=...)`,
builds a session through `django.contrib.sessions`, and returns a cookie dict
(`name="sessionid"`, value, and `domain`/`url` derived from `live_server.url`) suitable
for `context.add_cookies([...])`; a seed fixture using `Environment.objects.create(...)`
and `Reservation.objects.create(..., during=_range(...))` with a **timestamp/uuid suffix
on the environment name** (CLAUDE.md e2e rule) and reusing the `_range()`/`_dt()`/
`_FIXED_NOW` idiom from `reservations/tests/_helpers.py`. Both depend on
`transactional_db` so `live_server` sees the rows.

**Contract (cookie-before-goto, the one non-obvious bit)**:
```python
from urllib.parse import urlparse
# session minted server-side via django.contrib.sessions; then, before any page.goto:
context.add_cookies([{
    "name": "sessionid",
    "value": session_key,
    "domain": urlparse(live_server.url).hostname,  # NOT including the port
    "path": "/",
}])
```

#### 2. Harness smoke test

**File**: `tests/e2e/test_smoke.py` (new)

**Intent**: Prove the three moving parts cooperate — `live_server` boots the real app on
Postgres, the injected session cookie authenticates without the login UI, and the seeded
environment row renders on the dashboard. This validates the harness only; it asserts
nothing about the HTMX filter/reserve swap (that is the Risk #2 test, owned by
`/10x-e2e`).

**Contract**: two `test_*` functions, both headless and never using
`page.wait_for_timeout` (wait on `to_be_visible()` / `to_have_url()`):

- **Authenticated (positive)** — takes `live_server`, `transactional_db`, `page`, and the
  auth + seed fixtures; adds the session cookie to the context, `page.goto(live_server.url)`,
  and asserts the seeded environment name is visible
  (`expect(page.get_by_text(<seeded-name>)).to_be_visible()`).
- **Unauthenticated (negative)** — takes `live_server`, `transactional_db`, `page` (no
  cookie added); `page.goto(live_server.url)` and asserts the gated dashboard redirects to
  the login page (`expect(page).to_have_url(re.compile(r"/login"))`, or assert the login
  form's email field is visible). This proves the seeded row is gated by auth, not public,
  so the positive test's pass is genuinely an authentication result — replacing the manual
  cookie-toggle check. `environment_list` is `@login_required` (`catalog/views.py:21`),
  `LOGIN_URL = "login"`.

#### 3. Run command, cookbook & handoff documentation

**File**: `context/foundation/test-plan.md` (§6.3, and §6.6 a phase note)

**Intent**: Replace the §6.3 "Adding an e2e test" TBD with the now-real harness facts
(location, run command, fixtures, the `DJANGO_DEBUG=True` requirement, row-scoping
hazard) and add a §6.6 phase note recording the `/10x-e2e` handoff: that the skill now
discovers the harness, owns `test_seed.py` + the rules file, and should scope the Risk #2
test to **happy path + conflict rejection**. Record the deferred follow-ups (optional
dashboard visual snapshot; `role="alert"`/`aria-live` on the conflict `<p>`).

**Contract**: §6.3 lists location `tests/e2e/test_*.py`, single-test command
`DJANGO_DEBUG=True uv run pytest tests/e2e/test_<x>.py::test_<y>`, the auth + seed fixture
names, and the `#env-row-{pk}` row-scoping rule for the duplicate-auto-id hazard;
§6.6 gets a dated "Phase 3 — Critical-path e2e harness" entry. No change to §3/§4 status
columns here (the test-plan orchestrator owns those).

### Success Criteria:

#### Automated Verification:

- Smoke test passes headless (both the authenticated and unauthenticated cases):
  `DJANGO_DEBUG=True uv run pytest tests/e2e/test_smoke.py` exits 0.
- Auth is genuinely exercised: the unauthenticated test asserts the gated dashboard
  redirects to `/login` (proves the seeded row is not public).
- Single-test invocation works as documented:
  `DJANGO_DEBUG=True uv run pytest tests/e2e/test_smoke.py::<test>` exits 0.
- Re-run is deterministic: running the smoke test twice in a row both pass (unique
  suffix + test-DB reset prevent collision).
- No `wait_for_timeout` in the e2e tree: `uv run ruff check tests/` clean and a grep for
  `wait_for_timeout` returns nothing.
- Existing unittest suite still green:
  `DJANGO_DEBUG=True uv run python manage.py test`.

#### Manual Verification:

- Reading `.claude/skills/10x-e2e/SKILL.md`'s discovery check against the new tree
  confirms `/10x-e2e` would now pass its setup gate (deps present, `tests/e2e/test_*.py`
  present, `conftest.py` auth fixture present) rather than STOP.
- test-plan §6.3/§6.6 read correctly and the run command is copy-pasteable.

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation. The next action is **not** another
`/10x-implement` phase — it is `/10x-e2e testing-e2e-critical-path` to generate the Risk
#2 test against the now-built harness.

---

## Testing Strategy

### Unit Tests:

- None new. The harness is verified by its own smoke test, not by unit tests; the
  trivial DB test in Phase 1 exists only to prove pytest-django + Postgres wiring.

### Integration Tests:

- The smoke test is the integration check for the harness itself (app boot + auth +
  seed visibility). The behavioral integration of the HTMX flow is covered later by the
  `/10x-e2e`-generated Risk #2 test, not here.

### Manual Testing Steps:

1. With Postgres running (`docker compose up -d`), run
   `DJANGO_DEBUG=True uv run pytest tests/e2e/test_smoke.py` and confirm green.
2. Temporarily remove the cookie injection; confirm the test now fails with a login
   redirect (auth is real), then restore.
3. Run the smoke test twice; confirm both pass (determinism / unique suffix).
4. Read the `/10x-e2e` SKILL.md setup gate and confirm the new tree satisfies it.

## Performance Considerations

Headless Chromium + a per-run Postgres test DB add a few seconds of startup. Acceptable
for a single critical-path harness; the smoke test keeps assertions minimal. Timing of
the future Risk #2 flow is captured as a logged observation, not asserted (decision:
<30s is a UX target, not a gate) — recorded here so the `/10x-e2e` test author follows it.

## Migration Notes

None — additive only. No schema, no data migration. The existing `manage.py test`
unittest suite is untouched and continues to run independently of pytest.

## References

- Research: `context/changes/testing-e2e-critical-path/research.md` (HTMX wiring §1,
  conflict path §2, false-confidence baseline §5, seed shape §6, infra to build §7,
  locator candidates).
- Test plan: `context/foundation/test-plan.md:70` (Phase 3 rollout), `:54` (Risk #2
  proof/anti-pattern), `:91-93` (Postgres-only + planned e2e stack), `:179-180`
  (`DJANGO_DEBUG=True`), `:163` (§6.3 TBD this plan fills).
- Skill boundary: `.claude/skills/10x-e2e/SKILL.md:50-63, 113-122`.
- Seed idiom: `reservations/tests/_helpers.py:5,8,13`;
  `reservations/tests/test_views.py:29-73`.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands.
> Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Harness install & config

#### Automated

- [x] 1.1 Dependencies resolve and lock (`uv sync` with new dev group) — 8403577
- [x] 1.2 Chromium installed (`uv run playwright install chromium`) — 8403577
- [x] 1.3 pytest discovers Django + suite (`pytest --collect-only` exits 0) — 8403577
- [x] 1.4 Trivial `transactional_db` test passes against Postgres test DB — 8403577
- [x] 1.5 Existing unittest suite still green (`manage.py test`) — 8403577

#### Manual

- [x] 1.6 `test_envbooker` created and torn down cleanly by the run
- [x] 1.7 `uv.lock` diff contains only intended additions

### Phase 2: Fixtures, smoke test & handoff

#### Automated

- [x] 2.1 Smoke test passes headless, both cases (`pytest tests/e2e/test_smoke.py`) — 696a880
- [x] 2.2 Unauthenticated test asserts gated dashboard redirects to `/login` — 696a880
- [x] 2.3 Single-test invocation works as documented — 696a880
- [x] 2.4 Re-run is deterministic (two consecutive passes) — 696a880
- [x] 2.5 No `wait_for_timeout` in e2e tree; `ruff check tests/` clean — 696a880
- [x] 2.6 Existing unittest suite still green — 696a880

#### Manual

- [x] 2.7 `/10x-e2e` setup gate would pass on the new tree (read SKILL.md against tree)
- [x] 2.8 test-plan §6.3/§6.6 read correctly; run command copy-pasteable
