---
project: envbooker
researched_at: 2026-05-26
recommended_platform: railway
runner_up: render
context_type: mvp
tech_stack:
  language: python
  framework: django
  runtime: python-3.14
---

## Recommendation

**Deploy on Railway.**

Railway is the strongest fit for a Django 6.0.5 / Python 3.14 / uv stack on a solo, cost-sensitive, 3-week after-hours timeline. The Railpack builder auto-detects `uv.lock` and reads `.python-version` (which uv already maintains), so the project deploys without a hand-written Dockerfile — a real advantage over Fly.io and Render, both of which require Dockerfile authoring for Python 3.14 today. The 30-day Free Trial credit ($5, no card) realistically covers the entire 10xDevs M1–M5 cohort window (2026-05-18 → 2026-06-15) for an always-on Django + Postgres MVP at low QPS, after which the project either moves to the Hobby plan ($5/mo subscription with $5 usage credit) or is torn down. Managed Postgres is co-located on the same private network at near-zero added latency, matching the "co-location preferred" interview answer.

Render came in a close second on the agent-friendliness scorecard (Render MCP went GA in August 2025; Railway's MCP is still beta), but a Django+Postgres always-on setup on Render costs $14/mo from day one (Starter web $7 + Starter Postgres $7) with no free-trial equivalent suitable for a course project. Fly.io, despite being the original `tech-stack.md` default, was the weakest of the three: Managed Postgres has a ~$38/mo floor, the auto-generator doesn't handle uv, unmanaged Fly Postgres is officially deprecated, and `fly mcp` is self-described as "experimental demoware".

## Platform Comparison

**Hard filter applied:** Cloudflare Workers, Vercel, and Netlify were dropped before scoring. Django on Python 3.14 needs a long-running WSGI/ASGI process talking to a relational database; Cloudflare Workers (V8 isolates, JS/TS), Vercel serverless functions (10s / 250MB execution limits, Django not idiomatic), and Netlify Functions (JS-first serverless shell) all fail this constraint structurally — no amount of weight tuning rescues them.

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration | Result |
|---|---|---|---|---|---|---|
| Cloudflare Workers | — | — | — | — | — | **Dropped** — no Python WSGI/ASGI runtime |
| Vercel | — | — | — | — | — | **Dropped** — serverless funcs, Django not idiomatic |
| Netlify | — | — | — | — | — | **Dropped** — JS-first serverless funcs |
| **Railway** | Pass | **Pass** | Pass | Pass | Partial | **4 Pass + 1 Partial** |
| **Render** | Pass | Pass | Pass | Pass | **Pass** | **5 Pass** |
| **Fly.io** | Pass | Partial | Partial | Pass | Partial | **2 Pass + 3 Partial** |

**Soft weights applied** (cost-min, single region, no familiarity, co-location preferred): cost preference penalises Fly.io heavily (Managed Postgres floor ~$38/mo); co-location preference is satisfied by all three; familiarity tie-break does not fire. Render edges Railway on raw scorecard because Render's MCP is GA, but Railway wins on cost-fit (free trial covers the course window) and on "managed" depth (Railpack auto-detects uv → no Dockerfile to maintain). The user selected Railway after reviewing the anti-bias cross-check on Render.

### Shortlisted Platforms

#### 1. Railway (Recommended)

Won on the combination of agent-friendly score (4/5 Pass) and the practical match to a solo cost-sensitive course project. Railpack autodetect for uv is unique among the three — Render and Fly both require Dockerfile authoring for Python 3.14 today. Managed Postgres, Redis, and Volumes are GA and live on the same private network. Both local and Remote MCP servers exist (`mcp.railway.com`, OAuth-backed) but are explicitly "a work in progress" as of 2026-05-26, so treat MCP as opportunistic and operate via the `railway` CLI for now. The 30-day trial credit covers an always-on Django+Postgres MVP for roughly one calendar month at low QPS, after which the project transitions to the Hobby plan ($5/mo, $5 usage credit included, realistic monthly bill $10–18).

#### 2. Render

Best raw agent-friendliness score (5/5 Pass) — the only platform in this matrix with a GA MCP server (Aug 2025, 20+ tools, hosted at `mcp.render.com/mcp`) and the cleanest `llms.txt` + `llms-full.txt` story. Lost to Railway on the course-project economics: $14/mo always-on floor (Starter web $7 + Starter Postgres $7) with no trial-credit equivalent, and Python 3.14 not yet on Render's native Python runtime → Dockerfile authoring is mandatory, negating the "auto-detect uv.lock" advantage for this specific project. Strong runner-up: if Railway's MCP beta proves frustrating or the trial economics shift, Render is the platform to swap to.

#### 3. Fly.io

Despite being the `tech-stack.md` default, Fly came third on substance. Managed Postgres (MPG) has a Basic-tier floor of ~$38/mo (shared-2x, 1 GB RAM, $0.28/GB storage), and the alternative — unmanaged Fly Postgres — is officially deprecated ("we are not able to provide support or guidance"). Python 3.14 + uv requires a hand-written Dockerfile because the official `dockerfile-django` generator targets Poetry/pip. `fly mcp` is shipped but explicitly "experimental demoware that is subject to change." Docs are on GitHub as markdown but no `llms.txt`. Strong infra fundamentals; wrong cost shape for a free/cheap course project.

## Anti-Bias Cross-Check: Railway

### Devil's Advocate — Weaknesses

1. **Railway's MCP servers (local + remote) are explicitly "a work in progress" / beta as of 2026-05-26.** The exact criterion that would have pushed Render to #1 is Railway's soft spot. Plan to operate via the `railway` CLI for now and treat the MCP as opportunistic.
2. **Usage-based pricing is unpredictable.** $20/vCPU-mo + $10/GB-mo + $0.10/GB egress means a runaway middleware, a memory leak, or a tight retry loop can produce real money before you notice. Render's $14/mo Starter is a known ceiling; Railway's is not.
3. **Railpack is still young.** Nixpacks moved to maintenance and Railpack took over as default; Python 3.14 (Oct 2025) detection edge cases may bite. Dockerfile fallback is the contingency, not the default plan.
4. **15-minute hard cap on WebSocket connections.** Not relevant to EnvBooker today (PRD says no realtime), but it locks the door on long-poll / SSE features later without explicit reconnection logic.
5. **Ephemeral filesystem by default.** Any feature that writes files (CSV export of reservations, generated audit logs) needs a Volume ($0.25/GB-mo) or `railway bucket` (which is beta) — a stealth cost vector if added carelessly.

### Pre-Mortem — How This Could Fail

The team picked Railway in May 2026 because Railpack auto-detected uv + Python 3.14 and the $5 trial felt low-stakes. By July EnvBooker had 80 daily users and a teammate shipped an "export reservations to CSV" feature that wrote temp files; the ephemeral filesystem deleted them on every restart and a user filed a P1 because their compliance export vanished mid-download. They migrated to `railway bucket`, but bucket was still beta — the SDK changed twice between July and October and they spent two evenings tracking a silent permissions regression. Meanwhile a Django middleware misconfiguration kept the DB connection pool larger than needed and the monthly usage bill drifted from $12 to $34; nobody had set a budget alert because Railway's billing dashboard doesn't push them by default. In September Railway rotated the MCP auth flow, breaking the team's Claude Code setup mid-deploy and taking staging offline for an evening. The cost story stayed cheaper than Fly would have been, but the operational story was rougher than Render — fewer guardrails, more moving parts still in flux.

### Unknown Unknowns

- **`${{Postgres.DATABASE_URL}}` template variables resolve at deploy time, not runtime.** Rotating the Postgres password through the dashboard won't propagate to the running service until the next deploy.
- **Railway "environments" are not Postgres branches.** Forking an environment forks variable refs, but the Postgres instance is shared by default. A real isolated staging DB means provisioning a second Postgres service explicitly.
- **Railpack pins Python via `.python-version` which uv writes as `3.14`** — Railpack may grab a later 3.14 patch than tested locally if the pin is loose. Pin to the patch (`3.14.x`) if reproducibility matters.
- **Hobby plan's $5/mo is a *credit floor*, not a hard ceiling.** Overuse rolls into pay-as-you-go silently; the project doesn't "stay at $5" if a misbehaving service eats the credit.
- **MCP tokens are workspace-scoped, not project-scoped.** Agent token compromise reaches every Railway project in the workspace — not just EnvBooker.

## Operational Story

How Railway actually operates for EnvBooker day to day. One concrete answer per axis.

- **Free-tier window (course-specific):** The 30-day Free Trial grants $5 of usage credit (no credit card) with same-features-as-Hobby during the window: 1 GB RAM ceiling, shared vCPU, up to 5 services per project, databases allowed. At EnvBooker's low-QPS profile a realistic monthly bill is $3–5, so the $5 credit covers approximately one full month of always-on Django+Postgres. **This window aligns with the 10xDevs M1–M5 cohort schedule (2026-05-18 → 2026-06-15).** After the trial expires (30 days OR $5 consumed, whichever first), the account reverts to the permanent Free plan with **$1/month credit, 0.5 GB RAM, 1 vCPU, 0.5 GB volume, 1 replica** — enough for one tiny idling service but **not enough for an always-on Django + Postgres setup**. The decision point at day 30: upgrade to Hobby ($5/mo subscription + $5 usage credit, realistic bill $10–18), or tear down the project. Stateful volumes are deleted 30 days after trial credit expiry if neither happens.
- **Preview deploys:** Railway's PR preview environments are GA on Hobby+. Branch deploys create isolated environments; Postgres is *not* automatically branched — provision a second Postgres service for staging if isolation matters. Fork PRs do not get previews without explicit token grants.
- **Secrets:** Project/service variables stored in Railway's vault; set via `railway variables set KEY=value` or the dashboard. Cross-service refs use `${{Postgres.DATABASE_URL}}` syntax. **Critical: move `DEBUG` and the insecure `SECRET_KEY` out of `envbooker/settings.py` to env vars before first deploy** — Railway will not warn you. Rotation: set the new value, redeploy (template vars resolve at deploy time, not runtime).
- **Rollback:** `railway redeploy --deployment <id>` to a prior deployment. Time-to-revert: 30–90 seconds depending on image cache. Caveat: this does NOT roll back DB migrations — destructive migrations require a separate restore plan.
- **Approval:** Destructive actions (delete Postgres service, delete project, change billing plan) are human-only via the dashboard. The agent may unattended: deploy, redeploy, tail logs, set non-sensitive env vars, run one-off commands. Production secret rotation and DB drops are panel-by-hand.
- **Logs:** Read-only via `railway logs` (runtime) and `railway logs --build` (build), with `-n <count>` for tail length. Both stream to stdout — agent-parseable. Filter by service/environment with `--service` and `--environment` flags.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Trial credit expires before MVP is feature-complete; project suspended | Operational story (free-tier window) | M | M | At day 21 of trial, decide: upgrade to Hobby ($5/mo) or accept teardown. Set a calendar reminder. Export volume data before day 30+30. |
| Permanent Free plan ($1/mo, 0.5 GB RAM) cannot run Django+Postgres always-on | Research finding | H (if relied on) | H | Treat Free plan as "tiny demo only". Plan for Hobby tier post-trial; budget $10–18/mo. |
| Runaway usage produces unexpected bill on Hobby (no default budget alerts) | Pre-mortem | M | M | Set an explicit usage alert on the Railway dashboard immediately after upgrading; add a per-service resource cap if possible. |
| Railway MCP auth/schema changes during course window break Claude Code integration | Devil's advocate / Pre-mortem | M | L | Don't rely on MCP for critical ops during the course; use `railway` CLI as the primary interface. Pin a known-working CLI version. |
| Python 3.14 detection regression in Railpack | Devil's advocate | L | M | Fallback Dockerfile committed but not active; switch builder to Dockerfile mode (`builder = "DOCKERFILE"` in railway.toml) if Railpack fails. |
| Ephemeral filesystem silently loses user-uploaded or generated files | Pre-mortem | M (if features added) | H | Any future feature touching disk must use a Volume or `railway bucket`. Add a lint/CI guard if uploads enter scope. |
| `STATIC_ROOT` directory missing on first deploy → `collectstatic` fails | Research finding (Django gotcha) | M | L | Bake `mkdir -p staticfiles && python manage.py collectstatic --noinput` into the start command; ensure WhiteNoise is in `MIDDLEWARE`. |
| Migrations run before health check; broken release leaves DB ahead of code | Unknown unknowns | L | H | Run `migrate` in the start command (not build); for destructive migrations, take a DB snapshot via `railway connect` first. |
| Workspace-scoped MCP token compromised → blast radius beyond EnvBooker | Unknown unknowns | L | M | Keep one Railway workspace per project for now; rotate the MCP token after the course window if it was ever exposed in chat. |
| `DEBUG=True` + insecure `SECRET_KEY` from starter ship to production | Research finding | M | H | Move both to env vars BEFORE first deploy; verify with `curl <prod-url>/__nonexistent__/` — DEBUG page must not appear. |
| Template variable `${{Postgres.DATABASE_URL}}` doesn't pick up password rotation until next deploy | Unknown unknowns | L | M | After any Postgres credential rotation, trigger `railway redeploy` explicitly. |

## Getting Started

Concrete first steps for EnvBooker specifically — not generic Railway onboarding. Validated against the project's pinned versions: Django 6.0.5, Python 3.14, uv (no pip in `.venv`).

1. **Install the Railway CLI** — `brew install railway` (macOS), or `curl -fsSL cli.new | sh`. Verify: `railway --version`.
2. **Sign up and start the trial** — `railway login` opens a browser; the $5 trial credit attaches automatically (no card).
3. **Move `DEBUG` and `SECRET_KEY` out of `envbooker/settings.py`** — read them from `os.environ` with no default for `SECRET_KEY` and `DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"`. This is non-negotiable before the first deploy (see CLAUDE.md tripwire).
4. **Add `ALLOWED_HOSTS = [os.environ["RAILWAY_PUBLIC_DOMAIN"], "localhost", "127.0.0.1"]`** to `settings.py` — Railway injects `RAILWAY_PUBLIC_DOMAIN` automatically.
5. **Add WhiteNoise** — `uv add whitenoise`, insert `whitenoise.middleware.WhiteNoiseMiddleware` directly after Django's `SecurityMiddleware`, set `STATIC_ROOT = BASE_DIR / "staticfiles"` and use the Django 6.0 `STORAGES` setting (not the deprecated `STATICFILES_STORAGE` key).
6. **Initialize the Railway project** — `railway init` in the repo root, accept the default project name (`envbooker`).
7. **Provision Postgres** — `railway add --database postgres`. Reference from the web service as `DATABASE_URL=${{Postgres.DATABASE_URL}}` (set via `railway variables set` or the dashboard).
8. **Configure the start command** — in Railway service settings (or `railway.toml`):
   `mkdir -p staticfiles && uv run python manage.py collectstatic --noinput && uv run python manage.py migrate && uv run gunicorn envbooker.wsgi --bind 0.0.0.0:$PORT`
9. **Deploy** — `railway up`. Watch logs with `railway logs --build` then `railway logs`. First deploy takes ~3–5 minutes.
10. **Create the admin user** — `railway run python manage.py createsuperuser` (runs locally with the production env injected; for a true in-container superuser use `railway ssh` then the same command).
11. **Set a budget alert** — Railway dashboard → project → Usage → Alerts. Set a soft alert at $4 (trial 80%) and a hard alert at $4.80.
12. **Mark the calendar for day 21 of trial** — decide upgrade-to-Hobby vs teardown by then.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration (only mentioned as a Railpack fallback; not designed).
- CI/CD pipeline setup beyond the auto-deploy-on-merge default (GitHub Actions wiring is the next module's concern).
- Production-scale architecture: multi-region failover, HA Postgres, read replicas, dedicated support tiers.
- Custom domain configuration (project will use the auto-assigned `<project>.up.railway.app` URL for the course window).
