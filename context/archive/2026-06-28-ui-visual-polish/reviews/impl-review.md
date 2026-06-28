<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: UI Visual Polish (S-07)

- **Plan**: context/changes/ui-visual-polish/plan.md
- **Scope**: All 3 phases (full plan)
- **Date**: 2026-06-28
- **Verdict**: APPROVED (with 2 documented-deviation warnings to acknowledge)
- **Findings**: 0 critical, 2 warnings, 4 observations

Automated criteria re-verified this run: 132 tests green (1 skipped); ruff clean;
no `.py` files changed (mypy gate trivially unaffected); collectstatic post-processes
`app.css` into the manifest (`app.f1eb174c09c8.css`).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Plan body contradicts the shipped implementation

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: context/changes/ui-visual-polish/plan.md:46-50, 170
- **Detail**: Two deviations are recorded in change.md but plan.md still asserts the opposite. "No markup restructure beyond adding class attributes" (plan.md:48-50) vs. the env table dropping Version/Owner columns (b166d76); "no JS added" (plan.md:170) vs. the vanilla-JS theme toggle + no-FOUC script (d607838, base.html:8-18,52-70). A future reviewer reading plan.md as ground truth would be misled.
- **Fix**: Append a short "## Addendum (2026-06-28)" to plan.md noting the two user-requested deviations, mirroring change.md.
- **Decision**: FIXED — addendum appended to plan.md

### F2 — Version/Owner columns dropped from the public browse table

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Scope Discipline
- **Location**: templates/catalog/_environment_results.html:7-14, templates/catalog/_environment_row.html
- **Detail**: The browse/reserve table no longer shows Version or Owner. Intentional and documented (b166d76, slim horizontal scroll); both remain on the admin Manage table (environment_manage.html:28,32). Open question is product: is losing at-a-glance Version on the browse page acceptable, given Version is part of an environment's identity?
- **Fix**: Confirm with product that Version need not appear on the browse table. If it should, restore it as a compact mono cell (.cell-mono pattern exists) rather than a full column.
- **Decision**: FIXED (differently) — Version + Owner restored as a hover `title` tooltip on the env name (`.env-name[title]`, _environment_row.html:2), with a dotted-underline "help" affordance. No new column / no horizontal scroll; browse queryset already select_related("owner") so no N+1.

### F3 — Dark theme overrides non-color tokens (shadows)

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: static/css/app.css:190-191, 217-218
- **Detail**: Plan contract (plan.md:64,91) says dark overrides ONLY --color-* tokens. Dark blocks also override --shadow-sm/--shadow-md. Harmless/arguably correct, but diverges from the stated contract.
- **Fix**: Relax the contract wording in plan.md to "--color-* and --shadow-*", or stop overriding shadows in dark.
- **Decision**: FIXED — plan.md contract wording (lines 63-64 and the Phase 1 contract) updated to include --shadow-*.

### F4 — Dark palette remap duplicated across two selector blocks

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: static/css/app.css:168-192 and 194-220
- **Detail**: The ~25-line token mapping is written twice (data-theme=dark and prefers-color-scheme). The --dark-* indirection avoids duplicating values, but the mapping block is copy-pasted: a token added to one block can be forgotten in the other.
- **Fix**: Share one declaration block across both selectors (`:root[data-theme="dark"], @media (prefers-color-scheme: dark) :root:not([data-theme="light"])`).
- **Decision**: FIXED (differently) — head script now resolves OS preference and always sets data-theme, so the duplicated `@media (prefers-color-scheme: dark)` block was deleted; `:root[data-theme="dark"]` is the single dark source. Removes ~26 duplicated lines. Trade-off: no-JS OS-dark no longer applies, acceptable since the app already hard-depends on JS (htmx booking flow). Verified: collectstatic + catalog tests green.

### F5 — Theme toggle doesn't expose its state to assistive tech

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: templates/base.html:41-42
- **Detail**: Toggle is a real <button> with aria-label, but never sets aria-pressed and the label doesn't change, so a screen-reader user can't tell the current theme. Low priority — cosmetic control.
- **Fix**: Toggle aria-pressed in the click handler (base.html:52-70) to reflect the active theme.
- **Decision**: SKIPPED

### F6 — Inline <script> blocks create a future CSP dependency

- **Severity**: 🔭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: templates/base.html:8-18, 52-70
- **Detail**: No CSP configured today, so the two inline scripts work and have no XSS surface (data-theme allow-listed; localStorage try/catch-guarded). If CSP is added later both blocks break without a nonce/hash. Head script must run inline pre-paint.
- **Fix**: Add a code comment noting the inline scripts will need a CSP nonce if a policy is introduced. No action now.
- **Decision**: FIXED — CSP-nonce note added as a template comment above the head script (base.html).

### Note

templates/home.html is listed in Phase 2 #3 but received no changes (just <h1>+<p> inheriting base styles) — a benign no-op, not a real gap.
