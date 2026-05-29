# S-01: Org-restricted authentication (sign-up, sign-in, sign-out) Implementation Plan

## Overview

Add user-facing authentication to EnvBooker: self-serve sign-up restricted to the organization's email domain, sign-in with email + password, sign-out, and redirect of unauthenticated requests to sign-in. This is roadmap slice S-01, a prerequisite for the north-star booking flow (S-02) and the admin catalog (S-05).

## Current State Analysis

- `accounts.User` (`accounts/models.py:4`) is a bare `AbstractUser`: `username` unique+required, `email` `blank=True` and non-unique, no domain restriction. Registered in admin with stock `UserAdmin` (`accounts/admin.py`).
- **No auth views, forms, URLs, templates, `LOGIN_URL`, or org-domain restriction exist.** There is no `templates/` directory (frontend absent per roadmap baseline).
- `accounts/migrations/0001_initial.py` is **already applied locally and on Railway** — a user-model change needs a *new* migration, not an edit to 0001.
- `envbooker/urls.py` routes only `/admin/`. `settings.py` has no `LOGIN_URL`/redirect settings; `TEMPLATES[0]["DIRS"]` is empty with `APP_DIRS=True`.
- `catalog.Environment` and `reservations.Reservation` (F-01) FK to `settings.AUTH_USER_MODEL`, so the User PK must stay stable. FR-010 requires the owner's identity to be displayed, so the user model must carry a human-friendly display name.

## Desired End State

A visitor can open `/`, be redirected to sign-in, create an account with an org-domain email + first/last name + password, land on a placeholder home page that greets them by full name, and sign out. Sign-up with a non-allowed domain (when domains are configured) is rejected with a clear message. Admins manage allowed domains via `/admin/`. Verified by: `manage.py migrate` clean, full `manage.py test` green, and the manual flow below.

### Key Discoveries:

- User model is fresh — only superuser rows exist; S-01 introduces the first real users (`accounts/models.py:4`).
- `0001_initial` already applied on Railway → migration 0002 must be additive/altering, and recreating the superuser is a manual step (`accounts/migrations/0001_initial.py`).
- Stock `UserAdmin` references `username` and breaks once it's removed (`accounts/admin.py`).
- Django ≥5 disables logout via GET — sign-out must be a POST form.

## What We're NOT Doing

- No env list, reservation UI, or filtering (S-02/S-03).
- No password reset (PRD non-goal; admin resets manually).
- No CSS framework / visual design (deferred to S-02; pages functional but unstyled).
- No first-class admin UI for domains beyond stock Django admin registration.
- No email verification / activation — domain restriction is the only signup gate.

## Implementation Approach

Three phases, each independently verifiable. Phase 1 converts the user model to email-identity (the riskiest change — touches an applied migration). Phase 2 adds the allowed-domain model and the org-restricted signup path. Phase 3 wires login/logout, the gated home route, settings, and templates, then completes end-to-end tests.

## Critical Implementation Details

- **Migration on an applied table (Phase 1).** Migration 0002 must `RemoveField(username)` and `AlterField(email, unique=True)`. The `AlterField` to `unique=True` succeeds only if no duplicate emails exist; any pre-existing superuser likely has a blank email and **cannot log in by email** afterward — it must be recreated or have its email set. Treat superuser recreation as a manual migration step locally and on Railway.
- **`REQUIRED_FIELDS` cannot contain `USERNAME_FIELD`.** With `USERNAME_FIELD = "email"`, set `REQUIRED_FIELDS = ["first_name", "last_name"]` so `createsuperuser` prompts for a display name.
- **Custom manager needs `use_in_migrations = True`** so the migration's `managers=[...]` entry resolves to the accounts manager (currently `django.contrib.auth.models.UserManager`).
- **Stock `UserAdmin` references `username`** in its `fieldsets`/`add_fieldsets`/`ordering` and will raise once `username` is gone — Phase 1 must replace it.
- **Django ≥5 disables logout via GET** — sign-out must be a POST form (a button), not a link.

## Phase 1: Convert User to email-as-identity

### Overview

Make email the unique login credential, drop `username`, add a custom manager, and fix the admin so `/admin/` and `createsuperuser` keep working.

### Changes Required:

#### 1. Custom user manager + model

**File**: `accounts/models.py`

**Intent**: Replace the inherited username-based manager/identity with an email-based one so authentication keys on email while keeping `first_name`/`last_name` for display.

**Contract**: Add `class UserManager(BaseUserManager)` with `use_in_migrations = True` and `create_user(email, password, **extra)` / `create_superuser(...)` (normalize email, hash password, enforce `is_staff`/`is_superuser` for superuser). On `User`: `username = None`; `email = models.EmailField(unique=True)`; `USERNAME_FIELD = "email"`; `REQUIRED_FIELDS = ["first_name", "last_name"]`; `objects = UserManager()`.

#### 2. Migration

**File**: `accounts/migrations/0002_email_identity.py` (new)

**Intent**: Apply the model delta to the already-migrated table.

**Contract**: `RemoveField(username)`, `AlterField(email → unique=True)`, and `AlterModelManagers` to the new manager. Generated via `makemigrations accounts`; review that it does not attempt to recreate the table.

#### 3. Admin

**File**: `accounts/admin.py`

**Intent**: Replace stock `UserAdmin` (which references the now-removed `username`) with an email-based admin.

**Contract**: Custom `ModelAdmin` (or `UserAdmin` subclass) with `ordering`, `list_display`, `fieldsets`, and `add_fieldsets` keyed on `email`/`first_name`/`last_name`/password — no `username`.

### Success Criteria:

#### Automated Verification:

- [ ] Migrations generate with no model-state drift: `uv run python manage.py makemigrations --check --dry-run`
- [ ] Migration applies cleanly: `uv run python manage.py migrate`
- [ ] Manager test passes (create_user / create_superuser by email): `uv run python manage.py test accounts`

#### Manual Verification:

- [ ] `uv run python manage.py createsuperuser` prompts for email + first/last name and succeeds.
- [ ] The new superuser can log into `/admin/` with email + password.

**Implementation Note**: Pause for manual confirmation after this phase — it alters an already-applied migration and may require recreating the local/Railway superuser.

---

## Phase 2: Allowed-domain model + org-restricted signup

### Overview

Add the admin-managed allowed-domain list and the signup form/view/template that enforces it.

### Changes Required:

#### 1. AllowedEmailDomain model + admin

**File**: `accounts/models.py`, `accounts/admin.py`, new migration `accounts/migrations/0003_allowedemaildomain.py`

**Intent**: Store the org's allowed email domains, editable by admins via `/admin/`.

**Contract**: `AllowedEmailDomain` with a unique `domain` CharField, lowercased on save (override `save()` or normalize in the validator). Registered in admin with `list_display = ["domain"]`.

#### 2. Signup form with domain validation

**File**: `accounts/forms.py` (new)

**Intent**: Collect email + first/last name + password and reject non-org domains; first/last name required so a display name always exists.

**Contract**: `SignUpForm(UserCreationForm)` with `Meta.model = User`, `Meta.fields = ("email", "first_name", "last_name")`, first/last name `required=True`. `clean_email` extracts the domain (lowercased); if `AllowedEmailDomain.objects.exists()` and the domain isn't in it, raise `ValidationError`. Empty table → accept.

#### 3. Signup view + URL + template

**File**: `accounts/views.py`, `accounts/urls.py` (new), `templates/registration/signup.html` (new)

**Intent**: Render and process signup; log the user in on success and redirect home.

**Contract**: `CreateView` (or function view) using `SignUpForm`; `name="signup"`; on valid save, `login()` the new user and redirect to `LOGIN_REDIRECT_URL`. Template extends `base.html`.

### Success Criteria:

#### Automated Verification:

- [ ] Migration applies: `uv run python manage.py migrate`
- [ ] Tests pass — signup rejects a disallowed domain when domains are configured, accepts a matching domain, and accepts any domain when the table is empty: `uv run python manage.py test accounts`
- [ ] Test: a successful signup creates a `User` with `first_name`/`last_name` set and logs them in.

#### Manual Verification:

- [ ] With an `AllowedEmailDomain` row present, signup with a non-matching domain shows a clear inline error; a matching domain succeeds and lands on home.
- [ ] New domain rows can be added/edited in `/admin/`.

**Implementation Note**: Pause for manual confirmation after this phase.

---

## Phase 3: Login / logout / gated home + settings + base template

### Overview

Wire Django's built-in login/logout, a `login_required` placeholder home, the unauth→sign-in redirect, and the shared base template.

### Changes Required:

#### 1. Auth + home URLs

**File**: `accounts/urls.py`, `envbooker/urls.py`

**Intent**: Expose login/logout/signup and a home route; redirect unauthenticated visitors to sign-in.

**Contract**: In `accounts/urls.py`, `LoginView` (`name="login"`), `LogoutView` (`name="logout"`), and `signup`. In `envbooker/urls.py`, `include("accounts.urls")` and a home path (`name="home"`). Home is a `login_required` view (function or `LoginRequiredMixin` `TemplateView`) rendering `home.html` and greeting `user.get_full_name()` (fallback email).

#### 2. Settings

**File**: `envbooker/settings.py`

**Intent**: Point Django's auth machinery at the new routes and register the project templates dir.

**Contract**: Add `LOGIN_URL`, `LOGIN_REDIRECT_URL = "home"`, `LOGOUT_REDIRECT_URL = "login"`; set `TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]`.

#### 3. Templates

**File**: `templates/base.html`, `templates/registration/login.html`, `templates/home.html` (all new; `signup.html` from Phase 2)

**Intent**: Provide a minimal shared layout, the login page, and the home page; sign-out is a POST.

**Contract**: `base.html` with `{% block title %}`/`{% block content %}` and a Django messages loop; a nav showing sign-out (POST form to `logout`) when authenticated, sign-in/sign-up links otherwise. `registration/login.html` is what `LoginView` renders by default. No CSS framework.

### Success Criteria:

#### Automated Verification:

- [ ] Test: GET `/` while unauthenticated → 302 redirect to `LOGIN_URL`.
- [ ] Test: valid login redirects to home; logout (POST) ends the session; home then redirects to login.
- [ ] Full suite green: `uv run python manage.py test`

#### Manual Verification:

- [ ] Visiting `/` logged-out lands on sign-in; after sign-in, home greets the user by full name.
- [ ] Sign-out button returns to sign-in and `/` is gated again.
- [ ] `runserver` flow (signup → home → logout → login) works end to end.

**Implementation Note**: Pause for manual confirmation after this phase.

---

## Testing Strategy

### Unit Tests:

- `UserManager.create_user`/`create_superuser` (email keyed, password hashed).
- `AllowedEmailDomain` normalization (lowercasing, uniqueness).
- `SignUpForm.clean_email` across allowed / disallowed / empty-table cases.

### Integration Tests:

- Signup creates + logs in a user with `first_name`/`last_name`.
- Login/logout session lifecycle.
- Unauthenticated `/` redirects to sign-in.

### Manual Testing Steps:

1. `createsuperuser` with email + first/last name; log into `/admin/`.
2. Add an `AllowedEmailDomain` row; sign up with a non-matching domain (expect inline error), then a matching domain (expect success → home).
3. Sign out (button), confirm `/` is gated again; sign back in.

## Migration Notes

Migration 0002 alters the already-applied `accounts.User` table. Locally and on Railway, **recreate the superuser** (or set its email) after migrating, since login is now by email and old superusers likely have a blank email. The Railway sequence is the standard `migrate` step in `railway.toml`; the superuser recreate is a one-time manual `createsuperuser`.

## References

- Roadmap slice: `context/foundation/roadmap.md` → S-01 (lines 79–90)
- PRD: FR-001/002/004, Access Control (`context/foundation/prd.md`)
- User model: `accounts/models.py:4`; applied migration `accounts/migrations/0001_initial.py`
- FK consumers (PK must stay stable): `catalog/models.py`, `reservations/models.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Convert User to email-as-identity

#### Automated

- [ ] 1.1 Migrations generate with no model-state drift: `makemigrations --check --dry-run`
- [ ] 1.2 Migration applies cleanly: `migrate`
- [ ] 1.3 Manager test passes (create_user / create_superuser by email): `test accounts`

#### Manual

- [ ] 1.4 `createsuperuser` prompts for email + first/last name and succeeds
- [ ] 1.5 New superuser can log into `/admin/` with email + password

### Phase 2: Allowed-domain model + org-restricted signup

#### Automated

- [ ] 2.1 Migration applies: `migrate`
- [ ] 2.2 Tests pass — signup rejects disallowed domain (configured), accepts matching, accepts any when empty: `test accounts`
- [ ] 2.3 Test: successful signup creates a User with first/last name and logs them in

#### Manual

- [ ] 2.4 Non-matching domain shows inline error; matching domain succeeds → home
- [ ] 2.5 Domain rows can be added/edited in `/admin/`

### Phase 3: Login / logout / gated home + settings + base template

#### Automated

- [ ] 3.1 Test: GET `/` unauthenticated → 302 redirect to `LOGIN_URL`
- [ ] 3.2 Test: valid login → home; logout (POST) ends session; home then redirects to login
- [ ] 3.3 Full suite green: `test`

#### Manual

- [ ] 3.4 Logged-out `/` lands on sign-in; after sign-in, home greets by full name
- [ ] 3.5 Sign-out button returns to sign-in and `/` is gated again
- [ ] 3.6 `runserver` flow (signup → home → logout → login) works end to end
