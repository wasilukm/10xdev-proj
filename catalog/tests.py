from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from catalog.services import build_row_context
from reservations.models import Reservation


def make_dt(hour, minute=0):
    return datetime(2024, 6, 15, hour, minute, tzinfo=dt_timezone.utc)


def make_range(start_hour, end_hour):
    return Range(lower=make_dt(start_hour), upper=make_dt(end_hour), bounds="[)")


class EnvironmentModelTest(TestCase):
    def test_create_and_str(self):
        user = User.objects.create_user(email="owner@example.com", password="pass")
        env = Environment.objects.create(
            name="staging-01",
            version="1.2.3",
            purpose="testing",
            project="alpha",
            use_case_tag="integration",
            owner=user,
        )
        self.assertEqual(env.name, "staging-01")
        self.assertEqual(env.version, "1.2.3")
        self.assertEqual(env.purpose, "testing")
        self.assertEqual(env.project, "alpha")
        self.assertEqual(env.use_case_tag, "integration")
        self.assertEqual(env.owner, user)
        self.assertEqual(str(env), "staging-01")


class DashboardAuthTest(TestCase):
    def test_anonymous_redirects_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('home')}",
            fetch_redirect_response=False,
        )


class DashboardGroupingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner@example.com", password="pass")
        self.env = Environment.objects.create(
            name="env-a", version="1.0", purpose="test",
            project="proj", use_case_tag="ci", owner=self.user,
        )

    def _reserve(self, start_h, end_h):
        return Reservation.objects.create(
            owner=self.user, environment=self.env,
            during=make_range(start_h, end_h),
        )

    def test_current_reservation_shown(self):
        now = make_dt(10)
        self._reserve(9, 12)
        ctx = build_row_context(self.env, now=now)
        self.assertTrue(ctx["is_busy"])
        self.assertIsNotNone(ctx["current_reservation"])

    def test_upcoming_within_24h_shown(self):
        now = make_dt(10)
        self._reserve(15, 17)
        ctx = build_row_context(self.env, now=now)
        self.assertFalse(ctx["is_busy"])
        self.assertEqual(len(ctx["upcoming_reservations"]), 1)

    def test_beyond_24h_excluded(self):
        now = make_dt(10)
        beyond = datetime(2024, 6, 17, 12, 0, tzinfo=dt_timezone.utc)
        beyond_end = datetime(2024, 6, 17, 14, 0, tzinfo=dt_timezone.utc)
        Reservation.objects.create(
            owner=self.user, environment=self.env,
            during=Range(lower=beyond, upper=beyond_end, bounds="[)"),
        )
        ctx = build_row_context(self.env, now=now)
        self.assertFalse(ctx["is_busy"])
        self.assertEqual(len(ctx["upcoming_reservations"]), 0)

    def test_current_not_also_in_upcoming(self):
        now = make_dt(10)
        self._reserve(9, 12)
        ctx = build_row_context(self.env, now=now)
        self.assertIsNotNone(ctx["current_reservation"])
        self.assertNotIn(ctx["current_reservation"], ctx["upcoming_reservations"])


class DashboardOwnerVisibilityTest(TestCase):
    """US-01: owner identity must be visible for current and upcoming reservations."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="visible@example.com",
            password="pass",
            first_name="Bob",
            last_name="Jones",
        )
        self.env = Environment.objects.create(
            name="vis-env", version="1.0", purpose="test",
            project="proj", use_case_tag="ci", owner=self.owner,
        )

    def test_current_reservation_owner_available(self):
        """Row context exposes owner identity on current reservation."""
        now = make_dt(10)
        Reservation.objects.create(
            owner=self.owner, environment=self.env,
            during=Range(lower=make_dt(9), upper=make_dt(12), bounds="[)"),
        )
        ctx = build_row_context(self.env, now=now)
        res = ctx["current_reservation"]
        self.assertIsNotNone(res)
        self.assertEqual(res.owner.get_full_name(), "Bob Jones")

    def test_upcoming_reservation_owner_available(self):
        """Row context exposes owner identity on upcoming reservations."""
        now = make_dt(10)
        Reservation.objects.create(
            owner=self.owner, environment=self.env,
            during=Range(lower=make_dt(15), upper=make_dt(17), bounds="[)"),
        )
        ctx = build_row_context(self.env, now=now)
        self.assertEqual(len(ctx["upcoming_reservations"]), 1)
        self.assertEqual(ctx["upcoming_reservations"][0].owner.get_full_name(), "Bob Jones")
