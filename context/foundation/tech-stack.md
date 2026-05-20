---
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
---

## Why this stack

EnvBooker is a medium-scale web app a solo developer is shipping in 3 weeks of after-hours work: email/password auth restricted to an org domain, two roles (user vs admin), CRUD over an environment catalog, and a no-overlap reservation rule. Django is the recommended default for the `(web, python)` cell and ships an ORM, migrations, a built-in authentication and permissions system, and an admin UI — directly covering the auth, role-based access, and catalog-management requirements without bolt-on libraries, which matters under a tight after-hours timeline. It clears the convention-based, popular-in-training, and well-documented quality gates; explicit typing is the known Python-web caveat, mitigated downstream with type hints and model-level schemas. Bootstrapper confidence is verified, so scaffolding will be smooth. Deployment defaults to Fly.io (the choice was deferred, so the starter default was locked); CI runs on GitHub Actions with auto-deploy on merge — the standard solo-team shape. Only the auth feature flag is set; payments, realtime, AI, and background jobs are all out of scope per the PRD's non-goals.
