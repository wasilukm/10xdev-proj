# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Verify named platform controls exist before relying on them in the risk register

- **Context**: /10x-infra-research risk register & mitigations — any phase of infrastructure.md authoring where a specific cost-control or safety mechanism is named as a mitigation row.
- **Problem**: infrastructure.md (2026-05-24) recommended "set Fly spending cap to $25/mo on day one" as risk #1 mitigation, but Fly.io does not offer spending caps (confirmed via Fly Cost Management docs and community staff replies — only post-hoc "Accident Forgiveness"). The risk register pointed at a control that doesn't exist, leaving the #1 risk effectively unmitigated until caught at deploy time.
- **Rule**: When /10x-infra-research names a specific cost-control or safety mechanism (spending cap, billing alert, hard ceiling, scoped token capability) as a mitigation, verify against the platform's first-party docs that the mechanism actually exists and is accessible to a new account before writing it into the risk register. If unverifiable, mark the risk as un-mitigated rather than papering it with a non-existent control.
- **Applies to**: research, plan-review

## Always save the impl-review report before finishing

- **Context**: Every /10x-impl-review run (or any review that produces findings), regardless of whether the user picks "Triage", "Save", or jumps straight to fixes.
- **Problem**: When triage is chosen directly, no report file is written, so findings/decisions/rationale aren't persisted and /10x-archive later warns "no impl-review found".
- **Rule**: Always write the review report to reviews/impl-review.md and set change.md status to impl_reviewed before finishing a review — even when the user triages directly without choosing a save option.
- **Applies to**: impl-review
