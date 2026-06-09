from datetime import timedelta
from unittest import mock

from django.test import TestCase

from reservations.forms import ReservationEditForm

from ._helpers import _dt


class ReservationEditFormTest(TestCase):
    """Unit tests for the hours-based duration-edit form."""

    # now = 08:00 UTC; start = 10:00 UTC (future), so any positive hours are valid by default
    _NOW = _dt(8)
    _START = _dt(10)

    def _form(self, hours_value, start=None):
        start = start or self._START
        return ReservationEditForm({"hours": str(hours_value)}, start=start)

    @mock.patch("django.utils.timezone.now", return_value=_dt(8))
    def test_valid_hours_produces_correct_during(self, _):
        """A valid hours value yields a Range from start to start + hours."""
        form = self._form(2)
        self.assertTrue(form.is_valid(), form.errors)
        expected_end = self._START + timedelta(hours=2)
        self.assertEqual(form.cleaned_data["during"].lower, self._START)
        self.assertEqual(form.cleaned_data["during"].upper, expected_end)

    @mock.patch("django.utils.timezone.now", return_value=_dt(8))
    def test_fractional_hours_allowed(self, _):
        """0.5h is above min_value (0.25) and produces correct end."""
        form = self._form(0.5)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["during"].upper,
            self._START + timedelta(hours=0.5),
        )

    @mock.patch("django.utils.timezone.now", return_value=_dt(8))
    def test_hours_below_min_value_invalid(self, _):
        """hours < 0.25 is rejected by the field's min_value constraint."""
        form = self._form(0.1)
        self.assertFalse(form.is_valid())
        self.assertIn("hours", form.errors)

    @mock.patch("django.utils.timezone.now", return_value=_dt(12))
    def test_end_in_the_past_rejected(self, _):
        """When now=12:00 and start=10:00, hours=1 → end=11:00 ≤ now → invalid."""
        form = self._form(1)
        self.assertFalse(form.is_valid())
        self.assertIn(
            "New end must be in the future",
            str(form.errors),
        )

    @mock.patch("django.utils.timezone.now", return_value=_dt(8))
    def test_end_exactly_now_rejected(self, _):
        """end == now is also in the past — rejected."""
        # start=06:00, hours=2 → end=08:00 == now
        form = ReservationEditForm({"hours": "2"}, start=_dt(6))
        self.assertFalse(form.is_valid())
        self.assertIn("New end must be in the future", str(form.errors))
