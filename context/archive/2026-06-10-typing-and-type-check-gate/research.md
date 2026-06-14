---
date: 2026-06-10T00:15:28+02:00
researcher: Mariusz Wasiluk
git_commit: 329bfd92cc320ca322a5688e6638b1f1feac4767
branch: main
repository: 10xdev-proj
topic: "Type-hint retrofit + mypy/django-stubs type-check gate (roadmap Q-01)"
tags: [research, codebase, typing, mypy, django-stubs, quality-gate, hooks]
status: complete
last_updated: 2026-06-10
last_updated_by: Mariusz Wasiluk
---

# Research: Type-hint retrofit + mypy/django-stubs type-check gate

**Date**: 2026-06-10T00:15:28+02:00
**Researcher**: Mariusz Wasiluk
**Git Commit**: 329bfd92cc320ca322a5688e6638b1f1feac4767
**Branch**: main
**Repository**: 10xdev-proj

## Research Question

For the `typing-and-type-check-gate` change (roadmap **Q-01**): map the current
typing state of the codebase and the hard-to-type sites, verify tooling
compatibility (mypy + django-stubs on Python 3.14 / Django 6.0.5) and weigh
alternatives, and ground where the type-check gate should be enforced given no
CI exists yet.

## Summary

- **Annotation surface is small and shallow but wide.** ~29 first-party
  functions/methods across `accounts/`, `catalog/`, `reservations/`,
  `envbooker/` — **0% currently annotated**. No `typing` imports, no
  `from __future__ import annotations`, no `py.typed`. The work is breadth, not
  depth: mostly straightforward signatures, with a handful of genuinely tricky
  return types concentrated in the two `services.py` files.
- **Tooling is NOT a blocker (this resolved in spring 2026).** `django-stubs`
  6.0.5 (2026-05-25) supports Django 6.0 + Python 3.10–3.14 + mypy 1.13–2.1;
  mypy 2.1.0 (2026-05-11) analyzes Python 3.14. The exact stack is on the
  supported matrix, not bleeding edge. **mypy + django-stubs is the right gate**
  — it is the only option today with ORM-aware Django 6.0 + Python 3.14 support.
  `ty` (Astral, best uv fit) is Beta with no Django/plugin support; `pyright`
  works fast but can't use the django-stubs plugin. Use either only as a
  non-authoritative editor pass.
- **Zero enforcement infrastructure exists** — no agent hooks, no git hooks, no
  CI (`.github`/`.gitea`/`.forgejo` all absent), no `[tool.*]` config. Only
  signal of intent: `.gitignore` already lists `.mypy_cache/` and `.ruff_cache/`.
- **The django-stubs plugin is slow**, so per the project's own M3L3 layering
  doctrine the typecheck belongs at **pre-commit / pre-push / CI**, not in a
  per-edit agent hook (those stay limited to fast lint/format).
- **Recommended baseline**: lenient global + strict islands, then invert. Don't
  start at `--strict`. Enable the plugin + `check_untyped_defs`, exclude
  `migrations`/`tests`, then ratchet `disallow_untyped_defs` onto the service
  layer and models first.

Two decisions remain explicitly for `/10x-plan` (roadmap Q-01 unknowns): the
**baseline strictness** and the **enforcement layer**. This research grounds
both but does not decide them.

## Detailed Findings

### Current typing state (0/29 annotated)

Per-file inventory of first-party callables (excluding migrations, tests,
`context/`). All currently **untyped**.

**accounts/ (7 callables)**
- `accounts/models.py:9` `UserManager.create_user(email, password=None, **extra_fields)`
- `accounts/models.py:20` `UserManager.create_superuser(email, password=None, **extra_fields)`
- `accounts/models.py:47` `AllowedEmailDomain.save(*args, **kwargs)`
- `accounts/models.py:51` `AllowedEmailDomain.__str__()`
- `accounts/forms.py:15` `SignUpForm.clean_email()`
- `accounts/forms.py:27` `EmailAuthenticationForm.clean_username()`
- `accounts/views.py:13` `SignUpView.form_valid(form)`

**catalog/ (6 callables)**
- `catalog/models.py:20` `Environment.__str__()`
- `catalog/services.py:10` `build_row_context(env, now=None)`
- `catalog/services.py:45` `filter_environments(queryset, *, availability=None, project=None, use_case_tag=None, now)`
- `catalog/services.py:58` `filter_options()`
- `catalog/services.py:68` `prefetch_reservations_for_list(now)`
- `catalog/views.py:11` `environment_list(request)`

**reservations/ (16 callables)**
- `reservations/models.py:42` `Reservation.__str__()`
- `reservations/services.py:11` `_qs_starting_at_or_after(env, start)`
- `reservations/services.py:24` `next_reservation_after(env, start)`
- `reservations/services.py:29` `compute_end(env, start, duration_choice, custom_hours=None)`
- `reservations/services.py:54` `describe_overlap_conflict(env, during, exclude_pk=None)`
- `reservations/services.py:74` `next_free_window(env, after)`
- `reservations/views.py:17` `_row_response(...)`, `:29` `_item_context(...)`, `:43` `_item_response(...)`
- `reservations/views.py:53` `reservation_create(request)`, `:89` `my_reservations(request)`, `:107` `reservation_edit(request, pk)`, `:142` `reservation_cancel(request, pk)`
- `reservations/forms.py:39` `ReservationForm.clean()`, `:78` `ReservationEditForm.__init__(*args, start, **kwargs)`, `:82` `ReservationEditForm.clean()`
- `reservations/admin.py:13` `ReservationAdmin.during_local(self, obj)`

**envbooker/**: 0 callables (settings/ASGI/WSGI config only).

No existing type infrastructure anywhere: no `from __future__ import
annotations`, no `typing` imports, no `py.typed` marker, no `->` returns.

### Hard-to-type sites (where the effort concentrates)

1. **Custom User model** — `accounts/models.py:30-41`. `class User(AbstractUser)`
   with `username = None` (`:31`), `email` unique (`:32`), `USERNAME_FIELD =
   "email"` (`:33`), `objects = UserManager()` (`:36`). The manager methods
   (`:9`, `:20`) take `**extra_fields` and return `self.model(...)`. With the
   **mypy plugin this is largely handled** because django-stubs resolves
   `AUTH_USER_MODEL` from settings — the dynamic-attr pain (`user.id` flagged
   missing) is mainly a pyright/django-types problem, fixable with `.pk` or an
   explicit `id: int`.
2. **Postgres range field** — `reservations/models.py:19` `during =
   DateTimeRangeField()`. Covered by django-stubs (Django 6.0 coverage), but the
   Python value type (`psycopg.types.range.Range` / `DateTimeTZRange`) is
   stubbed generically loose; reading/assigning `.during` may need a local
   annotation.
3. **ExclusionConstraint + RangeOperators** — `reservations/models.py:24-31`
   (`index_type="GIST"`). In django-stubs' Postgres coverage; no open blocking
   typing issue found.
4. **`Func(...)` queryset annotations** — `reservations/services.py:18` and
   `reservations/views.py:94-95`:
   `Func("during", function="lower", output_field=DateTimeField())`. Annotated
   queryset return types narrow weakly.
5. **Service return shapes** (the real meat):
   - `build_row_context` → `dict` with `env`, `is_busy: bool`,
     `current_reservation: Reservation | None`, `upcoming_reservations:
     list[Reservation]` — a candidate for a `TypedDict`.
   - `filter_environments` → `QuerySet[Environment]`; `filter_options` → `dict`
     of `list[str]`; `prefetch_reservations_for_list` → `Prefetch`.
   - `compute_end` → `datetime`; `duration_choice` is effectively a
     `Literal["1h","2h","4h","custom","until_next"]`; raises `ValueError`.
   - `describe_overlap_conflict` → `str | None`; `next_free_window` → `datetime`;
     `next_reservation_after` → `Reservation | None`.
6. **psycopg `Range`** — `reservations/forms.py:65`, `:98`; `catalog/services.py`
   uses `Range`. `psycopg` ships `py.typed` but `Range` is generic.
7. **Forms are plain `forms.Form`, not ModelForm** —
   `reservations/forms.py:20` `ReservationForm(forms.Form)`, `:69`
   `ReservationEditForm(forms.Form)`. `cleaned_data["environment"]` (a
   `ModelChoiceField`) won't auto-narrow to `Environment`.
8. **HTMX view branching** — `catalog/views.py:39`
   `if request.headers.get("HX-Request"):` returns a partial vs. full template;
   all views take an untyped `request` and return `HttpResponse` (incl. empty
   `HttpResponse("")` at `reservations/views.py:147`).

### Tooling compatibility & alternatives (web-verified 2026-06-10)

**Verdict: green — the Django 6.0 + Python 3.14 + django-stubs + mypy
intersection is fully supported.** (A real risk months ago; now resolved.)

| Tool | Django 6 | Python 3.14 | django-stubs / plugin | Maturity | uv fit | Gate fit |
|------|----------|-------------|-----------------------|----------|--------|----------|
| **mypy + django-stubs** | Yes (6.0.5) | Yes (mypy 2.1) | Native plugin — most precise ORM/manager/settings inference | Mature, de-facto standard | `uv add --dev "django-stubs[compatible-mypy]"` | **Authoritative gate**; slow → commit/push/CI |
| pyright (MS) | Partial | Yes | **No plugin** — use `django-types` fork; false positives on dynamic ORM attrs | Mature, very fast | Node toolchain | Fast editor pass; weaker Django accuracy |
| ty (Astral) | **No (roadmap "Stable 2026")** | Yes | **No plugin system yet** | **Beta** (since 2025-12-16), 10–60× faster | Best (same makers as uv/ruff) | Too immature to gate today |
| pyrefly (Meta) | Partial | Yes | No plugin | Early/fast | Single binary | Editor companion only |

- **django-stubs 6.0.5** (2026-05-25): classifiers Python 3.10–3.14, Django 5.0–6.0,
  mypy 1.13–2.1. The 6.0.x line added full Django 6.0 coverage.
- **mypy 2.1.0** (2026-05-11): analyzes Python 3.14 (PEP 750 t-strings, cp314
  wheels). Inside django-stubs' supported band.
- **Caveat for the plan**: django-stubs historically lags new Django releases by
  weeks-to-months. You're past the gap now; don't over-pin, and expect a similar
  lag if you ever jump to Django 6.1 before stubs catch up.
- **Trust note**: the agent's first WebFetch of the GitHub releases page
  mis-rendered 6.0.x dates as "2024"; authoritative **PyPI** values (2026) were
  used. Re-confirm exact version pins at install time with `uv add`.

### Recommended config (verified snippets)

```bash
uv add --dev "django-stubs[compatible-mypy]"   # pulls a compatible mypy+stubs pair
uv add --dev django-stubs-ext                  # optional runtime helpers
uv run mypy .
```

```toml
[tool.mypy]
plugins = ["mypy_django_plugin.main"]
check_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true

[tool.django-stubs]
django_settings_module = "envbooker.settings"
# strict_settings = true              # default; flip false only for split/dynamic settings
# strict_model_abstract_attrs = true  # default; flip false if abstract base models need .objects

[[tool.mypy.overrides]]
module = ["*.migrations.*", "*.tests.*"]
ignore_errors = true
```

Plugin knobs: `django_settings_module` (required), `strict_settings`,
`strict_model_abstract_attrs`. Custom `accounts.User` is understood natively via
`AUTH_USER_MODEL` resolution — no extra config beyond the settings module.

### Recommended baseline strictness (community-recommended retrofit)

Do **not** start at `--strict` on a 0-typed codebase:
1. Plugin + `check_untyped_defs`; exclude `*.migrations.*` and `*.tests.*`.
2. Tighten per-module via `[[tool.mypy.overrides]]` — apply
   `disallow_untyped_defs = true` first to the **service layer**
   (`catalog/services.py`, `reservations/services.py`) and models (where domain
   logic concentrates per CLAUDE.md).
3. Ratchet one flag at a time (`disallow_untyped_defs` → `no_implicit_optional`
   → …), committing between each.
4. Once most first-party code is typed, set `strict = true` globally and list
   the few holdouts. Keep migrations/tests lenient indefinitely.

This "lenient global + strict islands, then invert" pattern keeps the gate green
from day one without a big-bang annotation push, and matches Q-01's risk note
("cap it at first-party app code with a green baseline").

### Enforcement layer — current state (all absent)

| Layer | Configured? | Evidence |
|-------|-------------|----------|
| Per-edit agent hook | ❌ | No `hooks` key in `.claude/settings.local.json`, `~/.claude/settings.json`. (Stale typo file `.claude/settings.jsom` exists.) |
| Pre-commit git hook | ❌ | No `lefthook.yml`, `.husky/`, `.pre-commit-config.yaml`, `package.json`; only `.git/hooks/*.sample` |
| Pre-push git hook | ❌ | Same — samples only |
| CI | ❌ | No `.github/workflows`, `.gitea/`, `.forgejo/`, `.gitlab-ci.yml` (test-plan verified 2026-06-08) |
| Dev script | ⚠️ | `dev.sh` starts Postgres/migrate/runserver — no quality checks |
| Tool config | ❌ | No `[tool.*]` in `pyproject.toml`; `.gitignore` already lists `.mypy_cache/`, `.ruff_cache/` |

**Layering implication.** The django-stubs plugin makes mypy slow, so per the
project's own M3L3 doctrine (CLAUDE.md §"Three local layers") a **full typecheck
is a commit/push/CI gate, not a per-edit hook**. Per-edit hooks stay limited to
fast lint/format. The remote is self-hosted **Gitea** (`tea` CLI per memory),
not GitHub — so a "GitHub Actions job" option in the roadmap would actually be a
Gitea Actions / Forgejo workflow. Worth confirming in the plan.

## Code References

- `accounts/models.py:30-41` — custom `User(AbstractUser)`, `username=None`, `USERNAME_FIELD="email"`
- `accounts/models.py:9,20` — `UserManager.create_user/create_superuser(**extra_fields)`
- `accounts/models.py:40` — `UniqueConstraint(Lower("email"), name="user_email_ci_uniq")`
- `reservations/models.py:19` — `during = DateTimeRangeField()`
- `reservations/models.py:24-31` — `ExclusionConstraint(... index_type="GIST")`
- `reservations/services.py:8` — `MAX_DURATION = timedelta(hours=4)`
- `reservations/services.py:11-74` — service functions (the main annotation surface)
- `reservations/services.py:18` — `Func("during", function="lower", output_field=DateTimeField())`
- `catalog/services.py:10-72` — `build_row_context`, `filter_environments`, `filter_options`, `prefetch_reservations_for_list`
- `reservations/views.py:11` — cross-module import of `build_row_context` from `catalog.services`
- `catalog/views.py:39` — HTMX `HX-Request` branch
- `reservations/forms.py:20,69` — plain `forms.Form` (not ModelForm); `:54` `timezone.make_aware`
- `pyproject.toml` — no `[tool.*]`, deps untyped-tooling-free
- `.gitignore` — `.mypy_cache/`, `.ruff_cache/` (intent signal)

## Architecture Insights

- **Service layer is the typing payoff.** CLAUDE.md states views are thin and
  domain logic lives in `services.py`. The richest, most-reused return types
  (row-context dicts, querysets, range/datetime) are there — annotate it first
  and the `disallow_untyped_defs` island gives the most signal per unit effort.
  `build_row_context`'s dict is a natural `TypedDict`; `compute_end`'s
  `duration_choice` is a natural `Literal`.
- **Postgres-only by design** (`settings.py` raises `ImproperlyConfigured` on
  non-Postgres). The range/exclusion types that make this app distinctive are
  exactly the django-stubs edge cases — budget for a few local annotations and
  possibly targeted `# type: ignore` with `warn_unused_ignores` to catch them
  going stale.
- **Horizontal, shallow blast radius.** Q-01 touches nearly every `.py` file but
  changes no behavior. The named risk is scope creep into a strict-everywhere
  crusade — the baseline ladder above is the mitigation.

## Historical Context (from prior changes)

- `context/foundation/roadmap.md:163-177` — **Q-01** definition, change-id
  `typing-and-type-check-gate`, prerequisites F-01/S-01/S-02, and the three
  unknowns (baseline strictness; enforcement mechanism; django-stubs config for
  custom User + range fields). All marked "resolves in /10x-plan", non-blocking.
- `context/foundation/test-plan.md:47` (Risk #6), `:72` (Phase 5
  "Quality-gates wiring"), `:110` (gate table), `:117-126` (Phase 5 ↔ Q-01
  boundary): Q-01 owns the **typing-only** gate *definition*; Phase 5 stands up
  the CI harness and *consumes* it. Sequence Q-01 before/with Phase 5.
- `context/foundation/test-plan.md:58` (Risk #6 response): challenge "tests
  existing implies enforced"; warns against a gate that runs but doesn't block,
  and against chasing `--strict` everywhere.
- `context/foundation/lessons.md` — one lesson only (verify named platform
  controls exist before relying on them); no prior typing/lint/hook decisions.
- `context/archive/` — no prior typing, mypy, lint, hook, or CI work.
- CLAUDE.md §"Module 3 Lesson 3" — the per-edit → pre-commit → pre-push → CI
  layering doctrine and exit-code/`additionalContext` feedback mechanism that
  governs where this gate should sit.

## Related Research

- None — this is the first research artifact under
  `context/changes/typing-and-type-check-gate/`.

## Open Questions

These carry forward to `/10x-plan` (Q-01 unknowns), now grounded:

1. **Baseline strictness** — adopt the lenient-global + strict-islands ladder
   (recommended), starting `disallow_untyped_defs` on the service layer + models?
   Or a flatter `check_untyped_defs`-only first cut?
2. **Enforcement layer** — given no CI and a slow plugin: documented `uv run
   mypy` now → pre-commit (lefthook/pre-commit) → Gitea/Forgejo CI later? Note
   the remote is **Gitea**, not GitHub, so the roadmap's "GitHub Actions"
   phrasing needs translating. Per-edit agent hook is explicitly *not* the right
   layer for a full typecheck.
3. **`ty` as a future fast path** — leave a note to revisit `ty` for editor/
   per-edit speed once it reaches Stable with Django support; keep mypy as the
   authoritative gate.
4. **Version pinning** — confirm exact `django-stubs` / `mypy` versions at
   install time (PyPI dates were authoritative; one source mis-rendered them).
