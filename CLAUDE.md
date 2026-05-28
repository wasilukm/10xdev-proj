# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: EnvBooker

Django 6.0.5 web app on **Python 3.14** (see `.python-version`), managed with **uv** (not pip/poetry). Single Django config package at `envbooker/`; no domain apps yet — they'll be added as the PRD ships. SQLite (`db.sqlite3`) for dev; **Railway** is the deploy target (see `railway.toml` and `context/foundation/infrastructure.md`). Product & stack rationale live in `context/foundation/`.

### Common commands

```bash
uv sync                              # install/refresh dependencies from uv.lock
uv add <pkg>                         # add a runtime dependency
uv run python manage.py runserver    # dev server at http://127.0.0.1:8000
uv run python manage.py migrate      # apply pending migrations
uv run python manage.py makemigrations <app>  # generate migrations after model changes
uv run python manage.py createsuperuser       # bootstrap an admin user
uv run python manage.py test                  # run the full Django test suite
uv run python manage.py test <app>            # run tests for a single app
```

### Local dev setup

`settings.py` reads `DJANGO_SECRET_KEY` from the environment and will crash on startup if it is missing. Before running the dev server:

```bash
export DJANGO_SECRET_KEY=any-local-secret-value
export DJANGO_DEBUG=True          # optional; defaults to False if unset
```

### Project-specific tripwires

- **The uv-managed `.venv` has no `pip`**, so `pip-audit` cannot use `PIPAPI_PYTHON_LOCATION`. Audit via:
  `uv export --no-hashes | grep -v '^#' | pip-audit -r /dev/stdin`
- **Railway deploy** is defined in `railway.toml`: Railpack builder (auto-detects `uv.lock` + `.python-version`), runs `collectstatic → migrate → gunicorn` on start. No Dockerfile needed.
- **No linting tools** are configured in `pyproject.toml` yet — add ruff or similar before wiring up CI.

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

## 10xDevs AI Toolkit - Module 2, Lesson 2

Turn one roadmap item into the first implementation cycle with the **change planning chain**:

```
/10x-roadmap -> /10x-new -> /10x-plan -> /10x-plan-review -> /10x-implement
```

`/10x-new`, `/10x-plan`, `/10x-plan-review`, and `/10x-implement` are the lesson focus. `/10x-frame` and `/10x-research` are not required rituals here; they are escalation paths introduced in the next lesson.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Change setup (lesson focus)** | |
| `/10x-new <change-id>` | You selected a roadmap item and need a stable change folder. Creates `context/changes/<change-id>/change.md` so planning, implementation, progress, commits, and later review all share one identity. Use AFTER roadmap selection, BEFORE `/10x-plan`. |
| **Planning (lesson focus)** | |
| `/10x-plan <change-id>` | You have a change folder and need a reviewable implementation plan. Reads roadmap context, foundation docs, codebase evidence, and any existing change notes; writes `plan.md` and `plan-brief.md` with phases, file contracts, success criteria, and `## Progress`. |
| **Plan readiness (lesson focus)** | |
| `/10x-plan-review <change-id>` | You have `plan.md` and need a light pre-code readiness check. Use it to catch missing end state, weak contracts, malformed progress, scope drift, or blind spots before code changes begin. |
| **Implementation (lesson focus)** | |
| `/10x-implement <change-id> phase <n>` | You have an approved plan and want to execute one phase with verification, manual gate, commit ritual, and SHA write-back to `## Progress`. |
| **Lifecycle closure** | |
| `/10x-archive <change-id>` | A change is merged or intentionally closed. Move it out of active `context/changes/` into archive state. |

### How the chain hands off

- `/10x-new` creates the durable change identity.
- `/10x-plan` turns that identity into an implementation contract.
- `/10x-plan-review` checks the plan before the agent mutates code.
- `/10x-implement` executes one planned phase, verifies, asks for manual confirmation when needed, commits, and records progress.

### Lesson boundaries

- Plan is the default router after roadmap selection. Start with `/10x-plan` unless the problem is unclear or external evidence is blocking.
- Do not run `/10x-frame + /10x-research` as ceremony for every change.
- Do not turn this lesson into a full end-to-end product build. A checkpoint with a planned and partially or fully implemented stream is valid.
- Code review of the implemented diff belongs to Lesson 3 via `/10x-impl-review`.
- Lifecycle closure via `/10x-archive` after a change is merged or intentionally closed.

### Paths used by this lesson

- `context/foundation/roadmap.md` - upstream roadmap
- `context/changes/<change-id>/change.md` - change identity
- `context/changes/<change-id>/plan.md` - implementation contract
- `context/changes/<change-id>/plan-brief.md` - compressed handoff
- `context/foundation/lessons.md` - recurring rules and pitfalls
- `docs/reference/contract-surfaces.md` - load-bearing names registry

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
