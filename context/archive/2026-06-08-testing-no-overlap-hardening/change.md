---
change_id: testing-no-overlap-hardening
title: Testing no overlap hardening
status: archived
created: 2026-06-08
updated: 2026-06-09
archived_at: 2026-06-09T21:49:40Z
---

## Notes

Rollout Phase 1 from `context/foundation/test-plan.md` (Risk #1) — prove a
constraint-violating overlapping reservation is rejected with a clean user-facing
error (not a 500, not a silent second row) on both the create and edit write paths,
and convert `reservations/` to the `tests/` package layout (cookbook §6 first
sub-phase). See `research.md` for the grounded write-path trace and recommended
test surface.
