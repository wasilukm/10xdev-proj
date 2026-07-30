# code-reviewer

A scaffold for a future automated code-review agent, built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview). This
is an independent uv project — its own `pyproject.toml`, `uv.lock`, and
`.venv` — deliberately kept out of the root `envbooker` dependency tree so
the agent SDK never ships in the Django app's deploy image.

Currently this only proves the wiring works end to end: a minimal, read-only
"review this path" entry point. Real review logic, prompt design, and any
CI/PR integration are future work.

## Install

```bash
cd packages/code_reviewer
uv sync
```

## Run

```bash
uv run code-reviewer <path>
```

`<path>` defaults to `.` if omitted. The path is validated with pydantic
(`ReviewRequest`) before any API call is made — a nonexistent path fails
fast with a `ValidationError`.

The agent is given read-only tools (`Read`, `Grep`, `Glob`) and asked to end
its reply with a fenced JSON block. That block is parsed and validated
against a `ReviewResult` pydantic schema (`summary: str`, `issues: list[str]`)
before being printed, so a malformed agent response surfaces as a clear
validation error rather than being echoed as-is.

## Auth

The SDK needs an `ANTHROPIC_API_KEY` environment variable (it does not load
`.env` files automatically). If you're already logged in via the `claude`
CLI, the bundled SDK CLI may reuse that session instead.
