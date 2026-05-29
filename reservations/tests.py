from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from django.test import TestCase
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from reservations.models import Reservation


def make_range(start_hour, end_hour):
    return Range(
        lower=datetime(2024, 1, 1, start_hour, 0, tzinfo=timezone.utc),
        upper=datetime(2024, 1, 1, end_hour, 0, tzinfo=timezone.utc),
        bounds="[)",
    )


class ReservationNoOverlapTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass")
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
