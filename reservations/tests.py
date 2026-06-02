from datetime import datetime, timedelta, timezone
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from reservations.models import Reservation
from reservations.services import MAX_DURATION, compute_end, next_free_window, next_reservation_after


def make_range(start_hour, end_hour):
    return Range(
        lower=datetime(2024, 1, 1, start_hour, 0, tzinfo=timezone.utc),
        upper=datetime(2024, 1, 1, end_hour, 0, tzinfo=timezone.utc),
        bounds="[)",
    )


class ReservationNoOverlapTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="tester@example.com", password="pass")
        self.env1 = Environment.objects.create(
            name="env-1", version="1.0", purpose="test",
            project="alpha", use_case_tag="ci", owner=self.user,
        )
        self.env2 = Environment.objects.create(
            name="env-2", version="1.0", purpose="test",
            project="alpha", use_case_tag="ci", owner=self.user,
        )

    def _reserve(self, env, start_hour, end_hour):
        return Reservation.objects.create(
            owner=self.user, environment=env,
            during=make_range(start_hour, end_hour),
        )

    def test_overlap_rejected(self):
        """(a) Overlapping window on same env raises IntegrityError."""
        self._reserve(self.env1, 9, 13)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._reserve(self.env1, 11, 15)

    def test_back_to_back_allowed(self):
        """(b) Back-to-back [9,13) + [13,17) share no overlap."""
        self._reserve(self.env1, 9, 13)
        self._reserve(self.env1, 13, 17)
        self.assertEqual(Reservation.objects.filter(environment=self.env1).count(), 2)

    def test_cross_env_allowed(self):
        """(c) Same overlapping window on a different env is allowed."""
        self._reserve(self.env1, 9, 13)
        self._reserve(self.env2, 9, 13)
        self.assertEqual(Reservation.objects.count(), 2)

    def test_contained_window_rejected(self):
        """(d) Fully contained window on same env raises IntegrityError."""
        self._reserve(self.env1, 9, 17)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._reserve(self.env1, 10, 12)

    def test_empty_range_rejected(self):
        """(e) An empty/zero-duration range is rejected by the bounded check."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._reserve(self.env1, 9, 9)

    def test_unbounded_range_rejected(self):
        """(f) An open-ended range bypasses overlap; the bounded check rejects it."""
        open_ended = Range(
            lower=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            upper=None,
            bounds="[)",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Reservation.objects.create(
                    owner=self.user, environment=self.env1, during=open_ended,
                )


# ---------------------------------------------------------------------------
# Helpers shared by the new test classes below
# ---------------------------------------------------------------------------

_FIXED_NOW = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)


def _dt(h, m=0, d=1):
    """Aware UTC datetime on 2024-01-01 at the given hour/minute."""
    return datetime(2024, 1, d, h, m, tzinfo=timezone.utc)


def _range(sh, eh):
    return Range(lower=_dt(sh), upper=_dt(eh), bounds="[)")


# ---------------------------------------------------------------------------
# Service: compute_end
# ---------------------------------------------------------------------------

class ComputeEndTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ce@example.com", password="pass")
        self.env = Environment.objects.create(
            name="ce-env", version="1.0", purpose="test",
            project="proj", use_case_tag="ci", owner=self.user,
        )
        self.start = _dt(10)

    def _reserve(self, sh, eh):
        return Reservation.objects.create(
            owner=self.user, environment=self.env, during=_range(sh, eh),
        )

    def test_preset_1h(self):
        self.assertEqual(compute_end(self.env, self.start, "1h"), self.start + timedelta(hours=1))

    def test_preset_2h(self):
        self.assertEqual(compute_end(self.env, self.start, "2h"), self.start + timedelta(hours=2))

    def test_preset_4h(self):
        self.assertEqual(compute_end(self.env, self.start, "4h"), self.start + timedelta(hours=4))

    def test_custom(self):
        self.assertEqual(
            compute_end(self.env, self.start, "custom", custom_hours=2.5),
            self.start + timedelta(hours=2.5),
        )

    def test_until_next_no_reservation_caps_at_max(self):
        """No upcoming reservation → end = start + MAX_DURATION."""
        self.assertEqual(compute_end(self.env, self.start, "until_next"), self.start + MAX_DURATION)

    def test_until_next_stops_at_next_start(self):
        """next.start is before start+MAX → end equals next.start (adjacency, not overlap)."""
        self._reserve(11, 13)  # lower=11:00, which is < 10:00+4h=14:00
        self.assertEqual(compute_end(self.env, self.start, "until_next"), _dt(11))

    def test_until_next_caps_at_max_when_next_beyond(self):
        """next.start is after start+MAX → end equals start+MAX."""
        self._reserve(15, 17)  # lower=15:00 > 10:00+4h=14:00
        self.assertEqual(compute_end(self.env, self.start, "until_next"), self.start + MAX_DURATION)


# ---------------------------------------------------------------------------
# Service: next_reservation_after
# ---------------------------------------------------------------------------

class NextReservationAfterTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nra@example.com", password="pass")
        self.env = Environment.objects.create(
            name="nra-env", version="1.0", purpose="test",
            project="proj", use_case_tag="ci", owner=self.user,
        )

    def _reserve(self, sh, eh):
        return Reservation.objects.create(
            owner=self.user, environment=self.env, during=_range(sh, eh),
        )

    def test_no_reservation_returns_none(self):
        # FR-015: gap-finder returns nothing when env is clear
        self.assertIsNone(next_reservation_after(self.env, _dt(10)))

    def test_returns_first_at_or_after_start(self):
        # US-01: "until next reservation" needs the immediately next booking
        r = self._reserve(12, 14)
        self.assertEqual(next_reservation_after(self.env, _dt(10)), r)

    def test_skips_reservation_with_lower_bound_before_start(self):
        """Reservation whose lower bound is strictly before start is excluded."""
        self._reserve(8, 10)   # lower=8 < 10 → excluded
        r = self._reserve(12, 14)
        self.assertEqual(next_reservation_after(self.env, _dt(10)), r)


# ---------------------------------------------------------------------------
# Service: next_free_window
# ---------------------------------------------------------------------------

class NextFreeWindowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nfw@example.com", password="pass")
        self.env = Environment.objects.create(
            name="nfw-env", version="1.0", purpose="test",
            project="proj", use_case_tag="ci", owner=self.user,
        )

    def _reserve(self, sh, eh):
        return Reservation.objects.create(
            owner=self.user, environment=self.env, during=_range(sh, eh),
        )

    def test_no_block_returns_after_unchanged(self):
        # FR-015: when env is free, next free window is `after` itself
        after = _dt(10)
        self.assertEqual(next_free_window(self.env, after), after)

    def test_immediate_block_returns_upper(self):
        """`after` falls inside a reservation: next free window is its upper bound."""
        self._reserve(9, 13)
        self.assertEqual(next_free_window(self.env, _dt(10)), _dt(13))

    def test_contiguous_blocks_follow_chain(self):
        """Back-to-back reservations: returns the end of the entire chain."""
        self._reserve(9, 13)
        self._reserve(13, 17)
        self.assertEqual(next_free_window(self.env, _dt(10)), _dt(17))


# ---------------------------------------------------------------------------
# View: reservation_create (happy path, overlap rejection, auth)
# ---------------------------------------------------------------------------

class ReservationCreateViewTest(TestCase):
    """
    Integration tests for the HTMX booking endpoint.

    timezone.now is frozen to 2024-01-01 08:00 UTC so that the form's
    past-start check accepts datetimes around 10:00 on the same day.
    The submitted start string "2024-01-01T10:00" is interpreted by
    the form as Europe/Warsaw (CET = UTC+1), yielding 09:00 UTC —
    safely after the frozen now of 08:00 UTC.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="booker@example.com",
            password="pass",
            first_name="Alice",
            last_name="Smith",
        )
        self.env = Environment.objects.create(
            name="view-env", version="1.0", purpose="test",
            project="proj", use_case_tag="ci", owner=self.user,
        )
        self.url = reverse("reservations:create")

    def _post(self, start_str="2024-01-01T10:00", duration="1h"):
        return self.client.post(self.url, {
            "environment": self.env.pk,
            "start": start_str,
            "duration": duration,
        })

    def test_auth_required(self):
        """US-01: unauthenticated POST redirects to login, no reservation created."""
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertEqual(Reservation.objects.count(), 0)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_happy_path_creates_reservation(self, _):
        """FR-008: valid non-overlapping POST creates exactly one reservation and returns 200."""
        self.client.login(email="booker@example.com", password="pass")
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reservation.objects.filter(environment=self.env).count(), 1)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_overlap_rejection_names_owner_and_window(self, _):
        """FR-015: overlapping POST returns inline message naming the conflicting owner."""
        Reservation.objects.create(
            owner=self.user, environment=self.env, during=_range(9, 14),
        )
        self.client.login(email="booker@example.com", password="pass")
        response = self._post()
        self.assertEqual(response.status_code, 200)
        # No second reservation should have been created
        self.assertEqual(Reservation.objects.filter(environment=self.env).count(), 1)
        self.assertIn("Alice Smith", response.content.decode())

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_overlap_rejection_is_not_500(self, _):
        """FR-015: DB race (IntegrityError from exclusion constraint) is caught inline, not 500."""
        Reservation.objects.create(
            owner=self.user, environment=self.env, during=_range(9, 14),
        )
        self.client.login(email="booker@example.com", password="pass")
        response = self._post()
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(response.status_code, 200)
