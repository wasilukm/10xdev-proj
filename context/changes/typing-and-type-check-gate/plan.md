# Typing & Type-Check Gate (Q-01) Implementation Plan

## Overview

Retrofit type hints across the four first-party packages and stand up a `mypy` +
`django-stubs` type-check gate, enforced locally via a Lefthook pre-commit hook.
Closes roadmap **Q-01** and the typing half of test-plan **Risk #6**.

## Current State Analysis

- **0 of ~29 first-party callables annotated** (full inventory in research §"Current typing state"). No `typing` imports, no `from __future__ import annotations`, no `py.typed`.
- No tool config in `pyproject.toml` (`[tool.*]` absent); `.gitignore` already lists `.mypy_cache/` + `.ruff_cache/` (intent signal).
- No hooks, no CI (`.github`/`.gitea`/`.forgejo` all absent). Remote is **Gitea**, not GitHub.
- Domain logic concentrates in the two `services.py` files — the high-value annotation target. Views are thin; forms are plain `forms.Form` (not ModelForm).
- Tooling verified green: `django-stubs` 6.0.5 + `mypy` 2.1 support Django 6.0 / Python 3.14 (research §"Tooling compatibility").

## Desired End State

`uv run mypy .` passes under a lenient-global + strict-islands baseline; every
first-party callable carries annotations; and a Lefthook pre-commit hook blocks
any commit that introduces a type error. Verify by committing a deliberate type
error (rejected) and reverting (accepted). CI enforcement is deferred to
test-plan Phase 5, which consumes this gate definition.

### Key Discoveries:

- mypy boots Django via the plugin, hitting `envbooker/settings.py:22` (`os.environ["DJANGO_SECRET_KEY"]`) and the Postgres guard at `settings.py:104-113`. `dj_database_url.config()` only *parses* the URL, so a dummy `DJANGO_SECRET_KEY` + valid-syntax `DATABASE_URL` runs mypy with no live Postgres.
- django-stubs edge cases (research §"Hard-to-type sites"): `DateTimeRangeField` value type loosely stubbed; `ModelChoiceField.cleaned_data[...]` won't auto-narrow; `Func(...)` annotated querysets narrow weakly. Resolve with local annotations or scoped `# type: ignore[code]`; `warn_unused_ignores` keeps them honest. Custom `User`/`UserManager` is handled natively via `AUTH_USER_MODEL`.

## What We're NOT Doing

- No CI workflow (Gitea/Forgejo/GitHub Actions) — test-plan Phase 5.
- No per-edit agent hook for the typecheck — the slow plugin is wrong for that layer per M3L3; per-edit stays for fast lint/format only.
- No `ruff`/lint tooling — Q-01 is typing-only (lint tripwire stays out per roadmap risk note).
- No annotation of tests or migrations; no behavior changes anywhere.
- No `--strict`-everywhere pass.

## Implementation Approach

Three phases ordered so the gate ratchets over green code: install tooling and
reach a green lenient baseline → annotate all callables and tighten
`disallow_untyped_defs` onto the service layer + models → wire the Lefthook
pre-commit gate last. The Phase 3 hook invocation (plain mypy vs dmypy) is chosen
from the timing measured at the end of Phase 2.

## Critical Implementation Details

- **mypy needs runtime env vars.** The django-stubs plugin runs `django.setup()`, importing `envbooker/settings.py` → `os.environ["DJANGO_SECRET_KEY"]` (`settings.py:22`, hard `KeyError`) and `ImproperlyConfigured` without a Postgres `DATABASE_URL` (`settings.py:104-113`). **Mitigation:** export a dummy `DJANGO_SECRET_KEY` and a syntactically-valid `DATABASE_URL=postgres://...` — `dj_database_url.config()` parses without connecting, so no live Postgres is needed. Both the documented command and the Lefthook config must set these.
- **django-stubs edge cases to expect, not fight:** see Key Discoveries. Prefer a local annotation; fall back to a scoped `# type: ignore[code]`.

---

## Phase 1: Tooling + config + green lenient baseline

### Overview

Install the checker and get `uv run mypy .` passing under the lenient baseline —
proving the plugin loads, settings resolve, and the custom user model + Postgres
fields don't blow up — before any annotation work.

### Changes Required:

#### 1. Dependencies

**File**: `pyproject.toml` (+ `uv.lock`)

**Intent**: Add the checker + stubs as dev dependencies via uv.

**Contract**: `uv add --dev "django-stubs[compatible-mypy]"` (pulls a compatible mypy+stubs pair); optionally `django-stubs-ext`. Lands in a `[dependency-groups]` dev table.

#### 2. Mypy + plugin config

**File**: `pyproject.toml`

**Intent**: Configure the django-stubs mypy plugin pointed at the project settings, with a lenient global baseline and migrations/tests carved out.

**Contract**:
- `[tool.mypy]`: `plugins = ["mypy_django_plugin.main"]`, `check_untyped_defs = true`, `warn_redundant_casts = true`, `warn_unused_ignores = true`.
- `[tool.django-stubs]`: `django_settings_module = "envbooker.settings"`.
- `[[tool.mypy.overrides]]` for `*.migrations.*` and `*.tests.*` → `ignore_errors = true`.

### Success Criteria:

#### Automated Verification:

- mypy installed: `uv run mypy --version`
- Lenient baseline green: `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .` exits 0

#### Manual Verification:

- mypy resolved the custom user model and Postgres fields without plugin crashes (scan output for `AUTH_USER_MODEL` / range-field errors)

**Implementation Note**: After automated verification passes, pause for human confirmation of the manual check before Phase 2.

---

## Phase 2: Annotate first-party code + strict islands

### Overview

Annotate every callable in the four packages, then tighten
`disallow_untyped_defs` onto the service layer + models so the retrofit is
enforced where domain logic lives.

### Changes Required:

#### 1. Annotate all first-party callables

**File**: `accounts/`, `catalog/`, `reservations/`, `envbooker/` (source modules)

**Intent**: Add parameter + return annotations to all ~29 callables (inventory in research). Add `from __future__ import annotations` at the top of each touched module so annotations stay as strings.

**Contract**: representative shapes —
- `catalog/services.py:10` `build_row_context` → a `TypedDict` (`env`, `is_busy: bool`, `current_reservation: Reservation | None`, `upcoming_reservations: list[Reservation]`).
- `catalog/services.py:45/58/68` → `QuerySet[Environment]`, `dict[str, list[str]]`, `Prefetch`.
- `reservations/services.py:29` `compute_end` → `datetime`; `duration_choice: Literal["1h","2h","4h","custom","until_next"]`.
- `reservations/services.py:24/54/74` → `Reservation | None`, `str | None`, `datetime`.
- Views: `(request: HttpRequest, ...) -> HttpResponse`; helpers return `HttpResponse` / context `dict`.
- Forms `clean()` → `dict[str, Any]`; `accounts/models.py:9/20` manager methods → `"User"`.
- django-stubs edge cases handled per Critical Implementation Details.

#### 2. Tighten strict islands

**File**: `pyproject.toml`

**Intent**: Require typed defs on the modules now fully annotated.

**Contract**: `[[tool.mypy.overrides]]` with `disallow_untyped_defs = true` for `catalog.services`, `reservations.services`, and the three `*.models` modules (extend cautiously to views/forms if green).

### Success Criteria:

#### Automated Verification:

- Full typecheck green with strict-island overrides: `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .` exits 0
- No untyped defs remain in island modules (a deliberate unannotated def there fails mypy)
- Test suite still green: `DJANGO_DEBUG=True uv run python manage.py test`
- Typecheck duration measured — cold (`rm -rf .mypy_cache && time ... uv run mypy .`) and warm (`time ... uv run mypy .`) `real` times captured into Per-phase notes. Rule of thumb: warm run over a few seconds → use dmypy in Phase 3.

#### Manual Verification:

- `TypedDict`/`Literal`/`Optional` choices read naturally and match call sites; no `Any`-laden shortcuts in the service layer

**Implementation Note**: After automated verification passes, pause for human confirmation before Phase 3.

---

## Phase 3: Wire the Lefthook pre-commit gate

### Overview

Make the green typecheck enforced on every commit, last — so the hook ratchets
over already-annotated code instead of blocking commits mid-retrofit.

### Changes Required:

#### 1. Lefthook dependency + install

**File**: `pyproject.toml` (dev group)

**Intent**: Add Lefthook and register the git hooks.

**Contract**: `uv add --dev lefthook`, then `uv run lefthook install` (writes `.git/hooks/*`).

#### 2. Hook config

**File**: `lefthook.yml` (new, repo root)

**Intent**: Run the whole-project typecheck on pre-commit with the required env vars.

**Contract**: a `pre-commit` command running `uv run mypy .`, exporting the dummy `DJANGO_SECRET_KEY` + parse-only `DATABASE_URL` (see Critical Implementation Details). Whole-project, not staged-files (plugin needs full context). Invocation chosen by the Phase 2 warm-run timing: plain `uv run mypy .` if a couple seconds; `uv run dmypy run -- .` if meaningfully slow.

#### 3. Docs

**File**: `CLAUDE.md` (and/or `.env.example` note)

**Intent**: Record the gate, the `lefthook install` step, and the env-var requirement so the next dev/agent isn't surprised.

**Contract**: short subsection under the existing tooling/commands notes.

### Success Criteria:

#### Automated Verification:

- Hooks installed: `.git/hooks/pre-commit` exists and references lefthook
- Hook passes on clean tree (typed codebase commits successfully)
- Hook blocks on a type error: a deliberate bad annotation makes `uv run lefthook run pre-commit` exit non-zero

#### Manual Verification:

- A real `git commit` on a clean tree runs mypy and succeeds within a few seconds; reverting the deliberate error restores green

**Implementation Note**: After automated verification passes, pause for human confirmation that the manual commit test succeeded.

---

## Testing Strategy

### Unit Tests:

- No new unit tests — annotations are non-behavioral. The existing suite is the regression guard.

### Integration Tests:

- `DJANGO_DEBUG=True uv run python manage.py test` must stay green after each phase (proves annotations introduced no behavior change).

### Manual Testing Steps:

1. Run the documented `uv run mypy .` command with the dummy env vars → exit 0.
2. Introduce a deliberate type error, run `uv run lefthook run pre-commit` → blocked; revert → passes.
3. Perform a real `git commit` on a clean tree → hook runs and passes within a few seconds.

## Performance Considerations

The django-stubs plugin makes mypy slow to start (it boots Django). At this size
(~29 callables) a warm run should be a few seconds — acceptable per-commit. The
Phase 2 timing measurement is the decision input: if the warm run is meaningfully
slow, the Phase 3 hook uses `dmypy` (persistent daemon) instead of plain mypy.

## Migration Notes

None — no data or schema changes. Existing contributors must run
`uv run lefthook install` once after pulling (documented in Phase 3).

## References

- Research: `context/changes/typing-and-type-check-gate/research.md`
- Roadmap Q-01: `context/foundation/roadmap.md:163-177`
- Test-plan Risk #6 / Phase 5 boundary: `context/foundation/test-plan.md:47,72,117-126`
- Gotcha source: `envbooker/settings.py:22,104-113`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Tooling + config + green lenient baseline

#### Automated

- [x] 1.1 mypy installed (`uv run mypy --version`) — d62ce9c
- [x] 1.2 Lenient baseline green (`uv run mypy .` exits 0) — d62ce9c

#### Manual

- [x] 1.3 Plugin resolved custom user model + Postgres fields without crashes — d62ce9c

### Phase 2: Annotate first-party code + strict islands

#### Automated

- [x] 2.1 Full typecheck green with strict-island overrides — f710699
- [x] 2.2 No untyped defs remain in island modules — f710699
- [x] 2.3 Test suite still green — f710699
- [x] 2.4 Typecheck duration measured (cold + warm) and captured into notes — f710699

#### Manual

- [x] 2.5 TypedDict/Literal/Optional choices read naturally; no Any shortcuts in services — f710699

### Phase 3: Wire the Lefthook pre-commit gate

#### Automated

- [x] 3.1 Hooks installed (`.git/hooks/pre-commit` references lefthook)
- [x] 3.2 Hook passes on clean tree
- [x] 3.3 Hook blocks on a deliberate type error

#### Manual

- [ ] 3.4 Real `git commit` triggers hook and passes within a few seconds
