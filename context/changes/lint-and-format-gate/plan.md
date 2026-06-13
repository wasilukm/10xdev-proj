# Lint & Format Gate (Q-02) Implementation Plan

## Overview

Adopt **ruff** (lint + format in one binary) and enforce it at the two M3 L3
local layers — a per-edit Claude Code `PostToolUse` agent hook and the existing
Lefthook `pre-commit` gate. Reach a fully green baseline in one repo-wide cleanup
commit, then ratchet the hooks over it. Closes roadmap **Q-02**, the `CLAUDE.md`
lint tripwire, and the lint half of test-plan **§5** / **Risk #6** (Q-01 left it
typing-only). CI wiring is out of scope (test-plan Phase 5 consumes this gate).

## Current State Analysis

- **No lint/format tooling configured.** `pyproject.toml` has `[tool.mypy]` only
  (Q-01); no `[tool.ruff]`. `.gitignore` already lists `.ruff_cache/` (intent
  signal). Ruff is the `CLAUDE.md`-named default.
- **Measured blast radius (ruff 0.x, line-length 88, live tree):** 12 of 35
  first-party source files reformat; lint debt is dominated by `E501` (a
  line-length policy, being disabled) plus a handful of auto-fixable findings
  (`I001`, `UP017`, `SIM117`, `F401`); the **only** non-auto-fixable source
  finding is a single `SIM102` collapsible-if. Tests carry the two `F401`
  unused-imports. (Full measurements: `research.md`.)
- **Pre-commit harness exists** — `lefthook.yml` runs `mypy .` (Q-01). This
  change adds ruff commands to it. Lefthook is already a dev dependency.
- **No per-edit agent hook.** No `hooks` key anywhere. The project Claude
  settings file is **misnamed `.claude/settings.jsom`** (inert, stale generic
  template); real session permissions live in `.claude/settings.local.json`.
- **Quiescent window:** no `S-05`/`S-06`/`SPIKE-01` change folders exist on disk
  (`context/changes/` holds only `bootstrap-verification/` and this change), so a
  one-time format diff will not collide with an in-flight write-path branch.
- **Green typed baseline:** Q-01 left first-party code annotated and `mypy`-green;
  ruff lints over that.

## Desired End State

`uv run ruff check .` and `uv run ruff format --check .` both exit 0 on the whole
tree (migrations excluded). A commit with a ruff violation in a staged file is
auto-fixed and re-staged (or blocked if non-fixable). When the agent edits a
`.py` file, a `PostToolUse` hook formats + auto-fixes it and announces the change
(or surfaces residual findings) back into the agent's context. The gate is
documented in `CLAUDE.md`. Verify by the per-phase success criteria below.

### Key Discoveries:

- **`E501` is disabled** (formatter owns width) — collapses ~46 of the measured
  findings to zero with no manual edits; every remaining lint finding is
  actionable. (`research.md` §"The E501 / line-length decision".)
- **F3 lesson (`context/archive/2026-06-10-typing-and-type-check-gate/reviews/impl-review.md`):**
  a `*.tests.*`-style pattern misses flat `accounts/tests.py` / `catalog/tests.py`.
  This plan **lints tests fully** and excludes **only** migrations via
  `**/migrations/**` (a glob that catches every migration dir), so it avoids the
  fragile tests pattern entirely.
- **Ruff needs no env vars / DB** — unlike the mypy command (which exports dummy
  `DJANGO_SECRET_KEY`/`DATABASE_URL` to boot the django-stubs plugin), ruff is a
  static check, so its Lefthook command is a clean `{staged_files}` run.
- **`target-version = "py314"`** matches `.python-version`; `UP017` already fired,
  confirming ruff applies a modern target — pin it explicitly rather than infer.

## What We're NOT Doing

- **No CI workflow** (Gitea/Forgejo/GitHub Actions) — test-plan Phase 5 owns the
  CI harness and later consumes this gate.
- **No pre-push hook** — Q-02 scope is the per-edit + pre-commit layers only.
- **No `E501` enforcement** — the formatter owns line width.
- **No formatting/linting of migrations** — Django-generated; excluded.
- **No change to the existing mypy command** — it stays whole-project + env-var'd.
- **No `--unsafe-fixes`** — only ruff's safe auto-fixes, so fixes stay
  semantically neutral.
- **No behavior changes** — the existing test suite is the regression guard.

## Implementation Approach

Three phases, ordered so the gates ratchet over already-green code (mirroring
Q-01): install + configure ruff and land a fully green one-time cleanup commit →
wire the Lefthook pre-commit ruff commands → wire the per-edit agent hook, rename
the misnamed settings file, and document. Formatting and the auto-fixable lint rules
are bulk-applied in Phase 1; the lone `SIM102` is the single manual edit.

## Critical Implementation Details

- **Per-edit hook feedback & file-state drift.** The `PostToolUse` hook runs
  *after* the agent's `Write`/`Edit` lands, so when ruff rewrites the file the
  agent's cached view goes stale — a later `Edit` keyed on a line ruff changed
  will mismatch and force a re-read. Mitigate by having the hook **announce**
  every change it makes (so the agent re-reads proactively) via the PostToolUse
  `additionalContext` mechanism, and reserve a **blocking signal (exit 2)** for
  *residual, non-auto-fixable* findings the agent must fix itself. Safe fixes
  only keeps every mutation semantically neutral, so correctness is never at
  risk — only edit-flow continuity, which the announce step addresses.
- **Hook output mechanism (non-obvious).** A PostToolUse hook injects text into
  the agent's context either by emitting JSON on stdout with a
  `hookSpecificOutput.additionalContext` field (non-blocking note) or by exiting
  non-zero to surface blocking feedback. The hook should use the non-blocking
  note when it only reformatted/auto-fixed, and the blocking path when ruff
  reports findings it could not fix. Confirm the exact field names against the
  installed Claude Code version during implementation.
- **Lefthook `stage_fixed`.** The pre-commit ruff commands run with
  `stage_fixed: true` so auto-fixed files are re-added to the index and the
  commit lands clean; a finding ruff cannot fix still fails the commit.

---

## Phase 1: Tooling + config + one-time green baseline

### Overview

Install ruff, configure it, and bring the whole tree to green in a single
cleanup commit — before any hook exists — so the later hooks ratchet over clean
code instead of fighting a backlog.

### Changes Required:

#### 1. Dependency

**File**: `pyproject.toml` (+ `uv.lock`)

**Intent**: Add ruff as a dev dependency via uv (joins `django-stubs`, `lefthook`
in the `[dependency-groups] dev` table).

**Contract**: `uv add --dev ruff`.

#### 2. Ruff configuration

**File**: `pyproject.toml`

**Intent**: Configure the rule set, line length, Python target, and migration
exclusion agreed in research — lenient-but-useful global set with `E501` off and
the formatter owning width.

**Contract**:
- `[tool.ruff]`: `line-length = 88`, `target-version = "py314"`,
  `extend-exclude = ["**/migrations/**"]`.
- `[tool.ruff.lint]`: `select = ["E", "W", "F", "I", "UP", "B", "SIM"]`,
  `ignore = ["E501"]`.
- `[tool.ruff.format]`: defaults (no overrides needed).
- **No** test carve-out — tests are linted/formatted in full; only migrations are
  excluded (deliberately avoiding the fragile `*.tests.*` pattern per the F3
  lesson).

#### 3. One-time green cleanup

**File**: all first-party `.py` under `accounts/`, `catalog/`, `reservations/`,
`envbooker/` (migrations excluded by config)

**Intent**: Apply ruff's formatter and safe auto-fixes across the tree, then hand-
fix the single residual finding, so the baseline is fully green before enforcement.

**Contract**: run `uv run ruff format .` then `uv run ruff check --fix .`; manually
collapse the one `SIM102` nested-if (research located it in the source set). Land
as a single mechanical commit. No behavior change — verified by the regression run
in change #4.

#### 4. Regression verification (before + after)

**File**: n/a — verification activity gating the cleanup commit

**Intent**: Prove the bulk reformat + auto-fix changed no behavior by running the
full Django suite immediately **before** the cleanup (capture the baseline pass +
test count) and again **after**, and confirming identical results. This is the
regression guard the mechanical diff relies on, made explicit rather than assumed.

**Contract**: with local Postgres up and `DJANGO_DEBUG=True` set (disables
`SECURE_SSL_REDIRECT` per test-plan §6.6), run
`DJANGO_DEBUG=True uv run python manage.py test` on the clean tree first and
record the OK/test-count; run it again after `ruff format`/`check --fix` + the
`SIM102` fix; both must pass with the same test count. If Postgres is down, bring
it up (`docker compose up -d`) — the suite is Postgres-only and cannot be skipped
for this change (the exclusion-constraint tests are the core regression signal).

### Success Criteria:

#### Automated Verification:

- ruff installed: `uv run ruff --version`
- Lint clean: `uv run ruff check .` exits 0
- Format clean: `uv run ruff format --check .` exits 0
- Baseline regression run captured **before** cleanup: `DJANGO_DEBUG=True uv run
  python manage.py test` passes; OK + test count recorded
- Post-cleanup regression run **after** cleanup matches the baseline: same
  `DJANGO_DEBUG=True uv run python manage.py test` passes with the **same** test
  count (no tests added/removed/skipped by the reformat)
- mypy still green (no regression from formatting):
  `DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .`

#### Manual Verification:

- The reformat diff is layout/auto-fix only — spot-check a couple of the 12
  reformatted files for no semantic change
- Migrations are untouched by the format pass (excluded as intended)

**Implementation Note**: After automated verification passes, pause for human
confirmation of the manual check before Phase 2.

---

## Phase 2: Lefthook pre-commit gate

### Overview

Add ruff to the existing pre-commit hook over staged files, auto-fixing and
re-staging, so manual or teammate edits that bypass the agent are caught and
healed at commit time.

### Changes Required:

#### 1. Ruff commands in Lefthook

**File**: `lefthook.yml`

**Intent**: Add two ruff commands to the existing `pre-commit.commands` table
(beside `typecheck`), scoped to staged Python files, auto-fixing and re-staging.

**Contract**:
- A `format` command: `uv run ruff format {staged_files}` with `stage_fixed: true`,
  globbed to `*.py`.
- A `lint` command: `uv run ruff check --fix {staged_files}` with
  `stage_fixed: true`, globbed to `*.py`.
- Leave the existing `typecheck` command (whole-project `mypy` with dummy env
  vars) unchanged. Ruff commands need no env vars and no full-project context.

### Success Criteria:

#### Automated Verification:

- Hook config valid and lists the ruff commands: `uv run lefthook dump` (or
  `lefthook validate`) shows `format`, `lint`, `typecheck` under `pre-commit`
- Clean tree commits successfully (ruff finds nothing): a no-op staged change runs
  the hook and passes
- A staged file with a fixable violation (e.g. an unsorted import) is auto-fixed
  and re-staged by `uv run lefthook run pre-commit` (the staged content becomes
  clean; exit 0)
- A staged file with a **non-fixable** violation (e.g. an undefined name `F821`)
  fails the hook (exit non-zero)

#### Manual Verification:

- A real `git commit` with a deliberately mis-formatted staged file lands a clean,
  ruff-formatted commit (the working tree shows the fix applied) within a couple
  of seconds

**Implementation Note**: After automated verification passes, pause for human
confirmation of the real-commit test before Phase 3.

---

## Phase 3: Per-edit agent hook + cleanup + docs

### Overview

Add the per-edit `PostToolUse` agent hook (the only layer that feeds the agent
mid-session), rename the misnamed settings file into place, and document the gate.

### Changes Required:

#### 1. Rename the misnamed settings file

**File**: `.claude/settings.jsom` → `.claude/settings.json`

**Intent**: Give the inert file its correct name so Claude Code actually loads it
(rather than deleting and re-creating), preserving git history.

**Contract**: `git mv .claude/settings.jsom .claude/settings.json`.
(`settings.local.json` is unaffected.)

#### 2. Add the PostToolUse hook + adjust contents

**File**: `.claude/settings.json` (the renamed file)

**Intent**: On every agent `Write`/`Edit`, format + safe-auto-fix the edited
Python file and feed the result back into the agent's context — announce on
change, surface residual findings as blocking. Reconcile the stale generic-
template contents while here.

**Contract**:
- Add a `hooks.PostToolUse` entry, matcher `Write|Edit`, running a shell handler.
- Handler reads the path from stdin (`jq -r '.tool_input.file_path'`), bails
  (exit 0, no output) unless the path ends in `.py`, then runs
  `uv run ruff format <file>` and `uv run ruff check --fix <file>`.
- On a successful format/fix, emit a short non-blocking note via the PostToolUse
  `additionalContext` mechanism naming the file and advising a re-read (see
  Critical Implementation Details).
- On residual non-auto-fixable findings, surface them as blocking (exit 2 /
  blocking decision) so the agent fixes them next turn.
- Keep it fast: single file only, safe fixes only.
- Adjust the inherited template `permissions` block: drop the JS-ecosystem
  entries that don't apply to this Python/uv project (`npm`/`npx`/`node`) and
  keep only what's sensible for the project layer; leave `settings.local.json`
  as the source of session-specific permissions.

#### 3. Documentation

**File**: `CLAUDE.md`

**Intent**: Record the lint/format gate, the ruff commands, the
`uv run lefthook install` requirement (already noted for the typecheck), and the
per-edit hook — so the next dev/agent understands both layers. Update the "No
linting tools are configured" tripwire to reflect that ruff is now wired.

**Contract**: a short subsection under the existing tooling/commands notes,
mirroring the Q-01 typecheck docs; correct the stale tripwire line.

### Success Criteria:

#### Automated Verification:

- `.claude/settings.json` exists and is valid JSON with a `PostToolUse` hook
  matching `Write|Edit`: `jq . .claude/settings.json`
- The misnamed file is gone (renamed, not orphaned): `test ! -e .claude/settings.jsom`
- The hook handler is a no-op for non-Python paths and runs ruff for `.py` paths
  (exercise the handler script directly with a sample stdin JSON payload for each
  case)
- ruff still green repo-wide: `uv run ruff check .` and
  `uv run ruff format --check .` exit 0

#### Manual Verification:

- In a live session, editing a deliberately mis-formatted `.py` file triggers the
  hook: the file is reformatted and the agent receives the announce note (and, for
  a seeded non-fixable finding, the blocking feedback)
- `CLAUDE.md` reads correctly and the old "no linting tools" tripwire is updated

**Implementation Note**: After automated verification passes, pause for human
confirmation of the live-session hook test.

---

## Testing Strategy

### Unit Tests:

- None added — lint/format changes are non-behavioral. The existing Django suite
  is the regression guard (must stay green after Phase 1's reformat).

### Regression Tests (Phase 1):

- The full Django suite is the regression guard for the bulk reformat. Run it
  **before** the cleanup to capture a baseline (pass + test count), and **after**
  to confirm identical results — same count, all passing. Requires local Postgres
  up and `DJANGO_DEBUG=True` (Postgres-only suite; `SECURE_SSL_REDIRECT` else
  301s every request per test-plan §6.6). A divergence in count or any failure
  means the mechanical diff is not actually mechanical — stop and investigate.

### Manual Testing Steps:

1. Phase 1: inspect the cleanup diff for layout-only changes; run the suite.
2. Phase 2: stage a mis-formatted file, `git commit`, confirm it lands clean and
   fast; stage a non-fixable violation, confirm the commit is blocked.
3. Phase 3: in a live session, edit a mis-formatted `.py`, confirm the hook
   reformats and announces; seed a non-fixable finding, confirm blocking feedback.

## Performance Considerations

Ruff runs in milliseconds, so the per-edit hook stays well within the M3 L3
"few seconds" budget even on every `Write`/`Edit`. The pre-commit ruff commands
operate on staged files only and add negligible time over the existing mypy run.

## Migration Notes

No data or schema changes. Contributors already run `uv run lefthook install`
once after cloning (Q-01); no new install step. The Phase 1 cleanup is a single
mechanical commit; land it while write-path slices are quiescent (currently true).

## References

- Research: `context/changes/lint-and-format-gate/research.md`
- Roadmap Q-02: `context/foundation/roadmap.md:180-198`
- Q-01 precedent (config shape, phasing, Lefthook harness):
  `context/archive/2026-06-10-typing-and-type-check-gate/plan.md`
- F3 test-glob lesson:
  `context/archive/2026-06-10-typing-and-type-check-gate/reviews/impl-review.md`
- Test-plan §5 gate / Phase 5 boundary: `context/foundation/test-plan.md:108-126`
- M3 L3 hook doctrine: `CLAUDE.md` §"Module 3 Lesson 3"

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Tooling + config + one-time green baseline

#### Automated

- [ ] 1.1 ruff installed (`uv run ruff --version`)
- [ ] 1.2 Lint clean (`uv run ruff check .` exits 0)
- [ ] 1.3 Format clean (`uv run ruff format --check .` exits 0)
- [ ] 1.4 Baseline regression run captured green before cleanup (OK + test count recorded)
- [ ] 1.5 Post-cleanup regression run matches baseline (same test count, all passing)
- [ ] 1.6 mypy still green (no regression from formatting)

#### Manual

- [ ] 1.7 Reformat diff is layout/auto-fix only (spot-check reformatted files)
- [ ] 1.8 Migrations untouched by the format pass

### Phase 2: Lefthook pre-commit gate

#### Automated

- [ ] 2.1 Hook config lists `format`, `lint`, `typecheck` under `pre-commit`
- [ ] 2.2 Clean tree commits successfully (ruff finds nothing)
- [ ] 2.3 Fixable violation in a staged file is auto-fixed and re-staged
- [ ] 2.4 Non-fixable violation fails the hook

#### Manual

- [ ] 2.5 Real `git commit` lands a clean, ruff-formatted commit within seconds

### Phase 3: Per-edit agent hook + cleanup + docs

#### Automated

- [ ] 3.1 `.claude/settings.json` valid with a `Write|Edit` `PostToolUse` hook
- [ ] 3.2 `.claude/settings.jsom` renamed to `.json` (history preserved, no orphan)
- [ ] 3.3 Handler is a no-op for non-`.py` paths, runs ruff for `.py` paths
- [ ] 3.4 ruff still green repo-wide

#### Manual

- [ ] 3.5 Live edit of a mis-formatted `.py` triggers reformat + announce (and blocking feedback on a seeded non-fixable finding)
- [ ] 3.6 `CLAUDE.md` updated; old "no linting tools" tripwire corrected
