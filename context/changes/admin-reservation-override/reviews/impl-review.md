<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Admin Reservation Override

- **Plan**: context/changes/admin-reservation-override/plan.md
- **Scope**: Phases 1–3 of 3 (full plan)
- **Date**: 2026-06-28
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 1 warning, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

Automated criteria: ruff check + format ✅, mypy ✅ (53 files), full test suite ✅ (110 tests, 1 skipped). All manual Progress boxes (1.5–3.7) checked.

## Findings

### F1 — Invalid-form admin inline edit corrupts the table row

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (reliability / DOM integrity)
- **Location**: reservations/views.py:186-187
- **Detail**: The Phase 3 row-marker branch was only added to the success path (views.py:209). The form-invalid early return runs first and ignores `_is_row_request`: it returns `_item_response` (`<div id="reservation-{pk}">`) even when the admin edits from the browse row, where the form's hx-target is `#env-row-{pk}` with `hx-swap="outerHTML"`. HTMX then replaces the whole `<tr>` with a bare `<div>` inside `<tbody>` — malformed table, row loses its badge/owner-time/booking cell until refresh. Reachable: ReservationEditForm rejects hours < 0.25, blank, non-numeric, or end-not-in-future (forms.py:80,102,107). No test covers invalid-form + row-marker.
- **Fix A ⭐ Recommended**: In the invalid-form branch, honor the row marker and re-render the whole row, threading the bound invalid form into the edited reservation's item context so the hours error still shows (let `_row_response`/`admin_row_items` accept an optional override form for the edited pk).
  - Strength: Keeps DOM well-formed AND preserves Phase 3 intent + validation feedback; consistent with success/conflict paths already routing through `_row_response`.
  - Tradeoff: Touches row-context plumbing (one extra param).
  - Confidence: HIGH — `build_reservation_item` already takes a `form` arg.
  - Blind spot: Confirm the row cell surfaces per-item `form.hours.errors` via the included partial.
- **Fix B**: In the invalid-form branch, when `_is_row_request`, return `_row_response(...)` without the per-item error.
  - Strength: One-line; keeps DOM valid.
  - Tradeoff: Silently drops the validation message — admin sees the row snap back with no explanation.
  - Confidence: HIGH — trivial branch.
  - Blind spot: UX regression vs. My Reservations edit, which shows the error.
- **Decision**: FIXED via Fix A — invalid-form branch now honors `_is_row_request` and re-renders the whole row, threading the bound form into the edited item via `admin_row_items(edit_pk=, edit_form=)` so the validation error still shows (reservations/views.py). Regression test added: `test_invalid_edit_with_row_marker_rerenders_row_with_error`.

### F2 — Staff-guard asymmetry between current and upcoming cells

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: templates/catalog/_environment_row.html:11,23
- **Detail**: The current-reservation cell guards on `{% if user.is_staff and current_item %}` while the upcoming cell guards on `{% if user.is_staff %}` alone. Harmless today (admin_row_items always pairs items with the staff flag) but reads as if one path was hardened and the other wasn't.
- **Fix**: No action required; optionally align the two guards for readability.
- **Decision**: SKIPPED — benign, no functional impact.
