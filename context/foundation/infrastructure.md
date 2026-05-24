---
project: envbooker
researched_at: 2026-05-24
recommended_platform: fly.io
runner_up: railway
context_type: mvp
tech_stack:
  language: python
  framework: django
  runtime: python-3.14
---

## Recommendation

**Deploy on Fly.io.**

Fly.io scores 5/5 on the agent-friendly criteria, is the only candidate with a first-party MCP server (`superfly/flymcp`), and its per-second billing with auto-suspend keeps idle cost near zero — the best match for EnvBooker's cost-sensitive, low-QPS, after-hours-MVP profile. Choosing Fly.io also validates the `tech-stack.md` default (`deployment_target: fly`) under deliberate scoring rather than letting it stand by inertia.

## Platform Comparison

Hard filter applied: **Cloudflare Workers, Vercel, and Netlify dropped** — their serverless function runtimes don't host a full Django app (ORM + admin + sessions) without significant hackery, and the PRD requires Django's auth/admin/migrations stack out-of-the-box. Three candidates survived to scoring.

| Platform | CLI-first | Managed | Agent docs | Deploy API | MCP integration | Score |
|---|---|---|---|---|---|---|
| Fly.io | Pass | Pass | Pass | Pass | Pass | **5/5** |
| Railway | Pass | Pass | Partial | Pass | Pass | **4.5/5** |
| Render | Partial | Pass | Partial | Partial | Fail | **2.5/5** |

### Shortlisted Platforms

#### 1. Fly.io (Recommended)

`flyctl` covers the full operational loop (deploy, rollback, logs, secrets, volumes, scale). Docs are MDX in a public GitHub repo, so the agent can read source directly. `fly deploy` is deterministic with built-in release tracking and rollback. First-party `superfly/flymcp` MCP server wraps `flyctl` for Claude integration, and `fly mcp launch` is a one-command path for deploying MCP servers themselves. The pay-as-you-go model with auto-suspend means an idle EnvBooker can cost near $0 between work hours; an always-on small app + Postgres lands around $5-10/mo at MVP scale.

#### 2. Railway

Strong all-around platform with full `railway` CLI, Nixpacks auto-detection of Django, first-party MCP server, and predictable $5/mo Hobby billing (includes $5 in usage credit). The gap vs. Fly.io: no auto-suspend, so the flat $5 is paid even during quiet periods. Slightly weaker on docs format (markdown availability unclear). Would be the right choice if predictable billing matters more than idle savings.

#### 3. Render

Solid managed runtime, but the CLI is less complete than Fly's or Railway's — historically dashboard-first, and some operations still require the dashboard. No first-party MCP server. The free tier looks attractive at $0 but Postgres expires after 30 days (+14 day grace), which is a data-loss trap for any MVP with real users. Realistic paid path is ~$13/mo ($7 web + paid Postgres) — more expensive than either Fly or Railway at MVP scale, with worse agent integration.

## Anti-Bias Cross-Check: Fly.io

### Devil's Advocate — Weaknesses

1. **No default spending cap.** Pay-as-you-go means a buggy client polling the env list every second can quietly accumulate egress charges until the credit-card statement arrives. The user must opt into spending limits manually.
2. **Auto-suspend cold start eats into the 30-second success-criterion budget.** First request after suspend = 100-500ms; for a first-time user landing on the dashboard, that's measurable against the PRD's 30-second find-and-reserve target.
3. **Postgres-on-Fly's "Managed" tier is still relatively new** vs. the legacy "Unmanaged" path. Picking the cheap unmanaged option means backups, replication, and failover are *your* responsibility — a footgun for a solo dev without ops experience.
4. **Trial is 2 VM-hours / 7 days** — the user will be paying within the first week, not after a month of evaluation.
5. **`flymcp` is a Fly project but the MCP ecosystem itself is moving fast** — no stability commitment yet on the wrapper.

### Pre-Mortem — How This Could Fail

Six months in, the EnvBooker team's Fly.io deployment has become a quiet disaster. The first pager came at midnight: the Postgres VM had filled its 1 GB volume and rejected new reservations. The team had picked the cheapest unmanaged Postgres tier without configuring automated backups, so recovery involved `fly volumes extend` followed by a frantic check of whether the last manual snapshot — three months stale — would survive. Around the same time, the Fly bill jumped from $8 to $47 in one month because an internal Slack bot polled the env list every second to "see what's free"; no spending cap was set, and egress charges accumulated silently. The team eventually moved to Railway, citing "predictable monthly cost" as the only reason — they'd never actually benefited from auto-suspend because the app was active enough during work hours to never sleep.

### Unknown Unknowns

- **`fly deploy` rebuilds the entire container image every time** unless BuildKit caching is configured. Without optimization, deploys take 2-5 minutes. Learn `--remote-only` and `release_command` for migrations early.
- **Fly Postgres uses pgBouncer in transaction mode by default.** Django features that rely on session state (advisory locks, named cursors, `LISTEN/NOTIFY`) don't work. For EnvBooker MVP this likely doesn't bite, but if reservation-overlap protection later moves to DB advisory locks, you'd hit it.
- **`fly secrets set` triggers a full app redeploy.** Setting a single env var causes a brief restart — useful for incident response planning.
- **Single-region Postgres has no automatic failover.** Regional outage = your app is down until Fly recovers. Multi-region requires explicit setup at significantly higher cost.
- **Logs on Fly are ephemeral.** `flyctl logs` is live-only; historical logs beyond ~24h need shipping to BetterStack / Logtail / etc. — your problem to set up.
- **Python 3.14 is fresh (Oct 2025 GA).** Fly supports any Python version via Dockerfile (`FROM python:3.14-slim`), but `fly launch`'s Django auto-detection may default to an older Python — verify the generated Dockerfile pins 3.14 before first deploy.
- **Future realtime calendar view (deferred by Q1)** would require Django Channels + Redis. Fly supports both (WebSockets natively, Upstash Redis via add-on or external), so no decision regret — but the day Channels lands, an ASGI server (Daphne/Uvicorn) replaces gunicorn and the Postgres pgBouncer caveat above becomes more relevant.

## Operational Story

- **Preview deploys**: Fly doesn't ship preview-deploys-on-PR out of the box. Use a GitHub Actions workflow that runs `flyctl deploy --app envbooker-pr-<num>` per PR with `--strategy=immediate`, and a teardown step on PR close. For solo dev MVP, skip until validated; deploy main branch only.
- **Secrets**: `fly secrets set KEY=value` writes to Fly's encrypted store; values are available as env vars at runtime. Rotation: `fly secrets set KEY=newvalue` triggers redeploy. `SECRET_KEY`, `DATABASE_URL`, and any org-email-domain config live here — *not* in `envbooker/settings.py` (which currently ships with `DEBUG=True` and an insecure default — see CLAUDE.md tripwires).
- **Rollback**: `fly releases` lists deploys; `fly deploy --image registry.fly.io/envbooker:deployment-<id>` rolls forward to a prior image. Database migrations do *not* roll back automatically — every migration that adds a column must remain backward-compatible across one release boundary.
- **Approval**: Human-only — `fly secrets unset` (could break the app), `fly postgres destroy`, `fly volumes destroy`, any change to the production cert / domain, spending-limit increases. Agent-OK — `fly deploy`, `fly status`, `fly logs`, `fly ssh console` (read-only commands).
- **Logs**: `fly logs -a envbooker` (live tail). For historical or structured search, plan to ship to BetterStack or similar — not configured at MVP, but in the risk register.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Unbounded spend from buggy client / scraper | Devil's advocate / Pre-mortem | M | M | Set Fly spending limit on day one (`Account → Billing → Spending Limit`); start at $25/mo, raise consciously |
| Postgres volume fills, rejects writes | Pre-mortem | M | H | Use Fly Managed Postgres (not legacy unmanaged); enable autoscaling volume or set CloudWatch-equivalent alert at 80% full |
| No automated DB backups on cheap-tier Postgres | Pre-mortem | M | H | Pick Fly Managed Postgres tier (includes automated snapshots) — do NOT save $2/mo by picking the unmanaged tier |
| Cold-start latency violates the 30-second PRD success criterion | Devil's advocate | L | M | Measure first-request latency after suspend; if >500ms, switch `auto_stop_machines` to `suspend` (faster wake) instead of `stop`, or set `min_machines_running = 1` (costs ~$2/mo more for always-on) |
| pgBouncer transaction mode breaks future advisory-lock use | Unknown unknowns | L | M | Document in CLAUDE.md tripwires; if Channels lands, route reservation-overlap check to a separate session-pooled connection or use SELECT FOR UPDATE instead of advisory locks |
| Trial expires before first deploy is fully working | Devil's advocate | M | L | Deploy a hello-world Django app on day one to start the clock with budget for iteration; don't wait until app is "ready" |
| Logs lost beyond 24h during an incident | Unknown unknowns | L | M | Ship logs to BetterStack from week one if compliance/debugging matters; otherwise accept and note in CLAUDE.md |
| Single-region outage takes app fully down | Unknown unknowns | L | M | Accepted for MVP per Q4 (single region is fine); revisit at production scale |

## Getting Started

Concrete first steps for EnvBooker (Django 6.0.5 / Python 3.14 / uv) on Fly.io:

1. **Install flyctl**: `curl -L https://fly.io/install.sh | sh` then `fly auth signup` (or `fly auth login`).
2. **Set a spending cap on day one**: dashboard → `Account → Billing → Spending Limit`. Start at $25/mo. Rationale: the #1 risk in the register.
3. **Write a Dockerfile manually** (don't let `fly launch` auto-generate it for a uv project — its default Python detection assumes pip/poetry). Skeleton: `FROM python:3.14-slim`; install uv via the official installer; `COPY pyproject.toml uv.lock ./` then `uv sync --frozen --no-dev`; copy app source; `CMD ["uv", "run", "gunicorn", "envbooker.wsgi:application", "--bind", "0.0.0.0:8000"]`.
4. **Run `fly launch --no-deploy`** to generate `fly.toml` (it'll detect the Dockerfile). Edit `fly.toml`: set `primary_region` (closest to your org), set `[deploy] release_command = "uv run python manage.py migrate"`, set `auto_stop_machines = "suspend"` and `min_machines_running = 0` for cost savings.
5. **Provision Managed Postgres** (NOT the legacy unmanaged tier): `fly mpg create --name envbooker-db --region <same-as-app>`. Then `fly mpg attach envbooker-db --app envbooker` to inject `DATABASE_URL` as a secret.
6. **Move `SECRET_KEY` and `DEBUG` out of `envbooker/settings.py`** (currently hardcoded — see CLAUDE.md tripwires) into env-var reads. Then: `fly secrets set SECRET_KEY="<generated>" DEBUG=False ALLOWED_HOSTS="envbooker.fly.dev"`.
7. **First deploy**: `fly deploy`. Verify `/admin/` loads. Tail logs with `fly logs`. Use `fly status` to confirm machine health.
8. **Optional, recommended**: install `superfly/flymcp` MCP server so future agent sessions can read deploy state, releases, and logs as structured tool calls instead of shelling out to `flyctl`.

## Out of Scope

The following were not evaluated in this research:
- Docker image optimization (multi-stage builds, BuildKit caching, image size)
- CI/CD pipeline setup (GitHub Actions workflow for auto-deploy on merge — the tech-stack.md hint exists but the pipeline is a separate concern)
- Production-scale architecture (multi-region failover, read replicas, HA, DR)
- Application Performance Monitoring (Sentry, Datadog, etc.)
- Custom domain + cert provisioning beyond the default `envbooker.fly.dev`

## Sources

- [Fly.io Pricing (official)](https://fly.io/pricing/)
- [Fly.io Resource Pricing docs](https://fly.io/docs/about/pricing/)
- [Fly.io Free Tier 2026 — what's left after the cuts](https://www.saaspricepulse.com/blog/flyio-free-tier-2026)
- [superfly/flymcp — MCP server for Fly.io CLI](https://github.com/superfly/flymcp)
- [Launching MCP Servers on Fly.io (Fly Blog)](https://fly.io/blog/mcp-launch/)
- [Railway Pricing (official)](https://railway.com/pricing)
- [Railway MCP Server docs](https://docs.railway.com/reference/mcp-server)
- [Railway vs. Fly (Railway docs)](https://docs.railway.com/platform/compare-to-fly)
- [Render Pricing (official)](https://render.com/pricing)
- [Render Postgres flexible plans / 30-day expiry](https://render.com/docs/postgresql-refresh)
- [How to Deploy MCP Servers: Vercel vs Railway vs Render vs Heroku vs Fly.io (2026)](https://mcpplaygroundonline.com/blog/deploy-mcp-server-vercel-railway-render-heroku-flyio)
