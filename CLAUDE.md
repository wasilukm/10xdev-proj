# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: EnvBooker

Django 6.0.5 web app on **Python 3.14** (see `.python-version`), managed with **uv** (not pip/poetry). Django config package at `envbooker/`; domain logic split across three apps: `accounts`, `catalog`, `reservations`. **Railway** is the deploy target (see `railway.toml` and `context/foundation/infrastructure.md`). Product & stack rationale live in `context/foundation/`.

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

### Templates & static files

Global templates live in `templates/` (configured in `TEMPLATES[0]["DIRS"]`). `whitenoise` serves static files in production via `CompressedManifestStaticFilesStorage`; `STATIC_ROOT = staticfiles/`. Login/logout redirects are `login` → `home`.

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

## 10xDevs AI Toolkit - Module 3, Lesson 1

Open Module 3 by producing a **durable, risk-first quality contract** before any test is written — then drive each rollout phase through the standard change chain.

```
PRD + roadmap + archive
        │
        ▼
   /10x-test-plan  ──►  context/foundation/test-plan.md  (strategy §1–§5 frozen + cookbook §6 grows)
        │
        ▼  (one rollout phase at a time, /clear between handoffs)
   /10x-new ──► /10x-research ──► /10x-plan ──► /10x-implement
```

`/10x-test-plan` is a **stateful orchestrator**, not a one-shot generator. On first run it writes the phased rollout to `context/foundation/test-plan.md`. On every subsequent run it re-derives state from on-disk artifacts and presents the next handoff. The lesson focus is **strategy and rollout sequencing, not configuration**. Hooks, MCP servers, and CI YAML are configured in later lessons of this module.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Quality strategy as a rules-file (lesson focus)** | |
| `/10x-test-plan` | You have a PRD (and ideally a roadmap and a few archived slices) and you are about to write the project's first tests, or you noticed that AI-generated tests are landing on helpers while critical flows go uncovered. First invocation runs discovery (PRD + roadmap + archive + hot-spot scan), a 5-question user interview, and a synthesis pass with a mandatory challenger check, then writes `test-plan.md` in `context/foundation/` with a risk map (5–7 failure scenarios), a phased rollout table, a stack table, a quality-gates table, a cookbook section (`§6`, fills in as phases ship), and a negative-space section (what we deliberately don't test). Subsequent invocations advance the rollout one handoff at a time. |
| `/10x-test-plan --status` | A `test-plan.md` already exists and you want a compact snapshot of where the rollout stands — which phases are `not started`, `change opened`, `researched`, `planned`, `implementing`, or `complete`, and what the next action is. Does no work; safe to run any time. |
| `/10x-test-plan --refresh` | A `test-plan.md` already exists and one of: a new top-3 risk surfaced from the roadmap or archive, a tool's `checked:` date is older than three months, the project's tech stack changed, or §7 negative-space no longer matches what the team believes. Opens a new `test-plan-refresh-<YYYY-MM-DD>` change folder rather than editing the guide in place. |

### Rollout chain — what happens after the guide is written

The guide's §3 *Phased Rollout* table is the orchestrator's state. For each non-`complete` row the orchestrator selects the next handoff based on which artifacts exist in `context/changes/<change-id>/`:

| State on disk | Next handoff | Status transitions to |
| --- | --- | --- |
| change folder missing | `/10x-new <change-id>` | `change opened` |
| `change.md` only | `/10x-research` (with a risks-to-verify brief) | `researched` |
| `+ research.md` | `/10x-plan` (with cost × signal + cookbook-update constraints) | `planned` |
| `+ plan.md` with pending `## Progress` items | `/10x-implement <change-id> phase <N>` | `implementing` / `complete` |
| `+ plan.md` fully `[x]` | Mark §3 row `complete`; loop to next pending row | — |

Each handoff is a **STOP point**. The orchestrator copies the next command to the clipboard, asks the user to `/clear` and run it, then exits. Re-invoke `/10x-test-plan` (no arguments) to advance.

### Risk-first prioritization rules

- Risks are **failure scenarios in user / business terms**, not test names. "Logged-out user reaches paid content via stale token" is a risk; "test the login form" is not.
- 5 to 7 risks. Fewer is too coarse; more makes prioritization useless.
- Impact and likelihood are user/business ratings, not technical complexity.
- Every risk traces to a source: PRD section, archived slice, roadmap entry, Phase 2 interview question, hot-spot **directory** with churn count, or a tech-stack constraint. No invented risks.
- **Signal, not knowledge.** §2 cites *evidence that raised the risk*, never a file as "where the failure lives." File:line anchors, function names, schema names, and module names are forbidden in §2 — they belong in `/10x-research`'s output, produced per rollout phase against current code. The plan is a QA spec; it is not a code audit.
- Coverage is not the metric. **Risk coverage** is the metric.

### Dual-layer mapping rules

- Classic layer first: the cheapest test that gives a real signal wins. Promote to e2e only when no cheaper layer covers the risk.
- AI-native layer second, and only where it adds signal classic tests do not give cheaply.
- Every AI-native row has a **"When NOT to use"** line. If you cannot write one, drop the row.
- Every tool name carries a `checked: <YYYY-MM-DD>` date. Tool names are examples of the category, not endorsements.
- Both layers must be non-empty in the final guide if the project warrants them. Classic-only is a 2020 plan; AI-native-only is hype. AI-native phases are not mandatory — include them only when the brief justified them under cost × signal.

### Quality gates rules

- Required gates (lint, typecheck, unit+integration, e2e on critical flows) must map to actual CI steps. If a required gate is not yet wired, mark it as `required after §3 Phase <N>` and let the named rollout phase wire it.
- Post-edit hook is **recommended local**, not a CI substitute.
- Multimodal visual review is **selective**, applied to 1–3 critical screens, not to every page.
- Vision-driven fallback (Anthropic Computer Use or OpenAI CUA) is reserved for DOM-unreachable surfaces; expensive per action.

### Cookbook patterns (§6) — fills in over time

`test-plan.md` is both a phased strategy and a **growing cookbook**. §6 starts as placeholders (`TBD — see §3 Phase <N>`) and fills in incrementally — each rollout phase's plan ends with a sub-phase that updates the relevant §6 entry (location, naming, reference test, run command). After Module 3 completes, §6 becomes the canonical answer to "how do I add a test for X in this project?" — and is what `/10x-tdd` reads in Lesson 2.

### Lesson boundaries

- Do not write test code. That is Lesson 2 (`/10x-tdd` and unit-test authoring).
- Do not configure hooks, hook lifecycle, or debugging hooks. That is Lesson 3.
- Do not configure MCP servers, Playwright API, e2e code, or multimodal scenario code. That is Lesson 4.
- Do not run the bug-to-fix-to-regression-test workflow. That is Lesson 5.
- Do not author CI/CD pipelines from scratch or write GitHub Actions YAML. The guide names gates; configuration is owned by Module 1 Lesson 5 and Module 2 Lesson 5.
- Do not benchmark multimodal models. Cite criteria (cost, latency, agent-friendliness), never a ranking.
- Do not read the codebase for knowledge (call graphs, schemas, "which file owns this failure"). That is `/10x-research`'s job, per rollout phase.

### Paths used by this lesson

- `context/foundation/test-plan.md` — the quality contract produced and maintained by `/10x-test-plan`
- `context/foundation/prd.md` — primary risk source
- `context/foundation/roadmap.md` — likelihood weighting
- `context/foundation/tech-stack.md` — stack input (when present)
- `context/archive/<change-id>/plan.md` — implemented risk surface
- `context/changes/<change-id>/` — per-rollout-phase change folder (one per row in §3)

<!-- END @przeprogramowani/10x-cli -->
