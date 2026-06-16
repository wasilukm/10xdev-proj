---
date: 2026-06-14T20:26:12+02:00
researcher: Mariusz Wasiluk
git_commit: dc8efebaa381426c496f42e6e2a56017ed18ed78
branch: main
repository: 10xdev-proj
topic: "Critical-path e2e — prove find → filter → reserve → appears-without-reload in a real browser (Risk #2)"
tags: [research, codebase, htmx, e2e, reservations, catalog, playwright]
status: complete
last_updated: 2026-06-14
last_updated_by: Mariusz Wasiluk
last_updated_note: "Corrected /10x-e2e ownership boundary — the skill discovers but does NOT build Playwright infra; added §7 scoping the infrastructure this change must build."
---

# Research: Critical-path e2e — find → filter → reserve → appears-without-reload (Risk #2)

**Date**: 2026-06-14T20:26:12+02:00
**Researcher**: Mariusz Wasiluk
**Git Commit**: dc8efebaa381426c496f42e6e2a56017ed18ed78
**Branch**: main
**Repository**: 10xdev-proj

## Research Question

Phase 3 of the test plan (`context/foundation/test-plan.md:70`), covering **Risk #2**: the
filter → pick → reserve → appears-without-reload flow could break in a real browser (HTMX
swap, JS, or template wiring) while every current partial-render test still passes — the
primary <30s success criterion silently fails. Per the Risk #2 grounding row
(`test-plan.md:54`), research must ground three things before a plan is written:

1. The HTMX request/response wiring (trigger, target, swap).
2. The partial vs. full-page template boundary.
3. Which screen is the single critical one for an optional visual check.

## Summary

The flow is a **two-hop HTMX targeted-swap** chain, no JS beyond `htmx.min.js`, no
out-of-band swaps, no `HX-Trigger` headers:

- **Hop 1 (filter):** the filter form does `hx-get` → swaps the whole `#env-results`
  container (`outerHTML`) and pushes the URL. The home view branches on the `HX-Request`
  header to return the results **partial** instead of the full page.
- **Hop 2 (reserve):** each row carries its own `hx-post` form that targets **its own row
  id** (`#env-row-{pk}`) and swaps `outerHTML`. The create view returns the **same row
  partial re-rendered** with fresh data — so the new reservation "appears" because the
  re-queried row now shows Busy + the reservation, all without a full reload.

The conflict path is the same swap: an overlap raises `IntegrityError`, the view detects it
by matching the constraint name `reservation_no_overlap` in the error text, builds a
named-conflict string, and returns it inside the swapped row at HTTP 200 (never a 500,
never a reload).

**The false-confidence baseline is real and identified.** 5 reservation view-tests exercise
the create/edit partial responses *without* the `HX-Request` header and without asserting on
any swap target — they pass even if the `hx-target`/`hx-swap`/JS wiring is broken. Only 3
`FilterUITest` methods send `HX-Request`, and none drives filter→pick→reserve end-to-end.
**Zero browser/e2e infrastructure exists** (no Playwright, no Node/`package.json`, no
`LiveServerTestCase`). **Correction (2026-06-14): the `/10x-e2e` skill does NOT own/create
the runner or config** — it *discovers* an existing Playwright setup and **STOPs** if one is
absent (SKILL.md:61, 113-122). It creates only two levers (`seed.spec.ts` + an E2E rules
file). Therefore **this change must build the Playwright infrastructure itself** before
`/10x-e2e` can drive the test — see §7 "E2E infrastructure to build in THIS change".

**Single critical screen for optional visual review:** the environment-list **dashboard**
(`templates/catalog/environment_list.html` → `_environment_results.html` →
`_environment_row.html`) — it is the only screen the whole flow happens on.

> ⚠️ **Top implementation hazard for the test author:** every row renders the booking form
> via `{{ booking_form.as_p }}` with Django's **default auto-ids**, so *every* row emits the
> same `id_start` / `id_duration` / `id_custom_hours` and the same "Book" button text.
> A page-global `getByLabel('Start')` / `getByRole('button', {name:'Book'})` will match
> multiple elements. **Every form interaction must be scoped to the target row**, e.g.
> `page.locator('#env-row-' + pk).getByRole('button', { name: 'Book' })`.

## Detailed Findings

### 1. HTMX request/response wiring (trigger → target → swap)

**Hop 1 — Filter (whole-container swap).**

- Filter form, `templates/catalog/environment_list.html:8-12`:
  `hx-get="{% url 'home' %}"`, `hx-target="#env-results"`, `hx-swap="outerHTML"`,
  `hx-push-url="true"`. The `<form method="get">` also degrades without JS.
- Home view branches on the header — `catalog/views.py:53`: `if request.headers.get("HX-Request"):`
  → returns partial `catalog/_environment_results.html` (`views.py:56`); else full page
  `catalog/environment_list.html` (`views.py:65`).
- Swap target container: `templates/catalog/_environment_results.html:1` —
  `<div id="env-results">`. Matches the `hx-target` id exactly.

**Hop 2 — Reserve (single-row swap).**

- Booking form lives **inside each row**, `templates/catalog/_environment_row.html:29-35`:
  `hx-post="{% url 'reservations:create' %}"`, `hx-target="#env-row-{{ env.pk }}"`,
  `hx-swap="outerHTML"`, `{% csrf_token %}`, `{{ booking_form.as_p }}`,
  `<button type="submit">Book</button>`.
- Row element: `templates/catalog/_environment_row.html:1` — `<tr id="env-row-{{ env.pk }}">`.
  The form targets the row it sits in.
- Create view: `reservations/views.py:82-118`. It does **not** branch on `HX-Request` — it
  always returns the row partial via the `_row_response()` helper (`views.py:23-40`, renders
  `catalog/_environment_row.html` at `views.py:40`).
- `htmx.min.js` is loaded once in `templates/base.html:7`.

**Why the new reservation "appears" (no OOB, no HX-Trigger).** `_row_response` rebuilds
context with `catalog.services.build_row_context(env)` (`reservations/views.py:30`,
`catalog/services.py:24`). Called **without** a prefetch cache, it hits the fallback query
`catalog/services.py:38-43` (`env.reservations...filter(during__overlap=window)`), so the
just-created row is included and surfaces as `current_reservation` / `upcoming_reservations`
(`services.py:45-58`). The Status cell flips Free→Busy at `_environment_row.html:8`; the
reservation renders at `_environment_row.html:10-24`. HTMX swaps the fresh `<tr>` over the
old one — single-row replacement, fresh empty booking form re-supplied.

### 2. Conflict / reject path (in-page, HTTP 200)

- Constraint name: `reservations/models.py:26-27` — `ExclusionConstraint(name="reservation_no_overlap", ...)`
  (also `reservation_during_bounded` at `models.py:35`).
- Detection by name-substring match — `reservations/views.py:104-108`:
  ```python
  except IntegrityError as e:
      cause = str(getattr(e, "__cause__", "") or e)
      if "reservation_no_overlap" in cause:
          conflict_message = services.describe_overlap_conflict(env, during)
          next_free = services.next_free_window(env, start)
  ```
  The bounded-range case maps to a different message (`views.py:109-112`); anything else
  re-raises (`views.py:114`). This is the **constraint-name-pin** pattern that Phase 1's
  `ReservationConstraintNamesTest` protects (`test-plan.md:178`).
- Message construction — `reservations/services.py:89-92` (verified verbatim):
  ```
  Conflicts with {owner_label}'s reservation (YYYY-MM-DD HH:MM – YYYY-MM-DD HH:MM)
  ```
  `owner_label` = `conflict.owner.get_full_name() or conflict.owner.email` (`services.py:86`).
  **Assertion wording for the e2e test:** it is "**Conflicts with**" (not "overlaps with"),
  the window is **parenthesized** with an **en-dash `–`** (not "from … to …").
- Rendered in the swapped row — `templates/catalog/_environment_row.html:26-28`:
  `{% if conflict_message %}<p>{{ conflict_message }}</p>{% endif %}` then
  `{% if next_free %}<p>Next free: {{ next_free }}</p>{% endif %}`. Same `hx-target`/`hx-swap`,
  so the rejection appears in-page with no reload, at 200 OK.

### 3. Partial vs. full-page template boundary

**Full-page templates** (extend `base.html`):
- `templates/catalog/environment_list.html` — the dashboard shell + filter form.
- `templates/reservations/my_reservations.html` — secondary (edit/cancel surface).

**Partial fragments** (returned to a swap target, no `base.html`):
- `templates/catalog/_environment_results.html` — `<div id="env-results">`, the Hop-1 target.
- `templates/catalog/_environment_row.html` — `<tr id="env-row-{pk}">`, the Hop-2 target;
  also carries the booking form and the conflict/next-free messages.
- `templates/reservations/_reservation_item.html` — `<div id="reservation-{pk}">`, the
  edit/cancel swap target (secondary surface, shares the idiom).

The boundary test that already guards Hop 1: `catalog/tests.py:295`
`test_htmx_request_returns_partial_only` asserts the partial has no `<html>`/`<nav>` and
keeps `id="env-results"`.

### 4. The single critical screen (optional visual review)

The entire flow happens on **one screen** — the environment-list dashboard. Composition:
`environment_list.html` (full page) → `_environment_results.html` (results container) →
`_environment_row.html` (rows + booking form + conflict message). View: `catalog/views.py:22`
`environment_list()`. This is the only screen worth a 1-screen visual check (matches
`test-plan.md:94` and §7 "dashboard only"). Pixel regression, if ever wanted, should use a
deterministic tool — not a vision model (CLAUDE.md / M3 L4 boundary).

### 5. The false-confidence baseline (tests that pass while the browser breaks)

**Send `HX-Request`, but only Hop 1 (filter), never the full flow** — `catalog/tests.py`,
`FilterUITest`:
- `:295` `test_htmx_request_returns_partial_only` — partial-only shape.
- `:306` `test_htmx_filtered_returns_narrowed_rows` — filter narrows rows.
- `:315` `test_htmx_zero_match_shows_no_match_message` — "No environments match these filters".

**Exercise the reserve/edit partials WITHOUT `HX-Request` and WITHOUT asserting any swap
target** (these are the false-confidence tests — they 200 even if `hx-target`/`hx-swap`/JS is
broken):
- `reservations/tests/test_views.py:63` `ReservationCreateViewTest.test_happy_path_creates_reservation`
- `reservations/tests/test_views.py:71` `...test_overlap_rejection_names_owner_and_window`
- `reservations/tests/test_views.py:169` `ReservationEditViewTest.test_happy_path_updates_during`
- `reservations/tests/test_views.py:213` `...test_overlap_conflict_names_other_owner_not_self`
- `reservations/tests/test_views.py:342` `ReservationCancelViewTest.test_cancel_deletes_row_and_returns_empty`

None of these assert that the row's `hx-target`/`hx-swap` actually wires to a live DOM
element, that the browser issues the request, or that the swap renders. That gap is exactly
what the browser test must close.

**No e2e infrastructure exists** (searched whole repo): no `playwright`/`selenium` in
`pyproject.toml`, no Node/`package.json`/`node_modules`, no `LiveServerTestCase`/
`StaticLiveServerTestCase`, no `tests/e2e/`, no `playwright.config.*`, no `conftest.py`.
**The `/10x-e2e` skill will not create any of this** — it discovers it and stops if missing
(see §7). It owns only `seed.spec.ts` + the E2E rules file.

> ⚠️ **Correction to a sub-agent claim:** the existing Django tests do **not** run on
> "in-memory SQLite." This project is **Postgres-only even in tests**
> (`CLAUDE.md`; `test-plan.md:91`) — the `btree_gist` exclusion constraint is Postgres-only
> and `settings.py` raises `ImproperlyConfigured` on a non-Postgres `DATABASE_URL`. Any e2e
> harness must also run against Postgres, and `DJANGO_DEBUG=True` must be set so
> `SECURE_SSL_REDIRECT` doesn't 301 requests before they reach the view
> (`test-plan.md:179-180`).

### 6. Seed-data shape for the browser test

The browser test needs DB rows before driving the UI. The reservation view tests' pattern
(`reservations/tests/test_views.py:29-73`, helpers in `reservations/tests/_helpers.py`):
- User: `User.objects.create_user(email=..., password=..., first_name=..., last_name=...)`
  (email-as-identity; full name drives the owner label in the conflict message).
- Environment: `Environment.objects.create(name=..., version=..., purpose=..., project=...,
  use_case_tag=..., owner=user)`.
- Reservation (to force a conflict): `Reservation.objects.create(owner=user, environment=env,
  during=_range(start_h, end_h))` — `_helpers.py` `_range()` builds the `[)` Postgres range;
  `_FIXED_NOW` anchor is `2024-01-01 08:00 UTC` (`_helpers.py:5`).
- Per the project e2e rules (CLAUDE.md): unique ids with a **timestamp suffix** on the env
  name so parallel runs / re-runs don't collide; each test does its own setup + cleanup.

### 7. E2E infrastructure to build in THIS change (the `/10x-e2e` skill will NOT create it)

**This is the corrected ownership boundary.** The earlier framing ("runner/config owned by
M3 L4 / the `/10x-e2e` skill") is **wrong**. Read from `.claude/skills/10x-e2e/SKILL.md`:

- **SKILL.md:61** — "This skill **discovers** them; it does **not** install Playwright,
  scaffold configs, or wire up CI. If Playwright is absent entirely, stop and tell the user
  to set it up first."
- **SKILL.md:63** — "It creates the two quality levers, but nothing more" (`seed.spec.ts` +
  the E2E rules file).
- **SKILL.md:113-122** — Setup hard-stop: "**If there is no Playwright config and no
  `*.spec.ts` files at all, STOP**" with a message telling the user to
  `npm init playwright@latest` first.

So if we invoke `/10x-e2e` against this repo today it will **immediately STOP**. The
infrastructure is in-scope for this change's plan.

> **DECISION (2026-06-14): Python binding — `pytest-playwright` + `pytest-django`.** We keep a
> single Python/uv toolchain and seed via the Django ORM. The `/10x-e2e` skill **and its
> reference levers have been adapted to Playwright Python** (sync API) in this repo — the
> STOP gate now keys on `pytest-playwright` + `tests/e2e/test_*.py` (not `playwright.config.*`/
> `*.spec.ts`), and the seed/rules/anti-pattern/prompt files carry Python syntax. So the
> "Option A vs B" framing below is **resolved to Option B**; the table rows still describe the
> concrete build tasks, now in their Python form.

**What the skill DISCOVERS (must pre-exist — we build these):**

**What the skill DISCOVERS (must pre-exist — we build these), now in Python form:**

| Pre-req the (adapted) skill expects | Status here | Build task for this change |
|---|---|---|
| `pytest-playwright` + `pytest-django` installed + browsers | absent | `uv add --group dev pytest-playwright pytest-django` → `uv run playwright install chromium` |
| pytest config wired to Django | absent | `[tool.pytest.ini_options]` with `DJANGO_SETTINGS_MODULE = "envbooker.settings"` (+ markers) |
| Command to run a **single** test | works once installed | `uv run pytest tests/e2e/test_<x>.py::test_<y>` |
| Auth fixture (no UI login) | absent | `conftest.py` fixture: inject a Django `sessionid` cookie (or a saved `storage_state`) |
| App start under test | absent | pytest-django `live_server` + `transactional_db` against the Postgres test DB |

**What the skill CREATES (leave for `/10x-e2e`, do NOT pre-build):** `tests/e2e/test_seed.py`
and the E2E rules file (from its `references/`). The plan reserves these for the skill.

**App-start under Postgres (non-negotiable).** The harness boots the real app against
**Postgres** with `DJANGO_DEBUG=True` (SQLite unsupported; `SECURE_SSL_REDIRECT` 301s
otherwise — see §5 correction). With pytest-django, **`live_server` + `transactional_db`**
runs the app in a thread against the auto-created test DB (`test_envbooker`) and the
live-server thread sees committed rows — no separate `webServer`, no `dev.sh` needed at test
time (`dev.sh` remains the manual-run recipe). The test DB is created/migrated/torn down by
pytest-django.

**Auth without the UI.** Login is `path("login/", LoginView, name="login")`
(`accounts/urls.py`) using `EmailAuthenticationForm` (email + password). Idiomatic Django
"auth without the UI": a fixture creates the `User` via the ORM, mints a server-side session
(`django.contrib.sessions`), and `context.add_cookies([...])` injects the `sessionid` — no
login form driven, ever. (A saved `storage_state` produced by a one-time login is the
alternative; the cookie-injection path is simpler and DB-native here.)

**Seed data via the ORM (the payoff of choosing Python).** The browser test needs
deterministic users/envs/reservations (§6 shape) *before* it drives the UI. A **pytest fixture
seeds directly through the Django ORM** (reusing `Environment.objects.create(...)` /
`Reservation.objects.create(..., during=_range(...))`), under `transactional_db` so
`live_server` sees it — no management command, no seed endpoint, no fixtures file. Seed
**unique** data per run (timestamp/uuid-suffixed env name) per CLAUDE.md's e2e rules; the
test-DB reset handles teardown.

**CI is NOT part of this change.** Wiring the e2e gate into CI is **Phase 5**
(`test-plan.md:112` "required after §3 Phase 3"; Phase 5 stands up the harness). This change
only needs the **local** single-test run to work; the plan should keep the test CI-ready
(headless, deterministic) but stop short of authoring the CI workflow.

## Code References

- `catalog/views.py:22-71` — `environment_list()`; `HX-Request` branch at `:53`, partial at `:56`, full page at `:65`.
- `catalog/views.py:50` — `ReservationForm(initial={"environment": env.pk})` per row → duplicate auto-ids.
- `catalog/services.py:24-59` — `build_row_context()`; fallback re-query at `:38-43` is why the new row appears.
- `catalog/services.py:62` `filter_environments()`, `:84` `filter_options()`, `:98` `prefetch_reservations_for_list()`.
- `reservations/views.py:23-40` — `_row_response()` helper (renders `catalog/_environment_row.html`).
- `reservations/views.py:82-118` — `reservation_create()`; atomic create `:97-103`, conflict catch `:104-114`, return `:116-118`.
- `reservations/services.py:70-92` — `describe_overlap_conflict()` (exact message string).
- `reservations/services.py:95` — `next_free_window()`.
- `reservations/models.py:26-27` — `reservation_no_overlap` exclusion constraint.
- `templates/catalog/environment_list.html:8-12,13-36` — filter form HTMX attrs + labelled selects + Filter button.
- `templates/catalog/_environment_results.html:1` — `#env-results` swap target.
- `templates/catalog/_environment_row.html:1,8,26-35` — row id, Free/Busy, conflict/next-free, booking form.
- `templates/base.html:7` — `htmx.min.js`.
- `reservations/forms.py:24-41` — `ReservationForm` fields (`start` datetime-local, `duration`, `custom_hours`, hidden `environment`).
- `catalog/tests.py:253-322` — `FilterUITest` (the 3 real HTMX tests).
- `reservations/tests/test_views.py:63,71,169,213,342` — partial-render tests lacking HTMX/swap assertions.
- `reservations/tests/_helpers.py:5,8,13` — `_FIXED_NOW`, `_dt()`, `_range()` fixtures.

## Architecture Insights

- **Two distinct swap idioms, one page.** Filter = whole-container swap keyed on a fixed id
  (`#env-results`); reserve = self-targeting row swap keyed on a per-row id (`#env-row-{pk}`).
  The browser test must assert *both* hops to cover Risk #2, and the second hop is the one no
  existing test exercises through a browser.
- **"Appears without reload" is an emergent property of a re-query, not an explicit push.**
  There is no OOB swap or `HX-Trigger`. The row reappears Busy only because
  `build_row_context` re-queries on the create path. A regression that (e.g.) reintroduced a
  stale prefetch cache on the create path would silently break "appears" while every
  view-test stays green — strong argument for the browser assertion.
- **Progressive enhancement is present** (filter form has `method="get"` + `hx-get`), but the
  reserve form is HTMX-only (`hx-post`, no non-JS `action`), so the reserve hop genuinely
  requires JS — exactly the layer a real browser exercises and view-tests cannot.
- **Accessibility seams are good on the filter, thin on the results.** Filter selects are
  `getByLabel`-addressable; the results container and the conflict `<p>` have no role/`aria-live`.
  Prefer role/label/text locators (CLAUDE.md hard rule); fall back to `#env-row-{pk}` scoping
  or a `data-testid` only where attributes are genuinely ambiguous (the duplicate-form-id case).

### Concrete locator candidates (for the plan / `/10x-e2e`)

- Filter: `getByLabel('Availability:')`, `getByLabel('Project:')`, `getByLabel('Tag:')`,
  `getByRole('button', { name: 'Filter' })` (`environment_list.html:13-36`).
- Row scope: `page.locator('#env-row-' + pk)` (`_environment_row.html:1`) — **scope all reserve
  interactions through this**.
- Reserve (scoped): `…getByLabel('Start')`, `…getByLabel('Duration')`,
  `…getByRole('button', { name: 'Book' })` (`forms.py:29-34`, `_environment_row.html:34`).
- Appears: scoped `getByText('Busy')` (`_environment_row.html:8`) and the new reservation
  owner/window text in the row.
- Conflict: `getByText(/Conflicts with .*'s reservation/)` (`_environment_row.html:27`).
- **Never** `page.waitForTimeout()` — wait on `toBeVisible()` / `waitForResponse()` for the
  POST to `reservations:create`.

## Historical Context (from prior changes)

- `context/foundation/test-plan.md:43,54,70` — Risk #2 definition, its proof/anti-pattern row,
  and the Phase 3 rollout entry that scopes this work (e2e + optional single-screen visual).
- `context/foundation/test-plan.md:178` — Phase 1's **constraint-name-pin** lesson; the same
  `reservation_no_overlap` literal the create view matches on is what makes the conflict path
  detectable (and what would silently break on a rename).
- `context/foundation/test-plan.md:179-180` — `DJANGO_DEBUG=True` requirement to avoid
  `SECURE_SSL_REDIRECT` 301s in the test environment (applies to the e2e harness too).
- `context/changes/testing-no-overlap-hardening/` — Phase 1 (complete); hardened the
  *server-side* overlap rejection this browser test now confirms reaches the *user*.
- `context/foundation/prd.md:34,54,57` — the success criteria this phase proves (see below).

## Spec grounding (the assertion targets)

- `prd.md:34` — reservation creatable "in **under 30 seconds** from landing on the dashboard …
  visible on the env list immediately after confirmation."
- `prd.md:54` — round-trip landing→confirmed "in under 30 seconds for a … first-time" user.
- `prd.md:57` — "**Filter results update without a full page reload.**"
- `roadmap.md:98` — echoes the no-reload critical-path criterion.

## Related Research

- None prior for this change (first research artifact). Sibling: Phase 1 lives under
  `context/changes/testing-no-overlap-hardening/`.

## Open Questions

1. **30s timing — assert it, or treat as non-functional?** The PRD frames <30s as a UX
   criterion. A browser test can assert the *behavioral* parts deterministically (no reload,
   row appears, conflict shows). A hard wall-clock <30s assertion would be flaky and is not
   recommended; the plan should decide whether to capture timing as an observation only.
2. **`data-testid` vs. `role="alert"` on the conflict `<p>`.** The cleanest fix for the
   conflict-message locator (and accessibility) is a small template change adding
   `role="alert"`/`aria-live`. Is a production-template tweak in-scope for a test phase, or
   should the test rely on `getByText` against the verified string? (Lean: `getByText` now;
   note the a11y improvement for a follow-up.)
3. **Visual review — in or out?** test-plan marks it "optional, dashboard only." Decide in the
   plan whether Phase 3 ships the e2e behavior test alone or also a single deterministic
   dashboard snapshot.
**Resolved 2026-06-14 (were open):**

4. **Language binding — DECIDED: Playwright Python (`pytest-playwright` + `pytest-django`).**
   The `/10x-e2e` skill + its levers were adapted to Python in this repo (see §7). Plan builds
   the Python harness, not a Node toolchain.
5. **App-start + test DB — DECIDED: pytest-django `live_server` + `transactional_db`** against
   the auto-managed Postgres test DB, `DJANGO_DEBUG=True`. No `webServer`/`dev.sh` at test time.
6. **Seeding — DECIDED: pytest fixtures via the Django ORM** (no management command, no seed
   endpoint). Unique-suffixed data; test-DB reset handles teardown.
7. **Auth — DECIDED: inject a server-side `sessionid` cookie via a fixture** (no UI login;
   `storage_state` is the fallback).

> These were net-new because the `/10x-e2e` skill does **not** build infrastructure
> (correction in §7); they are now settled and feed straight into `/10x-plan`. The harness
> build (install + pytest/Django config + `live_server` + auth fixture + ORM seed fixtures) is
> the plan's first phase, **before** any `/10x-e2e` run.
