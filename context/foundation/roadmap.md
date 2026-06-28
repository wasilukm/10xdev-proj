---
project: EnvBooker
version: 1
status: draft
created: 2026-05-27
updated: 2026-06-28
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
| S-03  | filter-env-list                 | filter the env list by availability, purpose / use-case tag, and project — closing the <30s primary success criterion | S-02             | FR-009, US-01, Success Criteria §Primary                  | done     |
| S-04  | edit-own-reservation            | modify or cancel a reservation they own                                                                             | S-02             | FR-012, FR-013, FR-015, Access Control                    | done     |
| S-05  | admin-env-catalog               | (admin) create, modify (with warn + change-badge), and delete (when no active reservations) env definitions via a first-class admin UI | F-01, S-01       | FR-005, FR-006, FR-007, Access Control                    | done     |
| S-06  | admin-reservation-override      | (admin) modify or cancel any reservation, including those owned by other users                                      | S-02, S-01       | FR-014, Access Control                                    | done     |
| S-07  | ui-visual-polish                | see a visually polished, legible UI across every page — color, clear row/column structure, state badges, consistent type & spacing — built on a reusable design-token layer | S-02, S-03, S-04, S-05, S-06 | — (SC §Primary <30s legibility, §Secondary horizon, NFR §response) | done |
| SPIKE-01 | timezone-calendar-edge-cases | (spike) understand & harden time-window handling against DST gaps/folds, leap years, and other calendar boundaries  | S-02             | NFR §reliability, FR-011, FR-015                          | proposed |
| Q-01  | typing-and-type-check-gate      | (enabler) first-party code carries type hints and a `mypy` + `django-stubs` gate blocks untyped drift | F-01, S-01, S-02 | — (traces to `tech-stack.md` typing commitment) | done |
| Q-02  | lint-and-format-gate            | (enabler) a linter/formatter (tool TBD via research) runs locally via a per-edit agent hook + pre-commit, blocking style/lint drift | Q-01             | — (traces to `CLAUDE.md` lint tripwire, `test-plan.md` §5, M3 L3) | done     |

## Streams

Navigation aid — groups items that share a Prerequisites chain. Canonical ordering still lives in the dependency graph below; this table is the proposed reading order across parallel tracks.

| Stream | Theme                | Chain                                                | Note                                                                                              |
| ------ | -------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| A      | Booking core         | `F-01` → `S-02` → `S-03` / `S-04` / `S-06`           | Carries the north star and the discovery closure; capacity bias keeps `S-03`/`S-04`/`S-06` parallel after `S-02`. |
| B      | Account lifecycle    | `S-01`                                               | Standalone visible-enabler slice; joins Stream A at `S-02` and Stream C at `S-05`.                |
| C      | Admin catalogue      | `S-05`                                               | Joins Stream A at `F-01` and Stream B at `S-01`; can run parallel with the rest of Stream A once both are done. |
| D      | Quality / enablers   | `Q-01` → `Q-02`                                      | Cross-cutting; not vertical slices. `Q-01` (typing) lands first and stands up the lefthook `pre-commit` harness + `.claude/` hook conventions; `Q-02` (lint + format) extends that harness and adds the M3 L3 per-edit agent hook. |
| E      | Presentation / UX    | `S-07`                                               | Cross-cutting visual polish over the pages Stream A/B/C produced; ready once the user-facing slices it restyles are done. Establishes the design-token layer a future timeline-reservations view will inherit. |

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
- **Status:** done

### S-04: Modify and cancel own reservation

- **Outcome:** A signed-in user can modify their own reservation (time window) or cancel it. Modifications are subject to the same overlap rejection (FR-015) as creation. Modifications/cancellations to other users' reservations are not permitted (the admin-override path is S-06).
- **Change ID:** edit-own-reservation
- **PRD refs:** FR-012, FR-013, FR-015, Access Control
- **Prerequisites:** S-02
- **Parallel with:** S-03, S-05, S-06
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Small surface; mostly a re-use of S-02's overlap check on a different write path. Low complexity, no new domain concepts.
- **Status:** done

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
- **Status:** done

### S-06: Admin override of any reservation

- **Outcome:** An admin can modify or cancel any reservation, including reservations owned by other users. Documented as the escape hatch for stale or abandoned reservations.
- **Change ID:** admin-reservation-override
- **PRD refs:** FR-014, Access Control
- **Prerequisites:** S-02, S-01
- **Parallel with:** S-03, S-04, S-05
- **Blockers:** —
- **Unknowns:** —
- **Risk:** The audit-trail question — "should admin overrides be logged so the original owner can see who cancelled their reservation?" — is not in scope per PRD §Non-Goals (no notifications) but is the natural next concern. Keep this slice strictly to the FR-014 capability; do not grow it.
- **Status:** done

### S-07: Visual / UX polish across all pages

- **Outcome:** Every existing page reads as an intentionally designed product rather than raw Django output: a coherent color palette, clear visual structure for the env-list and reservations tables (legible row/column separation, hover/selected row states), colored availability **state badges** (free / busy) and reservation-owner cues, consistent typography and spacing, and styled forms/buttons across the booking, my-reservations, auth, and admin (manage / form / confirm-delete) surfaces. No new end-user capability — this restyles what S-02–S-06 already deliver so the <30-second find-and-reserve flow is fast to *scan*, not just functionally complete.
- **Change ID:** ui-visual-polish
- **PRD refs:** — (no direct FR; traces to Success Criteria §Primary — legibility serves the <30s scan-and-reserve target — §Secondary at-a-glance 24h horizon, and NFR §user-perceived response / browser support)
- **Prerequisites:** S-02, S-03, S-04, S-05, S-06 (polishes the pages those slices created; all done)
- **Parallel with:** SPIKE-01 — but both touch templates; coordinate to avoid churn if SPIKE-01's form-layer hardening lands concurrently
- **Approach (committed):** Hand-rolled design system, **no CSS framework and no build step** — a single static stylesheet served by the existing whitenoise pipeline. Three layers: (1) a modern CSS **reset/normalize** at the top; (2) a **design-token layer expressed as CSS custom properties** (color palette incl. `--color-free` / `--color-busy` / owner-accent, spacing scale, type scale, radii); (3) **component classes** (table + row states, badges, form fields, buttons, nav). Rejected: a utility framework (Tailwind) because it adds a Node build to a deliberately uv-only, build-step-free stack; a classless framework (Pico/Water) because it yields a templated look and gives nothing for the row/column-legibility and state-badge work that is the actual ask. See the styling-approach decision discussion (2026-06-28) and the `frontend-design` skill.
- **Forward-compat (timeline view):** A timeline / calendar reservations view is a planned **future** feature (its own slice + `/10x-plan`; likely a JS calendar library and new data shaping — explicitly **not** part of S-07). S-07 must leave a clean seam for it: define the design tokens as CSS custom properties from day one, and choose the **free / busy / owner color semantics so they read well as a filled time-block, not only as a badge** — those same tokens and state colors are what a future timeline (hand-built CSS-grid or a themed calendar lib) will inherit for visual consistency.
- **Blockers:** —
- **Unknowns:**
  - Exact palette, type scale, and component visual language — Owner: user / research (the `frontend-design` skill drives the aesthetic direction). Block: no.
  - Does any page need a layout change (e.g. the env-list table → cards on narrow viewports), or is this purely a styling pass over existing markup? — Owner: `/10x-plan`. Block: no.
  - Light-only, or also a dark-mode token set (cheap to leave room for given CSS-custom-property tokens)? — Owner: user. Block: no.
- **Risk:** Low blast radius (CSS + template class attributes, no behavior change), but two traps: (a) scope creep into re-architecting templates or sneaking in the timeline view — keep it a styling pass with a token seam; (b) inconsistency from styling page-by-page without the token layer first — land the reset + tokens before the per-page component classes so everything shares one source of truth.
- **Source:** Raised 2026-06-28 — end-user functionality is complete (S-01–S-06 done) but pages render as raw, uncolored Django output with no clear table structure. First user-experience-quality slice; sequenced after the functional slices it restyles.
- **Status:** done

## Quality / Enablers

Cross-cutting engineering-quality work that is not a user-visible slice. Items here harden the codebase against the agent-friendliness quality bar set in `context/foundation/tech-stack.md` rather than delivering a new user outcome.

### Q-01: Type-hint retrofit + mypy type-check gate

- **Outcome:** (enabler) Public functions/methods across `accounts/`, `catalog/`, `reservations/`, and `envbooker/` carry type annotations, and `mypy` (with the `django-stubs` plugin) runs clean under an agreed baseline strictness, wired as a gate so future untyped drift is caught. Closes the gap between the stack commitment ("explicit typing ... mitigated downstream with type hints and model-level schemas", `tech-stack.md` §Why this stack) and the codebase, where 0 of ~125 functions are currently annotated.
- **Change ID:** typing-and-type-check-gate
- **PRD refs:** — (no direct FR; traces to the `tech-stack.md` typing commitment and the stack's agent-friendliness quality bar)
- **Prerequisites:** F-01, S-01, S-02 (annotate code that already exists; sequence after the north star so the gate ratchets over a shipped baseline rather than churning against in-flight slices)
- **Parallel with:** S-03, S-04, S-05, S-06, SPIKE-01 — but those slices touch the same `views.py` / `services.py` / `forms.py` files, so once Q-01 lands they inherit the gate and must pass it; coordinate to avoid merge churn (best landed when write-path slices are quiescent or rebased onto Q-01).
- **Blockers:** —
- **Unknowns:**
  - What mypy baseline to adopt — full `--strict`, or a pragmatic first-party baseline (`disallow_untyped_defs` on the three apps + `envbooker/`, lenient on `migrations/` and tests)? — Owner: user. Block: no.
  - How is the gate enforced given no CI exists yet (`CLAUDE.md` notes CI is unwired) — a minimal GitHub Actions job, a `pre-commit` hook, or a documented `uv run mypy` command for now? — Owner: TBD (resolves in `/10x-plan`). Block: no.
  - Does `django-stubs` need extra plugin config for the custom `accounts.User` (`AbstractUser`, `username=None`) and the Postgres `DateTimeRangeField` / `ExclusionConstraint` on `Reservation`? — Owner: TBD (resolves in `/10x-plan`). Block: no.
- **Risk:** Horizontal change touching nearly every `.py` file — blast radius is wide but shallow (annotations + config, no behavior change). The real risk is scope creep into a strict-everywhere crusade that stalls; cap it at first-party app code with a green baseline and defer test/migration coverage. The ruff/lint CI tripwire (`CLAUDE.md`) is deliberately excluded to keep this item typing-only.
- **Source:** Drift discovered 2026-06-07 — typing committed in `tech-stack.md` but never implemented (0/125 functions annotated, no checker installed).
- **Status:** done

### Q-02: Lint + format tooling with pre-commit & agent hooks

- **Outcome:** (enabler) A linter/formatter is selected (via research) and wired so style/lint violations are caught automatically at two local layers: a per-edit Claude Code agent hook (`PostToolUse` on `Write|Edit`) that surfaces fixes mid-session, and the existing lefthook `pre-commit` gate over staged files. Closes the `CLAUDE.md` lint tripwire and fulfils the lint half of the `test-plan.md` §5 `lint + typecheck` gate, which Q-01 left typing-only.
- **Change ID:** lint-and-format-gate
- **PRD refs:** — (no direct FR; traces to the `CLAUDE.md` lint tripwire, `test-plan.md` §5 quality gate, and the M3 L3 hooks lesson)
- **Prerequisites:** Q-01 (extends the lefthook `pre-commit` harness and `.claude/` hook conventions Q-01 established; lints over a green typed baseline)
- **Parallel with:** S-05, S-06, SPIKE-01 — those slices touch the same `views.py` / `services.py` / `forms.py`, so once Q-02 lands they inherit the lint gate and must pass it; best landed when write-path slices are quiescent or rebased onto Q-02.
- **Blockers:** —
- **Scope (M3 L3):** Deliver BOTH local layers — (1) a per-edit agent hook (the only layer that feeds the agent mid-work) and (2) the pre-commit git hook on staged files. CI wiring is out of scope (Phase 5 owns the CI harness, which later consumes this gate).
- **Unknowns (resolve in research / `/10x-plan`):**
  - Which tool? `ruff` (lint + format in one; the `CLAUDE.md`-suggested default, fastest, ideal for a per-edit hook) vs `flake8`+`black`+`isort` vs others — Owner: research. Block: no.
  - Baseline strictness — which rule sets on first-party `accounts/`/`catalog/`/`reservations/`/`envbooker/`, and lenient handling for `migrations/` + tests (as Q-01 did for mypy) — Owner: research / `/10x-plan`. Block: no.
  - Agent-hook shape — lint just the edited file (`jq -r .tool_input.file_path` from stdin) vs whole tree; auto-`--fix` vs report-only; exit-code/`additionalContext` feedback — Owner: `/10x-plan`. Block: no.
  - Should format/`--fix` run inside pre-commit or only report? — Owner: `/10x-plan`. Block: no.
  - How to handle existing non-compliant files — one-time repo-wide cleanup commit (end fully green), grandfather/changed-files-only enforcement (no bulk diff), or phased per-app adoption? Decide formatting (mechanical, safe to bulk-apply) and lint rules (may need real fixes) separately; mind churn against in-flight S-05/S-06/SPIKE-01. — Owner: research / `/10x-plan`. Block: no.
- **Risk:** Low blast radius (config + a possibly large one-time auto-format diff, no behaviour change). Real risks: (a) a noisy first-format diff churning against in-flight write-path slices — sequence when quiescent; (b) a slow per-edit hook blocking the agent loop — M3 L3's own rule keeps per-edit hooks to a few seconds, favouring a fast tool (ruff) and scoped single-file runs; (c) scope creep into CI wiring (belongs to Phase 5).
- **Source:** Lint deferred out of Q-01 (`typing-and-type-check-gate`), which was scoped typing-only (roadmap Q-01 risk note; `test-plan.md` §5). Raised 2026-06-13 to give lint a dedicated home and satisfy the M3 L3 hooks lesson.
- **Status:** done

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
| S-07       | ui-visual-polish                | EnvBooker: Visual / UX polish across all pages (hand-rolled design-token CSS)                          | yes                   | All prereqs (S-02–S-06) done. Run `/10x-new ui-visual-polish` then `/10x-plan`. Timeline view stays a separate future slice |
| SPIKE-01   | timezone-calendar-edge-cases    | EnvBooker: Spike — DST/leap-year/calendar edge-case hardening for reservation time windows             | no                    | Deferred from S-02 impl review (F5); ready after S-02 |
| Q-01       | typing-and-type-check-gate      | EnvBooker: Retrofit type hints + mypy (django-stubs) type-check gate                                    | no                    | Promotes to ready once S-02 is done (baseline to annotate)        |
| Q-02       | lint-and-format-gate            | EnvBooker: Lint + format tooling (tool TBD) with pre-commit + per-edit agent hook                       | no                    | Promotes to ready once Q-01 is done; start with tool-selection research |

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
- **S-03: filter the env list by availability, purpose / use-case tag, and project — closing the <30s primary success criterion** — Archived 2026-06-07 → `context/archive/2026-06-04-filter-env-list/`. Lesson: —.
- **S-04: modify or cancel a reservation they own** — Archived 2026-06-07 → `context/archive/2026-06-04-edit-own-reservation/`. Lesson: —.
- **Q-01: (enabler) Public functions/methods across `accounts/`, `catalog/`, `reservations/`, and `envbooker/` carry type annotations, and `mypy` (with the `django-stubs` plugin) runs clean under an agreed baseline strictness, wired as a gate so future untyped drift is caught. Closes the gap between the stack commitment ("explicit typing ... mitigated downstream with type hints and model-level schemas", `tech-stack.md` §Why this stack) and the codebase, where 0 of ~125 functions are currently annotated.** — Archived 2026-06-13 → `context/archive/2026-06-10-typing-and-type-check-gate/`. Lesson: —.
- **Q-02: (enabler) A linter/formatter is selected (via research) and wired so style/lint violations are caught automatically at two local layers: a per-edit Claude Code agent hook (`PostToolUse` on `Write|Edit`) that surfaces fixes mid-session, and the existing lefthook `pre-commit` gate over staged files. Closes the `CLAUDE.md` lint tripwire and fulfils the lint half of the `test-plan.md` §5 `lint + typecheck` gate, which Q-01 left typing-only.** — Archived 2026-06-14 → `context/archive/2026-06-13-lint-and-format-gate/`. Lesson: —.
- **S-05: An admin can create new env definitions, modify existing definitions (with a pre-save warning if active or upcoming reservations exist, and a "definition changed since you reserved" badge on those reservations post-save), and delete env definitions only when no active or upcoming reservations remain. Replaces the Django `/admin/` fallback that F-01 leaves in place.** — Archived 2026-06-28 → `context/archive/2026-06-24-admin-env-catalog/`. Lesson: —.
- **S-06: An admin can modify or cancel any reservation, including reservations owned by other users. Documented as the escape hatch for stale or abandoned reservations.** — Archived 2026-06-28 → `context/archive/2026-06-25-admin-reservation-override/`. Lesson: —.
- **S-07: Every existing page reads as an intentionally designed product rather than raw Django output: a coherent color palette, clear visual structure for the env-list and reservations tables (legible row/column separation, hover/selected row states), colored availability **state badges** (free / busy) and reservation-owner cues, consistent typography and spacing, and styled forms/buttons across the booking, my-reservations, auth, and admin (manage / form / confirm-delete) surfaces. No new end-user capability — this restyles what S-02–S-06 already deliver so the <30-second find-and-reserve flow is fast to *scan*, not just functionally complete.** — Archived 2026-06-28 → `context/archive/2026-06-28-ui-visual-polish/`. Lesson: —.
