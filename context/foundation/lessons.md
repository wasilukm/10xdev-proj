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

## Cross-app data migrations need an explicit dependency, and must be verified on a fresh DB

- **Context**: Any Django data migration (RunPython) that reads a model from another app via a relation — e.g. `catalog/migrations/0003_backfill_environment_updated_at.py` annotating `Min("reservations__created_at")` from within the catalog app.
- **Problem**: 0003 declared only `dependencies = [("catalog", "0002_...")]`. On a fresh-DB build the executor ordered it before the reservations FK existed in the historical project state, so the reverse accessor was unknown → `FieldError: Cannot resolve keyword 'reservations'`. This broke `create_test_db` (the entire suite couldn't run) and would fail a clean CI/prod `migrate`. It was missed because the authoring "migrate clean" check ran against an already-migrated dev DB (a single-pending-node state that includes every app's tables), which masks the missing dependency — and tests were not re-run after the migration was written.
- **Rule**: When a data migration references another app's model (FK, reverse relation, or `apps.get_model` from a sibling app), add that app's relevant migration to `dependencies` so ordering is deterministic. Always verify migration changes by building a fresh test/throwaway DB (`manage.py test`, or migrate on an empty DB), never by `migrate` on the existing dev DB.
- **Applies to**: implement, impl-review
