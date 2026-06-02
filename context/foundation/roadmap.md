---
project: EnvBooker
version: 1
status: draft
created: 2026-05-27
updated: 2026-06-03
prd_version: 1
main_goal: low-complexity
top_blocker: capacity
---

# Roadmap: EnvBooker

> Derived from `context/foundation/prd.md` (v1) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Vision recap

A small, fixed pool of shared test environments is contended for by a much larger pool of QA engineers and developers, with no shared system of record. EnvBooker turns "find an available env that fits this purpose" from a multi-minute chat thread into a self-serve action a new joiner can complete in 30 seconds, by surfacing per-env metadata (version, owner, purpose) the way generic room-booking tools cannot — and by guaranteeing no two reservations on the same env overlap. The core hypothesis being shipped — the one claim this roadmap exists to validate — is that an attribute-filtered env list plus a strictly non-overlapping reservation flow is the smallest combination that replaces the chat-based status quo.

## North star

**S-02: User signs in, browses the env list with reservation owners visible, creates a non-overlapping reservation on a free env, and sees it appear on the list immediately** — this is the smallest end-to-end slice (the validation milestone: the slice whose successful delivery would prove the core product hypothesis above) we can ship that exercises both halves of the value proposition (purpose-built discovery + collision-free booking with owner visibility). It is sequenced as early as Prerequisites allow.

Filtering (FR-009) is deliberately excluded from the north-star slice and lands in `S-03`; the primary Success Criterion's "under 30 seconds" target is therefore satisfied by `S-02 + S-03` together, not by `S-02` alone. This is a low-complexity sequencing bias — ship the booking half of the hypothesis first, then close the discovery half — not a scope cut.

## At a glance

| ID    | Change ID                       | Outcome (user can …)                                                                                                | Prerequisites    | PRD refs                                                  | Status   |
| ----- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------- | --------------------------------------------------------- | -------- |
| F-01  | env-and-reservation-data-model  | (foundation) Env + Reservation tables exist with DB-enforced no-overlap; admin seeds catalogue via Django `/admin/` | —                | FR-015, NFR §no-double-booking, Access Control            | done     |
| S-01  | org-restricted-auth             | sign up with an org-domain email, sign in, and sign out                                                             | —                | FR-001, FR-002, FR-004, Access Control                    | done     |
| S-02  | browse-and-reserve              | sign in, see the env list with owners + upcoming windows, and create a non-overlapping reservation that appears immediately | F-01, S-01       | FR-008, FR-010, FR-011, FR-015, US-01                     | done     |
| S-03  | filter-env-list                 | filter the env list by availability, purpose / use-case tag, and project — closing the <30s primary success criterion | S-02             | FR-009, US-01, Success Criteria §Primary                  | proposed |
| S-04  | edit-own-reservation            | modify or cancel a reservation they own                                                                             | S-02             | FR-012, FR-013, FR-015, Access Control                    | proposed |
| S-05  | admin-env-catalog               | (admin) create, modify (with warn + change-badge), and delete (when no active reservations) env definitions via a first-class admin UI | F-01, S-01       | FR-005, FR-006, FR-007, Access Control                    | proposed |
| S-06  | admin-reservation-override      | (admin) modify or cancel any reservation, including those owned by other users                                      | S-02, S-01       | FR-014, Access Control                                    | proposed |
| SPIKE-01 | timezone-calendar-edge-cases | (spike) understand & harden time-window handling against DST gaps/folds, leap years, and other calendar boundaries  | S-02             | NFR §reliability, FR-011, FR-015                          | proposed |

## Streams

Navigation aid — groups items that share a Prerequisites chain. Canonical ordering still lives in the dependency graph below; this table is the proposed reading order across parallel tracks.

| Stream | Theme                | Chain                                                | Note                                                                                              |
| ------ | -------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| A      | Booking core         | `F-01` → `S-02` → `S-03` / `S-04` / `S-06`           | Carries the north star and the discovery closure; capacity bias keeps `S-03`/`S-04`/`S-06` parallel after `S-02`. |
| B      | Account lifecycle    | `S-01`                                               | Standalone visible-enabler slice; joins Stream A at `S-02` and Stream C at `S-05`.                |
| C      | Admin catalogue      | `S-05`                                               | Joins Stream A at `F-01` and Stream B at `S-01`; can run parallel with the rest of Stream A once both are done. |

## Baseline

What's already in place in the codebase as of 2026-05-27 (auto-researched + user-confirmed). Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent — no `templates/` directory, no frontend framework; Django default rendering only.
- **Backend / API:** partial — Django 6.0.5 config in `envbooker/`, only `/admin/` wired in `envbooker/urls.py`; zero domain apps (`apps.py` / `models.py` absent project-wide).
- **Data:** partial — `dj_database_url` configured in `envbooker/settings.py` (SQLite local / Postgres on Railway); no domain models or migrations beyond Django built-ins.
- **Auth:** partial — `django.contrib.auth` + `AuthenticationMiddleware` installed in `envbooker/settings.py`; no custom user model, no sign-up/sign-in/sign-out views, no org-domain restriction.
- **Deploy / infra:** present — Railway via `railway.toml` (Railpack → `collectstatic` → `migrate` → `gunicorn`); first deploy already shipped per `context/foundation/infrastructure.md`.
- **Observability:** absent — gunicorn access-log only; no Sentry / OTel / structured logging.

## Foundations

### F-01: Env + Reservation data model with DB-enforced no-overlap

- **Outcome:** (foundation) Environment and Reservation tables exist with descriptive attributes (version, owner, purpose, project, use-case tag) on Env and a Postgres-level exclusion constraint guaranteeing no two reservations on the same env overlap in time. Admin can seed and edit both via Django's built-in `/admin/` until a first-class admin UI ships in S-05.
- **Change ID:** env-and-reservation-data-model
- **PRD refs:** FR-015, NFR §no-double-booking, Access Control
- **Unlocks:** S-02 (needs Env table to list against and Reservation table to write into), S-05 (replaces Django `/admin/` with first-class env CRUD UI), the FR-015 race-condition unknown (resolved at DB layer, not in app code)
- **Prerequisites:** —
- **Parallel with:** S-01
- **Blockers:** —
- **Unknowns:**
  - Should the DB-level overlap constraint use `tstzrange` + `EXCLUDE USING gist`, or a query-time lock + check? — Owner: TBD (resolves in `/10x-plan`). Block: no.
- **Risk:** Carrying the no-overlap rule at the application layer alone is the documented race-condition trap (PRD FR-015 Socratic note); pushing it into the DB schema is the durable fix and the load-bearing correctness call for the entire product. Sequenced first because every booking slice depends on it.
- **Status:** done

## Slices

### S-01: Org-domain-restricted authentication (sign-up, sign-in, sign-out)

- **Outcome:** A new user can sign up with an email whose domain matches the organisation's, sign in with email + password, and sign out. Unauthenticated requests to gated routes are redirected to sign-in.
- **Change ID:** org-restricted-auth
- **PRD refs:** FR-001, FR-002, FR-004, Access Control
- **Prerequisites:** —
- **Parallel with:** F-01
- **Blockers:** —
- **Unknowns:**
  - Which exact org email domain(s) does the sign-up validator allow? — Owner: user. Block: no (a placeholder env-var-driven validator unblocks S-02; the literal domain list can be wired at deploy time).
- **Risk:** Auth absent in baseline; all subsequent user-facing slices depend on this. Keeping it visible-enabler (a real slice, not a "scaffold" foundation) reflects that the sign-up domain restriction is a product rule, not infra plumbing.
- **Status:** done

### S-02: Browse env list and create a non-overlapping reservation (north star)

- **Outcome:** A signed-in user opens the env list, sees every env with its current state (free / reserved) and the identities + time windows of current and upcoming reservation owners, picks a free env, enters a time window, and confirms. The reservation is created and appears on the list immediately (no page reload); attempts to reserve an overlapping window are rejected with a message naming the conflicting reservation's owner and window.
- **Change ID:** browse-and-reserve
- **PRD refs:** FR-008, FR-010, FR-011, FR-015, US-01
- **Prerequisites:** F-01, S-01
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Should the rejection message name only the conflicting reservation, or also suggest the next free window on that env? — Owner: user. Block: no.
  - What's the recommended-max-duration nudge wording (PRD FR-011 says ~4h)? — Owner: user. Block: no.
- **Risk:** This is the validation milestone; if it lands and the no-overlap guarantee holds end-to-end under realistic concurrent use, the product hypothesis is proven. The principal risk is scope creep — keep filtering, edit/cancel, and admin override OUT of this slice so it stays plannable in one `/10x-plan` invocation.
- **Status:** done

### S-03: Filter env list (availability, purpose / use-case, project)

- **Outcome:** The signed-in user can narrow the env list to "free now" / "busy now", by purpose/use-case tag, and by project; results update without a full page reload. Combined with S-02, this is what makes the primary <30-second find-and-reserve success criterion achievable.
- **Change ID:** filter-env-list
- **PRD refs:** FR-009, US-01, Success Criteria §Primary
- **Prerequisites:** S-02
- **Parallel with:** S-04, S-05, S-06
- **Blockers:** —
- **Unknowns:**
  - Is filter state shareable via URL (so a new joiner can be pointed at a pre-filtered list)? — Owner: user. Block: no.
- **Risk:** Filtering is must-have but was deliberately deferred from the north-star slice to keep S-02 plannable. The <30s success criterion is not provable until this lands; treat S-03 as the closure of the primary success criterion, not a nice-to-have.
- **Status:** proposed

### S-04: Modify and cancel own reservation

- **Outcome:** A signed-in user can modify their own reservation (time window) or cancel it. Modifications are subject to the same overlap rejection (FR-015) as creation. Modifications/cancellations to other users' reservations are not permitted (the admin-override path is S-06).
- **Change ID:** edit-own-reservation
- **PRD refs:** FR-012, FR-013, FR-015, Access Control
- **Prerequisites:** S-02
- **Parallel with:** S-03, S-05, S-06
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Small surface; mostly a re-use of S-02's overlap check on a different write path. Low complexity, no new domain concepts.
- **Status:** proposed

### S-05: Admin env-catalogue UI (create, modify with warning + change-badge, delete-if-no-active-reservations)

- **Outcome:** An admin can create new env definitions, modify existing definitions (with a pre-save warning if active or upcoming reservations exist, and a "definition changed since you reserved" badge on those reservations post-save), and delete env definitions only when no active or upcoming reservations remain. Replaces the Django `/admin/` fallback that F-01 leaves in place.
- **Change ID:** admin-env-catalog
- **PRD refs:** FR-005, FR-006, FR-007, Access Control
- **Prerequisites:** F-01, S-01
- **Parallel with:** S-03, S-04, S-06
- **Blockers:** —
- **Unknowns:**
  - How long does the "definition changed since you reserved" badge persist on a reservation — until the reservation ends, until the owner acknowledges it, or both? — Owner: user. Block: no.
- **Risk:** The notify-instead-of-block stance on modify (PRD FR-006 Socratic note) is deliberate but easy to half-implement; getting the badge persistence and pre-save warning right is what makes the resolution coherent rather than just lenient. Can be parked behind the user-flow slices because Django `/admin/` covers seeding in the interim — a deliberate low-complexity sequencing choice.
- **Status:** proposed

### S-06: Admin override of any reservation

- **Outcome:** An admin can modify or cancel any reservation, including reservations owned by other users. Documented as the escape hatch for stale or abandoned reservations.
- **Change ID:** admin-reservation-override
- **PRD refs:** FR-014, Access Control
- **Prerequisites:** S-02, S-01
- **Parallel with:** S-03, S-04, S-05
- **Blockers:** —
- **Unknowns:** —
- **Risk:** The audit-trail question — "should admin overrides be logged so the original owner can see who cancelled their reservation?" — is not in scope per PRD §Non-Goals (no notifications) but is the natural next concern. Keep this slice strictly to the FR-014 capability; do not grow it.
- **Status:** proposed

## Spikes

### SPIKE-01: Timezone & calendar edge-case hardening

- **Outcome:** (spike) A documented understanding of how EnvBooker's time-window handling behaves across calendar edge cases, plus targeted hardening of the reservation form. Concretely: `ReservationForm.clean()` calls `timezone.make_aware(start, get_current_timezone())`, which raises on a DST gap/fold local datetime (`Europe/Warsaw`, twice a year) — today that surfaces as a 500 rather than a form error. The spike scopes the full class of calendar corner cases (DST gaps/folds, leap years, leap seconds if relevant, month/year boundaries on "until next reservation" gap math) and lands fixes that turn each into a graceful, user-visible outcome.
- **Change ID:** timezone-calendar-edge-cases
- **PRD refs:** NFR §reliability, FR-011 (duration), FR-015 (no-overlap)
- **Prerequisites:** S-02
- **Parallel with:** S-03, S-04, S-05, S-06
- **Blockers:** —
- **Source:** Deferred from the S-02 (`browse-and-reserve`) implementation review (finding F5, 2026-06-03). Booking otherwise works; this is reliability hardening, not a functional gap.
- **Unknowns:**
  - Which calendar edge cases can actually occur given a single org timezone + half-open `[start, end)` ranges, and which are theoretical? — Owner: user. Block: no.
  - For a DST-gap start time, reject with a form error or snap forward to the valid instant? — Owner: user. Block: no.
- **Risk:** Low blast radius (form-layer input handling), but the failure mode is a 500 on otherwise-valid-looking input twice a year. Easy to under-scope to just the `make_aware` call and miss the gap math in `compute_end` / `next_free_window`; the spike exists precisely to map the whole class before patching one symptom.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                       | Suggested issue title                                                                                  | Ready for `/10x-plan` | Notes                                            |
| ---------- | ------------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------- | ------------------------------------------------ |
| F-01       | env-and-reservation-data-model  | EnvBooker: Env + Reservation models with DB-enforced no-overlap                                        | yes                   | Run `/10x-plan env-and-reservation-data-model`   |
| S-01       | org-restricted-auth             | EnvBooker: Sign-up (org domain), sign-in, sign-out                                                     | yes                   | Run `/10x-plan org-restricted-auth`              |
| S-02       | browse-and-reserve              | EnvBooker: Browse env list and create non-overlapping reservation (north star)                         | no                    | Promotes to ready once F-01 + S-01 are done       |
| S-03       | filter-env-list                 | EnvBooker: Filter env list (availability, purpose, project)                                            | no                    | Promotes to ready once S-02 is done               |
| S-04       | edit-own-reservation            | EnvBooker: Modify and cancel own reservation                                                           | no                    | Promotes to ready once S-02 is done               |
| S-05       | admin-env-catalog               | EnvBooker: Admin env-catalogue UI (create / modify-with-warning / delete-if-no-active)                 | no                    | Promotes to ready once F-01 + S-01 are done       |
| S-06       | admin-reservation-override      | EnvBooker: Admin override of any reservation                                                           | no                    | Promotes to ready once S-02 + S-01 are done       |
| SPIKE-01   | timezone-calendar-edge-cases    | EnvBooker: Spike — DST/leap-year/calendar edge-case hardening for reservation time windows             | no                    | Deferred from S-02 impl review (F5); ready after S-02 |

## Open Roadmap Questions

(PRD `## Open Questions` reports no blocking questions — `gray_areas_resolved` checkpoint cleared during shaping. No cross-cutting questions surfaced during this roadmap generation either. Add entries here if planning surfaces new gaps that span multiple slices.)

## Parked

- **Usage statistics / analytics dashboards.** Why parked: PRD §Non-Goals.
- **Notifications about reservations (email, push, in-app reminders).** Why parked: PRD §Non-Goals; users check the UI when they need to know.
- **Integration with external test-runner / CI systems.** Why parked: PRD §Non-Goals; EnvBooker is a booking-of-record, not an automation hub.
- **Native iOS / Android apps.** Why parked: PRD §Non-Goals; web-only for v1 (responsive layout may be considered but is not a v1 commitment).
- **Self-service password reset.** Why parked: PRD §Non-Goals; admin resets passwords manually for v1.
- **Audit log of admin reservation overrides.** Why parked: not in PRD; called out in S-06's Risk line as the natural next concern but explicitly out of v1 scope.

## Done

- **F-01: (foundation) Environment and Reservation tables exist with descriptive attributes (version, owner, purpose, project, use-case tag) on Env and a Postgres-level exclusion constraint guaranteeing no two reservations on the same env overlap in time. Admin can seed and edit both via Django's built-in `/admin/` until a first-class admin UI ships in S-05.** — Archived 2026-05-30 → `context/archive/2026-05-28-env-and-reservation-data-model/`. Lesson: —.
- **S-01: A new user can sign up with an email whose domain matches the organisation's, sign in with email + password, and sign out. Unauthenticated requests to gated routes are redirected to sign-in.** — Archived 2026-05-31 → `context/archive/2026-05-29-org-restricted-auth/`. Lesson: —.
- **S-02: A signed-in user opens the env list, sees every env with its current state (free / reserved) and the identities + time windows of current and upcoming reservation owners, picks a free env, enters a time window, and confirms. The reservation is created and appears on the list immediately (no page reload); attempts to reserve an overlapping window are rejected with a message naming the conflicting reservation's owner and window.** — Archived 2026-06-03 → `context/archive/2026-05-31-browse-and-reserve/`. Lesson: —.
