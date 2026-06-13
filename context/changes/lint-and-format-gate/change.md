---
change_id: lint-and-format-gate
title: Lint and format tooling with pre-commit and per-edit agent hooks
status: implementing
created: 2026-06-13
updated: 2026-06-13
archived_at: null
---

## Notes

Roadmap enabler Q-02. Deferred out of Q-01 (typing-only). Scope: select a
linter/formatter via research (ruff the likely default), then wire the two
M3 L3 local hook layers — a per-edit Claude Code agent hook (`PostToolUse` on
`Write|Edit`) and the existing lefthook `pre-commit` gate over staged files.

Out of scope: CI wiring (owned by test-plan Phase 5, which consumes this gate).

Open decisions for research/plan: tool choice; baseline strictness (lenient on
`migrations/` + tests, per Q-01 precedent); agent-hook shape (single-file vs
tree, `--fix` vs report-only); and how to handle existing non-compliant files
(one-time cleanup vs grandfather/changed-files-only vs phased per-app), treating
formatting and lint rules separately. Mind churn against in-flight S-05/S-06/SPIKE-01.
