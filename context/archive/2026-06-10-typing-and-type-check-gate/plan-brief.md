# Typing & Type-Check Gate (Q-01) — Plan Brief

> Full plan: `context/changes/typing-and-type-check-gate/plan.md`
> Research: `context/changes/typing-and-type-check-gate/research.md`

## What & Why

`tech-stack.md` committed to explicit typing, but the codebase never followed
through — **0 of ~29 first-party callables are annotated** and no type checker is
installed. This change (roadmap **Q-01**) retrofits type hints across the four
first-party packages and stands up a `mypy` + `django-stubs` gate so untyped
drift is caught automatically.

## Starting Point

A Django 6.0.5 / Python 3.14 app with three domain apps + the config package,
zero annotations, no `[tool.*]` config, and no hooks or CI. Domain logic lives in
the two `services.py` files. Tooling compatibility is verified green
(django-stubs 6.0.5 + mypy 2.1 support this exact stack).

## Desired End State

`uv run mypy .` passes under a lenient-global + strict-islands baseline, every
first-party callable is annotated, and a Lefthook pre-commit hook blocks any
commit that introduces a type error. CI enforcement is left to test-plan Phase 5,
which consumes this gate.

## Key Decisions Made

| Decision | Choice | Why | Source |
| --- | --- | --- | --- |
| Enforcement target | Config + annotations + local Lefthook pre-commit gate; CI deferred | Matches M3L3 layering; stays inside Q-01's typing-only scope | Plan |
| Baseline strictness | Lenient global + strict islands (services + models first) | Green from day one; strongest signal where domain logic lives; avoids the strict-everywhere stall | Plan (research-rec.) |
| Annotation scope | All first-party callables; exclude migrations + tests | Closes the whole 0/29 gap per Q-01 outcome | Plan |
| Hook tool | Lefthook | Named in CLAUDE.md M3L3; single binary, fits uv | Plan |
| Mypy invocation | Whole-project `uv run mypy .` | django-stubs needs whole-project context; ~seconds at this size | Plan (research) |
| Type checker | mypy + django-stubs | Only ORM-aware option with Django 6.0 + Py 3.14 support today | Research |

## Scope

**In scope:** dev-dep install (mypy, django-stubs, lefthook); `[tool.mypy]` +
`[tool.django-stubs]` config; annotations across all four packages;
`lefthook.yml` pre-commit gate; docs.

**Out of scope:** CI workflows (Phase 5); per-edit agent hook; ruff/lint;
annotating tests/migrations; any behavior change; `--strict`-everywhere.

## Architecture / Approach

Three phases ordered so the gate ratchets over green code: (1) install tooling +
config, reach a green lenient baseline; (2) annotate all callables, tighten
`disallow_untyped_defs` onto the service layer + models; (3) wire the Lefthook
pre-commit hook last. The hook runs whole-project mypy with dummy env vars (the
plugin boots Django, so `DJANGO_SECRET_KEY` + a parse-only `DATABASE_URL` are
required — no live Postgres needed).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Tooling + green baseline | mypy + django-stubs installed, config in place, `uv run mypy .` green (lenient) | Plugin can't boot Django without env vars (mitigated) |
| 2. Annotate + strict islands | All ~29 callables typed; `disallow_untyped_defs` on services + models; timing measured | django-stubs edge cases (range fields, ModelChoiceField narrowing) |
| 3. Lefthook gate | `lefthook.yml` pre-commit blocking on type errors; docs | Hook latency if the warm mypy run is slow (→ dmypy fallback) |

**Prerequisites:** F-01, S-01, S-02 shipped (the baseline being annotated). uv-managed env.
**Estimated effort:** ~1–2 sessions across 3 phases (wide but shallow, non-behavioral diff).

## Open Risks & Assumptions

- django-stubs has known soft spots on Postgres range/exclusion fields and `ModelChoiceField` narrowing — resolved with local annotations or scoped `# type: ignore[code]` (`warn_unused_ignores` keeps them honest), not by fighting the tool.
- Local-only enforcement until Phase 5 — a teammate who skips `lefthook install` can still push untyped code until CI lands.
- Assumes the verified tooling versions still resolve at install time (confirm pins via `uv add`).

## Success Criteria (Summary)

- `uv run mypy .` exits 0 under the strict-islands baseline, with every first-party callable annotated.
- A deliberate type error is rejected at commit time; reverting restores a clean commit.
- The existing test suite stays green (annotations introduced no behavior change).
