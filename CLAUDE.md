# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: EnvBooker

Django 6.0.5 web app on **Python 3.14** (see `.python-version`), managed with **uv** (not pip/poetry). Django config package at `envbooker/`; domain logic split across three apps: `accounts`, `catalog`, `reservations`. **Railway** is the deploy target (see `railway.toml` and `context/foundation/infrastructure.md`). Product & stack rationale live in `context/foundation/`.

### Common commands

```bash
uv sync                              # install/refresh dependencies from uv.lock
uv add <pkg>                         # add a runtime dependency
./dev.sh                             # one-shot: starts Postgres, migrates, runs server
uv run python manage.py runserver    # dev server at http://127.0.0.1:8000
uv run python manage.py migrate      # apply pending migrations
uv run python manage.py makemigrations <app>  # generate migrations after model changes
uv run python manage.py createsuperuser       # bootstrap an admin user
uv run python manage.py test                  # run the full Django test suite
uv run python manage.py test <app>            # run tests for a single app
uv run python manage.py test reservations.tests.test_models              # single file
uv run python manage.py test reservations.tests.test_models.SomeTestClass  # single class
```

### Local dev setup

Local dev uses **Postgres** (not SQLite) for full parity with Railway prod (exclusion constraints require it). Start Postgres first:

```bash
docker compose up -d              # start Postgres 17 on localhost:5432
```

Then export the three required env vars (copy from `.env.example`):

```bash
export DJANGO_SECRET_KEY=any-local-secret-value
export DJANGO_DEBUG=True          # optional; defaults to False if unset
export DATABASE_URL=postgres://envbooker:envbooker@localhost:5432/envbooker
```

Run migrations and start the dev server:

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

## Architecture

### App layout

| App | Responsibility |
|-----|---------------|
| `accounts` | Custom `User` model (email-as-identity, no `username`), `AllowedEmailDomain` org-restriction, signup/login views |
| `catalog` | `Environment` model — bookable environments with `name`, `version`, `purpose`, `project`, `use_case_tag`, and an `owner` FK |
| `reservations` | `Reservation` model — links `owner` + `environment` with a `DateTimeRangeField(during)`; enforces no-overlap via a Postgres GiST exclusion constraint |

### Auth model

`accounts.User` extends `AbstractUser` with `username=None`; `email` is the `USERNAME_FIELD`. Uniqueness is enforced both at the DB level (`UNIQUE`) and case-insensitively via a `UniqueConstraint(Lower("email"))`. Sign-up is gated by `AllowedEmailDomain` — if any rows exist, only matching email domains are accepted. Domains are stored and matched lowercase.

### Booking constraint

`Reservation` uses `django.contrib.postgres.constraints.ExclusionConstraint` with `btree_gist`. This is **Postgres-only** — `settings.py` raises `ImproperlyConfigured` at startup for any non-Postgres `DATABASE_URL`. SQLite is not supported even in development.

### Service layer

Both `catalog` and `reservations` contain a `services.py`. Views are thin — all queryset composition, N+1 prevention, conflict detection, and domain rules live in the service layer. Cross-module calls (e.g. `catalog.services.build_row_context` called from `reservations.views`) are intentional. `reservations/services.py` also defines `MAX_DURATION` and free-window helpers.

### Templates & static files

Global templates live in `templates/` (configured in `TEMPLATES[0]["DIRS"]`). `whitenoise` serves static files in production via `CompressedManifestStaticFilesStorage`; `STATIC_ROOT = staticfiles/`. Login/logout redirects are `login` → `home`.

`htmx.min.js` is vendored at `static/vendor/` and powers the filter→pick→reserve partial-rendering flow (no full page reload). HTMX requests hit the same Django views; partial-template responses are distinguished by the `HX-Request` header or separate URL patterns.

### Project-specific tripwires

- **The uv-managed `.venv` has no `pip`**, so `pip-audit` cannot use `PIPAPI_PYTHON_LOCATION`. Audit via:
  `uv export --no-hashes | grep -v '^#' | pip-audit -r /dev/stdin`
- **Railway deploy** is defined in `railway.toml`: Railpack builder (auto-detects `uv.lock` + `.python-version`), runs `collectstatic → migrate → gunicorn` on start. No Dockerfile needed.
- **No linting tools** are configured in `pyproject.toml` yet — add ruff or similar before wiring up CI.
- **`reservations/tests/` is a package** (not a flat `tests.py`). Files: `test_models.py`, `test_forms.py`, `test_services.py`, `test_views.py`. Shared fixtures live in `_helpers.py` (fixed anchor: 2024-01-01 08:00 UTC).

## Course context

This is a **10xDevs 3.0** course project (`10xdevs3`), configured for Claude Code via `@przeprogramowani/10x-cli` (v1.6.0). Lesson artifacts (prompts, skills, rules, configs) are fetched from the course platform and written into `.claude/`.

## Fetching lesson content

```bash
10x list                          # browse available modules and lessons
10x get <ref>                     # fetch a lesson (e.g. m1l1 = Module 1 Lesson 1)
10x get <ref> --tool claude-code  # explicit tool override
10x get <ref> --dry-run           # preview what would be written
10x doctor                        # validate auth and connectivity
```

Artifacts land in `.claude/prompts/`, `.claude/skills/`, etc. The manifest tracking applied lessons is at `.claude/.10x-cli-manifest.json`.

## Course schedule

| Module | Title | Release |
|--------|-------|---------|
| m0 | Prework | unlocked |
| m1 | Agentic Environment | 2026-05-18 |
| m2 | 10xDevs Workflow | 2026-05-25 |
| m3 | AI Development Quality & Maintenance | 2026-06-01 |
| m4 | Large Scale & Legacy Projects | 2026-06-08 |
| m5 | AI-Native Teamwork | 2026-06-15 |

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 3, Lesson 2

Lesson 2 is about **writing tests that actually protect code** — not just maximise coverage. The oracle problem and vibe-testing anti-patterns explain why LLM-generated tests fail on real code; the risk-first quality contract from Lesson 1 is the fix.

```
context/foundation/test-plan.md (§3 Phased Rollout)
        │
        ▼  (one rollout phase at a time)
   /10x-research  ──►  research.md  (oracle source: what code should do, not what it does)
        │
        ▼
   /10x-plan  ──►  plan.md  (cost × signal, two-layer strategy, ordered phases)
        │
        ▼
   /10x-implement  or  /10x-tdd   ──►  working tests + §6 cookbook update
```

`/10x-tdd` is an **optional test-first mode**, not a replacement for the chain. It reads the same `plan.md`, writes to the same `## Progress` section, and covers the same phases as `/10x-implement`. Use it only when you can name the first failing assertion before writing any code.

### Task Router — Where to start

| Skill / Prompt | Use it when |
| --- | --- |
| `/10x-research` | Before writing any test for a risk. Research produces the oracle — what behaviour a test must prove — from sources (PRD, tech-stack, docs), not from the implementation shape. Also reveals whether a risk is already covered or has two separate faces (one safe, one real). |
| `/10x-plan` | Research is done. Plan decomposes the risk into ordered phases: environment setup first, then rules that depend on it, then hermetic stubs for failures that real infra cannot trigger, then cookbook update. Each phase names the behaviour it asserts and the regression it catches. |
| `/10x-implement` | Default executor for plan phases. Use for environment setup, existing code, scaffolding, and any phase where you cannot define a red test before writing code. |
| `/10x-tdd` | Optional. Use instead of `/10x-implement` for a phase where you can name the first red test in one sentence. Agent writes the failing test first, then the minimal code to green it, then refactors. Stops at the assertion before touching the implementation — that pause is the point. |
| `m3l2-ad-hoc-testing` prompt | You have a single file and want tests now, without the full research→plan→implement cycle. The prompt forces oracle-from-sources (reads PRD + TECH_STACK before asserting), behavioural assertions, edge cases from risk, and a regression table. Use it knowing you are trading depth for speed. |

### When to use `/10x-tdd` vs `/10x-implement`

The deciding question: *Can you name the first red test in one sentence?*

Good conditions for `/10x-tdd`:
- "promuje wyłącznie drafty w stanie `accepted`, a `pending`/`rejected` nigdy nie trafiają do talii"
- "zwraca `ok: true` i loguje `orphan_review_state`, gdy upsert stanu powtórek padnie w trakcie zapisu"
- "zwraca 401, gdy użytkownik nie ma dostępu do kursu"
- "resetuje interwał powtórki do jednego dnia, gdy ocena wynosi 0"

Each of these names an observable outcome, not an internal detail. If you cannot produce a sentence like this, stay on `/10x-implement` or return to `/10x-research`.

`/10x-tdd` is **not suited** for: environment setup, CI/CD config, documentation, thin wiring where the test would just rewrite the implementation, or a spike where you are still discovering the contract.

You can mix both modes in one plan:

```
/10x-implement <change-id> phase 1   # environment
/10x-tdd       <change-id> phase 2   # contract (new code)
/10x-tdd       <change-id> phase 3   # contract (API endpoint)
/10x-implement <change-id> phase 4   # cookbook + plan sync
```

Both write progress to the same `## Progress` section in `plan.md`.

### Two-layer test strategy (cost × signal)

For each risk, pick the **cheapest test that gives a real signal**. Do not default to e2e "because it's safest", and do not chase coverage percentage.

| Layer | When to use | When NOT to use |
| --- | --- | --- |
| Integration (real DB / real infra) | The rule involves DB constraints, cascades, real SQL, or unique constraints that a mock would lie about. | Auth flows gated by RLS that belong to a separate phase; anything where setup cost exceeds signal value. |
| Hermetic (stub client) | Partial failures that real infra cannot trigger easily (e.g. second operation in a sequence fails). | Rules that depend on actual DB state — a stub will lie about constraint violations and cascades. |

A non-atomic save sequence (multiple independent operations without a transaction) means: write hermetic tests for partial-failure branches, not integration tests that force a mid-sequence error.

### Oracle rules

- The oracle — what the code *should* do — must come from sources: PRD, docs, tech-stack constraints, domain knowledge. It must **not** come from reading the implementation.
- If the implementation has a bug, copying its output as the expected value produces a mirror test that passes against the bug.
- When sources do not resolve the expected behaviour unambiguously, **stop and ask** rather than guessing.
- Research's job is to surface the oracle before any test is written.

### Vibe-testing anti-patterns to avoid

| Anti-pattern | How it looks | What to do instead |
| --- | --- | --- |
| Mirror implementation | Assertion computes the expected value with the same logic as the tested code. | Assert against a value derived from the oracle (PRD / domain rule), not from the implementation. |
| Happy paths only | Tests only pass valid inputs; edge cases absent. | Add at least one edge case per risk: `null`, empty, dependency error, invalid input. |
| Redundant copies | Six nearly identical tests checking the same absence of a sentinel. | One parameterised test (`it.each`) per property; each test catches a different regression. |

### Mutation testing (Stryker) — selective quality gate

Coverage says "this line was executed". Mutation score says "would a test fail if I broke this line?" Use Stryker as a **selective gate** after a risk phase, not as a CI gate on every commit.

Workflow:
1. Tests pass for the risk phase.
2. Run `npx stryker run --mutate "path/to/file.ts"` (narrow scope to the changed module).
3. Open the HTML report; find survived mutants.
4. For each survived mutant ask: "Would this change hurt a user or the business?"
   - Yes → add an assertion that kills the mutant.
   - No (equivalent mutant or cosmetic change) → ignore consciously.
5. Do not chase 100% mutation score. A test that pins implementation details to kill a cosmetic mutant is itself a vibe test.

The integration gate can stay **ad hoc** (not on every commit) when running local infra is expensive. Mark it accordingly in `test-plan.md §4`.

### Lesson boundaries

- Do not configure hooks, hook lifecycle, or debugging hooks. That is Lesson 3.
- Do not configure MCP servers, Playwright API, e2e code, or multimodal scenario code. That is Lesson 4.
- Do not run the bug-to-fix-to-regression-test workflow. That is Lesson 5.
- Do not author CI/CD pipelines from scratch. That is Module 1 Lesson 5 / Module 2 Lesson 5.
- Do not run `/10x-test-plan` to change the risk strategy. That is Lesson 1. Use `/10x-test-plan --status` to read current state.
- Do not write tests without a research step unless using the ad-hoc prompt with full awareness of its trade-offs.

### Paths used by this lesson

- `context/foundation/test-plan.md` — §3 rollout state; §6 cookbook (filled in as phases ship)
- `context/changes/<change-id>/research.md` — oracle source per rollout phase
- `context/changes/<change-id>/plan.md` — ordered phases with `## Progress` as execution state
- `.claude/prompts/m3l2-ad-hoc-testing.md` — ad-hoc file-level testing prompt

<!-- END @przeprogramowani/10x-cli -->
