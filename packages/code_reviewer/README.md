# code-reviewer

A diff-only, agentic PR reviewer for EnvBooker, built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview). This is an
independent uv project — its own `pyproject.toml`, `uv.lock`, and `.venv` —
deliberately kept out of the root `envbooker` dependency tree so the agent SDK never
ships in the Django app's deploy image.

Given a PR's title, description, and diff, it scores six criteria on a 1–10 scale via
the SDK's structured output, computes a pass/fail verdict in pure Python (never asked
of the model), and renders a sanitized PR comment from the validated result alone. The
agent has **no tools** — no filesystem access, no web access — so there is no read
primitive for a malicious diff to exploit.

## Install

```bash
cd packages/code_reviewer
uv sync
```

## Run

```bash
uv run code-reviewer <diff-file> --comment-path <out.md> --result-json-path <out.json>
```

| Input | Source |
|---|---|
| PR title | `PR_TITLE` environment variable |
| PR description | `PR_BODY` environment variable |
| Diff | contents of `<diff-file>` (a path, never passed as diff text on argv) |

Flags: `--max-diff-bytes` (default 200000), `--model` (default `claude-sonnet-5`, a
full model ID — never the `"sonnet"`/`"opus"` alias), `--max-turns` (default 5),
`--max-budget-usd` (default 0.50).

Outputs:
- The rendered PR comment markdown, written to `--comment-path`.
- The raw validated `ReviewResult` JSON, written to `--result-json-path`.
- `verdict=<pass|fail|error|skipped>` appended to `$GITHUB_OUTPUT`, if set.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Review ran, verdict pass |
| 1 | Review ran, verdict fail |
| 2 | Reviewer malfunctioned (API error, auth failure, schema violation, missing structured output, budget exhausted) |
| 3 | Skipped — diff exceeded `--max-diff-bytes` |

Codes 2 and 3 both fail closed — an unreviewable or broken run never reports as
`pass` — but stay distinguishable from code 1 so a broken reviewer is never mistaken
for bad code.

## Criteria

Six criteria, each scored 1–10: `implementation_correctness`, `idiomaticity`,
`complexity`, `test_coverage`, `security_and_safety`, `review_integrity`. The last
scores whether the PR itself attempts to manipulate the review (prompt injection,
false claims of prior approval); see `src/code_reviewer/prompt.py` for the full
rubric. The verdict fails if any criterion scores below its floor —
`security_and_safety` and `review_integrity` carry an elevated floor
(`src/code_reviewer/verdict.py`).

## Security posture

- The agent runs with `tools=[]` and a matching `disallowed_tools` list, so there is
  no read primitive to exfiltrate with.
- `setting_sources=[]` — the run never loads `.claude/settings.json` from the checked
  out PR branch (that file can define hooks that execute shell commands).
- The rubric and output contract live in the trusted `system_prompt`; PR content is
  passed in the user turn JSON-encoded, never string-interpolated.
- The verdict is computed in pure Python from the validated score struct — the model
  is never asked for a verdict, so an injection can at worst lower a score, never
  raise one or grant a pass directly.
- `render.py` sanitizes every piece of model-authored text before it can reach a
  rendered comment: HTML tags stripped, markdown images/links neutralized to their
  label text, `@`-mentions defused, and length-capped.

## Auth

The SDK needs an `ANTHROPIC_API_KEY` environment variable (it does not load `.env`
files automatically).

## Advisory posture

`ai-cr:passed` must never become a required status check, and the label may only
subtract, never grant merge rights — the reviewed party authors 100% of the PR
content, so a pass is a statistical quality signal, not an authorization decision.
