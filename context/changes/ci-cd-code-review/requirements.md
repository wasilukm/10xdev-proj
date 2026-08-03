## Overall concept

- GHA workflow run for every new pull request to master
- composite action for the review itself so that main workflow is easy to reason about

## Input parameters

- pull request title
- pull request description (?? cost tradeoff)
- git diff

## Code Review Criteria

Each criterion is scored on a 1–10 scale, where 1 is the worst outcome and 10 is the best.

### implementation correctness

Does the diff actually do what the PR title and description claim, without logic errors, unhandled edge cases, or broken behavior for existing callers?

| Score | Meaning |
|-------|---------|
| 1–3 | Clearly broken: the stated goal is not achieved, or the change breaks existing behavior. |
| 4–6 | Mostly works on the happy path, but edge cases, error paths, or boundary conditions are mishandled. |
| 7–8 | Correct for realistic inputs; only minor or unlikely gaps remain. |
| 9–10 | Correct and complete, including edge cases and failure modes. |

### idiomaticity

Does the code read like the surrounding codebase — matching its Django/Python conventions, naming, layering (thin views, logic in `services.py`), and typing style?

| Score | Meaning |
|-------|---------|
| 1–3 | Fights the framework or the codebase: wrong layer, ad-hoc patterns, ignores established conventions. |
| 4–6 | Works, but noticeably diverges in naming, structure, or idiom from neighbouring code. |
| 7–8 | Follows local conventions with small inconsistencies. |
| 9–10 | Indistinguishable in style from well-written existing code; uses the framework as intended. |

### complexity

Is the solution as simple as the problem allows — free of unnecessary abstraction, duplication, deep nesting, or over-long functions?

| Score | Meaning |
|-------|---------|
| 1–3 | Hard to follow: speculative abstraction, heavy duplication, or functions that do far too much. |
| 4–6 | Understandable but carries avoidable indirection, nesting, or repetition. |
| 7–8 | Reasonably simple; a few spots could be tightened. |
| 9–10 | Minimal and direct — the simplest shape that solves the problem, and easy to change later. |

### test coverage

Are the behaviors introduced or changed by this diff covered by tests that would actually fail if the behavior regressed?

| Score | Meaning |
|-------|---------|
| 1–3 | No tests for changed behavior, or tests that cannot fail (asserting nothing meaningful). |
| 4–6 | Happy path covered; error paths, edge cases, and regressions are not. |
| 7–8 | Good coverage of main paths and the important edge cases. |
| 9–10 | Every meaningful branch and failure mode is covered by focused, independent tests. |

### security and safety

Does the change avoid introducing security or data-integrity risks — auth/permission gaps, injection, secret leakage, unsafe input handling, or destructive/irreversible operations?

| Score | Meaning |
|-------|---------|
| 1–3 | Introduces an exploitable flaw: missing authorization, injectable query, leaked secret, or unguarded destructive operation. |
| 4–6 | No direct exploit, but weak input validation, over-broad permissions, or risky error/data handling. |
| 7–8 | Safe under expected use; minor hardening opportunities remain. |
| 9–10 | Inputs validated, access properly scoped, secrets handled correctly, destructive paths guarded. |

## Parked for later

- business alignment (require broader context)
- architectural fit (require broader context)

## Expected side-effects

- PR comment with summary
- labels: `ai-cr:failed` (red) OR `ai-cr:passed` (green)

## Expected behavior

- on-demand retry when label `ai-cr:review` is added
