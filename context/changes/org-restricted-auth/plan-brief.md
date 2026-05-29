# S-01: Org-restricted authentication — Plan Brief

> Full plan: `context/changes/org-restricted-auth/plan.md`

## What & Why

EnvBooker has no user-facing auth. This slice (roadmap S-01) adds self-serve sign-up restricted to the organization's email domain, sign-in with email + password, and sign-out — with unauthenticated requests to gated routes redirected to sign-in. It's the prerequisite for reservation ownership (S-02) and the admin catalog (S-05); without it there's no concept of "who owns this reservation."

## Starting Point

`accounts.User` is a bare `AbstractUser` (username-based login, optional non-unique email) with `AUTH_USER_MODEL` wired but no auth views, forms, URLs, templates, `LOGIN_URL`, or domain restriction. No `templates/` directory exists. The `0001_initial` migration is already applied locally and on Railway. Catalog/reservation models (F-01) FK to the user, so its PK must stay stable.

## Desired End State

A visitor hits `/`, is redirected to sign-in, signs up with an org-domain email + first/last name + password, lands on a placeholder home that greets them by full name, and can sign out. Non-org-domain signups are rejected (when domains are configured); admins manage the allowed-domain list in `/admin/`.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Login identity | Email-as-identity (`USERNAME_FIELD="email"`, drop `username`, custom manager) | Matches PRD "sign in with email + password"; email is the single credential | Plan |
| Display name | Reuse `first_name`/`last_name`, required on signup, shown via `get_full_name()` | FR-010 needs a friendly owner label, not bare email; no new field required | Plan |
| Allowed domains | Admin-managed `AllowedEmailDomain` model (empty = allow any) | Admins change domains at runtime via `/admin/` with no redeploy; consistent with F-01/S-05 admin-panel pattern | Plan |
| Gated route + UI | Throwaway `login_required` home + minimal unstyled `base.html` | Makes the unauth→sign-in redirect testable now; styling belongs to S-02 | Plan |
| Auth views | Built-in `LoginView`/`LogoutView` + custom signup view/form | Standard Django; minimal custom surface | Plan |

## Scope

**In scope:** email-identity user model + custom manager, email-based admin, `AllowedEmailDomain` model + admin, org-restricted signup form/view/template, login/logout, `login_required` placeholder home, settings + base/login/home templates, unit + integration tests.

**Out of scope:** env list / reservations / filtering (S-02/S-03), password reset (PRD non-goal), CSS framework / visual design, email verification, first-class domain admin UI.

## Architecture / Approach

Django built-in auth + a thin custom layer. Phase 1 rebuilds the user model around email (the riskiest change — a new migration on an already-applied table). Phase 2 adds the DB-backed allowed-domain gate and the signup path. Phase 3 wires login/logout, the gated home route, settings, and the project-level template tree (`templates/base.html`, `registration/login.html`, `registration/signup.html`, `home.html`).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Email-as-identity | Email login, custom manager, email-based admin, migration 0002 | Migration on applied table; superuser must be recreated (blank email can't log in) |
| 2. Allowed-domain + signup | `AllowedEmailDomain` model, org-restricted `SignUpForm`/view/template | Empty-table-allows-any could silently open prod signup if domain unset |
| 3. Login/logout/home | Built-in login/logout, gated home, settings, base templates, e2e tests | Django ≥5 GET-logout disabled — sign-out must be POST |

**Prerequisites:** Postgres running locally (`docker compose up -d`) and the three env vars from `.env.example`; F-01 already merged.
**Estimated effort:** ~1–2 sessions across 3 phases.

## Open Risks & Assumptions

- Phase 1's migration assumes ≤1 superuser row with no duplicate emails; recreating the superuser locally and on Railway is a manual post-migrate step.
- Empty `AllowedEmailDomain` table allows any domain — a deploy checklist must seed the prod domain (the chosen fail-open default).
- Only superuser rows exist today; S-01 introduces the first real users, so the model rebuild carries no real-user data migration.

## Success Criteria (Summary)

- A new user signs up with an org-domain email, lands on home greeted by name, and can sign out.
- A non-org-domain signup is rejected with a clear message when domains are configured.
- Unauthenticated access to `/` redirects to sign-in; full `manage.py test` suite is green.
