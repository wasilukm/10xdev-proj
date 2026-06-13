<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Lint & Format Gate (Q-02)

- **Plan**: context/changes/lint-and-format-gate/plan.md
- **Scope**: All 3 phases (full plan)
- **Date**: 2026-06-14
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

Behavior-neutrality of the Phase-1 reformat verified across all 15 source files
(import sorting, F401 removals, UP017 UTC swap, SIM117 with-collapses, and the
one manual SIM102 — all equivalent). Hook is injection-safe and loop-safe.
Automated criteria re-verified: ruff check/format green, rename clean, lefthook
lists format/lint/typecheck, all four hook exit-paths behave correctly.

## Findings

### F1 — Blocking hook feedback written to stdout, not stderr

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: .claude/hooks/ruff-post-edit.sh:16
- **Detail**: On a residual non-fixable finding the handler prints the message to stdout then `exit 2`. Claude Code feeds **stderr** back to the agent on exit 2; stdout on exit 2 shows in transcript but isn't injected into context. The block fires but the concrete finding text likely never reaches the agent to self-correct from — the core point of the agentic hook. The plan deferred "confirm field names against the installed version."
- **Fix**: Redirect the blocking message to stderr (`printf ... >&2` on line 16); re-confirm against the installed Claude Code hook contract.
- **Decision**: FIXED — superseded by unified JSON: blocking findings now emit `decision: block` + `reason` (exit 0). F1 and F3 share one feedback mechanism (JSON on stdout) via an `emit()` helper.

### F2 — Tooling failure conflated with lint findings (agent wedge)

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (Reliability)
- **Location**: .claude/hooks/ruff-post-edit.sh:12-18
- **Detail**: `LINT_EXIT` is treated as blocking whenever non-zero. ruff returns 1 for lint violations, 2 for internal/config error, 127 when ruff/uv is missing. All non-1 cases take `exit 2` and tell the agent "non-auto-fixable issues … fix before proceeding" — so an environment fault wedges the agent on every edit with a misleading, un-actionable message.
- **Fix A ⭐ Recommended**: Block only on `LINT_EXIT == 1`; for `>= 2` (incl. 127) print a "ruff/uv unavailable or errored" note and `exit 0`.
  - Strength: Agent never wedged by an environment problem it can't fix from an edit; matches M3 L3 "don't block the loop."
  - Tradeoff: A genuine ruff internal error on a real violation passes silently until pre-commit catches it.
  - Confidence: HIGH — ruff exit-code semantics are stable/documented.
  - Blind spot: None significant.
- **Fix B**: Keep blocking but branch the message for `>= 2`/127 ("tooling unavailable") while still `exit 2`.
  - Strength: Surfaces a broken toolchain loudly.
  - Tradeoff: Still blocks the agent every edit until env is repaired.
  - Confidence: MED.
  - Blind spot: Doesn't help if the agent can't fix the environment.
- **Decision**: SKIPPED

### F3 — Reformat "re-read" note not injected into agent context

- **Severity**: 🔎 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: .claude/hooks/ruff-post-edit.sh:24-26
- **Detail**: The "ruff auto-fixed … re-read" note is plain stdout on exit 0. PostToolUse success stdout isn't injected into context, so the announce-on-change mechanism the plan and CLAUDE.md (l.51, "additionalContext") describe doesn't reach the agent. Only OBSERVATION because safe-fixes-only means a stale view never risks correctness — a later Edit mismatch forces a re-read anyway.
- **Fix**: Emit the note as JSON `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"..."}}`, or align CLAUDE.md/plan to state the note is transcript-only.
- **Decision**: FIXED — emit hookSpecificOutput.additionalContext JSON via shared `emit()` helper (same mechanism as F1's blocking path)

### F4 — `ruff format` exit code unchecked

- **Severity**: 🔎 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .claude/hooks/ruff-post-edit.sh:10
- **Detail**: Only `check --fix` gates the hook; a `ruff format` failure is captured into `FORMAT_OUT` and silently ignored. Low impact — `check` usually fails on the same file — but the format leg has no signal.
- **Fix**: Optionally surface a non-zero `ruff format` exit alongside the lint result; otherwise leave as-is.
- **Decision**: SKIPPED

### F5 — Change description undersells the autofix families

- **Severity**: 🔎 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency / Docs
- **Location**: context/changes/lint-and-format-gate/change.md (+ p1 commit)
- **Detail**: The cleanup is described as "layout + auto-fixes plus one manual SIM102," but the diff also applies UP017 (`timezone.utc`→`UTC`) and SIM117 (nested-`with` collapse) semantic-rewrite autofixes — behavior-neutral and within ruff's safe set (research anticipated them), so a description-completeness nit. Also: the handler parses stdin with `python3` where plan/CLAUDE.md say `jq` (benign, arguably better — jq isn't installed here).
- **Fix**: One line in the changelog naming UP017/SIM117; optionally update CLAUDE.md's jq reference to match the python3 handler.
- **Decision**: FIXED (CLAUDE.md only) — noted handler parses path via python3, not jq; UP017/SIM117 changelog note declined
