# Admin Env-Catalog UI (S-05 / FR-005, FR-006, FR-007) Implementation Plan

## Overview

EnvBooker roadmap slice **S-05 (`admin-env-catalog`)** delivers a first-class admin UI to **create**,
**modify** (with a pre-save warning + a post-save "definition changed" badge), and **delete** (only when
no active/upcoming reservations exist) environment definitions — retiring the Django `/admin/` fallback
that F-01 left in place. Closes PRD **FR-005/006/007** and the admin half of Access Control.

## Current State Analysis

Django 6 app (Python 3.14, Postgres-only), three apps. Conventions verified during research:

- **Thin views + `services.py` + htmx partials** (`catalog/views.py`, `reservations/views.py`, `services.py`
  in both). Cross-app service calls are explicitly endorsed (CLAUDE.md).
- **Auth:** `accounts.User` extends `AbstractUser` → `is_staff`/`is_superuser` exist. `@login_required`
  gates user routes; non-owner writes return 404 (`reservations/views.py`).
- **`Environment`** (`catalog/models.py`) has **no timestamp**; `Reservation.environment` is
  `on_delete=PROTECT` (`reservations/models.py`).
- **Owner-facing reservation surface:** `reservations.my_reservations` → `_item_context` →
  `templates/reservations/_reservation_item.html` (badge renders here).
- Typing (`mypy` + `django-stubs`) and ruff (per-edit hook + lefthook pre-commit) gates are live. All new
  first-party code must be annotated and lint-clean.
- `catalog/admin.py` registers `EnvironmentAdmin` (the fallback this slice retires).

## Desired End State

A signed-in **staff** user sees a "Manage environments" nav link leading to `/manage/environments/`, where
they can create envs (owner selectable, default self), edit them (with a two-step "Save anyway" warning that
lists affected active/upcoming reservations when present), and delete them (blocked while active/upcoming
reservations exist; otherwise the env and its past reservations are removed together). Affected reservation
owners see a "definition changed since you reserved" badge on their own reservations in *My reservations*.
`Environment` is no longer editable via Django `/admin/`. Non-staff users get 403 on every manage route;
anonymous users are redirected to login.

### Key discoveries
- `catalog/urls.py` has **no `app_name`** and `base.html` uses `{% url 'home' %}` — adding a namespace
  would break `home`. Use flat names (`env_manage`, `env_create`, `env_edit`, `env_delete`).
- `PROTECT` on `Reservation.environment` blocks deletion if **any** reservation (incl. past) exists — so
  FR-007's "active/upcoming only" rule needs an application-level guard + cascade of past rows.
- Badge can be **derived** from a new `Environment.updated_at` (`auto_now`) vs `Reservation.created_at`
  (`auto_now_add`, already present) — no per-reservation writes, no acknowledgement state.
- `reservations/services.py` already uses `Func("during", function="lower"/"upper", ...)` for range-bound
  filtering — reuse that pattern for the active/upcoming and past queries.

## What We're NOT Doing
- S-06 (admin override of *reservations*) — separate slice; `Reservation`/`User`/`AllowedEmailDomain`
  Django admin registrations stay untouched.
- Badge acknowledgement/dismissal, or showing the badge on the shared env list.
- Soft-delete / history retention of deleted envs (past reservations are hard-deleted on cascade).
- Any change to booking, filter, or edit-own-reservation flows.

## Implementation Approach

Mirror the existing thin-view + `services.py` + template conventions. Access control via a small
`staff_required` decorator (anon → login redirect, non-staff → 403). Four function-based views under
`/manage/environments/`. Server-rendered form/confirm pages (full-page, not htmx) keep the two-step edit
warning and delete-confirm flows simple and testable; the read-only booking list at `home` is unchanged.

## Critical Implementation Details

- **Delete race safety:** in `delete_environment`, inside one `transaction.atomic()`, check
  active/upcoming → BLOCKED; otherwise delete only **past** reservations, then `env.delete()`, catching
  `ProtectedError` (a reservation that raced in) → BLOCKED. This closes the check-then-delete race without
  row locking; `PROTECT` is the backstop.
- **Badge derivation:** `definition_changed = env.updated_at > reservation.created_at`. `my_reservations`
  already lists only `upper_bound > now` (active/upcoming) and `select_related("environment")`, so the
  badge needs only a context flag + template branch.

## Phase 1: Data model + access scaffolding

### Changes Required

#### 1. Environment timestamp
**File**: `catalog/models.py`
**Intent**: Give `Environment` a modification timestamp to drive the derived change-badge.
**Contract**: `updated_at = models.DateTimeField(auto_now=True)`.

#### 2. Migration
**File**: `catalog/migrations/000X_environment_updated_at.py`
**Intent**: Add the field with a one-off default for existing rows.
**Contract**: `AddField` with `default=django.utils.timezone.now` (auto_now overrides on later saves).

#### 3. Retire Django admin for Environment
**File**: `catalog/admin.py`
**Intent**: Make the new UI the single env write path.
**Contract**: Remove the `@admin.register(Environment)` / `EnvironmentAdmin` registration.

#### 4. Reservation-window service
**File**: `reservations/services.py`
**Intent**: Shared query for reservations that block edit-warning (Ph3) and delete (Ph4).
**Contract**: `active_or_upcoming_reservations(env, now=None) -> QuerySet[Reservation]` — annotate
`upper_bound = Func("during", function="upper", ...)`, filter `environment=env, upper_bound__gt=now`,
`select_related("owner")`, order by lower bound.

#### 5. Access-control decorator
**File**: `catalog/permissions.py` (new)
**Intent**: Gate all manage views on staff.
**Contract**: `staff_required` — anon → login redirect (reuse `login_required`); authenticated non-staff →
`HttpResponseForbidden`.

### Success Criteria

#### Automated Verification:
- `uv run python manage.py makemigrations --check` clean after generating the migration
- `uv run python manage.py migrate` applies cleanly
- `mypy` + `ruff` clean
- Test: `Environment` not in `django.contrib.admin.site._registry`
- Test: `active_or_upcoming_reservations` excludes past, includes active + upcoming

#### Manual Verification:
- `/admin/` no longer lists Environments

**Implementation Note**: Pause for manual confirmation after automated checks pass before Phase 2.

---

## Phase 2: Create + manage list + nav (FR-005)

### Changes Required

#### 1. Environment form
**File**: `catalog/forms.py` (new)
**Intent**: ModelForm for create/edit.
**Contract**: `EnvironmentForm(forms.ModelForm)` over `name, version, purpose, project, use_case_tag, owner`;
`owner` is a `ModelChoiceField(User.objects.all())`. Create view sets initial owner = `request.user`.

#### 2. List service
**File**: `catalog/services.py`
**Intent**: Queryset for the manage table.
**Contract**: `manage_environments() -> QuerySet[Environment]` (`select_related("owner").order_by("name")`).

#### 3. List + create views
**File**: `catalog/views.py`
**Intent**: Staff-gated list and create.
**Contract**: `environment_manage` (GET → table). `environment_create` (GET → form; POST valid → create +
`messages` success + redirect to `env_manage`; invalid → re-render with errors).

#### 4. Routes
**File**: `catalog/urls.py`
**Contract**: `env_manage` → `manage/environments/`, `env_create` → `manage/environments/new/` (no `app_name`).

#### 5. Templates + nav
**File**: `templates/catalog/environment_manage.html`, `templates/catalog/environment_form.html`, `templates/base.html`
**Intent**: Admin table + "New environment" button; shared form page; staff-only nav link.
**Contract**: nav adds `{% if user.is_staff %}<a href="{% url 'env_manage' %}">Manage environments</a> |{% endif %}`.

### Success Criteria

#### Automated Verification:
- Test: anon → login redirect; authenticated non-staff → 403; staff GET → 200
- Test: staff POST creates exactly one `Environment`; owner defaults to self and is settable to another user
- Test: invalid POST re-renders with errors and creates nothing
- `mypy` + `ruff` clean

#### Manual Verification:
- Nav shows "Manage environments" only for staff
- Create flow works end-to-end in the browser

**Implementation Note**: Pause for manual confirmation before Phase 3.

---

## Phase 3: Edit with pre-save warning + change badge (FR-006)

### Changes Required

#### 1. Edit view (two-step warning)
**File**: `catalog/views.py`
**Intent**: Edit an env; warn before saving over active/upcoming reservations.
**Contract**: `environment_edit(pk)` staff-gated. GET pre-fills `EnvironmentForm`. POST: if valid AND
`active_or_upcoming_reservations(env).exists()` AND no `confirm` POST flag → re-render form with the affected
list (owner + window, first ~5 + "+N more") and a hidden `confirm=1`; else save → redirect to `env_manage`.
`confirm` is a view-level POST flag, not a model field. Save bumps `updated_at` (auto_now).

#### 2. Form template warning block
**File**: `templates/catalog/environment_form.html`
**Contract**: Conditionally render affected-reservations warning + "Save anyway" (resubmits with `confirm=1`).

#### 3. Badge context
**File**: `reservations/views.py`
**Intent**: Expose the derived change flag to the owner's reservation list.
**Contract**: in `_item_context`, `definition_changed = reservation.environment.updated_at > reservation.created_at`.

#### 4. Badge rendering
**File**: `templates/reservations/_reservation_item.html`
**Contract**: Render a "Definition changed since you reserved" badge when `definition_changed`.

#### 5. Route
**File**: `catalog/urls.py`
**Contract**: `env_edit` → `manage/environments/<int:pk>/edit/`.

### Success Criteria

#### Automated Verification:
- Test: edit with no active/upcoming reservation saves one-step (fields updated)
- Test: edit with an active/upcoming reservation and no `confirm` re-renders the warning (names the affected owner) and does not save
- Test: resubmitting with `confirm=1` saves
- Test: after an env edit, `my_reservations` shows the badge for a pre-existing reservation and not for one created after the edit
- `mypy` + `ruff` clean

#### Manual Verification:
- Warning lists the correct affected reservations
- Badge appears on the affected owner's reservation in My reservations

**Implementation Note**: Pause for manual confirmation before Phase 4.

---

## Phase 4: Delete guard with cascade (FR-007)

### Changes Required

#### 1. Delete service
**File**: `catalog/services.py`
**Intent**: Enforce the active/upcoming delete guard with race safety.
**Contract**: `delete_environment(env, now=None)` returns DELETED | BLOCKED. Inside `transaction.atomic()`:
if `active_or_upcoming_reservations(env, now).exists()` → BLOCKED; else delete past reservations
(`upper_bound <= now`), then `env.delete()`, catching `ProtectedError` → BLOCKED.

#### 2. Delete view
**File**: `catalog/views.py`
**Intent**: Staff-gated confirm + perform.
**Contract**: `environment_delete(pk)`. GET → confirm page (blocking list if any, submit hidden when blocked;
else confirm button). POST → `delete_environment`; BLOCKED → re-render with blocking list; DELETED → redirect
to `env_manage` with a success note.

#### 3. Confirm template
**File**: `templates/catalog/environment_confirm_delete.html`
**Contract**: Confirm vs blocked states.

#### 4. Route
**File**: `catalog/urls.py`
**Contract**: `env_delete` → `manage/environments/<int:pk>/delete/`.

### Success Criteria

#### Automated Verification:
- Test: delete blocked (env preserved) when an active or upcoming reservation exists
- Test: delete succeeds and cascades past reservations when only past reservations exist
- Test: delete succeeds when no reservations exist
- Test: non-staff → 403
- `mypy` + `ruff` clean

#### Manual Verification:
- Confirm page shows the blocking reservations
- Successful delete removes the env from the list

**Implementation Note**: Pause for manual confirmation; this completes the slice.

---

## Testing Strategy

### Unit / Integration Tests:
- **`catalog/tests.py`** (flat, matching current structure): access control (anon/non-staff/staff) on all four
  views; create happy + invalid + owner default/selectable; edit one-step vs two-step warning vs confirm;
  delete blocked/cascade/clean; `EnvironmentAdmin` unregistered; `active_or_upcoming_reservations` and
  `delete_environment` service units.
- **`reservations/tests/test_views.py`**: badge present/absent in `my_reservations` after an env edit
  (reuse `_FIXED_NOW`/`_range` helpers from `reservations/tests/_helpers.py`).

### Manual Testing Steps:
1. As staff: create an env, edit it with no reservations, edit it with an active reservation (see warning →
   Save anyway), delete a reservation-free env, attempt to delete one with an upcoming reservation (blocked).
2. As the reservation owner: see the change badge in My reservations after a staff edit.
3. As a non-staff user: confirm 403 on `/manage/environments/` and absence of the nav link.

- Run: `docker compose up -d` then `uv run python manage.py test catalog reservations`.

## Migration Notes
- One new migration (`Environment.updated_at`, auto_now, one-off default). No backfill — reservations created
  before the field simply won't show a badge until their env is next edited.

## References
- Roadmap S-05: `context/foundation/roadmap.md`
- PRD FR-005/006/007: `context/foundation/prd.md`
- Patterns to mirror: `reservations/views.py` (thin views, IntegrityError handling),
  `reservations/services.py` (`Func("during", ...)` annotations), `reservations/forms.py` (form style),
  `templates/reservations/_reservation_item.html` (owner+window rendering)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Data model + access scaffolding

#### Automated
- [x] 1.1 `makemigrations --check` clean after generating; `migrate` applies cleanly
- [x] 1.2 `mypy` + `ruff` clean
- [x] 1.3 `Environment` not in `admin.site._registry` (test)
- [x] 1.4 `active_or_upcoming_reservations` excludes past, includes active + upcoming (test)

#### Manual
- [x] 1.5 `/admin/` no longer lists Environments

### Phase 2: Create + manage list + nav (FR-005)

#### Automated
- [ ] 2.1 anon → login redirect; non-staff → 403; staff GET → 200
- [ ] 2.2 staff POST creates one Environment (owner default self + selectable); invalid POST re-renders, creates nothing
- [ ] 2.3 `mypy` + `ruff` clean

#### Manual
- [ ] 2.4 Nav link staff-only; create flow works end-to-end

### Phase 3: Edit with pre-save warning + change badge (FR-006)

#### Automated
- [ ] 3.1 Edit with no active/upcoming reservation saves one-step
- [ ] 3.2 Edit with active/upcoming + no `confirm` re-renders warning (names affected owner), does not save
- [ ] 3.3 Resubmit with `confirm=1` saves
- [ ] 3.4 Badge present for pre-existing reservation, absent for one created after the edit
- [ ] 3.5 `mypy` + `ruff` clean

#### Manual
- [ ] 3.6 Warning lists correct reservations; badge visible to owner in My reservations

### Phase 4: Delete guard with cascade (FR-007)

#### Automated
- [ ] 4.1 Delete blocked (env preserved) when active/upcoming exists
- [ ] 4.2 Delete cascades past reservations when only past exist
- [ ] 4.3 Delete succeeds when no reservations exist
- [ ] 4.4 Non-staff → 403
- [ ] 4.5 `mypy` + `ruff` clean

#### Manual
- [ ] 4.6 Confirm page shows blocking list; successful delete removes env
