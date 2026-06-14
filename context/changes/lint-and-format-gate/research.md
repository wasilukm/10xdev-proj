---
date: 2026-06-13T22:34:36+02:00
researcher: Mariusz Wasiluk
git_commit: 4f0fe8595563cae90b71ce0c7074847a5dd52f35
branch: main
repository: 10xdev-proj
topic: "Lint + format tooling with pre-commit & per-edit agent hooks (roadmap Q-02)"
tags: [research, codebase, lint, format, ruff, quality-gate, hooks, lefthook]
status: complete
last_updated: 2026-06-13
last_updated_by: Mariusz Wasiluk
---

# Research: Lint + format tooling with pre-commit & per-edit agent hooks

**Date**: 2026-06-13T22:34:36+02:00
**Researcher**: Mariusz Wasiluk
**Git Commit**: 4f0fe8595563cae90b71ce0c7074847a5dd52f35
**Branch**: main
**Repository**: 10xdev-proj

## Research Question

For the `lint-and-format-gate` change (roadmap **Q-02**): select a
linter/formatter, decide the baseline strictness (and lenient handling for
`migrations/` + tests, per the Q-01 precedent), design the two M3 L3 local hook
layers (a per-edit Claude Code `PostToolUse` agent hook and the existing Lefthook
`pre-commit` gate), and decide how to handle existing non-compliant files —
treating mechanical formatting and lint rules separately, while minding churn
against in-flight write-path slices (S-05 / S-06 / SPIKE-01).

## Summary

- **Tool choice: `ruff` — near-unconditional.** It is the `CLAUDE.md`-suggested
  default, is one binary that does **both** lint and format, runs in
  milliseconds (the only profile fast enough for a per-edit hook per the M3 L3
  "keep it fast" rule), and is from the same makers as `uv`. `.gitignore`
  already lists `.ruff_cache/` — the intent signal is on disk. There is no
  serious competitor for this project; `flake8`+`black`+`isort` is three tools,
  slower, and adds nothing here.
- **The blast radius is small and overwhelmingly mechanical.** Measured with
  `ruff` 0.x at line-length 88 against the live tree:
  - **Format**: 12 of 35 first-party source files would reformat; 7 of 10
    migration files would reformat. Pure layout, zero behaviour change.
  - **Lint, default rules (`E4,E7,E9,F`)**: only **2 findings**, both
    unused-import (`F401`) in `tests.py`, both auto-fixable.
  - **Lint, a broader sensible set (`E,W,F,I,UP,B,SIM,C4`)**: **27 findings on
    source** (22 `E501` line-too-long, 4 `I001` import-order [auto], 1 `SIM102`
    collapsible-if [manual]); **38 on tests** (24 `E501`, plus auto-fixable
    `UP017`/`SIM117`/`I001`/`F401`). The single non-mechanical decision is
    **`E501` / line length** — it dominates both counts and is a policy choice,
    not a bug list.
- **Recommended adoption: one-time repo-wide `ruff format` + `ruff check --fix`
  commit that lands fully green, then enforce.** Churn risk is **low right now**
  because the named in-flight slices (S-05, S-06, SPIKE-01) **have no change
  folders on disk** — nothing is mid-flight to collide with. This is the
  quiescent window the roadmap asked to wait for. Format and the auto-fixable
  lint rules are mechanically safe to bulk-apply; the lone `SIM102` is a
  one-line manual fix.
- **`E501` recommendation: let the formatter own line length, don't enable
  `E501` in the linter** (or keep it only as a loose backstop). `ruff format`
  wraps code at 88; the residual `E501` are mostly long strings/comments/URLs
  the formatter deliberately won't break, so an enabled `E501` just produces
  un-actionable noise. This collapses ~46 of the findings to zero with no manual
  edits.
- **Mirror Q-01's "lenient global + strict islands" config shape**, and carry
  forward its **F3 lesson**: the test carve-out must match **both** the
  `reservations/tests/` *package* **and** the flat `accounts/tests.py` /
  `catalog/tests.py` modules. Exclude `**/migrations/**` entirely.
- **Hook layering (M3 L3):** the per-edit `PostToolUse` hook runs `ruff` on the
  **single edited file** (fast, scoped); the Lefthook `pre-commit` gate adds
  `ruff` commands over `{staged_files}` alongside the existing `mypy` command.
  **Tripwire:** the project's Claude settings file is misnamed
  **`.claude/settings.jsom`** (stale generic template, no `hooks` key) — the new
  hook must go in a correctly-named `.claude/settings.json`.

Three decisions remain explicitly for `/10x-plan`: the **exact rule set + line
length**, **fix-vs-report** in each layer, and the **single-commit vs
grandfather** adoption call (this research recommends single-commit and explains
why).

## Detailed Findings

### Tool selection — ruff

- `CLAUDE.md` §tripwires: *"No linting tools are configured in `pyproject.toml`
  yet — add ruff or similar before wiring up CI."* Ruff is the named default.
- `roadmap.md:190` (Q-02 unknown): *"`ruff` (lint + format in one; the
  `CLAUDE.md`-suggested default, fastest, ideal for a per-edit hook) vs
  `flake8`+`black`+`isort` vs others."*
- One binary covers lint **and** format, removing the black/isort/flake8 triad
  and any tool-ordering coordination. Sub-second (here, sub-100ms) runtime is
  the only thing that satisfies the M3 L3 rule that a per-edit hook stay within
  "a few seconds" (`CLAUDE.md` §Key rules).
- Same vendor (Astral) as `uv`, which the project already standardises on.
- `.gitignore` already ignores `.ruff_cache/` — installed via `uvx ruff` for
  this measurement; the plan will `uv add --dev ruff`.
- **Open knob for the plan:** `target-version`. `UP017` (suggesting
  `datetime.UTC`) fired, so ruff is applying a modern Python target; pin
  `target-version = "py314"` (matching `.python-version`) explicitly rather than
  relying on inference, and confirm ruff's released versions accept `py314`.

### Measured blast radius (live tree, line-length 88)

**Formatting** (`ruff format --check`):

| Scope | Would reformat | Already clean |
|-------|----------------|---------------|
| First-party source (excl. migrations) | **12** | 23 |
| Migrations | **7** | 3 |

**Linting — default rules `E4,E7,E9,F`** (`ruff check`): **2 errors total**,
both `F401` unused-import in `accounts/tests.py:2` and `catalog/tests.py:2`,
both `[*]` auto-fixable.

**Linting — broader set `E,W,F,I,UP,B,SIM,C4`** (`ruff check --statistics`):

*First-party source (excl. migrations & tests) — 27 findings, 4 auto-fixable:*

| Rule | Count | Auto-fix | Note |
|------|-------|----------|------|
| `E501` line-too-long | 22 | no | **policy decision** — mostly long strings/comments the formatter won't break |
| `I001` unsorted-imports | 4 | yes | mechanical |
| `SIM102` collapsible-if | 1 | no | the **only** genuine manual source edit |

*Tests (`accounts/tests.py`, `catalog/tests.py`, `reservations/tests/`) — 38
findings, 14 auto-fixable:*

| Rule | Count | Auto-fix |
|------|-------|----------|
| `E501` line-too-long | 24 | no |
| `UP017` datetime-timezone-utc | 5 | yes |
| `SIM117` multiple-with-statements | 4 | yes |
| `I001` unsorted-imports | 3 | yes |
| `F401` unused-import | 2 | yes |

**Reading:** strip `E501` (a line-length policy, see below) and the actual
human-judgement surface is **one** `SIM102` on source. Everything else is either
`ruff format`'s job or `ruff check --fix`'s job.

### The `E501` / line-length decision (the only real strictness lever)

- `E501` accounts for 22/27 source and 24/38 test findings — it is the entire
  apparent "lint debt".
- `ruff format` reflows **code** to the configured width but intentionally does
  **not** break long string literals, comments, or URLs. So an enabled `E501`
  rule mostly flags lines the formatter has already decided to leave — producing
  un-actionable noise rather than fixes.
- **Standard ruff practice:** let the formatter own line length and either
  disable `E501` or keep it only as a loose backstop (e.g. a higher
  `line-length` so only egregious lines flag). Recommendation: **don't enable
  `E501` in the lint set** (formatter owns width). This removes ~46 findings
  with zero manual edits and keeps the gate honest (every remaining lint finding
  is actionable).
- Line-length value is a plan knob: 88 (ruff/black default) is the path of least
  resistance and what the measurements above assume.

### Baseline strictness — mirror Q-01's shape

Q-01 (`pyproject.toml`) established the precedent config shape this change
should mirror for consistency:

- `[tool.mypy]` lenient global + `[[tool.mypy.overrides]]` carve-outs for
  `*.migrations.*`, `*.tests`, `*.tests.*`, then `disallow_untyped_defs` strict
  islands on services/models/views/forms.
- The ruff analogue: a **modest, high-signal rule set** globally
  (`E`/`W`/`F`/`I`/`UP`/`B`/`SIM` is a reasonable starting proposal; `E501` off
  per above), `exclude = ["**/migrations/**"]`, and `per-file-ignores` relaxing
  test-only noise if desired. Ratchet additional rule families later (the
  "lenient global, tighten over time" ladder), exactly as Q-01 inverted toward
  `--strict`.
- **F3 lesson carried forward (critical):** Q-01's impl-review found
  `*.tests.*` matched the `reservations/tests/` package but **missed flat
  `accounts/tests.py` and `catalog/tests.py`**. Any ruff test carve-out
  (`per-file-ignores`/`extend-exclude`) must use a glob that catches **both**
  `**/tests/**` *and* `**/tests.py`. (`context/archive/2026-06-10-typing-and-type-check-gate/reviews/impl-review.md` F3.)

### Existing-files handling — recommend single green commit

The roadmap (`roadmap.md:194`) frames three options: (a) one-time repo-wide
cleanup commit ending fully green, (b) grandfather / changed-files-only, (c)
phased per-app — deciding **formatting** (mechanical, safe to bulk-apply) and
**lint rules** (may need real fixes) separately.

- **Formatting → bulk-apply (option a).** 12 source + 7 migration files, pure
  layout, no behaviour change, and the existing test suite is the regression
  guard (Q-01 ran the same play for annotations).
- **Lint → bulk-apply too, because the manual surface is one `SIM102`.** With
  `E501` off, `ruff check --fix` clears `I001`/`UP017`/`SIM117`/`F401`
  automatically; the single `SIM102` is a one-line manual collapse. There is no
  meaningful "real fixes" backlog that would justify grandfathering.
- **Churn is low *now* and that is the deciding factor.** `roadmap.md:186` and
  the change note both warn to land this "when write-path slices are quiescent."
  `ls context/changes/` shows only `bootstrap-verification/` and
  `lint-and-format-gate/` — **S-05, S-06, and SPIKE-01 have no change folders on
  disk**, i.e. none are in-flight. This *is* the quiescent window; a one-time
  format diff will not collide with an open branch. (If a write-path slice opens
  before this lands, prefer to land Q-02 first or rebase it.)
- **Migrations:** exclude from the gate (Django-generated; test-plan §7 "do not
  test generated migrations" reflects the same trust boundary). Don't bulk-format
  them into the enforced set — `extend-exclude`/`exclude` `**/migrations/**`.

### Hook layering (M3 L3) — concrete shapes

**Current enforcement state** (extends Q-01's harness):

| Layer | State | Evidence |
|-------|-------|----------|
| Lefthook `pre-commit` | **exists** — runs `mypy .` only | `lefthook.yml` (typecheck command) |
| Per-edit agent hook | **absent** | no `hooks` key anywhere; `.claude/settings.jsom` is a stale generic template |
| CI | absent (out of scope) | test-plan Phase 5 owns it |

**Layer 1 — per-edit `PostToolUse` agent hook** (the new layer; the only one
that feeds the agent mid-session):
- Matcher `Write|Edit` (`CLAUDE.md` §Task Router).
- Read the path from stdin: `jq -r '.tool_input.file_path'`; **guard to `*.py`**
  and bail (exit 0) on anything else — ruff is fast but most edits aren't Python.
- Run `ruff format <file>` then `ruff check --fix <file>` on the **single file**
  (scoped, sub-second). On residual (non-auto-fixable) findings, exit **2** so
  stdout flows into `additionalContext` and the agent self-corrects next turn
  (`CLAUDE.md` §Exit codes). Unlike the typecheck (slow django-stubs plugin,
  deliberately *not* a per-edit hook per Q-01 research), ruff is the textbook
  fast per-edit check.
- **Tripwire:** write this into a correctly-named **`.claude/settings.json`**.
  The existing `.claude/settings.jsom` (note the typo) is inert and holds an
  unrelated stale template (`npm`/`npx`/`node` perms); real session permissions
  live in `.claude/settings.local.json`. Plan should also decide whether to
  delete/rename the dead `.jsom`.

**Layer 2 — Lefthook `pre-commit`** (catches manual edits / teammate commits
that bypass the agent):
- Add `ruff` command(s) to the existing `pre-commit.commands` table over
  `{staged_files}` (Lefthook templating), filtered to `*.py`. Two commands:
  `ruff format` and `ruff check`.
- **Fix-vs-report decision (plan):** either fail on `--check`/`--diff` and let
  the developer/agent fix, or auto-fix with Lefthook `stage_fixed: true` to
  re-stage. Unlike `mypy`, ruff over staged files needs **no** env vars or full
  project context, so it's a clean staged-files command.
- Keep the existing `mypy .` typecheck command as-is (whole-project, env-var'd —
  plugin needs full context).

**Out of scope (confirmed):** CI wiring — test-plan **Phase 5** stands up the CI
harness and later *consumes* this gate (`test-plan.md:110,117-126`;
`roadmap.md:188`). Don't author a Gitea/Forgejo workflow here. (Remote is
self-hosted **Gitea** via `tea`, not GitHub — relevant only to Phase 5.)

## Code References

- `pyproject.toml:21-44` — Q-01's `[tool.mypy]` + `[[tool.mypy.overrides]]`
  (lenient global + strict islands + `*.migrations.*`/`*.tests`/`*.tests.*`
  carve-out); the config-shape precedent to mirror for ruff.
- `lefthook.yml:1-4` — existing `pre-commit.commands.typecheck` (the harness
  Q-02 extends; add ruff commands alongside).
- `.claude/settings.jsom` — **misnamed** stale template (no `hooks` key); the
  per-edit hook belongs in a new `.claude/settings.json`.
- `.claude/settings.local.json` — real session permissions (no hooks).
- `.gitignore` — already lists `.ruff_cache/` (intent signal).
- `accounts/tests.py:2`, `catalog/tests.py:2` — `F401` unused imports (the only
  default-rule findings).
- `reservations/views.py` — among the 12 source files `ruff format` would touch.
- `CLAUDE.md` §"Module 3 Lesson 3" / §Task Router / §Exit codes — the hook
  lifecycle, per-edit/commit/push/CI layering, and `additionalContext` feedback
  doctrine governing both layers.

## Architecture Insights

- **Two-layer, not three.** Q-02 deliberately delivers only the per-edit and
  pre-commit layers (`roadmap.md:188`); pre-push and CI are out of scope. The
  per-edit hook is the *new* capability — it's the only layer that hands
  feedback to the agent mid-work.
- **Fast-vs-slow split is the organising principle.** Q-01 put the *slow*
  django-stubs typecheck at pre-commit and explicitly refused it as a per-edit
  hook. Q-02 supplies the *fast* check (ruff) that the per-edit layer was
  reserved for — the two changes complete the layering by speed class, not by
  accident.
- **Mechanical-vs-judgement split governs adoption.** Formatting + auto-fixable
  lint = bulk-apply safely; the residual human surface here is a single
  `SIM102`. This is why a one-time green commit beats grandfathering — the usual
  reason to grandfather (a large real-fix backlog) doesn't exist.
- **The gate ratchets over a green typed baseline.** Q-01 left first-party code
  typed and mypy-green; Q-02 lints over that, fulfilling the lint half of the
  `test-plan.md §5 "lint + typecheck"` gate that Q-01 left typing-only.

## Historical Context (from prior changes)

- `context/archive/2026-06-10-typing-and-type-check-gate/research.md` — Q-01
  research. Establishes: the enforcement-layer table (all absent then; Lefthook
  now exists), the "lenient global + strict islands, then invert" ladder, the
  M3 L3 fast-vs-slow layering rule (slow checks → commit/push/CI; per-edit stays
  fast lint/format — i.e. *exactly* ruff), and the Gitea-not-GitHub note for CI.
- `context/archive/2026-06-10-typing-and-type-check-gate/plan.md` — the 3-phase
  shape (tooling+config+green baseline → fix/annotate → wire Lefthook last so the
  hook ratchets over green code). A clean template for Q-02's phasing.
- `context/archive/2026-06-10-typing-and-type-check-gate/reviews/impl-review.md`
  — **F3** (test carve-out must catch flat `tests.py` *and* the `tests/`
  package) and F1/F2 (the "annotate/lint *every* first-party callable/file"
  goal is easy to under-cover at the edges, e.g. `admin.py`). Carry both into
  Q-02's exclude/per-file-ignore globs and its "fully green" definition.
- `context/foundation/roadmap.md:180-198` — Q-02 definition, unknowns, scope
  (BOTH local layers), and the churn/quiescence risk note.
- `context/foundation/test-plan.md:108-126` — §5 gate table: `lint + typecheck`
  is "required after Phase 5"; Q-02 supplies the lint half locally, Phase 5
  enforces in CI. `post-edit hook` row is "recommended (config owned by M3 L3)"
  — that's this change.
- `context/foundation/lessons.md` — no lint/format/hook lesson yet; the only
  entries are the infra-control-verification rule and the always-save-impl-review
  rule (the latter applies when Q-02 reaches its own impl-review).

## Related Research

- `context/archive/2026-06-10-typing-and-type-check-gate/research.md` — the
  direct predecessor (Q-01); Q-02 extends its harness and reuses its config
  shape and layering doctrine.

## Open Questions

Carried to `/10x-plan` (Q-02 unknowns, now grounded):

1. **Exact rule set + line length** — adopt `E,W,F,I,UP,B,SIM` (+`C4`?) with
   `E501` **off** (formatter owns width) and `line-length = 88`? Or keep `E501`
   on with a higher width as a backstop? Research recommends `E501` off.
2. **Fix-vs-report per layer** — per-edit hook: `--fix` then exit 2 on residue
   (recommended). Pre-commit: `--check`/fail vs auto-`--fix` + `stage_fixed`?
3. **Adoption** — single repo-wide green commit (recommended; churn is low, no
   slices in-flight) vs grandfather. Land before any S-05/S-06/SPIKE-01 folder
   opens, or rebase it.
4. **`target-version`** — pin `py314` (matches `.python-version`); confirm the
   pinned ruff release accepts it.
5. **Dead `.claude/settings.jsom`** — delete/rename it when adding the correctly
   named `.claude/settings.json`? (Plan decision; it's currently inert.)
6. **Tests in the gate** — lint tests too (auto-fixes are clean), or relax via
   `per-file-ignores`? Mind the F3 glob (both `tests.py` and `tests/`).
