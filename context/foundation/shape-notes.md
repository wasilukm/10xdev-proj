---
project: "EnvBooker"
context_type: greenfield
created: 2026-05-18
updated: 2026-05-18
product_type: web-app
target_scale:
  users: medium
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 3
  hard_deadline: null
  after_hours_only: true
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  gray_areas_resolved:
    - topic: "persona scope"
      decision: "QA engineers and developers in one specific org (single-tenant internal tool)"
    - topic: "pain category"
      decision: "coordination overhead + conflict/collision + lack of visibility + slow access for new joiners"
    - topic: "insight"
      decision: "test envs need attribute metadata (version, owner, purpose) that a generic calendar/booking tool cannot capture"
    - topic: "auth"
      decision: "email + password; self-serve sign-up"
    - topic: "roles"
      decision: "admin (env CRUD + reserve) + regular user (reserve only); admin can override foreign reservations"
    - topic: "mvp flow"
      decision: "5 steps: sign in → filter envs → pick a free env → pick a time window → reservation confirmed"
    - topic: "timeline"
      decision: "3 weeks of after-hours work; default greenfield budget; no acknowledgment block needed"
    - topic: "filter dimensions"
      decision: "availability (free/busy), purpose/use-case tag, project"
    - topic: "FR-003 password reset"
      decision: "dropped from MVP; admin resets passwords manually in v1"
    - topic: "FR-001 sign-up scope"
      decision: "self-serve, restricted to the organization's email domain"
    - topic: "FR-006 env modification under active reservations"
      decision: "notify-only — warn admin pre-save, flag affected reservations with 'definition changed' badge post-save"
    - topic: "FR-007 env deletion under active reservations"
      decision: "blocked while active/upcoming reservations exist; admin must cancel or wait them out first"
    - topic: "FR-011 max reservation length"
      decision: "UI recommends a sensible max (e.g. 4h) but does not enforce a hard limit"
    - topic: "FR-015 race condition"
      decision: "FR stands as behavioral statement; concurrency control is downstream implementation detail"
  frs_drafted: 14
  quality_check_status: accepted
---

# EnvBooker — Shape Notes

## Vision & Problem Statement

An organization owns a small, fixed pool of shared test environments. The population of QA engineers and developers who need those environments is much larger than the pool itself. Without a shared system of record, access is coordinated informally — by asking colleagues in chat, checking spreadsheets, or simply trying an environment and discovering mid-use that someone else is already on it. The collision corrupts in-flight tests, blocks deploys, and is invisible to anyone outside the immediate conversation.

The insight that makes this PRD worth writing: test environments are not interchangeable like meeting rooms. Each environment carries metadata — its current version, its owner, its purpose, the dataset it carries — that a generic calendar or room-booking tool does not capture. A purpose-built reservation system can filter and surface envs by those attributes, which is the thing that turns "find an available env" from a multi-minute Slack-thread into a self-serve action a new joiner can complete in 30 seconds.

## User & Persona

**Primary persona — QA engineer / developer inside one organization.** Works on a team that depends on a shared pool of test environments to validate changes before they reach production. May be new to the team (and thus unfamiliar with which envs exist or which fit a given purpose), or experienced (and thus annoyed by the time cost of asking around). Reaches for this product the moment they need a test environment for a specific task and want to avoid colliding with someone else.

## Access Control

Two roles:

- **Regular user** — anyone with an account inside the org. Can browse and filter environments, create reservations on any environment for any free time window, and modify or cancel their own reservations. Cannot create, modify, or delete environment definitions, and cannot touch reservations they do not own.
- **Admin** — superset of the regular user. Can create, modify, and delete environment definitions, and can override (modify or cancel) any reservation, including reservations owned by other users. The admin role exists primarily as an escape hatch for stale / abandoned reservations and for maintaining the env catalog.

Authentication is email + password with self-serve sign-up. Forgot-password is via email link. Unauthenticated requests to any gated route are redirected to the sign-in screen.

## Success Criteria

### Primary

- A user who has never used the system before can sign in, filter the env list by a relevant criterion, identify a free environment, and create a reservation for a specific time window in **under 30 seconds** from landing on the dashboard. The reservation is visible on the env list immediately after confirmation.

### Secondary

- The env list shows an at-a-glance upcoming-reservation horizon (the next ~24 hours of reservations on each env), so users can plan ahead instead of only grabbing what's free right now.

### Guardrails

- **No double-booking.** Two reservations on the same environment cannot overlap in time, at any layer. Breaking this means the system has actively created the problem it was built to solve.
- **Reservation ownership is respected.** A user cannot modify or cancel a reservation owned by another user. Admin is the only exception, by design.
- **Reservation owner is always visible.** For every current and upcoming reservation on every env, the owner's identity is shown in the UI so that anyone considering a conflicting time window can contact the owner directly to ask whether the reservation is still needed.

## User Stories

### US-01: A new user finds and reserves a free environment

- **Given** a signed-in user who has never used the system before
- **When** they open the env list and filter by relevant attributes (e.g., "free now" + project = "billing")
- **And** they pick an environment that shows as free for the time window they need
- **And** they confirm a reservation for that window
- **Then** the reservation is created and visible on the env list, the env shows as reserved for that window with the user's identity, and the round-trip from landing on the dashboard to a confirmed reservation completes in under 30 seconds for a user encountering the product for the first time.

#### Acceptance Criteria
- Filter results update without a full page reload.
- The reservation-creation form rejects time windows that overlap existing reservations on the same env, with a message that names the conflicting reservation's owner and time window.
- After confirmation, the env's row on the list immediately reflects the new reservation (the user is not required to refresh).

## Functional Requirements

### Authentication & accounts

- FR-001: User can sign up with email + password, restricted to the organization's email domain. Priority: must-have
  > Socrates: Counter-argument considered: "self-serve sign-up risks non-org users creating accounts." Resolution: kept; restrict sign-up to the organization's email domain rather than going invite-only or hardcoding accounts.
- FR-002: User can sign in with email + password. Priority: must-have
  > Socrates: No counter-argument; without sign-in there is no concept of reservation ownership and the access-control guardrails fail.
- FR-004: User can sign out. Priority: must-have
  > Socrates: No counter-argument; standard expected UX, trivial to add.

(FR-003 — password reset — dropped from MVP during Socrates round. Admin resets passwords manually for v1.)

### Environment catalog (admin)

- FR-005: Admin can create a new environment definition (name + descriptive attributes such as version, owner, purpose). Priority: must-have
  > Socrates: Counter-argument considered: "admin-gating creates friction; anyone should be able to create envs." Resolution: kept admin-gated to prevent catalog pollution; the admin pool can be wide (e.g. any team lead can be admin) to keep friction low.
- FR-006: Admin can modify an existing environment definition. The system warns the admin pre-save when the env has active or upcoming reservations, and flags those reservations with a "definition changed since you reserved" badge post-save. Priority: must-have
  > Socrates: Counter-argument considered: "modifying an env mid-reservation is dangerous — active reservations should block edits." Resolution: do not block; notify-only. Admin sees warning before save; affected reservations carry a change badge afterward.
- FR-007: Admin can delete an environment definition, but only when no active or upcoming reservations exist for it. Priority: must-have
  > Socrates: Counter-argument considered: "hard-deleting an env with active reservations silently breaks them." Resolution: block delete while active/upcoming reservations exist; admin must cancel them or wait them out first.

### Environment discovery (all users)

- FR-008: User can browse the list of all environments. Priority: must-have
  > Socrates: No counter-argument; realistic env count (20–50) is comfortably small for a single-page list.
- FR-009: User can filter the environment list by structured attributes including availability (free now / busy now), purpose/use-case tag, and project. Priority: must-have
  > Socrates: Counter-argument considered: "multi-attribute filter UIs are expensive; v1 could ship with just availability + free-text search." Resolution: kept structured; filtering is foundational to the 30-second success criterion.
- FR-010: User can see, for each environment, who owns the current and upcoming reservations and the time windows they cover. Priority: must-have
  > Socrates: No counter-argument; this IS the Phase 3 visibility guardrail — owner visible to anyone considering a conflicting window.

### Reservations

- FR-011: User can create a reservation on an environment for a specific time window. The UI suggests a recommended maximum duration (e.g. 4h) but does not enforce a hard upper bound. Priority: must-have
  > Socrates: Counter-argument considered: "should the system enforce a maximum reservation length to prevent indefinite hoarding?" Resolution: do not enforce; recommend a sensible max (4h default suggestion) in the UI to nudge against hoarding while keeping the system flexible for legitimate longer holds.
- FR-012: User can modify their own reservation. Priority: must-have
  > Socrates: Counter-argument considered: "extending into someone else's slot is the main risk." Resolution: FR-015's overlap check handles this; FR-012 stands.
- FR-013: User can cancel their own reservation. Priority: must-have
  > Socrates: No counter-argument; owners need this to release envs they don't need.
- FR-014: Admin can modify or cancel any reservation, including reservations owned by other users. Priority: must-have
  > Socrates: No counter-argument; admin override is the documented escape hatch for stale or abandoned reservations.
- FR-015: System rejects any attempted reservation that would overlap an existing reservation on the same environment. Priority: must-have
  > Socrates: Counter-argument considered: "race conditions could allow two concurrent reservations to slip past a naive overlap check." Resolution: FR-015 stands as a behavioral statement; concurrency control is an implementation detail handled downstream during design / stack selection.

## Business Logic

EnvBooker resolves contention for a finite, shared pool of test environments by classifying every (environment, time-window) pair as either *available* or *taken-by-named-user*, and enforces that no two takes overlap while making every take visible to everyone else who might want the same window.

The rule consumes three user-facing inputs: the environment the user is interested in, the time window they want it for, and the global state of existing reservations on that environment. Its output is a binary decision — accept or reject the proposed reservation — accompanied, on rejection, by enough context (which existing reservation conflicts, who owns it, what window it covers) for the user to either pick a different window or contact the conflicting owner.

The user encounters the rule at two moments. First, *passively*, when browsing or filtering the env list: every environment is labelled with its current availability state and the identities of upcoming reservation owners. Second, *actively*, when attempting to create or modify a reservation: the system either confirms the reservation or rejects it with a named conflict.

## Non-Functional Requirements

- User-perceived response: the system acknowledges any interaction within 200ms and shows continuous, visible progress on any operation that takes longer than 2 seconds. This is binding because the 30-second find-and-reserve success criterion cannot hold otherwise.
- Browser support: the product remains fully usable on the latest two major versions of the four mainstream desktop browsers (Chrome, Firefox, Safari, Edge).

## Non-Goals

- **Usage statistics / analytics dashboards.** No reports on env utilization, popular slots, or per-user activity. Defers a meaningful data-visualization scope.
- **Notifications about reservations.** No email reminders, no push notifications, no in-app conflict warnings beyond what the booking UI itself displays at the moment of action. Users check the UI when they need to know.
- **Integration with test-runner / CI systems.** EnvBooker does not trigger CI jobs, deploy versions to envs, or sync state with Jenkins / GitHub Actions / etc. It is purely a booking-of-record.
- **Mobile apps.** Web-only for v1. Native iOS / Android apps are explicitly out of scope; a responsive web layout may be considered but is not a v1 commitment.

## Quality cross-check

Greenfield cross-check completed 2026-05-18. All five required elements present:

- Access Control: two roles (admin, regular user), email + password with org-domain restriction.
- Business Logic: one-sentence rule captured (validation + classification of (env, time-window) pairs).
- Project artifacts: shape-notes.md present with valid checkpoint.
- Timeline-cost ack: mvp_weeks = 3, within default greenfield budget; no acknowledgment block needed.
- Non-Goals: 4 entries from seed (statistics, notifications, test-runner integration, mobile apps).

No gaps; `quality_check_status: accepted`.

