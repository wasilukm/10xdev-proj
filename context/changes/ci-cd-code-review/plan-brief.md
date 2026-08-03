# CI/CD Agentic Code Reviewer — Plan Brief

> Full plan: `context/changes/ci-cd-code-review/plan.md`
> Research: `context/changes/ci-cd-code-review/research.md`
> Requirements: `context/changes/ci-cd-code-review/requirements.md`

## What & Why

Every PR to `main` should get an automated, structured code review — six criteria scored 1–10
with rationales, posted as a PR comment plus a pass/fail label. The repo has **no CI at all**
today, and `packages/code_reviewer` is a 67-line scaffold that reviews a filesystem path, not
a diff. On a **public** repo, PR content is attacker-controlled by design, so the reviewer's
architecture matters as much as its rubric.

## Starting Point

No `.github/` directory exists — this is the repo's first CI workflow. (Two prior research
docs claim the remote is Gitea; that is stale — `origin` is GitHub, the repo is public, and
the default branch is `main`, not the `master` in `requirements.md:3`.) None of the three
`ai-cr:*` labels exist. The `code_reviewer` scaffold has three live defects research
identified: it is **not actually read-only** (`allowed_tools` auto-approves, it doesn't
restrict — so with `bypassPermissions` the agent has `Bash` and `Write`), its JSON extraction
only searches the last text block, and it exits 1 identically for "bad code" and "API down".
The package is also excluded from mypy (`pyproject.toml:30`).

## Desired End State

Opening a PR triggers a review that posts one sticky comment with six scores and a summary,
and applies `ai-cr:passed` or `ai-cr:failed`. Pushing commits updates that same comment.
Adding `ai-cr:review` re-runs it. Fork PRs skip silently. Nothing the reviewer does can block
a merge.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Runtime | Own SDK program + in-repo composite action | Keeps the rubric fully under local control | Research (D1) |
| Auth | Scoped API key in a spend-capped workspace | On a public repo the CI secret should be the one whose theft hurts least | Research (D2) |
| Credential handling | Generic `api-credential` + `credential-kind` inputs | Lets the auth choice be revisited without touching the action | Research (D3) |
| Agent tools | **None at all** — no filesystem access | Removes the read primitive structurally; every published incident was fixed at the architecture layer, none by better prompting | Research (D6) |
| Verdict | Computed in Python, not asked of the model | Deterministic, tunable without prompt edits, and injection cannot raise it | Research (D5) |
| Posture | Advisory — never a required status check | The reviewed party authors 100% of the input, so a pass is a quality signal, not authorization | Research (D7) |
| Threshold | Any criterion < 6 fails; security & integrity < 7 fails | A floor names *which* criterion failed; a mean lets four 9s average away a security hole | Plan |
| Rubric size | 6 criteria — the 5 from requirements + `review_integrity` | An injection attempt surfaces as a low score instead of silently succeeding | Plan |
| Context passed | Diff only — no file contents in v1 | Smallest surface and cost; the smoke test showed diff-only caught both a perf and a behavioral regression | Plan |
| Fork PRs | Skip silently via job-level `if:` | Skipped counts as passing, so the guard can never wedge a fork PR | Plan |
| Model | `claude-sonnet-5`, full ID pinned | Aliases move with SDK upgrades; A/B against Opus after ~20 real PRs on false-positive rate, not price | Plan |
| Package shape | Rewrite in place, split into 5 modules | Makes verdict + rendering pure and unit-testable without an API call | Plan |
| Type checking | Close the mypy gap in this change | The code parsing hostile input should be checked; config lands with the code it protects | Plan |
| Reviewer ref | PR merge commit (checkout default) | Lets you iterate on the reviewer inside a PR — revisit if anyone else gets push access | Plan |
| Labels | Created by hand once | Avoids granting repo-wide `issues: write` permanently to solve a one-time problem | Plan |

## Scope

**In scope:** rewrite of `packages/code_reviewer` (models, hardened SDK call, prompt, verdict,
rendering, CLI exit codes); subpackage mypy + pytest wired into `lefthook.yml`; workflow +
composite action + sticky-comment script; the two outcome labels and the `ai-cr:review` retry;
README and `CLAUDE.md` updates.

**Out of scope:** `anthropics/claude-code-action`; any file context beyond the diff; fork PR
review; the `workflow_run` privilege split; required status checks or branch-protection
changes; `issues: write`; a lint/test CI job (that's test-plan Phase 5, a different thing);
prompt-caching env vars; fixing the pre-existing `ruff-post-edit.sh:32` conflation.

## Architecture / Approach

```
.github/workflows/ai-code-review.yml   when / who / permissions / side-effects
.github/actions/ai-code-review/        how the review runs (composite)
.github/scripts/sticky-comment.sh      comment upsert by marker
packages/code_reviewer/                the reviewer itself (pure, testable)
```

`gh pr diff` (three-dot, with exclusions) → JSON-encoded into the user turn → agent with
`tools=[]`, `setting_sources=[]`, `permission_mode="dontAsk"`, and a pydantic-derived
`output_format` schema → validated `ReviewResult` → Python computes the verdict → comment
rendered from the struct alone. The rubric lives in the system prompt (trusted); PR content
never does (untrusted). The two modules an attacker would most want to reach — verdict and
rendering — are pure functions with no SDK dependency.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Rewrite the package | Diff-in / verdict-out program, testable locally with no GitHub dependency | Rubric quality is unknown until real diffs hit it; the SDK's hardening options must all be set correctly at once |
| 2. Workflow + action, dry-run | Runs on every same-repo PR, writes to the job summary only | Shell injection via PR title/body if `${{ }}` is interpolated into a `run:` body; permission 403s |
| 3. Write-back | Sticky comment, outcome labels, `ai-cr:review` retry | Comment duplication if marker matching is wrong; a stuck `ai-cr:review` label if removal isn't `if: always()` |

**Prerequisites:** an `ANTHROPIC_API_KEY` scoped to a spend-capped Console workspace, stored
as a repo secret — and per `lessons.md`, *verify the workspace spend limit actually exists on
this account tier* before treating it as the mitigation. Before Phase 3: create `ai-cr:passed`,
`ai-cr:failed`, `ai-cr:review` by hand.

**Estimated effort:** ~3 sessions, one per phase — but Phase 2 has a deliberate observation
window (several real PRs) between its automated completion and Phase 3.

## Open Risks & Assumptions

- **Rubric calibration is unproven.** The only evidence is a 6-line synthetic diff. The
  floor-6 / security-7 threshold is a starting guess; Phase 2's real deliverable is tuning it
  before anything becomes visible on PRs.
- **The workspace spend cap may not exist** on this account tier. If it doesn't,
  `max_budget_usd` per run is the only ceiling and the monthly exposure is unbounded by
  anything but PR volume.
- **A PR can modify the reviewer that judges it** (checkout defaults to the merge commit).
  Accepted for a single maintainer, and necessary to iterate on the reviewer at all — must be
  revisited the moment anyone else gets push access.
- **Sonnet 5's introductory pricing ends 2026-08-31**; budget at $3/$15 after that.
- **`review_integrity` will score 10/10 on nearly every honest PR** — low information most of
  the time, and its false-positive behaviour on oddly-worded descriptions is untested.
- Diff-only review gives a weaker `idiomaticity` signal, since the model can't see whether a
  helper duplicates something in `catalog/services.py`.

## Success Criteria (Summary)

- Every same-repo PR to `main` gets exactly one comment with six defensible scores, and it
  updates in place rather than accumulating.
- A weak PR draws `ai-cr:failed`; fixing it flips the same comment to `ai-cr:passed`.
- A broken reviewer (bad key, API outage, oversized diff) is visibly distinguishable from bad
  code — different exit code, different comment — while still failing closed to
  `ai-cr:failed`.
