---
change_id: ui-visual-polish
title: Ui visual polish
status: archived
created: 2026-06-28
updated: 2026-06-28
archived_at: 2026-06-28T22:42:43Z
---

## Notes

Implemented across `74ae95c` (design system), `d607838` (button row + theme toggle),
`b166d76` (slim env table). Plan was authored retrospectively; manual visual review passed
2026-06-28.

Deviations from the committed plan (both user-requested during manual review):

- **Dark-mode toggle.** Plan committed dark via `prefers-color-scheme` only; user asked for
  an in-app switch. Added a nav `◐ Theme` toggle — a small vanilla-JS snippet (no build step)
  that sets `data-theme` on `<html>` and persists to `localStorage`, with a no-FOUC head
  script; CSS lets a manual choice override the OS default. Still no framework/build step.
- **Env-list table slimmed.** Plan said "no markup restructure beyond classes"; user asked to
  drop the Version and Owner columns (neither is a filter axis) and move Status beside Name to
  cut horizontal scroll. Env owner still shows in the admin Manage table. Duration field pinned
  to 5.5rem so it stays legible in the roomier Current/Upcoming cells.
