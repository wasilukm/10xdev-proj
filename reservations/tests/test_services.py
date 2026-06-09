from datetime import timedelta

from django.test import TestCase

from accounts.models import User
from catalog.models import Environment
from reservations.models import Reservation
from reservations.services import MAX_DURATION, compute_end, next_free_window, next_reservation_after

from ._helpers import _dt, _range


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
