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

### Type checking

```bash
# Run the type checker (dummy env vars — no live DB needed for mypy)
DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .

# After a fresh clone or after adding a team member: register the pre-commit hook
uv run lefthook install
```

The `pre-commit` hook (`lefthook.yml`) runs the full mypy pass before every commit. It requires no live Postgres — `dj_database_url.config()` parses the URL without connecting. New contributors must run `uv run lefthook install` once after cloning.

### Linting and formatting

**ruff** handles both lint and format (one binary, no separate tools):

```bash
uv run ruff check .              # lint the whole tree (migrations excluded)
uv run ruff format --check .     # check formatting without writing
uv run ruff format .             # reformat in-place
uv run ruff check --fix .        # lint + apply safe auto-fixes
```

Two enforcement layers:

- **Pre-commit** (`lefthook.yml`): `format` and `lint` commands run over staged `.py` files with `stage_fixed: true`, so fixable issues are auto-healed and re-staged before the commit lands. A non-fixable finding blocks the commit.
- **Per-edit agent hook** (`.claude/settings.json`): a `PostToolUse` hook fires on every `Write`/`Edit`, runs ruff format + check --fix on the edited `.py` file, and feeds results back into the agent's context — reformatted files are announced (prompting a re-read); residual non-fixable findings are surfaced as blocking. Both signals use one mechanism — a JSON result on stdout (`additionalContext` for the note, `decision: block` + `reason` for the finding).

Hook script lives at `.claude/hooks/ruff-post-edit.sh`; it reads the edited path from the tool payload with `python3` (no `jq` dependency). Migrations (`**/migrations/**`) are excluded from all ruff passes.

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

### packages/code_reviewer

An **independent** uv project (own `pyproject.toml`, `uv.lock`, `.venv`) wrapping the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) for a future automated code-review agent. It is **not** a uv workspace member and is not a dependency of the root `envbooker` project — this keeps `claude-agent-sdk` out of the Django app's Railway deploy image. Root `pyproject.toml`'s `[tool.mypy]` excludes `^packages/` accordingly (its own dependencies aren't installed in the root `.venv` that the repo-wide mypy gate runs against). See `packages/code_reviewer/README.md` for install/run/auth. Ruff still applies repo-wide: the subpackage has no `[tool.ruff]` table of its own, so ruff's config discovery walks up to root's.

### Project-specific tripwires

- **The uv-managed `.venv` has no `pip`**, so `pip-audit` cannot use `PIPAPI_PYTHON_LOCATION`. Audit via:
  `uv export --no-hashes | grep -v '^#' | pip-audit -r /dev/stdin`
- **Railway deploy** is defined in `railway.toml`: Railpack builder (auto-detects `uv.lock` + `.python-version`), runs `collectstatic → migrate → gunicorn` on start. No Dockerfile needed.
- **ruff** is configured in `pyproject.toml` (`[tool.ruff]`) and enforced at two layers: a per-edit agent hook (`.claude/hooks/ruff-post-edit.sh`) and the Lefthook `pre-commit` gate. Migrations are excluded.
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

## 10xDevs AI Toolkit - Module 3, Lesson 4 (E2E Tests)

**For E2E tests, use the `/10x-e2e` skill.** It is the single source of truth
for the workflow — risk → seed test + rules → generate → review against the five
anti-patterns → re-prompt → verify. The skill's `references/` carry the full
rules, anti-patterns, seed pattern, and prompt-template.

A few hard rules that hold even before you invoke the skill:

- **Locators:** `getByRole` / `getByLabel` / `getByText` first; `getByTestId`
  only when accessibility attributes are ambiguous. Never CSS selectors, XPath,
  or DOM structure.
- **Never `page.waitForTimeout()`.** Wait for state: `toBeVisible()`,
  `waitForURL()`, `waitForResponse()`.
- **Test independence + cleanup.** Each test runs standalone — its own setup,
  action, assertion, and cleanup; unique ids (timestamp suffix) so parallel runs
  and re-runs don't collide.

Two boundaries to keep straight:

- **DOM (snapshot) is the default.** Vision (`--caps=vision`) is a supplement for
  visual-only risks (layout, z-index, animation); for pixel regression prefer
  deterministic tools (`toMatchSnapshot`, Argos, Lost Pixel). VLM model
  selection/cost is a debugging topic (Lesson 5), not testing.
- **Healer helps on selectors, harms on logic.** A changed selector → healer
  re-finds it (route through PR review). A changed business behavior → healer
  masks the bug; that failing-test-to-fix case is Lesson 5.

<!-- END @przeprogramowani/10x-cli -->
