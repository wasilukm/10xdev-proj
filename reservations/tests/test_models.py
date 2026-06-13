from django.db import IntegrityError, transaction
from django.test import TestCase
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from reservations.models import Reservation

from ._helpers import _dt, _range


class ReservationNoOverlapTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tester@example.com", password="pass"
        )
        self.env1 = Environment.objects.create(
            name="env-1",
            version="1.0",
            purpose="test",
            project="alpha",
            use_case_tag="ci",
            owner=self.user,
        )
        self.env2 = Environment.objects.create(
            name="env-2",
            version="1.0",
            purpose="test",
            project="alpha",
            use_case_tag="ci",
            owner=self.user,
        )

    def _reserve(self, env, start_hour, end_hour):
        return Reservation.objects.create(
            owner=self.user,
            environment=env,
            during=_range(start_hour, end_hour),
        )

    def test_overlap_rejected(self):
        """(a) Overlapping window on same env raises IntegrityError."""
        self._reserve(self.env1, 9, 13)
        with self.assertRaises(IntegrityError), transaction.atomic():
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
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._reserve(self.env1, 10, 12)

    def test_empty_range_rejected(self):
        """(e) An empty/zero-duration range is rejected by the bounded check."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._reserve(self.env1, 9, 9)

    def test_unbounded_range_rejected(self):
        """(f) An open-ended range bypasses overlap; the bounded check rejects it."""
        open_ended = Range(
            lower=_dt(9),
            upper=None,
            bounds="[)",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.create(
                owner=self.user,
                environment=self.env1,
                during=open_ended,
            )


class ReservationConstraintNamesTest(TestCase):
    """Guard the view translation coupling against silent constraint renames.

    Both reservation_create (views.py:77) and reservation_edit (views.py:128)
    detect a no-overlap violation by matching the literal string
    "reservation_no_overlap" in the IntegrityError cause. If the constraint is
    renamed in a migration, the match fails silently and control reaches
    `else: raise` — an unhandled 500, i.e. exactly the Risk-#1 failure mode
    reintroduced. This test fails immediately on a rename, pointing the author
    at the coupling before it ships.
    """

    def test_no_overlap_constraint_name_is_stable(self):
        """'reservation_no_overlap' is present in Reservation._meta.constraints by that exact name."""
        names = [c.name for c in Reservation._meta.constraints]
        self.assertIn(
            "reservation_no_overlap",
            names,
            "Constraint renamed — update the string match at views.py:77 and views.py:128 before proceeding.",
        )
