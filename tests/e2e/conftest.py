"""Shared e2e fixtures: no-UI auth cookie and ORM seed."""

import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import pytest
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from reservations.models import Reservation


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def _range(lower: datetime, upper: datetime) -> Range:
    return Range(lower=lower, upper=upper, bounds="[)")


@pytest.fixture
def auth_cookie(live_server, transactional_db):
    """Mint a server-side Django session for an ORM-created user.

    Returns a cookie dict for page.context.add_cookies([cookie]).
    Must be added BEFORE the first page.goto or the cookie is dropped.
    domain is hostname-only (no port) — that is what Playwright requires.
    """
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"e2e-auth-{suffix}@example.com",
        password="testpass123",
        first_name="E2E",
        last_name="User",
    )
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return {
        "name": "sessionid",
        "value": session.session_key,
        "domain": urlparse(live_server.url).hostname,
        "path": "/",
    }


@pytest.fixture
def seeded_environment(transactional_db):
    """Create a collision-free Environment + existing Reservation via ORM.

    uuid suffix prevents name-unique collisions on parallel runs and re-runs.
    The existing reservation seeds the conflict scenario for the Risk #2 test
    owned by /10x-e2e (happy path + conflict rejection).
    """
    suffix = uuid.uuid4().hex[:8]
    owner = User.objects.create_user(
        email=f"e2e-owner-{suffix}@example.com",
        password="testpass123",
        first_name="Env",
        last_name="Owner",
    )
    env = Environment.objects.create(
        name=f"smoke-env-{suffix}",
        version="1.0",
        purpose="E2E smoke test",
        project=f"project-{suffix}",
        use_case_tag="testing",
        owner=owner,
    )
    Reservation.objects.create(
        owner=owner,
        environment=env,
        during=_range(_dt(2024, 1, 1, 8), _dt(2024, 1, 1, 10)),
    )
    return env
