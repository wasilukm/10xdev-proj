<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: S-01 Org-restricted authentication

- **Plan**: context/changes/org-restricted-auth/plan.md
- **Scope**: Phases 1–3 of 3 (full plan)
- **Date**: 2026-05-31
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

Success criteria verified: `makemigrations --check --dry-run` → "No changes detected"; full suite `manage.py test` → 25 tests OK; all Progress checkboxes `[x]` with commit shas.

## Findings

### F1 — Email not canonicalized; case-variant duplicate accounts & login mismatch

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Safety & Quality
- **Location**: accounts/models.py:11,31 · accounts/forms.py:16-23 · accounts/tests.py:20-22
- **Detail**: `email = EmailField(unique=True)` is case-sensitive in Postgres. `normalize_email` lowercases only the domain; the signup form path (ModelForm.save) never calls `create_user`, so the address is stored verbatim including domain case, and `clean_email` lowercases the domain only for the membership check before `return email`. Result: `alice@x.com` and `Alice@x.com` are two distinct users (account confusion), and a user who signs up as `Bob@EXAMPLE.COM` cannot log in by typing `bob@example.com` (case-sensitive ModelBackend lookup). The domain restriction itself is NOT bypassable by case. tests.py:22 asserts the non-canonical result, locking in the behavior.
- **Fix**: Canonicalize email to lowercase on every write and make uniqueness case-insensitive: `clean_email` → `return email.lower()`; `create_user` → `email = self.normalize_email(email).lower()`; add `UniqueConstraint(Lower("email"))` (+ migration) or a case-insensitive auth backend, and lowercase the login identifier; update tests.py:22 to expect `alice@example.com`.
  - Strength: Removes the duplicate-identity class and login mismatch with one canonical rule across DB/manager/form.
  - Tradeoff: Touches model + manager + form + new migration + an existing test; functional unique index is Postgres-specific (fine — prod is Postgres).
  - Confidence: HIGH — code paths verified directly; signup bypasses normalize_email.
  - Blind spot: Existing prod rows with mixed-case emails not checked (likely none — fresh schema).
- **Decision**: FIXED — lowercased email in forms.clean_email + UserManager.create_user; added EmailAuthenticationForm (case-insensitive login) wired into LoginView; added UniqueConstraint(Lower("email")) via migration 0004; updated tests.py:22 + added test_login_is_case_insensitive. 26 tests green.

### F2 — AllowedEmailDomain accepts unvalidated domain strings

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: accounts/models.py:38-43 · accounts/forms.py:17
- **Detail**: `domain` is a free CharField, lowercased on save but otherwise unvalidated. An admin entering `@acme.com`, `acme.com/`, or stray whitespace creates a row that `clean_email`'s bare `email.split("@")[-1]` can never match — silently disabling sign-up for the intended domain with no feedback.
- **Fix**: Normalize/validate `domain` in `AllowedEmailDomain.clean()`/`save()` — strip whitespace, drop a leading `@`, validate it's a bare hostname.
- **Decision**: SKIPPED — trusting admins to enter bare hostnames for the MVP.

### F3 — Unplanned edits to catalog/tests.py and reservations/tests.py

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: catalog/tests.py:9 · reservations/tests.py:22
- **Detail**: Both changed `create_user(username=...)` → `create_user(email=...)` in the p3 commit. Not in the plan, but required: after `username` removal these would raise TypeError and plan criterion 3.3 (full suite green) is otherwise unachievable. Mechanical, no test logic changed — benign required fallout.
- **Fix**: None needed — accept as necessary side effect; optionally note in plan as an addendum for traceability.
- **Decision**: ACCEPTED — benign required fallout, no change.

### F4 — Manager doesn't enforce names that the form requires

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: accounts/models.py:8-26
- **Detail**: `REQUIRED_FIELDS` governs only the createsuperuser prompt. The form enforces first/last name but `create_user`/`create_superuser` accept nameless users. Inconsistency, not a hole; `get_full_name|default:user.email` handles the empty case.
- **Fix**: Either validate names in create_user, or document name-required as a form-only constraint.
- **Decision**: SKIPPED — form enforces names where it matters; acceptable for MVP.

### F5 — Tests hardcode URL paths instead of using reverse()

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: accounts/tests.py:2,101,143…
- **Detail**: `reverse` is imported (line 2) but unused; tests use literals like "/accounts/signup/". Brittle to URL changes. Several imports also live inside test methods rather than module top.
- **Fix**: Use `reverse("signup"|"login"|"logout")`; hoist method-level imports to module scope.
- **Decision**: SKIPPED — cosmetic test cleanup, deferred.

### F6 — Email unique=True added to an already-applied table (no guard)

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/migrations/0002_email_identity.py:24-28
- **Detail**: `AlterField(email → unique=True)` aborts if existing rows share an email or carry the old blank default. Plan acknowledges this and treats superuser recreation as manual; schema is fresh (F-01), so risk is low. Pairs with F1 (future case-insensitive index riskier if mixed-case dupes exist).
- **Fix**: Confirm target DB has no colliding/blank emails before deploy (covered by the plan's manual superuser-recreate step).
- **Decision**: ACCEPTED — already covered by the plan's manual superuser-recreate step. Note: migration 0004 (CI unique index) carries the same deploy precondition.
