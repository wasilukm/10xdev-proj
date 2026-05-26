# First Deployment Plan — EnvBooker → Railway

## Context

EnvBooker is a Django 6.0.5 / Python 3.14 / uv project, currently a bare `django-admin startproject` scaffold with no production hardening: `DEBUG=True`, the insecure default `SECRET_KEY` in source, empty `ALLOWED_HOSTS`, SQLite, no `STATIC_ROOT`, no env-var integration, no `gunicorn` / `whitenoise` / `psycopg` / `dj-database-url` in `pyproject.toml`. `context/foundation/infrastructure.md` selected **Railway** with Railpack auto-detection of `uv.lock` + `.python-version`. There is no git remote, no `Dockerfile`, no `railway.toml`, no existing Railway project.

This plan executes the first production deploy: local code prep → Railway provisioning → `railway up` → smoke verification → guardrails. The end-state is an always-on Django + Postgres service reachable on `<project>.up.railway.app` with `/admin/` working, `DEBUG=False`, and budget alerts in place.

The plan itself is the audit artifact: after acceptance it is copied to `context/deployment/deploy-plan.md` per the Lesson 5 hand-off contract in `CLAUDE.md`.

## Ownership legend

- **[Agent]** — Claude executes via tools (Bash / Edit / Write).
- **[Human]** — Mariusz performs the step (browser login, dashboard click, credential paste).
- **[Mixed]** — Human action triggers it (e.g. paste a secret) and the agent runs the follow-up command.

Each step is a checkbox. Mark `[x]` as it completes during execution.

## External integrations involved

These are touchpoints where state lives outside this repo and where a mistake costs more than a re-run:

1. **Railway account** — created via browser, holds billing, MCP tokens are workspace-scoped (risk: blast radius beyond EnvBooker).
2. **Railway-managed Postgres** — credentials surfaced as `${{Postgres.DATABASE_URL}}`; resolves at **deploy time**, not runtime (any password rotation requires `railway redeploy`).
3. **GitHub** — not used for deploy trigger (CLI `railway up` from local working tree per accepted choice); only relevant when linking later.
4. **Railpack builder** — third-party (Railway) build pipeline, not part of this repo; Python 3.14 detection is new enough that a Dockerfile fallback is a documented contingency.
5. **`RAILWAY_PUBLIC_DOMAIN`** — env var injected by Railway at runtime; `ALLOWED_HOSTS` must read it, otherwise every request returns `Bad Request (400)`.

---

## Phase A — Local code prep [Agent]

Goal: make the repo deployable without changing app behaviour. All Phase A steps run locally; nothing touches Railway yet.

- [ ] **A.1 Add production dependencies via uv.**
  `uv add gunicorn whitenoise 'psycopg[binary]' dj-database-url`
  Why `psycopg[binary]`: ships with prebuilt wheels — no need for PostgreSQL headers in the build image. Why `dj-database-url`: one-line parser for the Railway-supplied `DATABASE_URL`.

- [ ] **A.2 Refactor `envbooker/settings.py`** (single critical file). Required edits:
  - `SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]` (no default — fail-fast if missing).
  - `DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"`.
  - `ALLOWED_HOSTS = [os.environ["RAILWAY_PUBLIC_DOMAIN"]] if "RAILWAY_PUBLIC_DOMAIN" in os.environ else ["localhost", "127.0.0.1"]`.
  - `CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]` — required for `/admin/` POSTs over HTTPS.
  - Replace `DATABASES` with `dj_database_url.config(default=f"sqlite:///{BASE_DIR}/db.sqlite3", conn_max_age=600)`.
  - Add `STATIC_ROOT = BASE_DIR / "staticfiles"`.
  - Insert `whitenoise.middleware.WhiteNoiseMiddleware` immediately **after** `django.middleware.security.SecurityMiddleware` (order matters).
  - Add the **Django 6.0 `STORAGES` setting** (not the deprecated `STATICFILES_STORAGE` key):
    ```python
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    ```
  - `import os` and `import dj_database_url` at the top.

- [ ] **A.3 Write `railway.toml`** at repo root:
  ```toml
  [build]
  builder = "RAILPACK"

  [deploy]
  startCommand = "mkdir -p staticfiles && uv run python manage.py collectstatic --noinput && uv run python manage.py migrate --noinput && uv run gunicorn envbooker.wsgi --bind 0.0.0.0:$PORT --workers 2 --access-logfile -"
  restartPolicyType = "ON_FAILURE"
  ```
  Notes: `migrate` runs in the start command, not in build — Railpack build has no DB access. `--workers 2` is conservative for 1 GB RAM trial; raise only after measuring.

- [ ] **A.4 Local smoke test with prod-shaped env.** From the repo root:
  ```bash
  DJANGO_SECRET_KEY=local-test DJANGO_DEBUG=False \
    uv run python manage.py collectstatic --noinput
  DJANGO_SECRET_KEY=local-test DJANGO_DEBUG=False \
    uv run python manage.py check --deploy
  ```
  `check --deploy` flags any remaining SECURE_* / SESSION_COOKIE_SECURE warnings before Railway sees them. Failures here are cheaper than failures over the wire.

- [ ] **A.5 Add `.env` and `staticfiles/` to `.gitignore`** (create `.gitignore` if absent — it is not in the current tree).

- [ ] **A.6 Commit.** `git add -A && git commit -m "prep: production settings, gunicorn, whitenoise, postgres driver"`. No push needed — first deploy is CLI-based.

---

## Phase B — Railway account & project provisioning

- [ ] **B.1 [Human] Install the Railway CLI** — `curl -fsSL cli.new | sh` (or `brew install railway` on macOS). Verify with `railway --version`.

- [ ] **B.2 [Human] `railway login`** — opens a browser; sign in with GitHub or email. The $5 / 30-day trial credit attaches automatically; no credit card required.

- [ ] **B.3 [Agent] `railway init`** in the repo root. Accept the default project name `envbooker` (or use `--name envbooker`). This creates a Railway project and writes `.railway/` metadata locally — do NOT commit `.railway/` (add to `.gitignore`).

- [ ] **B.4 [Agent] Provision Postgres.** `railway add --database postgres`. Wait for the service to be `Active` (`railway status`).

- [ ] **B.5 [Mixed] Configure env vars on the web service.** Generate a strong secret with `python -c "import secrets; print(secrets.token_urlsafe(64))"` — **[Human] paste it once**, then [Agent] runs:
  ```bash
  railway variables set DJANGO_SECRET_KEY=<pasted-value>
  railway variables set DJANGO_DEBUG=False
  railway variables set DATABASE_URL='${{Postgres.DATABASE_URL}}'
  ```
  Note the literal `${{ }}` template syntax — those braces must be passed through to Railway, not expanded by the local shell. Single-quote on bash; on PowerShell wrap in `'…'` too.

---

## Phase C — First deploy [Agent]

- [ ] **C.1 `railway up`.** Pushes the local working tree as a build context, Railpack runs, image is built and deployed. First build typically 3–5 minutes; subsequent deploys faster due to layer caching.

- [ ] **C.2 Watch the build.** `railway logs --build` (Ctrl-C once it shows "build complete"), then `railway logs` for runtime. Expect: `collectstatic` → `migrate` → `gunicorn` listening on `$PORT`.

- [ ] **C.3 Smoke test the public URL.** `railway open` (or read `railway status` for the domain). Hit `/admin/` — Django login page should render with hashed static URLs (WhiteNoise manifest active).

- [ ] **C.4 DEBUG-off verification.** `curl -s -o /dev/null -w "%{http_code}\n" https://<project>.up.railway.app/__definitely_missing__/` — must return `404`, **not** the yellow Django debug page. If the debug page appears, `DJANGO_DEBUG` was set wrong; re-run B.5 and redeploy.

---

## Phase D — Post-deploy hardening

- [x] **D.1 [Agent] Create the superuser.** `railway run uv run python manage.py createsuperuser` runs the command locally with the production env injected (incl. `DATABASE_URL`), so the user lands in the Railway Postgres. For an in-container shell instead: `railway ssh` then the same command.

- [x] **D.2 [Human] Log in to `/admin/`** with the new credentials. Visual confirmation the DB write path works end-to-end.

- [~] **D.3 [Human] Set budget alerts.** Railway dashboard → project → Usage → Alerts. Soft alert at **$4** (80% of trial), hard alert at **$4.80**. This is the single biggest mitigation for the pre-mortem "bill silently drifted from $12 to $34" scenario.
  **Execution finding (2026-05-26):** Budget alerts are gated behind the **Hobby plan** — the Free Trial does NOT expose Usage → Alerts. Deferred until the project upgrades. Interim mitigation: the $5 trial credit itself acts as a hard cap (service suspends, doesn't overcharge), and the pre-mortem "drift" scenario only applies *after* upgrading to Hobby where pay-as-you-go kicks in. Set the alerts as the **first action on the day of the Hobby upgrade**.

- [x] **D.4 [Human] Mark the calendar.** Day 21 of trial = ~2026-06-16 (trial started ≈2026-05-26): decide upgrade-to-Hobby vs teardown. Per `infrastructure.md` risk register row 1.

- [x] **D.5 [Agent] Save the approved plan.** Copy this file's content to `context/deployment/deploy-plan.md` (create the `context/deployment/` directory first). This file becomes the lesson hand-off audit trail.

---

## Edge cases and extra support steps

Triggered only if a specific symptom shows up. Each block names the failure shape and the fix.

### E1 — Railpack fails to detect Python 3.14
**Symptom:** build log says "no Python version detected" or installs 3.13.
**Fix:** confirm `.python-version` reads `3.14` (not `3.14.x`). If still failing, switch to a Dockerfile fallback — add `builder = "DOCKERFILE"` to `[build]` in `railway.toml` and commit BOTH a `Dockerfile` AND a `.dockerignore` (the latter prevents bloating the build context with local-only state, which would also defeat layer caching by invalidating the `COPY . .` step every time `db.sqlite3` or `staticfiles/` change locally).

**`Dockerfile`** (minimal, repo root):
```dockerfile
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
CMD mkdir -p staticfiles && python manage.py collectstatic --noinput && python manage.py migrate --noinput && gunicorn envbooker.wsgi --bind 0.0.0.0:$PORT
```

**`.dockerignore`** (repo root) — exclude everything that's local-only, build-time-generated, or sensitive:
```
.git
.gitignore
.venv
__pycache__
*.pyc
*.pyo
.python-version.local
db.sqlite3
db.sqlite3-journal
staticfiles
.railway
.env
.env.*
!.env.example
.idea
.vscode
.pytest_cache
.mypy_cache
.ruff_cache
context
.claude
*.md
!README.md
```
Notes: `.venv` is excluded because `uv sync` rebuilds it inside the image (host venv would be Linux-incompatible if you're on macOS). `db.sqlite3` is excluded so the local dev DB never accidentally ships to prod. `context/` and `.claude/` are course/agent metadata, not runtime artifacts. Keep `README.md` whitelisted in case any tooling reads it at import time; exclude other markdown to shrink the context.

Then `railway up` again. This is the contingency in `infrastructure.md` risk register row 5.

### E2 — `DisallowedHost` 400 on every request
**Symptom:** Railway URL returns `Bad Request (400)`, logs show `DisallowedHost at /`.
**Fix:** `RAILWAY_PUBLIC_DOMAIN` is not being read. `railway variables` to confirm it's set; if absent (rare), hardcode the assigned host into `ALLOWED_HOSTS` temporarily and file as a bug.

### E3 — `collectstatic` fails: `STATIC_ROOT` missing
**Symptom:** start command exits with "the STATIC_ROOT setting must be set".
**Fix:** A.2 was incomplete. Verify `STATIC_ROOT = BASE_DIR / "staticfiles"` is in settings; the `mkdir -p staticfiles` in the start command only creates the directory, it doesn't compensate for a missing Python setting.

### E4 — Migrations fail mid-deploy
**Symptom:** `migrate` exits non-zero; gunicorn never starts; deploy goes red but DB may have partial state.
**Fix:** **do not** redeploy blindly. Run `railway connect Postgres` to inspect schema, identify the failing migration, fix the model or migration locally, commit, then `railway up`. For destructive migrations specifically, snapshot first: in the Railway dashboard → Postgres → Backups → create on-demand.

### E5 — Postgres password rotation didn't take effect
**Symptom:** app keeps using old creds after rotation.
**Fix:** `${{Postgres.DATABASE_URL}}` resolves at **deploy time**, not runtime (Unknown Unknown #1 in `infrastructure.md`). Run `railway redeploy` after any credential rotation.

### E6 — uv `pip` tripwire (from `CLAUDE.md` lessons)
**Symptom:** any step that calls `pip` directly fails with "No module named pip".
**Fix:** the uv-managed `.venv` has no `pip`. Use `uv run <command>` or `uv pip <command>`. The start command in A.3 already wraps everything in `uv run`.

### E7 — Runaway usage alarm
**Symptom:** trial credit burning faster than the projected $3–5/mo.
**Fix:** `railway logs --service envbooker` to find the loop; `railway down` (stops the service, preserves data) buys time to diagnose. Default culprits per pre-mortem: oversized DB connection pool, retry loops, debug-level logging in prod.

### E8 — `gunicorn` workers OOM on 1 GB RAM
**Symptom:** workers killed with signal 9, frequent restarts.
**Fix:** lower `--workers 2` to `--workers 1` in `railway.toml` start command, or upgrade Hobby plan early. Django + 2 workers on 1 GB is tight if any view loads large querysets.

---

## Verification (end-to-end)

After Phase D completes the following must all be green. If any one fails, the deploy is not done.

1. `curl -s -o /dev/null -w "%{http_code}\n" https://<app>.up.railway.app/admin/login/` → `200`.
2. `curl -s https://<app>.up.railway.app/__missing__/ | grep -ci "DEBUG = True"` → `0` (no debug page leaking).
3. Browser login to `/admin/` with superuser → reaches the admin index.
4. `railway logs --service envbooker -n 50` shows gunicorn `Listening at: http://0.0.0.0:$PORT`, no tracebacks since boot.
5. `railway variables` lists `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DATABASE_URL` (template ref).
6. ~~Railway dashboard → Usage → Alerts shows two alerts ($4 soft, $4.80 hard).~~ **Deferred (2026-05-26): alerts UI is gated behind the Hobby plan; not available on Free Trial.** Revisit on the day of Hobby upgrade.
7. `context/deployment/deploy-plan.md` exists and matches this file.

## Critical files (modify or create)

- `envbooker/settings.py` — refactor per A.2.
- `pyproject.toml` / `uv.lock` — new deps via `uv add` (A.1).
- `railway.toml` — **new**, A.3.
- `.gitignore` — **new**, A.5 (include `.env`, `staticfiles/`, `.railway/`).
- `Dockerfile` + `.dockerignore` — **conditional**, only if E1 fires (both must land together).
- `context/deployment/deploy-plan.md` — **new**, D.5 (copy of this file).

---

## Execution log — 2026-05-26

First deploy executed in a single session. All checkboxes in Phases A, B, C, D resolved (D.3 deferred — see below). Repo commit kicking off the deploy: `e747758` ("prep envbooker for first Railway deploy").

### Live state

| Item | Value |
|---|---|
| Public URL | https://envbooker-production.up.railway.app |
| Project ID | `1245af82-f8db-4c8e-a209-111e3ea56c12` |
| Environment | `production` (`7781f08e-17ab-4e22-8184-8d4393eb8489`) |
| Web service | `envbooker` (`b4126d36-fc99-4eb2-ad39-31c493087e86`) |
| Database service | `Postgres` (`adfaa199-963c-462d-bce0-b1c0cf87813d`) |
| Internal Postgres host | `postgres.railway.internal:5432/railway` |
| Builder used | `RAILPACK` (auto-detected Python 3.14.5 + uv — Dockerfile fallback NOT needed) |
| Deploy time | ~3 minutes (build) + ~30s (migrate + boot) |

### Deviations from the plan

1. **B.3 `railway init` auto-linked the cwd to the Postgres service** after B.4, leaving no web service to deploy to. Fix: explicit `railway add --service envbooker` then `railway service link envbooker` before B.5. **Plan update suggested for next time:** insert "B.3a — `railway add --service envbooker` + `railway service link envbooker`" before B.4 to avoid the auto-link ambiguity.
2. **`RAILWAY_PUBLIC_DOMAIN` is not auto-injected** until a domain is generated. The plan assumed it would be present. Fix added: `railway domain --service envbooker --json` between B.5 and C.1. Without this, `ALLOWED_HOSTS` would fall back to `["localhost", "127.0.0.1"]` and every request would 400.
3. **D.3 budget alerts not available on Free Trial.** Documented inline in D.3 and in the verification checklist. Defer to Hobby upgrade.
4. **`railway login` requires a real TTY** — the `curl … | sh` installer also failed its PATH-update step under `dash` ("bad substitution"). Workarounds: symlink `~/.railway/bin/railway` into `~/.local/bin`, and run `railway login` from a real interactive terminal (not from a non-interactive subshell). Worth surfacing if this plan is reused on a fresh machine.
5. **D.1 `createsuperuser` doesn't work via `railway run` in a non-interactive shell** — solved with `railway ssh` (gives a real TTY inside the running container, with venv and `DATABASE_URL` already set up).

### Verification results

| # | Check | Result |
|---|---|---|
| 1 | `/admin/login/` returns 200 | ✅ |
| 2 | `/__missing__/` shows no DEBUG page | ✅ (`grep -ci "DEBUG = True"` → 0) |
| 3 | Browser login to `/admin/` | ✅ (user-confirmed) |
| 4 | gunicorn boot logs clean | ✅ |
| 5 | `railway variables` lists DJANGO_SECRET_KEY / DJANGO_DEBUG=False / DATABASE_URL | ✅ |
| 6 | Budget alerts in dashboard | ⏸ Deferred — Hobby-only feature |
| 7 | `context/deployment/deploy-plan.md` exists | ✅ |

Additional confirmed: WhiteNoise manifest active (`base.428a30193bdc.css` served HTTP 200 from `/static/admin/css/...`), HTTPS redirect live (HTTP → 301 → HTTPS, HSTS header set per `SECURE_HSTS_SECONDS = 3600`).
