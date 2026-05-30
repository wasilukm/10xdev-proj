# Env + Reservation Data Model (F-01) — Plan Brief

> Full plan: `context/changes/env-and-reservation-data-model/plan.md`

## What & Why

F-01 is the correctness foundation for EnvBooker. It creates the `Environment` and `Reservation` tables and enforces the product's central guardrail — **no two reservations on the same env may overlap** (PRD FR-015) — at the database layer via a PostgreSQL exclusion constraint. Getting this right at the DB is the load-bearing call for the whole product; every booking slice depends on it.

## Starting Point

A bare Django 6.0.5 skeleton (Python 3.14, uv): only the `envbooker/` config package and `/admin/` are wired, with **zero domain apps** and no custom user model. Postgres tooling (`psycopg`, `dj-database-url`, `django.contrib.postgres`) is already installed but unused; local dev currently runs SQLite.

## Desired End State

Three new apps (`accounts`, `catalog`, `reservations`) migrated on local + prod Postgres, all registered in Django `/admin/`. An admin can seed environments and reservations; the database itself rejects any overlapping reservation on the same env, and a test suite proves it.

## Key Decisions Made

| Decision | Choice | Why | Source |
| --- | --- | --- | --- |
| Local dev DB | Postgres via Docker Compose (retire SQLite locally) | Exclusion constraints are Postgres-only; full dev/test/prod parity so the guarantee is actually exercised | Plan |
| No-overlap enforcement | DB exclusion constraint **only** (single source) | The constraint is the true race-closer; an app-layer pre-check is redundant for correctness and still needs the `IntegrityError` catch anyway | Plan |
| Conflict messaging | Deferred to S-02 | Friendly "conflicts with X, window Y" belongs to the slice that builds the create UI | Plan |
| Custom user model | Empty `AbstractUser` subclass now (`accounts`) | F-01 is the first migration; retrofitting a custom user model later is the documented painful migration; de-risks S-01's email login | Plan |
| Env attributes | Indexed CharFields; `owner` FK to user | Small fixed catalog, low complexity; cheap to evolve to choices/lookups later; owner must be a real account | Plan |
| Reservation time | Single `DateTimeRangeField` (`during`) | Native fit for the gist constraint; half-open `[start,end)` makes back-to-back bookings non-conflicting | Plan |
| Reservation lifecycle | Live rows only (no status) | Smallest correct model; cancel/soft-delete is S-04's scope | Plan |
| App layout | `accounts` + `catalog` + `reservations` | Clear bounded contexts mapping to later slices (S-05 catalog vs S-02 booking) | Plan |
| Seed data | Admin `/admin/` only, no command/fixtures | Keep F-01 minimal — exactly the roadmap's committed scope | Plan |

## Scope

**In scope:** custom user model; Environment + Reservation models; the DB exclusion constraint (`btree_gist` + `EXCLUDE USING gist`); admin registration for all three; local Postgres via Docker; FR-015 proof tests.

**Out of scope:** any views/URLs/templates; filtering (S-03); edit/cancel (S-04); admin override (S-06); first-class admin catalog UI (S-05); auth views (S-01); app-layer overlap check + conflict messaging (S-02); reservation status/soft-delete; seed data; CI/lint.

## Architecture / Approach

Bottom-up and dependency-ordered. Local Postgres parity first (everything downstream needs it), then the custom user model (which must exist before the first migration), then `Environment`, then `Reservation` with its exclusion constraint. The constraint — `EXCLUDE USING gist (environment_id WITH =, during WITH &&)`, backed by the `btree_gist` extension — is the single authoritative enforcer of no-overlap.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Local Postgres | Docker Compose `postgres:17` + `DATABASE_URL` wiring | Onboarding friction; devs must run Postgres before `migrate` |
| 2. Custom user model | `accounts.User` + `AUTH_USER_MODEL` (first migration) | Must precede every other migration; ordering matters |
| 3. Environment catalog | `catalog.Environment` + admin | Low — straightforward model |
| 4. Reservation + constraint | `reservations.Reservation`, `btree_gist`, exclusion constraint, FR-015 tests | `BtreeGistExtension` must run before `AddConstraint`; extension privilege on Railway |

**Prerequisites:** Docker available locally; ability to run `CREATE EXTENSION btree_gist` (trusted extension on PG13+, works on Railway's managed role).
**Estimated effort:** ~1–2 sessions across 4 small phases.

## Open Risks & Assumptions

- `BtreeGistExtension` requires `CREATE EXTENSION` privilege; assumed available locally (Docker superuser) and on Railway (trusted extension). Verify the first Railway deploy log.
- Local dev now depends on Docker/Postgres — a deliberate trade against the project's low-complexity bias, accepted to guarantee the core invariant is exercised everywhere.
- The abandoned `db.sqlite3` is no longer the dev DB.

## Success Criteria (Summary)

- `uv run python manage.py migrate` applies cleanly on Postgres (extension + constraint).
- `uv run python manage.py test` passes, including: overlapping insert → `IntegrityError`; back-to-back allowed; cross-env allowed.
- In `/admin/`, an admin can seed envs/reservations and an overlapping reservation is rejected.
