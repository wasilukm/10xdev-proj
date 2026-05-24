---
bootstrapped_at: 2026-05-20T21:39:01Z
starter_id: django
starter_name: Django
project_name: envbooker
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit
---

## Hand-off

Verbatim copy of `context/foundation/tech-stack.md`:

```yaml
starter_id: django
package_manager: uv
project_name: envbooker
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
```

**Why this stack** (from hand-off body):

EnvBooker is a medium-scale web app a solo developer is shipping in 3 weeks of after-hours work: email/password auth restricted to an org domain, two roles (user vs admin), CRUD over an environment catalog, and a no-overlap reservation rule. Django is the recommended default for the `(web, python)` cell and ships an ORM, migrations, a built-in authentication and permissions system, and an admin UI — directly covering the auth, role-based access, and catalog-management requirements without bolt-on libraries, which matters under a tight after-hours timeline. It clears the convention-based, popular-in-training, and well-documented quality gates; explicit typing is the known Python-web caveat, mitigated downstream with type hints and model-level schemas. Bootstrapper confidence is verified, so scaffolding will be smooth. Deployment defaults to Fly.io (the choice was deferred, so the starter default was locked); CI runs on GitHub Actions with auto-deploy on merge — the standard solo-team shape. Only the auth feature flag is set; payments, realtime, AI, and background jobs are all out of scope per the PRD's non-goals.

## Pre-scaffold verification

| Signal       | Value                                          | Severity | Notes                                          |
| ------------ | ---------------------------------------------- | -------- | ---------------------------------------------- |
| npm package  | not run                                        | n/a      | non-JS starter; no npm CLI in cmd_template     |
| GitHub repo  | not run                                        | n/a      | card docs_url (docs.djangoproject.com) is not a GitHub repo — no recency signal available |

## Scaffold log

**Resolved invocation**: `django-admin startproject envbooker .`
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: manage.py, envbooker/__init__.py, envbooker/settings.py, envbooker/urls.py, envbooker/asgi.py, envbooker/wsgi.py
**Files written by CLI**: 6
**Pre-existing files preserved**: .claude, .git, CLAUDE.md, context, init-idea.md

Note: `{name}` was substituted with the project name (`envbooker`) rather than the literal `.` — `django-admin startproject` requires a valid Python identifier for the project name, and the cmd_template's literal trailing `.` already directs the CLI to scaffold into the current directory. Django 5.2.9 was used (installed globally; the starter card's `pre: pip install django` step is not executed by bootstrapper v1).

## Post-scaffold audit

**Tool**: pip-audit
**Status**: passed
**Command**: `uv export --no-hashes | grep -v '^#' | pip-audit -r /dev/stdin`
**Run date**: 2026-05-24
**Packages audited**: asgiref==3.11.1, django==6.0.5, sqlparse==0.5.5, tzdata==2026.2 (5 resolved)

```
No known vulnerabilities found
```

**Note**: uv-managed venvs do not include pip, so `PIPAPI_PYTHON_LOCATION` cannot be used. Dependencies were exported via `uv export` and piped to `pip-audit -r /dev/stdin` to audit the resolved lockfile tree.

## Hints recorded but not acted on

| Hint                    | Value               |
| ----------------------- | ------------------- |
| bootstrapper_confidence | verified            |
| quality_override        | false               |
| path_taken              | standard            |
| self_check_answers      | null                |
| team_size               | solo                |
| deployment_target       | fly                 |
| ci_provider             | github-actions      |
| ci_default_flow         | auto-deploy-on-merge |
| has_auth                | true                |
| has_payments            | false               |
| has_realtime            | false               |
| has_ai                  | false               |
| has_background_jobs     | false               |

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` is not needed — this directory is already a git repository.
- Declare Django as a project dependency so the environment is reproducible: `uv init` (creates `pyproject.toml`) then `uv add django`.
- Run the dependency audit once `pip-audit` is available: `uv tool install pip-audit` then `pip-audit`.
- `python manage.py migrate` then `python manage.py runserver` to confirm the scaffold runs.
- No `.scaffold` siblings were created — the scaffold wrote into the current directory with no file conflicts.
