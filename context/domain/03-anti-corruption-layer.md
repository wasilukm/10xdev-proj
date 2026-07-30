---
title: "EnvBooker — Anti-Corruption Layer Refactor Plan"
created: 2026-07-30
type: refactor-plan
---

# EnvBooker — Anti-Corruption Layer Refactor Plan

This is a **plan document**. No production code is modified here.

## Step 0 — Context discovery

Documents read: `context/foundation/prd.md`, `context/foundation/tech-stack.md`,
`context/foundation/infrastructure.md`, `context/domain/01-domain-distillation.md`,
`context/domain/02-invariant-aggregate-refactor.md` (reused as prior art — Step 1's
findings build directly on the aggregate/invariant map already established there,
rather than re-deriving the domain model from scratch).

Searched all three foundation docs for replaceability declarations ("wymienialność",
"swap", "interchangeable", "vendor", "lock-in"). Found exactly one hit, and it is
about a different concept than the one this plan targets: `prd.md:24` — "test
environments are **not** interchangeable like meeting rooms" — describes the
`Environment` domain concept's business meaning, not an infrastructure/library
swap intent. No document anywhere declares an intent to keep Postgres, psycopg, or
the range type swappable. The opposite is explicit and intentional:
`envbooker/settings.py:102-112` raises `ImproperlyConfigured` at startup for any
non-Postgres `DATABASE_URL`, with the comment "Fail fast on a missing/non-Postgres
DATABASE_URL rather than silently degrading" (`envbooker/settings.py:103`) — the
project is deliberately, permanently committed to Postgres's GiST exclusion
constraints, which SQLite cannot provide.

This absence matters for Step 2: the leak identified below is **not** motivated by
"we might swap the database someday" (that door is explicitly closed by design).
It is motivated by the other class of signal KROK 1 names: a third-party type is
reconstructed independently in multiple layers, appears in a domain-service
signature, and is walked by raw attribute access all the way out to HTML templates
— corruption of layer boundaries that is real and costly regardless of whether the
underlying database ever changes.

Stack confirmed by reading source directly: Django 6.0.5 / Python 3.14, `uv`-managed.
Runtime dependency manifest (`pyproject.toml:8-13`): `dj-database-url`, `django`,
`gunicorn`, `psycopg[binary]`, `whitenoise`. `psycopg` is the only dependency whose
Python-level types (as opposed to just its DB-API role) are visible to application
code — the other four are consumed either at the settings/WSGI boundary only
(`dj-database-url`, `gunicorn`, `whitenoise`) or not directly imported by app code
at all.

## Step 1 — Identify leaking dependencies

Two candidates were found; both are evaluated before selection in Step 2.

### Candidate A: `psycopg.types.range.Range`

`Range` — psycopg's Python representation of a Postgres range value — is imported
and directly constructed/read in five production modules across every
architectural layer this app has, plus four templates:

| File | What it does with `Range` |
|---|---|
| `reservations/models.py:5,21` | `DateTimeRangeField` (Django's Postgres wrapper) declares the persistence field; `RangeOperators` used in the `Meta.constraints` `ExclusionConstraint` (`reservations/models.py:26-33`). This is the one legitimate persistence-boundary touchpoint. |
| `reservations/forms.py:9,75,112` | Imports `Range` directly; constructs `Range(start, end, "[)")` twice, independently, in `ReservationForm.clean` (`reservations/forms.py:75`) and `ReservationEditForm.clean` (`reservations/forms.py:112`) — the bounds literal `"[)"` is duplicated, not shared. |
| `catalog/services.py:11,36,55,83,112,117` | Imports `Range`; constructs a lookahead window `Range(now, horizon, "[)")` independently **again**, twice more, in `build_row_context` (`catalog/services.py:36`) and `prefetch_reservations_for_list` (`catalog/services.py:112`) — same bounds literal, fourth occurrence project-wide; reads `.during.lower`/`.during.upper` raw attributes at `catalog/services.py:55`; issues `during__contains=now` (`catalog/services.py:83`) and `during__overlap=window` (`catalog/services.py:117`) ORM lookups that require a `Range` on the right-hand side. |
| `reservations/services.py:10,102,108,114,123-124,140,143-144` | Imports `Range`; **the library type appears in a domain-service function signature** — `describe_overlap_conflict(env, during: Range[datetime], exclude_pk=...)` (`reservations/services.py:106-109`) — exactly the "library types in domain signatures" smell named in the task brief. Six separate raw `.lower`/`.upper` reads across `compute_end` (`:102`), `describe_overlap_conflict` (`:123-124`), and `next_free_window` (`:140,143-144`). |
| `reservations/views.py:76,81,87,88,150,161,201,204,215-216,246` | Seven raw `.during.lower`/`.during.upper` reads across four view functions (`build_reservation_item`, `reservation_create`, `reservation_edit`, `reservation_cancel`); passes the raw `Range` through `cleaned_data["during"]` from form to `Reservation.objects.create(..., during=during)` (`reservations/views.py:150,161`) with no intermediate domain shape. |
| `reservations/admin.py:20-27` | `during_local` duplicates the same lower/upper-extraction-and-format pattern a fifth time, independently, for the Django admin list column. |
| `templates/catalog/environment_form.html:16-17`, `templates/catalog/environment_confirm_delete.html:16-17`, `templates/catalog/_environment_row.html:20,36`, `templates/reservations/_reservation_item.html:4` | Django template language reaches directly through the model attribute into the driver object's internal shape: `{{ reservation.during.lower\|date:"Y-m-d H:i" }}` / `{{ r.during.lower }} – {{ r.during.upper }}`. This is the deepest violation: the **presentation layer** knows a DB-driver attribute naming convention (`.lower`/`.upper`, not `.start`/`.end`). |

Also present, lower-priority: `catalog/tests.py`, `reservations/tests/_helpers.py`,
`reservations/tests/test_models.py` all import `psycopg.types.range.Range`
directly to build fixtures — expected once production code has no shared
domain-level window type to use instead, addressed as a follow-on in Step 6.

### Candidate B: HTMX request-detection header

`request.headers.get("HX-Request")` appears at exactly one production call site
(`catalog/views.py:61`) plus three test assertions
(`catalog/tests.py:304,316,325`) that set the same header on the way in. This is
a single string-literal check, not a reconstructed object, not a duplicated
constructor, and does not appear in any signature or template. It fails
Step 1's own signals (no duplication, no cross-layer type leak, one file) — noted
for completeness, not carried forward.

## Step 2 — Classify and select #1

| Axis | Candidate A (`Range`) | Candidate B (`HX-Request`) |
|---|---|---|
| (a) Layers/files touched | 6 architectural layers — persistence field, forms (input boundary), services (2 apps), views (4 functions), admin, templates (4 files) — 10 production files total, plus 3 test files. | 1 layer, 1 production file, 1 line. |
| (b) Cost/risk of changing the dependency today | High: `Range` construction is duplicated 4 times with a hand-typed bounds literal (`"[)"`) that must stay consistent everywhere; a psycopg major-version change to the range API (already happened once industry-wide, psycopg2→psycopg3, which this project is already on) would require a coordinated edit across 10 files instead of 1. `.lower`/`.upper` are also the exact names Python's own `datetime` objects do *not* use, so every reader must know psycopg's vocabulary, not the domain's. | Low: a header-name change is a one-line edit; no reconstruction, no vocabulary to relearn. |
| (c) Doc-declared replaceability vs. code | No explicit declaration either way (see Step 0) — this axis is neutral for Candidate A, not a driver of the decision. | Same — HTMX's replaceability is undeclared and irrelevant given (a)/(b) already rule it out. |

**Selected: Candidate A — `psycopg.types.range.Range`.** It dominates on the two
decisive axes (layer spread and duplication cost); axis (c) is neutral for both
candidates and does not change the outcome. This is the worst leak in the
codebase by a wide margin — no other external dependency in `pyproject.toml`
(`dj-database-url`, `gunicorn`, `whitenoise`) is imported by application code
outside `envbooker/settings.py` / the WSGI entrypoint at all.

## Step 3 — Diagnosis

**Duplication** (same construction logic, independently re-derived, not shared):

1. `reservations/forms.py:75` — `Range(start, end, "[)")`
2. `reservations/forms.py:112` — `Range(self._start, end, "[)")`
3. `catalog/services.py:36` — `Range(now, horizon, "[)")`
4. `catalog/services.py:112` — `Range(now, horizon, "[)")`

Four independent call sites hand-write the same three-argument constructor with
the same bounds literal. Nothing enforces that a fifth call site (a future
duration-editing feature, say) uses `"[)"` and not `"[]"` or `"()"` — the
half-open convention that `01-domain-distillation.md`'s Ubiquitous Language
table calls out as load-bearing (`during` — "a half-open range `[start, end)`",
`context/domain/01-domain-distillation.md:31`) is enforced by *convention across
four unrelated files*, not by one gate.

**Boundary crossing, in ascending order of severity:**

- Persistence (`reservations/models.py:21`) → legitimate; this is the one place
  a Postgres range field's Django wrapper is expected to appear.
- Input boundary (`reservations/forms.py:75,112`) → `Range` is constructed
  directly inside form-cleaning code and placed into `cleaned_data`, i.e. the
  library type is smuggled across the HTTP-input → domain boundary with no
  translation step.
- Domain-service signature (`reservations/services.py:106-109`) —
  `describe_overlap_conflict(env: Environment, during: Range[datetime], ...)` —
  a business-rule function's public signature names a third-party driver type.
  Any caller must import `psycopg.types.range` just to call a domain function;
  `reservations/views.py:166` and `reservations/views.py:227-228` both do exactly
  that.
- Presentation (`templates/catalog/environment_form.html:16-17` and 3 more
  templates) — the **worst** crossing: Django template language, which has no
  Python import statement and cannot document what `.lower`/`.upper` mean,
  directly reads a DB-driver object's attribute names. A future reader of
  `_reservation_item.html:4` has no way to discover that `.lower` means "start of
  the reservation" without already knowing psycopg's `Range` API.

No document declares this shape should be swappable (Step 0), so this diagnosis
does not rest on a documented-intent-vs-code gap — it rests on the duplication and
layer-crossing signals alone, which the task brief treats as sufficient triggers
in their own right.

## Step 4 — ACL design

**Domain value object — `TimeWindow`** — the sole place in the codebase that
knows `Range`'s shape (construction, attribute names, bounds convention):

```python
# reservations/timewindow.py  (new module — the ACL)

@dataclass(frozen=True)
class TimeWindow:
    """A half-open [start, end) interval. Domain-owned; no psycopg import here
    beyond the codec at the bottom of this file."""

    start: datetime
    end: datetime

    def duration(self) -> timedelta:
        return self.end - self.start

    def contains_instant(self, when: datetime) -> bool:
        return self.start <= when < self.end

    def has_started_by(self, when: datetime) -> bool:
        return self.start <= when

    def is_over_by(self, when: datetime) -> bool:
        return self.end <= when

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other.end and other.start < self.end
```

**Narrow port** (domain interface — what the rest of the app is allowed to know
about "a codec exists"; it does not know psycopg):

```python
class RangeCodec(Protocol):
    def encode(self, window: TimeWindow) -> object: ...   # driver-native range value
    def decode(self, value: object) -> TimeWindow: ...
```

**Adapter** (the only module allowed to import `psycopg.types.range`):

```python
# reservations/timewindow.py, continued

class PsycopgRangeCodec:
    def encode(self, window: TimeWindow) -> Range[datetime]:
        return Range(window.start, window.end, "[)")

    def decode(self, value: Range[datetime]) -> TimeWindow:
        assert value.lower is not None and value.upper is not None  # reservation_during_bounded guarantees this
        return TimeWindow(start=value.lower, end=value.upper)


_codec: RangeCodec = PsycopgRangeCodec()
```

**Model-level seam** — `Reservation` becomes the persistence-mapping site,
exposing `TimeWindow` instead of `Range` to every caller:

```python
# reservations/models.py

class Reservation(models.Model):
    during = DateTimeRangeField()  # persistence field — stays; ACL boundary lives here

    @property
    def window(self) -> TimeWindow:
        return _codec.decode(self.during)

    def set_window(self, window: TimeWindow) -> None:
        self.during = _codec.encode(window)
```

**Repository-style query helpers** (own the ORM `__overlap`/`__contains` lookups,
which are the one place a `Range` genuinely must exist to build a queryset —
kept inside `reservations/services.py`, next to `_codec`, not re-derived by
callers):

```python
# reservations/services.py

def overlapping(qs: QuerySet[Reservation], window: TimeWindow) -> QuerySet[Reservation]:
    return qs.filter(during__overlap=_codec.encode(window))

def covering_instant(qs: QuerySet[Reservation], when: datetime) -> QuerySet[Reservation]:
    return qs.filter(during__contains=when)

def describe_overlap_conflict(
    env: Environment, window: TimeWindow, exclude_pk: int | None = None
) -> str | None:
    qs = overlapping(Reservation.objects.select_related("owner").filter(environment=env), window)
    ...
    owner_label = conflict.owner.get_full_name() or conflict.owner.email
    return (
        f"Conflicts with {owner_label}'s reservation "
        f"({conflict.window.start:%Y-%m-%d %H:%M} – {conflict.window.end:%Y-%m-%d %H:%M})"
    )
```

Note `describe_overlap_conflict`'s signature changes from `during: Range[datetime]`
to `window: TimeWindow` — the domain-signature leak from Step 3 is closed directly.

**Callers**, after the change, only ever construct/read `TimeWindow`:

- `reservations/forms.py`: `cleaned_data["window"] = TimeWindow(start, end)` (no
  `Range` import).
- `catalog/services.py`: `window = TimeWindow(now, horizon)`;
  `services.overlapping(env.reservations.all(), window)` (no `Range` import).
- `reservations/views.py`: `reservation = Reservation(owner=..., environment=env); reservation.set_window(window); reservation.save()`;
  reads become `reservation.window.start` / `.window.end` / `.window.is_over_by(now)`.
- `reservations/admin.py`: `obj.window.start` / `obj.window.end`, formatting stays
  local to `during_local` (display formatting is legitimately admin's job — only
  the *extraction* was duplicated psycopg knowledge).
- Templates: `{{ reservation.window.start|date:"Y-m-d H:i" }}` /
  `{{ reservation.window.end|date:"Y-m-d H:i" }}` — same rendered output, but the
  template now reads a domain-named attribute (`start`/`end`), not a driver
  internal (`lower`/`upper`).

## Step 5 — Isolation proof + before/after

**Proof list — swapping `psycopg` (or its range-type API) touches only:**

- `reservations/timewindow.py` (the codec's `encode`/`decode` bodies)
- `reservations/models.py` (the `DateTimeRangeField` declaration itself, if the
  Django wrapper's type also changed — orthogonal to psycopg's Python API)

Every other file in the table under Step 1 — `reservations/forms.py`,
`catalog/services.py`, `reservations/services.py` (function bodies other than
`overlapping`/`covering_instant`), `reservations/views.py`, `reservations/admin.py`,
and all four templates — becomes provably unaware of `psycopg` after the refactor,
because none of them import it or construct/read its objects anymore.

**Before/after:**

| Site | Before | After |
|---|---|---|
| `reservations/forms.py:75,112` | `Range(start, end, "[)")`, imports `psycopg.types.range` | `TimeWindow(start, end)`, no `psycopg` import |
| `catalog/services.py:36,112` | `Range(now, horizon, "[)")` ×2, imports `psycopg.types.range` | `TimeWindow(now, horizon)`, no `psycopg` import |
| `reservations/services.py:106-109` | `describe_overlap_conflict(env, during: Range[datetime], ...)` | `describe_overlap_conflict(env, window: TimeWindow, ...)` — domain signature, no third-party type |
| `reservations/views.py:76,81,87,88,201,204,246` | 7× `reservation.during.lower` / `.during.upper` | 7× `reservation.window.start` / `.window.end` (or named predicates: `.window.is_over_by(now)`) |
| `reservations/admin.py:25-26` | `obj.during.lower`, `obj.during.upper` | `obj.window.start`, `obj.window.end` |
| `templates/catalog/_environment_row.html:20,36` and 3 more | `{{ r.during.lower }} – {{ r.during.upper }}` | `{{ r.window.start }} – {{ r.window.end }}` — UI now receives a domain-named value, not a raw driver object |

The UI layer's change is the one Step 5 specifically asks to demonstrate: before,
a template author had to know psycopg's `.lower`/`.upper` convention; after,
templates consume `TimeWindow.start` / `TimeWindow.end`, which read the same as
the domain's own Ubiquitous Language entry for `during`
(`context/domain/01-domain-distillation.md:31`, "a half-open range `[start,
end)`" — `start`/`end`, not `lower`/`upper`).

**Open question resolved:** whether `TimeWindow` should also own a display
formatter (e.g. `TimeWindow.format_local(tz)`) so `reservations/admin.py:24` and
the four templates stop each choosing their own `strftime`/`|date:` pattern.
Per psycopg/Django's own contract, `Range.lower`/`.upper` are plain `datetime`
objects with no formatting opinion, and this project already renders the *same*
window two different ways (admin: `"%Y-%m-%d %H:%M %Z"` with `timezone.localtime`;
templates: Django's `|date:"Y-m-d H:i"` filter, no explicit localization). That
inconsistency predates this refactor and is not caused by the `Range` leak, so
the decision is: keep formatting at the call site (admin vs. template each render
their own way, as today) and encode only the value-object + codec in the ACL —
do not fold display formatting into `TimeWindow`, since doing so would just move
a *different*, unrelated inconsistency into the domain layer rather than fixing
it.

## Step 6 — Verification and phased plan

**Success criterion:** `grep -rn "psycopg" --include="*.py" accounts catalog
reservations envbooker | grep -v migrations` returns matches only inside
`reservations/timewindow.py` (plus, if `Range[datetime]` is kept as the internal
type alias in the codec's own annotations, nowhere else). No template, view,
form, admin, or cross-app service module may match.

**Files that know the dependency today → files that will still know it after:**

| File | Knows `psycopg`/`Range` today? | Knows it after refactor? |
|---|---|---|
| `reservations/timewindow.py` (new) | — | Yes — this is the ACL |
| `reservations/models.py` | Yes (`DateTimeRangeField`, `RangeOperators`) | Yes, unchanged — legitimate persistence-field declaration |
| `reservations/forms.py` | Yes | No |
| `catalog/services.py` | Yes | No |
| `reservations/services.py` | Yes | No (except delegating to `_codec` inside `overlapping`/`covering_instant`, which live beside the codec) |
| `reservations/views.py` | Yes (transitively, via `cleaned_data["during"]`) | No |
| `reservations/admin.py` | Yes | No |
| 4 templates | Yes | No |
| `catalog/tests.py`, `reservations/tests/_helpers.py`, `reservations/tests/test_models.py` | Yes | Follow-on (see Phase 5) — should move to `TimeWindow` fixtures for consistency, but is not required for the grep criterion to pass since tests were excluded from the criterion's scope by convention (`--include="*.py" ... | grep -v migrations` still includes tests; if the criterion is meant to be pure, add `| grep -v /tests/ | grep -v tests.py` and track test-fixture migration as an explicit, separate phase rather than silently exempting it) |

**Phased plan** (test-first, matching this project's existing discipline — see
`02-invariant-aggregate-refactor.md`'s phased plan for the established pattern):

- **Phase 1 (test-first).** Add unit tests for `TimeWindow` and `PsycopgRangeCodec`
  in isolation (`overlaps`, `contains_instant`, `has_started_by`, `is_over_by`,
  round-trip `encode`→`decode`) — no Django test client needed, pure Python.
- **Phase 2.** Implement `reservations/timewindow.py` (`TimeWindow`, `RangeCodec`
  protocol, `PsycopgRangeCodec`, module-level `_codec`); add `Reservation.window`
  property and `Reservation.set_window()` to `reservations/models.py`; add
  `overlapping`/`covering_instant` to `reservations/services.py`; change
  `describe_overlap_conflict`'s signature to accept `TimeWindow`.
- **Phase 3.** Migrate `reservations/forms.py` and `catalog/services.py` off
  direct `Range` construction onto `TimeWindow`; migrate `reservations/views.py`
  and `reservations/admin.py` off `.during.lower`/`.upper` onto `.window.start`/
  `.end`. Run the full `catalog`/`reservations` suite after each file — this
  phase touches every call site enumerated in Step 1's table, so regressions are
  cheap to isolate one file at a time.
- **Phase 4.** Migrate the four templates (`environment_form.html`,
  `environment_confirm_delete.html`, `_environment_row.html`,
  `_reservation_item.html`) from `.during.lower`/`.upper` to `.window.start`/
  `.end`; visually diff rendered output (same `datetime` values, same filters) to
  confirm the display is byte-identical.
- **Phase 5.** Run the grep success criterion from this step; migrate
  `catalog/tests.py`, `reservations/tests/_helpers.py`,
  `reservations/tests/test_models.py` fixtures from `Range(...)` to
  `TimeWindow(...)` (via `Reservation.objects.create(...)` +
  `reservation.set_window(...)`, or a small test-only factory), so the only
  `psycopg` import left in the entire tree is inside `reservations/timewindow.py`.
- **Phase 6.** Full regression: `uv run python manage.py test`; `uv run mypy .`
  (the `[tool.mypy.overrides]` block in `pyproject.toml:26-38` already enforces
  `disallow_untyped_defs` on `reservations.services`, `reservations.views`,
  `reservations.forms` — the new `TimeWindow`-typed signatures must satisfy that
  gate without new `type: ignore` comments).

## Summary

The worst leaking dependency in EnvBooker is `psycopg.types.range.Range`, which is
directly imported and constructed in five production modules — `reservations/forms.py`,
`catalog/services.py`, `reservations/services.py`, `reservations/views.py`,
`reservations/admin.py` — and read via raw `.lower`/`.upper` attribute access in
four HTML templates, spanning every architectural layer the app has: persistence,
input boundary, domain services (including a bare `Range[datetime]` parameter on a
public domain function, `describe_overlap_conflict`), views, admin, and
presentation. Unlike a typical ACL scenario, no foundation document declares intent
to keep this dependency swappable — `envbooker/settings.py:102-112` explicitly
commits the project to Postgres permanently — so the case for isolation rests
entirely on the duplication (the same `Range(start, end, "[)")` construction is
hand-written four separate times) and the depth of the boundary crossing (template
code reading a DB-driver's internal attribute names), not on future
replaceability. The proposed fix introduces a domain value object `TimeWindow`
(`start`, `end`, plus `overlaps`/`contains_instant`/`has_started_by`/`is_over_by`),
a narrow `RangeCodec` port, and a `PsycopgRangeCodec` adapter that is the only
module allowed to import `psycopg`; `Reservation` gains a `.window` property and
`.set_window()` method so the model itself is the single persistence-mapping seam.
After the refactor, a `psycopg` grep across the tree returns exactly one file
(`reservations/timewindow.py`, plus the unavoidable `DateTimeRangeField`
declaration in `reservations/models.py`), and the presentation layer renders
`window.start`/`window.end` — names that match the project's own Ubiquitous
Language for `during` — instead of a driver's internal vocabulary. The phased,
test-first plan migrates one layer at a time (value object → model seam → services
→ views/admin → templates → test fixtures) so each phase's regression surface stays
small and independently verifiable against the existing `catalog`/`reservations`
test suites.
