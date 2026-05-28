# Env + Reservation Data Model (F-01) Implementation Plan

## Overview

Roadmap item **F-01** — the correctness foundation for the entire EnvBooker product. It creates the `Environment` and `Reservation` tables and pushes the **no-double-booking** rule (PRD FR-015) into the database via a PostgreSQL exclusion constraint as the **single source of enforcement**. It unlocks S-02 (browse-and-reserve, the north star) and S-05 (admin catalog), and resolves the FR-015 race-condition unknown at the DB layer. Friendly, user-facing conflict messaging (turning a DB `IntegrityError` into "conflicts with Alice, 12:00–14:00") is deferred to S-02, the slice that builds the create UI.

The codebase today is a bare Django 6.0.5 skeleton (Python 3.14, uv): only `envbooker/` config + `/admin/` wired, **zero domain apps**. F-01 ships the project's first domain apps and first migration.

## Current State Analysis

- **No domain apps exist** — `models.py`/`apps.py`/`migrations/` absent project-wide (`envbooker/urls.py:20-22` wires only `/admin/`). This is the first domain migration.
- **Postgres tooling already present**: `psycopg[binary]>=3.3.4` + `dj-database-url>=3.1.2` in `pyproject.toml:7-13`; `django.contrib.postgres` available. So `DateTimeRangeField`, `ExclusionConstraint`, and `BtreeGistExtension` are all importable.
- **DB config** (`envbooker/settings.py:92-97`): `dj_database_url.config(default="sqlite:///…", conn_max_age=600)` — reads `DATABASE_URL`, falls back to SQLite. Today local dev silently uses SQLite, where exclusion constraints **cannot exist**.
- **`USE_TZ = True`, `TIME_ZONE = "UTC"`** (`settings.py:124,128`) → reservations are tz-aware; the range column will be `tstzrange`.
- **INSTALLED_APPS** (`settings.py:49-56`) is stock contrib only; **no custom user model**. F-01 is the last cheap moment to introduce one (before the first migration).
- **No tests** anywhere; no lint tooling configured.

### Key Discoveries

- The DB-enforced guarantee is **Postgres-only**; SQLite has no range types, no `EXCLUDE`, no GiST. → local dev moves to Postgres (Docker) for full parity.
- A GiST exclusion combining scalar equality (`environment_id =`) with range overlap (`during &&`) **requires the `btree_gist` extension**, created via a migration operation *before* the constraint. `btree_gist` is a PG "trusted" extension (PG13+), so Railway's non-superuser DB role can create it.
- Half-open ranges `[start, end)` make **back-to-back bookings not overlap** — no special boundary handling needed.
- Custom user model **must** be set (`AUTH_USER_MODEL`) before the first `migrate`; retrofitting later is the documented painful schema+data migration.

## Desired End State

Four migrated apps on local + prod Postgres:
- `accounts.User` — empty `AbstractUser` subclass; `AUTH_USER_MODEL = "accounts.User"`.
- `catalog.Environment` — `name`, `version`, `purpose`, `project`, `use_case_tag` (CharFields; the filterable three indexed), `owner` FK → user.
- `reservations.Reservation` — `owner` FK → user, `environment` FK → `catalog.Environment` (PROTECT), `during` `DateTimeRangeField`, `created_at`; a DB `ExclusionConstraint` rejecting overlapping windows on the same env.
- All three models registered in Django `/admin/`. Test suite proves FR-015 at the DB layer (overlapping insert → `IntegrityError`).

**Verify**: `uv run python manage.py migrate` applies cleanly on Postgres; `uv run python manage.py test` passes including overlap-rejection tests; in `/admin/` an overlapping reservation is rejected and a back-to-back one is accepted.

## What We're NOT Doing

- No views, URLs, templates, or HTML (S-02 owns the booking UI).
- No filtering UI/logic (S-03), no edit/cancel flows (S-04), no admin override (S-06), no first-class admin catalog UI (S-05 — stock Django `/admin/` only).
- No auth views — sign-up/sign-in/sign-out is S-01. F-01 only ships the *empty* custom user model so S-01 isn't blocked.
- **No app-layer overlap pre-check or `create_reservation` service** — the DB exclusion constraint is the sole enforcer. Catching `IntegrityError` and rendering a friendly "conflicts with X, window Y" message belongs to S-02.
- No reservation `status`/soft-delete (live rows only). No seed command or fixtures. No CI/lint wiring.

## Implementation Approach

Bottom-up, dependency-ordered so each phase is independently migratable and verifiable: Postgres dev parity first → custom user model (first migration) → Environment → Reservation + the DB exclusion constraint and its proof tests. The exclusion constraint is the single, durable guarantee and the true race-closer (concurrent inserts serialize at the DB, not in app code). No application-layer pre-check is added — it would be redundant for correctness and still require catching `IntegrityError` anyway; that catch-and-explain step is S-02's concern.

## Critical Implementation Details

- **Migration ordering**: `AUTH_USER_MODEL` must be set and `accounts` migrated *before* any app FK-ing to the user model. In the `reservations` migration, `BtreeGistExtension()` must appear in `operations` *before* the `AddConstraint`.
- **Constraint definition** (the one non-obvious bit) — on `Reservation.Meta`:
  ```python
  from django.contrib.postgres.constraints import ExclusionConstraint
  from django.contrib.postgres.fields import RangeOperators
  constraints = [ExclusionConstraint(
      name="reservation_no_overlap",
      expressions=[("environment", RangeOperators.EQUAL),
                   ("during", RangeOperators.OVERLAPS)],
      index_type="GIST",
  )]
  ```
- **Half-open ranges**: build `during` as `[start, end)` (default bounds) so equal endpoints (one ends 13:00, next starts 13:00) do **not** conflict.
- **`on_delete=PROTECT`** on `Reservation.environment` lays the DB groundwork for FR-007 (block deleting an env with reservations); `PROTECT` on both `owner` FKs prevents orphaning.

---

## Phase 1: Local Postgres dev environment

### Overview
Move local dev/test from SQLite to Postgres so the gist constraint runs everywhere (full parity with Railway prod).

### Changes Required:

#### 1. Docker Compose service
**File**: `docker-compose.yml` (new)
**Intent**: Provide a one-command local Postgres matching Railway's managed Postgres major version.
**Contract**: A `postgres:17` service, named volume for persistence, host port `5432`, env `POSTGRES_DB=envbooker` / user / password. No app service needed (Django runs on host via uv).

#### 2. Settings — register contrib.postgres
**File**: `envbooker/settings.py`
**Intent**: Enable range form fields/operators and document that local `DATABASE_URL` must point at Postgres.
**Contract**: Add `"django.contrib.postgres"` to `INSTALLED_APPS`. Keep the `dj_database_url` config; local dev sets `DATABASE_URL=postgres://…@localhost:5432/envbooker`.

#### 3. Dev setup docs
**File**: `CLAUDE.md` (+ `.env.example` new)
**Intent**: Document the new local flow (bring up Postgres, set `DATABASE_URL`, alongside existing `DJANGO_SECRET_KEY`/`DJANGO_DEBUG`).
**Contract**: Update the "Local dev setup" section; `.env.example` lists the three env vars.

### Success Criteria:
#### Automated Verification:
- `docker compose up -d` brings the Postgres container to healthy.
- `uv run python manage.py migrate` connects to Postgres (no SQLite file created).
- `uv run python manage.py check` passes.
#### Manual Verification:
- `psql` (or container shell) confirms the `envbooker` database is reachable.
- Settings reads `DATABASE_URL` from the local env (confirm via `manage.py dbshell`).

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding.

---

## Phase 2: Custom user model (`accounts`)

### Overview
Introduce an empty custom user model now so S-01 can extend it later without the painful post-migration swap. This is the project's first migration.

### Changes Required:

#### 1. accounts app + model
**File**: `accounts/` (new app), `accounts/models.py`
**Intent**: Own the user table from day one.
**Contract**: `class User(AbstractUser): pass`. Behaviorally identical to stock user.

#### 2. Wire the model
**File**: `envbooker/settings.py`
**Intent**: Point Django at the custom model before any migration runs.
**Contract**: Add `"accounts"` to `INSTALLED_APPS`; set `AUTH_USER_MODEL = "accounts.User"`.

#### 3. Admin
**File**: `accounts/admin.py`
**Intent**: Manage users in `/admin/`.
**Contract**: Register `User` with Django's `UserAdmin`.

### Success Criteria:
#### Automated Verification:
- `uv run python manage.py makemigrations accounts` produces `accounts/0001_initial`.
- `uv run python manage.py migrate` applies cleanly on Postgres.
- `uv run python manage.py check` passes; `createsuperuser` succeeds (scripted/non-interactive).
#### Manual Verification:
- `/admin/` login works; Users section visible under the custom model.

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding.

---

## Phase 3: Environment catalog (`catalog`)

### Overview
The `Environment` model holding descriptive, admin-seeded attributes the env list (S-02) and filters (S-03) read.

### Changes Required:

#### 1. catalog app + Environment model
**File**: `catalog/` (new app), `catalog/models.py`
**Intent**: Define the env catalog row.
**Contract**: `Environment` with `name` (CharField, unique), `version`, `purpose`, `project`, `use_case_tag` (CharFields; `db_index=True` on `project`/`purpose`/`use_case_tag`), `owner` FK → `settings.AUTH_USER_MODEL` (`on_delete=PROTECT`). `__str__` returns name; sensible `Meta.ordering`.

#### 2. Settings + admin
**File**: `envbooker/settings.py`, `catalog/admin.py`
**Intent**: Install the app and make envs manageable.
**Contract**: Add `"catalog"` to `INSTALLED_APPS`. Admin `list_display` (name, version, project, owner), `list_filter` (project/purpose/use_case_tag), `search_fields` (name).

#### 3. Model test
**File**: `catalog/tests.py`
**Intent**: Basic creation/`__str__` sanity.
**Contract**: One test creating an Environment and asserting fields + str.

### Success Criteria:
#### Automated Verification:
- `makemigrations catalog` + `migrate` apply cleanly on Postgres.
- `uv run python manage.py test catalog` passes.
- `manage.py check` passes.
#### Manual Verification:
- `/admin/` creates an Environment; `list_filter` dropdowns work on project/purpose/tag.

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding.

---

## Phase 4: Reservation + no-overlap enforcement (`reservations`)

### Overview
The `Reservation` model, the DB exclusion constraint (the single, durable FR-015 guarantee), and the test suite that proves no double-booking. No app-layer pre-check — friendly conflict messaging is S-02's concern.

### Changes Required:

#### 1. reservations app + Reservation model
**File**: `reservations/` (new app), `reservations/models.py`
**Intent**: Define the booking row and the DB-level no-overlap invariant.
**Contract**: `Reservation` with `owner` FK → user (`PROTECT`), `environment` FK → `catalog.Environment` (`PROTECT`), `during` `DateTimeRangeField`, `created_at` (`auto_now_add`). `Meta.constraints` carries the `ExclusionConstraint` (see Critical Implementation Details). `during` built as half-open `[start, end)`.

#### 2. Migration with btree_gist
**File**: `reservations/migrations/0001_initial.py`
**Intent**: Create the extension before the constraint.
**Contract**: `operations` lists `BtreeGistExtension()` (from `django.contrib.postgres.operations`) **before** `CreateModel`/`AddConstraint`.

#### 3. Settings + admin
**File**: `envbooker/settings.py`, `reservations/admin.py`
**Intent**: Install app; manage reservations in `/admin/`.
**Contract**: Add `"reservations"` to `INSTALLED_APPS`. Admin `list_display` (environment, owner, during, created_at), autocomplete/raw-id for `environment` + `owner`.

#### 4. FR-015 test suite
**File**: `reservations/tests.py`
**Intent**: Prove the core invariant at the DB layer.
**Contract**: Tests for — (a) DB constraint rejects an overlapping insert (`IntegrityError`); (b) back-to-back `[…,13:00)` + `[13:00,…)` is allowed; (c) overlapping windows on *different* envs are allowed; (d) an identical/contained window is rejected.

### Success Criteria:
#### Automated Verification:
- `makemigrations reservations` + `migrate` apply cleanly (extension + constraint) on Postgres.
- `uv run python manage.py test` (full suite) passes, including all FR-015 cases.
- `manage.py check` passes.
#### Manual Verification:
- `/admin/` create a reservation; attempt an overlapping one on the same env → rejected; a back-to-back one → accepted; same window on a different env → accepted.

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation.

---

## Testing Strategy

### Unit / model tests
- Environment creation + `__str__` (Phase 3).
- Reservation: back-to-back allowed; cross-env non-conflict (Phase 4).

### Integration / DB-constraint tests
- Direct overlapping insert raises `IntegrityError` — the constraint is the sole, authoritative enforcer.
- Identical / fully-contained window on the same env is rejected.

### Manual testing steps
1. Bring up Postgres, migrate, `createsuperuser`.
2. In `/admin/`: create 2 users, 1 environment.
3. Create reservation A (09:00–13:00); create back-to-back B (13:00–17:00) → accepted.
4. Create overlapping C (12:00–14:00) → rejected (admin surfaces the `IntegrityError`).
5. Same overlapping window on a second environment → accepted.

## Performance Considerations

Trivial scale (20–50 envs, low QPS per PRD). The GiST index backing the constraint also accelerates overlap lookups. `conn_max_age=600` already set.

## Migration Notes

Greenfield — no data migration. The abandoned `db.sqlite3` is no longer the dev DB (may be deleted). On Railway, the start command already runs `migrate`; `BtreeGistExtension` will `CREATE EXTENSION btree_gist` (trusted extension, works on the managed role) on first deploy — verify the deploy log shows it succeed.

## References

- Roadmap F-01: `context/foundation/roadmap.md:63-75`
- PRD FR-015 + no-double-booking guardrail: `context/foundation/prd.md:42,102-103`
- DB config: `envbooker/settings.py:92-97`; deps: `pyproject.toml:7-13`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Local Postgres dev environment
#### Automated
- [ ] 1.1 `docker compose up -d` brings Postgres to healthy
- [ ] 1.2 `manage.py migrate` connects to Postgres (no SQLite file)
- [ ] 1.3 `manage.py check` passes
#### Manual
- [ ] 1.4 `psql` confirms `envbooker` DB reachable
- [ ] 1.5 Settings reads local `DATABASE_URL`

### Phase 2: Custom user model (accounts)
#### Automated
- [ ] 2.1 `makemigrations accounts` produces `0001_initial`
- [ ] 2.2 `migrate` applies cleanly on Postgres
- [ ] 2.3 `check` passes; `createsuperuser` succeeds
#### Manual
- [ ] 2.4 `/admin/` login + Users section visible

### Phase 3: Environment catalog (catalog)
#### Automated
- [ ] 3.1 `makemigrations catalog` + `migrate` apply cleanly
- [ ] 3.2 `test catalog` passes
- [ ] 3.3 `check` passes
#### Manual
- [ ] 3.4 `/admin/` create Environment; list_filter works

### Phase 4: Reservation + no-overlap (reservations)
#### Automated
- [ ] 4.1 `makemigrations reservations` + `migrate` apply (extension + constraint)
- [ ] 4.2 full `test` suite passes incl. all FR-015 cases
- [ ] 4.3 `check` passes
#### Manual
- [ ] 4.4 `/admin/` overlap rejected, back-to-back accepted, cross-env accepted
