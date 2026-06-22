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


# Mirrors the _dt/_range idiom in reservations/tests/_helpers.py
# (psycopg Range, bounds="[)", 2024-01-01 anchor). Re-defined locally rather
# than imported to avoid a cross-package dependency from tests/e2e on
# reservations.tests; keep the two in sync if the idiom changes.
def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def _range(lower: datetime, upper: datetime) -> Range:
    return Range(lower=lower, upper=upper, bounds="[)")


def _make_auth(live_server) -> tuple[User, dict]:
    """Create an ORM user, mint a server-side Django session, return (user, cookie).

    The cookie dict is for page.context.add_cookies([cookie]); it must be added
    BEFORE the first page.goto or it is dropped. domain is hostname-only (no port)
    — that is what Playwright requires. The user's last name carries a uuid suffix
    so its rendered full name is a unique, collision-free assertion target.
    """
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"e2e-auth-{suffix}@example.com",
        password="testpass123",
        first_name="E2E",
        last_name=f"User{suffix}",
    )
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    cookie = {
        "name": "sessionid",
        "value": session.session_key,
        "domain": urlparse(live_server.url).hostname,
        "path": "/",
    }
    return user, cookie


@pytest.fixture(autouse=True)
def _servable_static(settings):
    """Serve un-hashed static files so JS (htmx) loads under live_server.

    Production uses whitenoise CompressedManifestStaticFilesStorage, whose
    {% static %} URLs are content-hashed and only exist after `collectstatic`.
    live_server serves static via the staticfiles *finders* (source names), so
    the hashed names 404 and htmx never loads. Swapping to the plain backend for
    the test run makes {% static %} emit finder-resolvable names. Reassigning
    settings.STORAGES fires Django's setting_changed signal, which resets the
    cached staticfiles_storage so {% static %} picks up the new backend.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def auth_cookie(live_server, transactional_db):
    """Cookie dict for a pre-authenticated browser context (no UI login)."""
    _user, cookie = _make_auth(live_server)
    return cookie


@pytest.fixture
def auth_cookie_and_user(live_server, transactional_db):
    """Like auth_cookie, but also returns the User.

    Lets a test assert on the name the app renders for this user after they book —
    the Risk #2 'the new reservation appears' signal — without hard-coding it.
    """
    user, cookie = _make_auth(live_server)
    return cookie, user


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


@pytest.fixture
def bookable_environment(transactional_db):
    """An Environment with NO reservations, owned by someone other than the booker.

    Drives the Risk #2 happy path: a future booking succeeds and the booker's name
    appears in the row — so the row's owner column ('Env Owner') is deliberately a
    different person from the logged-in booker.
    """
    suffix = uuid.uuid4().hex[:8]
    owner = User.objects.create_user(
        email=f"e2e-owner-{suffix}@example.com",
        password="testpass123",
        first_name="Env",
        last_name="Owner",
    )
    return Environment.objects.create(
        name=f"bookable-env-{suffix}",
        version="1.0",
        purpose="Risk #2 happy path",
        project=f"proj-bookable-{suffix}",
        use_case_tag="testing",
        owner=owner,
    )


# Far-future window for the conflict scenario, wide enough that a booking made in
# the active timezone (Europe/Warsaw, UTC+1/+2) unambiguously overlaps it.
_CONFLICT_LOWER = _dt(2030, 1, 1, 6)
_CONFLICT_UPPER = _dt(2030, 1, 1, 20)


@pytest.fixture
def reserved_environment(transactional_db):
    """An Environment with an EXISTING far-future reservation owned by someone else.

    Drives the Risk #2 conflict path: an overlapping booking must be refused with the
    named-conflict message (naming this owner), never silently committed.
    """
    suffix = uuid.uuid4().hex[:8]
    owner = User.objects.create_user(
        email=f"e2e-conflict-owner-{suffix}@example.com",
        password="testpass123",
        first_name="Casey",
        last_name="Conflict",
    )
    env = Environment.objects.create(
        name=f"reserved-env-{suffix}",
        version="1.0",
        purpose="Risk #2 conflict path",
        project=f"proj-reserved-{suffix}",
        use_case_tag="testing",
        owner=owner,
    )
    Reservation.objects.create(
        owner=owner,
        environment=env,
        during=_range(_CONFLICT_LOWER, _CONFLICT_UPPER),
    )
    return env
