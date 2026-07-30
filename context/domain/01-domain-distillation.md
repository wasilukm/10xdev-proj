---
title: "EnvBooker — Domain Distillation"
created: 2026-07-30
type: domain-distillation
---

# EnvBooker — Domain Distillation

## Step 0 — Project context

Source documents read: `context/foundation/prd.md`, `context/foundation/roadmap.md`,
`context/foundation/lessons.md`. No extended narrative/decision-history doc beyond
these was found (no `shape-notes.md` decision log was read in depth beyond what PRD
cites — treat as available but not re-walked here).

Stack & structure (from `CLAUDE.md` + repo layout, confirmed by reading files
directly): Django 6.0.5 / Python 3.14, three domain apps —
`accounts`, `catalog`, `reservations` — each following
`models.py` → `services.py` (business rules, absent in `accounts`) → `views.py`
(thin) → `forms.py`. Business logic lives almost entirely in `catalog/services.py`
and `reservations/services.py`; views only orchestrate. This is a greenfield app
(`context_type: greenfield`, `prd.md:6`) — there is no legacy/pre-existing system
to diff against, so this distillation is PRD-vs-code, not old-system-vs-new-system.

## Step 1 — Ubiquitous Language

| Term | Definition | Source (doc) | Source (code) |
|---|---|---|---|
| **Environment** | A bookable, shared test environment with descriptive metadata (version, purpose, project, use-case tag) and an owner. | "test environments are not interchangeable... carry metadata" (`prd.md:24`) | `catalog/models.py:7-24` (`Environment`) |
| **Reservation** | A claim by one user on one environment for a specific time window; the unit that resolves contention. | "classifying every (environment, time-window) pair as available or taken-by-named-user" (`prd.md:112`) | `reservations/models.py:10-45` (`Reservation`) |
| **during** | The reserved time window itself, a half-open range `[start, end)`. | "a specific time window" (FR-011, `prd.md:94`) | `reservations/models.py:21` (`DateTimeRangeField`); `reservations/forms.py:75` (`Range(start, end, "[)")`) |
| **owner** (of a Reservation) | The user who created a reservation; only they (or an admin) may modify/cancel it. | "Reservation ownership is respected" guardrail (`prd.md:43`) | `reservations/models.py:11-15`; enforced in `reservations/views.py:46-55` (`_reservation_for_request`) |
| **owner** (of an Environment) | The user recorded as responsible for an environment definition — a distinct sense of "owner" from the Reservation one. | FR-005 "owner" attribute (`prd.md:76`) | `catalog/models.py:13-17` |
| **Availability (free / busy)** | Whether an environment has a reservation covering the current instant. | FR-009 "availability (free now / busy now)" (`prd.md:87`) | `catalog/services.py:80-87` (`filter_environments`, `_busy` annotation); `catalog/services.py:51-58` (`is_busy` in `build_row_context`) |
| **Conflict** | The existing reservation that blocks a proposed overlapping one; must be named (owner + window) on rejection. | "named conflict" (`prd.md:114`, FR-011 AC `prd.md:58`) | `reservations/services.py:106-128` (`describe_overlap_conflict`) |
| **Admin** | Role that is a superset of regular user: manages the env catalog and can override any reservation. | "Access Control" section (`prd.md:118-125`) | `reservations/services.py:46-51` (`is_reservation_admin`, defined as `is_staff or is_superuser`); `catalog/permissions.py:10-26` (`staff_required`) |
| **Regular user** | Any account inside the allowed org domain; can browse/filter/reserve and manage only their own reservations. | `prd.md:122` | Implicit — everyone who is not `is_reservation_admin`; `reservations/views.py:53-55` |
| **AllowedEmailDomain** | Org-domain allowlist gating self-serve sign-up; if any rows exist, only matching domains may sign up. | "restricted to the organization's email domain" (FR-001, `prd.md:65`) | `accounts/models.py:52-60`; enforced in `accounts/forms.py:17-27` (`SignUpForm.clean_email`) |
| **"Definition changed since you reserved"** | A per-reservation drift signal shown when the env definition was edited after the reservation was created. | FR-006 (`prd.md:78`) | `reservations/views.py:89-91` (`definition_changed`); template `templates/reservations/_reservation_item.html:11` |
| **Edit warning (affected reservations)** | Pre-save admin-facing warning listing active/upcoming reservations an env edit would affect. | FR-006 "warns the admin pre-save" (`prd.md:78`) | `catalog/views.py:114-150` (`environment_edit`, two-step confirm flow) |
| **Delete guard** | Env deletion is blocked while active/upcoming reservations exist. | FR-007 (`prd.md:80`) | `catalog/services.py:123-149` (`delete_environment`) |
| **MAX_DURATION** | A 4-hour cap, used only to bound the `until_next` duration choice — NOT a hard ceiling on reservation length in general. | "does not enforce a hard upper bound... recommend 4h" (FR-011, `prd.md:94-95`) | `reservations/services.py:21` (`MAX_DURATION = timedelta(hours=4)`); used in `compute_end` (`reservations/services.py:96-102`) — note `custom` duration has no `max_value` in `reservations/forms.py:36-41`, confirming no hard cap |
| **project / use_case_tag / purpose / version** | Structured attributes on Environment used for discovery. | FR-009 (`prd.md:87-88`) | `catalog/models.py:9-12` |
| **reservation_no_overlap** | The named DB constraint that is the ultimate enforcement point of "no double-booking." | Guardrail (`prd.md:42`) | `reservations/models.py:26-33` (`ExclusionConstraint`); test evidence `reservations/tests/test_models.py:41-70` |

## Step 2 — Subdomain classification

| Concept / area | Category | Rationale |
|---|---|---|
| Reservation lifecycle + no-overlap enforcement | **Core** | This *is* the product's stated reason to exist: "resolves contention for a finite, shared pool" (`prd.md:112`). The success criterion (`prd.md:34`) and all three guardrails (`prd.md:42-44`) are about this. |
| Environment catalog (metadata, discovery, filtering) | **Core** | The Vision section explicitly argues envs are "not interchangeable like meeting rooms" (`prd.md:24`) — the metadata-driven filter is what makes the 30-second success criterion achievable; this is the differentiator, not incidental CRUD. |
| Admin override of reservations / env catalog management | **Supporting** | Necessary escape hatch (`prd.md:123`) but not itself the value proposition — it exists to keep the Core mechanism healthy (stale reservations, catalog upkeep), not to create new value. |
| Authentication & org-domain restriction | **Generic** | Email+password auth and domain-gated sign-up (FR-001/002/004) are undifferentiated — any multi-tenant internal tool needs this; PRD itself frames it as a guardrail-enabler ("without sign-in there is no concept of reservation ownership," `prd.md:68`) rather than the product's purpose. |
| Non-goals explicitly fenced off (analytics, notifications, CI integration, mobile) | **Out of scope** | `prd.md:127-133` — listed to keep Core small; no code exists for these, correctly. |

## Step 3 — Aggregate candidates and invariants

### Candidate 1: `Reservation` (environment, during)

- **Invariant**: No two reservations for the same environment may have overlapping `during` ranges.
- **Source**: Guardrail "No double-booking... at any layer" (`prd.md:42`); FR-015 (`prd.md:102`).
- **Enforcement status**: **Enforced**, at two layers simultaneously:
  1. DB: `ExclusionConstraint` `reservation_no_overlap` (`reservations/models.py:26-33`), using `btree_gist` — this is the layer that actually holds under concurrency (per FR-015's own resolution note, `prd.md:103`).
  2. Application: `IntegrityError` is caught and translated into a named conflict message (`reservations/views.py:163-173`, `reservations/services.py:106-128`).
  - Verified by tests: `reservations/tests/test_models.py:41-70` (overlap rejected, back-to-back allowed, cross-env allowed, contained-window rejected, empty/unbounded range rejected).

### Candidate 2: `Reservation.owner` (ownership boundary)

- **Invariant**: A reservation may only be modified/cancelled by its owner, except an admin may act on any reservation.
- **Source**: "Reservation ownership is respected" guardrail (`prd.md:43`); FR-012/013/014 (`prd.md:96-101`).
- **Enforcement status**: **Enforced** — `_reservation_for_request` (`reservations/views.py:46-55`) scopes the lookup to `owner=request.user` unless `is_reservation_admin`, returning 404 otherwise (not 403 — a deliberate non-disclosure choice, undocumented in PRD but consistent with it).

### Candidate 3: `Environment` (catalog identity + deletion guard)

- **Invariant**: An environment cannot be deleted while it has active or upcoming reservations.
- **Source**: FR-007 (`prd.md:80`).
- **Enforcement status**: **Enforced**, with an explicit race-safety note in the code comment: the check and delete run inside one `transaction.atomic()` block, and a race is caught via `ProtectedError` rather than row locking (`catalog/services.py:123-149`, especially the docstring at `130-133`).

### Candidate 4: `Environment` (edit-drift visibility)

- **Invariant**: Editing an env definition must not silently invalidate reservations made against the old definition — it must warn pre-save and mark affected reservations post-save.
- **Source**: FR-006 (`prd.md:78`).
- **Enforcement status**: **Enforced but coarse-grained** — `definition_changed` (`reservations/views.py:89-91`) compares `environment.updated_at > reservation.created_at`, i.e. *any* field edit trips the badge, not just a semantically meaningful one (e.g. editing `owner`'s display metadata vs. changing `version`). This is a legitimate simplification, not a bug, but it's a coarser invariant than "the specific attribute the reservation depended on changed."

## Step 4 — Model vs. Code drift

| Document says | Code does | Evidence | Assessment |
|---|---|---|---|
| FR-009: filter env list by "availability... **purpose** / use-case tag, and project" (`prd.md:87`) | `purpose` is a real, indexed model field (`catalog/models.py:10`, `db_index=True`) but is **never filterable** — `filter_environments` only accepts `availability`, `project`, `use_case_tag` (`catalog/services.py:68-87`), and `filter_options()` only surfaces `projects` and `use_case_tags` (`catalog/services.py:90-101`). Templates only *display* `env.purpose` (`templates/catalog/_environment_row.html:11`, `templates/catalog/environment_manage.html:29`). | `catalog/services.py:68-101`; `catalog/views.py:32-52` (only reads `availability`, `project`, `use_case_tag` from `request.GET`) | **Real drift.** The PRD names `purpose` as one of the structured filter dimensions users need to hit the 30-second success criterion; the code silently dropped it from the filter surface while keeping the field. Worth a decision: either the PRD's filter list should be corrected to drop `purpose`, or the filter UI is missing a dimension it was meant to have. |
| PRD "Access Control": two roles, "Regular user" / "Admin" (`prd.md:118-125`) | Code has three Django-native flags (`is_staff`, `is_superuser`, `is_active`) and collapses them into one boolean check: `is_staff or is_superuser` (`reservations/services.py:46-51`). `accounts/admin.py:11` exposes both flags separately in the admin UI. | `reservations/services.py:46-51`; `accounts/admin.py:8-30` | **Minor terminology drift**, not a defect: the PRD's single "Admin" concept maps to *either* Django flag, so an operator could grant admin powers via `is_staff` alone without `is_superuser`, or vice versa — the PRD doesn't distinguish these, and nothing in the code doc-comments this deliberately-inclusive OR. Low risk (both are staff-console-gated), but worth naming explicitly if a future reader assumes "Admin" is a single flag. |
| PRD non-functional: "acknowledges any interaction within 200ms... visible progress on operations >2s" (`prd.md:107`) | No corresponding code artifact found (no loading-spinner/progress-indicator convention, no perf test). | — (absence) | **Declared but unverified.** Not necessarily wrong — HTMX's default swap is fast for this data volume — but there's no enforcement point in the code map's crosshairs; flagging as an open non-functional requirement with no owning mechanism. |
| FR-006: badge reads "definition changed **since you reserved**" implying a meaningful attribute change | Badge trips on *any* `updated_at` bump, including a no-op re-save or an edit to `owner` alone. | `reservations/views.py:89-91` | **Faithful but coarser than the prose implies** — see Aggregate Candidate 4 above. Not a contradiction, just a precision gap worth knowing about if the badge starts firing "too often" in practice. |

No drift found where the *code* enforces something the *docs* explicitly disclaim (i.e., no scope creep beyond PRD was found in the reservation/environment core).

## Step 5 — Refactor ranking

Ranked by (a) how core the underlying invariant is, and (b) how weakly today's code enforces the *documented* intent (not how weak the code is in isolation):

1. **#1 — FR-009 filter drift (`purpose` field un-filterable).** Highest priority: it's a **Core**-subdomain concept (env discovery, directly named in the 30-second success criterion) where the code silently diverges from an explicit, numbered functional requirement. This isn't a code-quality issue — it's a product-intent gap hiding in the codebase. Resolution is cheap (extend `filter_environments`/`filter_options`/the filter form) but needs a product decision first: is `purpose` supposed to be filterable, or should FR-009 be corrected?
2. **#2 — FR-006 badge granularity (Aggregate Candidate 4).** Core-adjacent (reservation trust signal), invariant is enforced but at a coarser grain than the PRD prose suggests. Lower risk than #1 because the current behavior is a safe over-trigger (false positives, never false negatives) rather than a silent gap.
3. **#3 — Admin role terminology (`is_staff or is_superuser`).** Supporting subdomain, enforcement exists and is safe by construction (OR of two gates, not a weaker check), so this is a documentation/naming clarification rather than a functional refactor.
4. **Not ranked — 200ms/2s non-functional requirement.** No enforcement point exists to refactor; this needs a monitoring/UX decision before it's a code-shaped problem at all.

**Refactor candidate #1 (filter drift) is the recommended next step** — it sits squarely in the Core subdomain, traces to a numbered FR, and is the only finding where a user-facing capability described in the PRD is absent from the running system.
