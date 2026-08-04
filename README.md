# EnvBooker

A shared booking system for a limited pool of test/dev environments — browse, filter, and reserve without double-booking. Built with Django 6 on Python 3.14, using a Postgres exclusion constraint to guarantee no overlapping reservations.

## Stack

- **Backend:** Django 6.0.5 / Python 3.14, managed with [uv](https://docs.astral.sh/uv/)
- **Database:** PostgreSQL 17 (required — reservation conflict detection relies on a GiST exclusion constraint)
- **Frontend:** Django templates + HTMX for partial-page updates
- **Deploy:** Railway (see `railway.toml`)

## Getting started

```bash
docker compose up -d              # start Postgres 17 on localhost:5432
uv sync                           # install dependencies

export DJANGO_SECRET_KEY=any-local-secret-value
export DATABASE_URL=postgres://envbooker:envbooker@localhost:5432/envbooker

uv run python manage.py migrate
uv run python manage.py runserver # http://127.0.0.1:8000
```

Or simply run `./dev.sh` to do all of the above in one step.

## Common commands

```bash
uv run python manage.py test              # run the test suite
uv run ruff check . && uv run ruff format .  # lint + format
DJANGO_SECRET_KEY=mypy DATABASE_URL=postgres://u:p@localhost:5432/db uv run mypy .  # type check
```

See `CLAUDE.md` for the full command reference and architecture notes.
