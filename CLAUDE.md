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

## 10xDevs AI Toolkit - Module 3, Lesson 3

Lesson 3 is about **hooks** — turning the quality gates from Lesson 1 and the tests from Lesson 2 into automatic, deterministic checks that fire while the agent works. A hook runs outside the model, so it survives context compression, instruction changes, and the model "forgetting". The payoff for agentic hooks specifically: a `PostToolUse` check can feed its result back into the agent's context, so the agent fixes trivial errors (formatting, a missing import, a wrong type) on its own in the next iteration instead of you discovering them minutes later.

```
context/foundation/test-plan.md  (§4 Quality Gates: which check, required when)
        │
        ▼  (assign each gate to the cheapest layer that still gives signal)
   per-edit (agent hooks)  →  pre-commit (git hooks)  →  pre-push  →  CI
        │ lint, format, scoped tests          │ staged       │ heavier    │ integration
        ▼
   exit code + stdout  →  additionalContext  →  agent reacts next turn
```

### Task Router — Which layer for this check

| You want to | Do this |
| --- | --- |
| React the instant the agent edits a file | A per-edit hook (`PostToolUse` matcher `Write\|Edit` in Claude Code). Right for fast checks: lint/format, and scoped tests on risk-area files. This is the **only** layer that can hand feedback to the agent mid-session. |
| Run only the tests that depend on the edited file | Parse the path from the hook's stdin (`jq -r .tool_input.file_path`) and run your runner's related-tests mode (`vitest related "$FILE" --run`, `jest --findRelatedTests $FILE`). Gate it on whether the file is a risk area in `test-plan.md`; don't run tests on every helper or config edit. |
| Catch changes that bypassed the agent (manual edits, a teammate's commit) | A pre-commit git hook (Lefthook or Husky+lint-staged) over staged files: lint + typecheck, and tests on staged risk files. |
| Run heavier checks before code leaves the machine | Pre-push: full typecheck or a broader test set. Anything too slow for per-edit moves here. |
| Decide where a given gate belongs | Ask: is it fast enough (a few seconds) for per-edit, or should it wait for commit/push/CI? Slow checks block the agent loop on every edit — push them up a layer. |
| Use the same hook across tools | The trigger → matcher → handler → signal pattern is the same in Cursor, Codex, Windsurf, and Copilot; only the config file and event names change. See the cross-tool table below. |

### Hook lifecycle — the universal pattern

Every tool's hooks follow four steps:

1. **Trigger** — an event in the tool (e.g. the agent just saved a file: `PostToolUse`).
2. **Matcher** — a filter deciding whether this hook runs (tool name like `Write`/`Edit`, file type, or a name pattern).
3. **Handler** — the action that runs, usually a shell command.
4. **Signal** — the result returns to the tool. The exit code says pass/fail; stdout can flow into the agent's context as feedback.

### Exit codes and the feedback loop

- **0** — success; the hook passed, continue.
- **2** — blocking error; the agent sees the feedback and should react.
- **anything else** — non-blocking error; logged, but does not interrupt work.

On a blocking failure, stdout flows into the agent's context (in Claude Code via `additionalContext`, capped at 10,000 characters; other tools have similar mechanisms with their own limits). That is why the agent can self-correct: it sees the concrete message — missing type, unimported module, badly formatted line — not just "something failed".

The boundary: the agent reliably fixes **trivial** corrections on its own. When a test fails because of wrong business logic, the hook surfaces it but the agent may not diagnose the real cause — it says "something is off" and tries a trivial fix. If that does not resolve in one or two tries, the signal comes back to you, and the problem may deserve its own change-id with the full `/10x-new → /10x-research → /10x-plan → /10x-implement` workflow.

### Three local layers (plus CI)

| Layer | Catches | Timing |
| --- | --- | --- |
| Per-edit (agent hooks) | Formatting, simple type errors, failing unit tests on risk files. Only layer that feeds the agent mid-work. | ms–s |
| Pre-commit (git hooks) | What slipped past per-edit: manual edits, files changed outside the hook, checks too slow for per-edit. Operates on staged files. | s |
| Pre-push | Heavier checks before pushing to remote (full typecheck, broader test set). | s–min |
| CI | Integration problems, cross-module dependencies, checks needing infra unavailable locally. | min |

Local layers do **not** replace CI — CI stays the key verification for shared repo state and environments you don't control. But each local layer that catches an error is one fewer CI round-trip. You don't need all layers from day one: start with one per-edit hook (lint) and one commit gate, add layers as you see what escapes. The quality gates in `test-plan.md §4` decide which checks are worth automating and when; a plan may legitimately defer per-edit hooks if the cost/signal ratio isn't there yet.

### Key rules

- Keep per-edit hooks fast. If a check takes more than a few seconds, move it to commit, push, or CI — a slow per-edit hook blocks the agent loop on every edit. Lint/format are ideal per-edit; full typecheck is often a commit gate in larger projects.
- Run scoped tests, not the whole suite, per edit — only tests related to the edited file, and only when that file is a risk area in `test-plan.md`.
- `related` is a subcommand, not a flag (`vitest related`, not `--related`). Use `--run` so the hook terminates instead of entering watch mode.
- `PostToolUse` fires once per tool use; three edits in one turn fire it three times independently — there is no built-in aggregation.
- The git hook tool (Lefthook vs Husky+lint-staged) is an implementation detail; the rule is the same — run checks on staged files before commit. If Husky already works, don't migrate.
- **Context injection is not universal.** Claude Code, Cursor, Codex, and Copilot (in VS Code) can pass a hook's result to the agent; Windsurf cannot — it can block (exit 2) but can't tell the agent what went wrong.

### The same pattern in every tool

| Tool | Events | Handlers | Context injection | Config |
| --- | --- | --- | --- | --- |
| Claude Code | ~30 | command, http, mcp_tool, prompt, agent | yes | `.claude/settings.json` |
| Cursor | ~18 | command, prompt | yes | `.cursor/hooks.json` |
| Codex | 10 | command | yes | `.codex/hooks.json` |
| Windsurf | 12 | command | **no** | `.windsurf/hooks.json` |
| Copilot | ~13 | command, http, prompt | yes (VS Code) | `.github/hooks/*.json` |

### Lesson boundaries

- This lesson configures hooks and local quality layers only. The hook JSON, `lefthook.yml`, and the per-edit/commit/push layering are the scope.
- Do not write E2E tests, configure Playwright/MCP, or run browser scenarios. That is Lesson 4.
- Do not run the bug-to-fix-to-regression-test debugging workflow. That is Lesson 5.
- Do not change the risk strategy or quality-gate definitions. That is Lesson 1 (`/10x-test-plan`); read current state with `/10x-test-plan --status`.
- Do not write unit/integration test code from scratch here. That is Lesson 2 — hooks only *run* the tests those lessons produced.
- Do not author CI/CD pipelines. That is Module 1 Lesson 5 / Module 2 Lesson 5; hooks are the local layers in front of CI.

### Paths used by this lesson

- `.claude/settings.json` — hook configuration (`~/.claude/settings.json` global, `.claude/settings.json` project, `.claude/settings.local.json` local overrides). Other tools use their own config file (see the table).
- `lefthook.yml` — pre-commit git hook config (lint + typecheck + tests on `{staged_files}`).
- `context/foundation/test-plan.md` — §4 quality gates decide which checks to automate and at which layer; risk areas decide which edits warrant scoped tests.

<!-- END @przeprogramowani/10x-cli -->
