# Browse & Reserve (S-02) — Plan Brief

> Full plan: `context/changes/browse-and-reserve/plan.md`

## What & Why

EnvBooker's north-star slice: a signed-in user browses the env list (owners + upcoming windows visible)
and creates a non-overlapping reservation that appears immediately. It's the **validation milestone** —
if the no-overlap guarantee holds end-to-end under realistic use, the core product hypothesis is proven.

## Starting Point

F-01 (Env + Reservation models with a Postgres GiST exclusion constraint) and S-01 (auth) are done. The
booking/listing UI does not exist: `catalog/views.py` and `reservations/views.py` are stubs, `/` is a
placeholder TemplateView, and the stack has no JS/HTMX/CSS framework yet.

## Desired End State

`/` becomes the env-list dashboard: each env shows free/busy-now state, current reservation, and upcoming
reservations within 24h (owner + localized window). A per-row form books a window (start + duration, incl.
"until next reservation" capped at 4h); the row updates live via HTMX with no page reload. Overlaps are
rejected inline, naming the conflict and suggesting the next free window.

## Key Decisions Made

| Decision | Choice | Why | Source |
|---|---|---|---|
| No-reload mechanism | HTMX partial swap (vendored, no build step) | Satisfies "no full page reload"; sets up S-03; Django-idiomatic | Plan |
| Time input | Start + duration; presets + "until next reservation" (4h cap) | Fewest inputs, surfaces the 4h nudge for free | Plan |
| Overlap rejection | Name conflict + suggest next free window | Smoother recovery; gap-finder already built for "until next" | Plan |
| Reservation horizon | Current + next 24h | Matches PRD secondary criterion; bounded row height | Plan |
| List route | Env list replaces `/` (keeps `name=home`) | Matches "from landing" <30s criterion | Plan |
| Timezone | Single org `settings.TIME_ZONE` | Correct for a single-org tool; one setting | Plan |
| Testing | Core behavior + overlap focus (incl. DB race) | Verifies the core no-double-booking promise | Plan |

## Scope

**In scope:** env-list dashboard, current + 24h horizon with owners, reservation creation, race-safe
overlap rejection with named conflict + suggestion, HTMX live row updates, core tests.

**Out of scope:** filtering (S-03), edit/cancel own reservation (S-04), admin override (S-06), admin
catalog UI (S-05), per-user timezones, notifications, analytics.

## Architecture / Approach

Server-rendered Django (CBVs + forms + templates) + HTMX for partial swaps. The env row is an includable
partial that is also the HTMX swap target, so both successful booking and overlap rejection re-render the
same fragment. Gap-finding lives in one `reservations/services.py` module, reused by the "until next
reservation" duration and the rejection's next-free-window suggestion. The DB exclusion constraint stays
the authority; the view catches `IntegrityError` and re-queries to build the message.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Dashboard + HTMX | Read-only env list at `/`, free/busy + 24h horizon, HTMX wired | N+1 across envs (mitigated by filtered Prefetch) |
| 2. Booking flow | Create view, gap-finder, race-safe overlap rejection, live row swap | Getting the IntegrityError race path right (no 500s) |
| 3. Tests | Core behavior + overlap/race coverage | Time-sensitive tests needing a frozen `now` |

**Prerequisites:** F-01 + S-01 (both done); local Postgres running per CLAUDE.md.
**Estimated effort:** ~2–3 sessions across 3 phases.

## Open Risks & Assumptions

- Exact org timezone string to confirm at implementation time (placeholder: `Europe/Warsaw`).
- Scope creep is the named risk for this slice — filtering / edit / admin override stay out.

## Success Criteria (Summary)

- A new user can land on `/`, find a free env, and book a non-overlapping window that appears live.
- Overlap attempts are rejected with a named conflict + suggested next window, no double-booking possible.
- The no-overlap guarantee is verified by tests including the concurrent DB race path.
