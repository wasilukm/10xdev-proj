# Lint & Format Gate (Q-02) — Plan Brief

> Full plan: `context/changes/lint-and-format-gate/plan.md`
> Research: `context/changes/lint-and-format-gate/research.md`

## What & Why

Adopt **ruff** (lint + format in one binary) and enforce it at two local M3 L3
layers — a per-edit Claude Code `PostToolUse` agent hook and the existing
Lefthook `pre-commit` gate. Closes the `CLAUDE.md` lint tripwire and the lint
half of test-plan §5 / Risk #6, which Q-01 deliberately left typing-only.

## Starting Point

`pyproject.toml` has `[tool.mypy]` only; Lefthook already runs `mypy` at
pre-commit (Q-01), over a green, typed first-party baseline. No ruff config, no
per-edit hook. The project Claude settings file is misnamed `.claude/settings.jsom`
(inert). Measured blast radius is small: 12/35 source files reformat; the only
non-auto-fixable lint finding is a single `SIM102`.

## Desired End State

`ruff check .` and `ruff format --check .` pass tree-wide (migrations excluded).
A commit with a fixable violation is auto-fixed and re-staged; a non-fixable one
is blocked. When the agent edits a `.py` file, a hook formats + auto-fixes it and
announces the change (or surfaces residual findings) back into the agent's
context. The gate is documented in `CLAUDE.md`.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Tool | ruff (lint + format) | One fast binary; the `CLAUDE.md` default; only profile fast enough for a per-edit hook | Research |
| Rule set | `E,W,F,I,UP,B,SIM`, `E501` off, line-length 88 | Every finding stays actionable; formatter owns width, collapsing ~46 noise findings | Plan |
| Python target | `target-version = "py314"` | Matches `.python-version`; pin explicitly rather than infer | Plan |
| Adoption | One-time repo-wide green commit | Manual surface is one line; churn is low now (no slices in-flight) | Plan |
| Per-edit hook | Auto-fix + announce; exit 2 on residue | Agent self-corrects mid-session; announce avoids stale file-state churn | Plan |
| Pre-commit | Auto-fix + re-stage (`stage_fixed`) | Heals manual/teammate edits inline; commit always lands clean | Plan |
| Tests | Linted + formatted fully | All test fixes are auto-fixable; only migrations excluded (avoids the fragile F3 pattern) | Plan |
| `.jsom` file | Rename to `.json` + adjust | Preserve history, give it the name Claude Code actually loads | Plan |

## Scope

**In scope:** ruff dependency + config; one-time green cleanup commit; Lefthook
pre-commit ruff commands; per-edit `PostToolUse` hook; rename `.jsom` → `.json`;
`CLAUDE.md` docs.

**Out of scope:** CI wiring (test-plan Phase 5); pre-push hook; `E501`
enforcement; linting/formatting migrations; changing the mypy command;
`--unsafe-fixes`; any behavior change.

## Architecture / Approach

Land green first, then ratchet gates over it (mirrors Q-01). Phase 1 installs +
configures ruff and applies a single mechanical cleanup commit. Phase 2 adds ruff
to the existing Lefthook pre-commit hook over `{staged_files}` with auto-fix +
re-stage. Phase 3 adds the per-edit agent hook (the only layer that feeds the
agent mid-work), renames the settings file, and documents. Fast/slow split:
ruff (ms) serves the per-edit layer that Q-01's slow mypy plugin could not.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Tooling + green baseline | ruff installed/configured; tree fully green | Bulk reformat hides a semantic change — guarded by the test suite |
| 2. Pre-commit gate | ruff over staged files, auto-fix + re-stage | Hook rewrites staged content (safe fixes only, so semantically identical) |
| 3. Per-edit hook + rename + docs | `PostToolUse` hook; `.json` rename; CLAUDE.md | Hook mutating edits causes stale file-state — mitigated by announce-on-change |

**Prerequisites:** Q-01 done (green typed baseline, Lefthook installed); write-path
slices quiescent (currently true — no S-05/S-06/SPIKE-01 folders on disk).
**Estimated effort:** ~1 session across 3 phases (small, mostly mechanical).

## Open Risks & Assumptions

- A write-path slice opening before this lands would collide with the cleanup
  diff — land Phase 1 while quiescent, or rebase the slice onto it.
- The exact PostToolUse `additionalContext` field names must be confirmed against
  the installed Claude Code version during Phase 3.
- Assumes ruff's released `target-version` accepts `py314` (UP017 already fired,
  indicating a modern target).

## Success Criteria (Summary)

- `ruff check .` and `ruff format --check .` exit 0 tree-wide; test suite + mypy
  stay green after the cleanup.
- A fixable staged violation auto-fixes and commits clean; a non-fixable one is
  blocked.
- Editing a mis-formatted `.py` in a live session reformats it and announces the
  change to the agent (and blocks on a seeded non-fixable finding).
