# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-06-07 (Phase 1 change opened)

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the team is
   worried about X, and the failure would surface somewhere in <area>" carry
   the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Hot-spot scope used for likelihood weighting: `accounts catalog reservations envbooker templates` (migrations, build output, and `context/` excluded).

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|-------------------------|--------|------------|--------------------------------|
| 1 | Two reservations overlap on the same environment under concurrent requests — the exact collision the product exists to prevent — because the app layer does not cleanly translate the database exclusion-constraint violation into a rejection. | High | Medium | PRD Guardrail §No-double-booking, FR-015 Socratic note; F-01 roadmap risk; interview Q1, Q2; hot-spot dir `reservations/` (23 commits/30d) |
| 2 | The filter → pick → reserve → appears-without-reload flow breaks in a real browser (HTMX swap, JS, or template wiring), while every current partial-render test still passes — the primary <30s success criterion silently fails. | High | Medium | PRD Success Criteria §Primary, US-01 AC ("without a full page reload"); interview Q1, Q2; hot-spot dirs `templates/catalog`, `catalog/` (21 commits/30d) |
| 3 | A user reaches or mutates a reservation or endpoint they are not authorized for — an unauthenticated gated route, an ownership bypass on edit/cancel, or the upcoming admin-override path (S-06) leaking to non-admins (IDOR). | High | Medium | PRD Access Control, Guardrail §ownership-respected; roadmap S-06; interview Q1 (abuse / authorization lens) |
| 4 | An otherwise-valid reservation time crashes with a 500 on a DST gap/fold (single org timezone, twice a year) instead of returning a clean form error. | Medium | Medium | roadmap SPIKE-01; S-02 implementation-review finding F5 (2026-06-03) |
| 5 | An admin edits or deletes an environment out from under active reservations — delete is not blocked when active/upcoming reservations exist, or the modify pre-save warning and post-save change-badge are missing (S-05). | Medium | Medium | roadmap S-05; PRD FR-006, FR-007; hot-spot dir `catalog/` (21 commits/30d) |
| 6 | A regression merges to main because no gate runs the existing suite and no type checker guards untyped drift — every other risk's protection is only as strong as the gate that enforces it. | High | High | `CLAUDE.md` tripwire (CI unwired, no linting tools); `tech-stack.md` (github-actions committed); roadmap Q-01 |

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|------|-----------------------------|----------------|--------------------------------------|-----------------------|-----------------------|
| #1 | A second overlapping reservation attempted against an existing one is rejected with a user-facing conflict message naming the other owner/window — never a 500, never a silently committed second row. | "Happy-path sequential overlap rejection implies the concurrent/constraint-violation path also rejects cleanly." | The write entry points for create and edit; how the DB exclusion-constraint violation surfaces (IntegrityError) and where it is translated to a form/user error; whether a true concurrent test (TransactionTestCase) is warranted vs. simulating the integrity error. | integration | Asserting only the model-layer reject that already has tests; mirroring the production overlap query in the test's expectation (oracle problem). |
| #2 | After a filter and a reserve action, the new reservation row is visible in the live DOM without a full page reload, and a conflicting attempt shows the named-conflict message in-page. | "A passing partial-render/view test implies the HTMX swap works in a real browser." | The HTMX request/response wiring (trigger, target, swap), the partial vs. full-page template boundary, and which screen is the single critical one for an optional visual check. | e2e (browser) | Re-testing partial rendering at the view layer and calling it e2e; pixel-snapshotting every page instead of asserting the one behavior. |
| #3 | Each gated route redirects/denies the unauthenticated; edit/cancel reject a non-owner; admin-only actions reject a non-admin — verified per route, not assumed from one. | "Authenticated implies authorized." / "One guarded view implies the sibling views are guarded too." | The full set of gated routes and their guard mechanism (decorator / mixin / queryset-ownership filter); the admin-vs-owner boundary for S-06 when it lands. | integration / view | Testing only the happy-path owner; copying the view's own permission check into the assertion instead of asserting the observable 403/404/redirect. |
| #4 | A reservation submitted with a non-existent local time (DST gap) yields a clean, user-visible form error (or a defined snap-forward), never an unhandled 500. | "`make_aware` on user input is safe." / "Only the form's `clean()` is affected and not the gap math elsewhere." | Where local→aware conversion happens on the input path, and whether the same gap/fold hazard exists in duration/next-free-window math. | unit | Patching only the one `make_aware` call and missing the wider calendar-math class the spike exists to map. |
| #5 | Delete is refused while active/upcoming reservations exist; a modify with affected reservations surfaces the warning and the post-save change-badge. | "Notify-not-block on modify means no guard is needed." / "Delete-blocking is the DB's job." | The admin env-catalog write paths (S-05, not yet built); how "active/upcoming reservation exists" is computed; badge persistence rule. | integration / view | Writing tests before S-05 ships (no surface yet) — this phase waits for the slice; asserting the warning string instead of the blocked side-effect. |
| #6 | A pull request with a failing test or a type error cannot merge — the suite and the type check run in CI and block. | "Tests existing implies tests are enforced." | The current gap between `manage.py test` locally and CI; the mypy + django-stubs baseline appropriate for the custom user model and Postgres range/exclusion fields (Q-01 unknowns). | gates | Wiring a gate that runs but does not block; chasing `--strict` everywhere and stalling instead of a green first-party baseline. |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|------------|-----------------|---------------|------------|--------|---------------|
| 1 | No-overlap hardening | Prove a concurrent or constraint-violating overlapping reservation is rejected with a clean user-facing error — not a 500, not a silent second row — on both the create and edit write paths. | #1 | integration (+ concurrency, scoped by research) | complete | `context/changes/testing-no-overlap-hardening/` |
| 2 | Authorization & endpoint access | Prove every gated route enforces authentication and ownership, and that admin-only actions reject non-admins. | #3 | integration / view | not started | — |
| 3 | Critical-path e2e | Prove the find → filter → reserve → appears-without-reload flow works in a real browser within the 30s success criterion. | #2 | e2e (browser; this phase **builds** the Playwright harness — the `/10x-e2e` skill discovers but does not create it) + optional single-screen visual review | change opened | `context/changes/testing-e2e-critical-path/` |
| 4 | Calendar reliability | Turn the DST gap/fold 500 into a graceful, user-visible outcome and map the calendar edge-case class. | #4 | unit | not started | — |
| 5 | Quality-gates wiring | Lock the floor: stand up the CI harness so the unit+integration suite (and the Phase 3 e2e gate) block merges, and adopt the mypy/django-stubs gate defined by roadmap Q-01. Ratchets over Phases 1–4. | #6 | gates | not started | — |

**Status vocabulary** (fixed — parser literals): `not started` → `change opened` → `researched` → `planned` → `implementing` → `complete`.

Order rationale: the team chose no-overlap to lead (the product's core
guarantee); authorization follows (strongly multi-selected in the interview);
e2e is third (the entirely-missing layer, but the heavier infra is owned by
Module 3 Lesson 4); calendar reliability is fourth (a real defect but not a
user-flagged top fear); the gate lands last so it ratchets over everything
added, matching Q-01's "after the S-02 baseline" sequencing.

## 4. Stack

The classic test base for this project. AI-native tools (if any) carry a
`checked:` date so future readers can see which lines need re-verification.

| Layer | Tool | Version | Notes |
|-------|------|---------|-------|
| unit + integration | Django test runner (`unittest`) | Django 6.0.5 | `uv run python manage.py test`; 87 `test_*` methods across the three apps. No pytest configured. |
| database (test) | PostgreSQL | 17 (local), Railway (prod) | Postgres-on-Postgres parity is mandatory — the `ExclusionConstraint` / `btree_gist` no-overlap rule is Postgres-only; SQLite is unsupported even in tests. |
| concurrency | Django `TransactionTestCase` | Django 6.0.5 | Needed if Phase 1 research justifies a true concurrent-insert test (default `TestCase` wraps each test in one transaction and cannot exercise the race). |
| e2e | **Playwright Python** — `pytest-playwright` + `pytest-django` (planned, Phase 3) | sync API | No browser layer exists yet. Phase 3 **builds** the harness: install + `playwright install`, pytest↔Django config, app-start via pytest-django `live_server` (+ `transactional_db`) on the Postgres test DB, auth via an injected `sessionid` cookie fixture, ORM seed fixtures. The `/10x-e2e` skill (M3 L4, adapted to Python in this repo) *discovers* this infra and STOPs if absent — it only creates the `tests/e2e/test_seed.py` + E2E-rules levers, not the runner/config. |
| visual review | none yet — see §3 Phase 3 | — | Selective, 1–2 critical screens only (the dashboard), never every page. |

**Stack grounding tools (current session):**
- Docs: none — Context7 / framework docs MCP not exposed in this session; stack facts taken from local manifests (`pyproject.toml`, `.python-version`, `docker-compose`) and `CLAUDE.md`; checked: 2026-06-07
- Search: WebSearch available — not used this pass; the stack is fully grounded by local config; checked: 2026-06-07
- Runtime/browser: none — no Playwright / browser MCP in this session; browser tooling arrives with Module 3 Lesson 4; checked: 2026-06-07
- Provider/platform: Linear MCP available (issue tracking); GitHub-equivalent via self-hosted Gitea CLI (`tea`) — relevant when Phase 5 wires the CI gate; checked: 2026-06-07

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required after §3 Phase <N>" means the gate is enforced once that rollout
phase lands; before that, the gate is planned.

| Gate | Where | Required? | Catches |
|------|-------|-----------|---------|
| lint + typecheck (mypy + django-stubs) | local + CI | required after §3 Phase 5 (Q-01) | type drift, untyped first-party code |
| unit + integration | local + CI | present locally now; CI-enforced after §3 Phase 5 | logic regressions, no-overlap and authorization breaks |
| e2e on critical flow | CI on PR | required after §3 Phase 3 | broken find-and-reserve / HTMX no-reload path |
| post-edit hook | local (agent loop) | recommended (config owned by M3 L3) | regressions at edit time |
| multimodal visual review | CI on PR | optional — dashboard screen only | rendering issues a partial-level test misses |
| pre-prod smoke | between merge and prod (Railway) | optional | environment-specific failures on deploy |

**Phase 5 ↔ roadmap Q-01.** No CI exists today (verified 2026-06-08: no
`.github`/`.gitea`/`.forgejo` workflows, no lint/type tooling in
`pyproject.toml`). Q-01 owns the type-hint retrofit and the mypy + django-stubs
*gate definition* (it is typing-only and excludes lint/test wiring). Phase 5
stands up the CI harness and enforces the unit+integration suite (and the
Phase 3 e2e gate), consuming Q-01's typecheck rather than redefining it — so
neither is redundant. Sequence Q-01 before or with Phase 5; whichever lands
first stands up the harness, the other plugs in. This plan only *names* these
gates; the YAML/config lands in each phase's downstream change, not in
`/10x-test-plan`.

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once the
relevant rollout phase ships; before that, it reads "TBD — see §3 Phase <N>."

**Test file layout.** Each app keeps its tests in a `<app>/tests/` package
(`__init__.py` + `test_*.py`), split **by surface under test**:
`test_models.py`, `test_services.py`, `test_forms.py`, `test_views.py`.
Classify by *what is exercised* (a model/constraint, a service function, a
form, a view) — never by a unit-vs-integration judgment. That boundary is
deliberately **not** used as the split axis here, because DB-touching tests
blur it (a model `.save()` or an overlap check is both). The default test
runner discovers `test_*.py` in the package automatically; no config change.
Conversion is incremental: `reservations/` converted as the first sub-phase of
§3 Phase 1; `catalog/` and `accounts/` convert when a phase next touches them
or they outgrow a single `tests.py`. Until an app is converted, its `tests.py`
stays as-is.

### 6.1 Adding a unit test

- **Location**: `<app>/tests/test_<surface>.py` matching what is exercised (e.g. `test_services.py` for a service function, `test_models.py` for model/constraint behavior). See *Test file layout* above.
- **Naming**: `class <Thing>Test(TestCase)` with `def test_<behavior>` methods.
- **Reference test**: `reservations` `ComputeEndTest` (service logic, no DB writes beyond setup) and `EnvironmentModelTest` — in `reservations/tests/test_services.py` / `reservations/tests/test_models.py`.
- **Run locally**: `uv run python manage.py test <app>`.

### 6.2 Adding an integration test

- **Location**: the same `<app>/tests/` package, in the `test_<surface>.py` matching the entry point under test (usually `test_views.py`). Use `TestCase`, or `TransactionTestCase` when a real DB transaction/constraint or concurrency is under test.
- **Cross-app placement**: most integration tests here span apps (a `Reservation` needs a catalog `Environment` and an accounts `User`). File the test under the app that owns the **entry point / behavior under test** — the view, form, or service being exercised — *not* under every app whose models it sets up. Existing precedent: `DashboardGroupingTest` creates reservations but lives in catalog (the dashboard is the surface); `ReservationCreateViewTest` creates environments + users but lives in reservations (the write path is the surface). Only if a flow has genuinely no single owning surface should you reach for a project-level `tests/` package (also discoverable by the default runner) — nothing in the current scope needs this.
- **Policy**: exercise the real DB (Postgres) and the real view/form; do not mock internal modules. Assert the observable side effect (row written/not written, status code, message), not an internal call.
- **Reference test**: `reservations` `ReservationCreateViewTest` and `ReservationNoOverlapTest` — in `reservations/tests/test_views.py` / `reservations/tests/test_models.py`.
- **Run locally**: `uv run python manage.py test <app>` (or `manage.py test` for the whole suite).

### 6.3 Adding an e2e test

- TBD — see §3 Phase 3.

### 6.4 Adding a test for a new endpoint / view

- TBD — see §3 Phase 2 (authorization patterns) and the §6.2 reference for the write-path shape.

### 6.5 Adding an authorization / ownership test

- TBD — see §3 Phase 2. Seed pattern today: `reservations/tests/test_views.py::ReservationEditViewTest::test_non_owner_404` and `::test_auth_required`.

### 6.6 Per-rollout-phase notes

**Phase 1 — No-overlap hardening (2026-06-09)**

- `reservations/tests/` package layout landed. Shared fixtures live in `_helpers.py` (leading underscore keeps the runner from treating it as a test module). When splitting a monolith `tests.py`, consolidate near-duplicate helpers into `_helpers.py` first — the deduplication is easiest while they're side-by-side.
- **Constraint-name-pin pattern** (`ReservationConstraintNamesTest` in `test_models.py`): when a view or service detects a DB constraint violation by matching a literal constraint name in the error text, add a no-DB test asserting that name is present in `Model._meta.constraints`. The docstring must cite the views/lines that depend on the name. This turns a silent rename-then-500 regression into an immediate test failure.
- `SECURE_SSL_REDIRECT = True` is active when `DEBUG=False`. Run tests with `DJANGO_DEBUG=True` (or export it in the shell) to prevent all view test requests from getting a 301 before they reach the view decorator.
- `DJANGO_DEBUG=True` must be set when running the test suite locally (disables `SECURE_SSL_REDIRECT`). Add this to your shell profile or `.env.example` annotation so the next developer doesn't chase phantom 301s.

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout (Phase 2 interview, Q5). Future
contributors should respect these unless the underlying assumption changes.

- **Django built-ins, the ORM, and the `/admin` UI** — trust the framework; do not re-test it. Re-evaluate only if we subclass or override framework behavior in a load-bearing way. (Source: Phase 2 interview Q5.)
- **The org-domain sign-up rule** — already well covered (`accounts/tests.py`: domain validator, case-insensitive matching, empty-table case). No further budget unless the rule changes. (Source: Phase 2 interview Q5.)
- **Generated migrations** — the migration system is the test; do not author tests against migration files. (Source: Phase 2 interview Q5.)
- **Exhaustive UI snapshot tests** — brittle and low-signal; reserve visual review for 1–2 critical screens (the dashboard). (Source: Phase 2 interview Q5.)
- **Cloud-provider / Railway outage** — high impact but low likelihood and not test-shaped; belongs to observability/alerting, not the suite.

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-06-07
- Stack versions last verified: 2026-06-07
- AI-native tool references last verified: 2026-06-07

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
