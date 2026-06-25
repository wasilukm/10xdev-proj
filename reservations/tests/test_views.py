from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Environment
from reservations.models import Reservation

from ._helpers import _FIXED_NOW, _dt, _range

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
            name="view-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user,
        )
        self.url = reverse("reservations:create")

    def _post(self, start_str="2024-01-01T10:00", duration="1h"):
        return self.client.post(
            self.url,
            {
                "environment": self.env.pk,
                "start": start_str,
                "duration": duration,
            },
        )

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
            owner=self.user,
            environment=self.env,
            during=_range(9, 14),
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
            owner=self.user,
            environment=self.env,
            during=_range(9, 14),
        )
        self.client.login(email="booker@example.com", password="pass")
        response = self._post()
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# View: reservation_edit
# ---------------------------------------------------------------------------


class ReservationEditViewTest(TestCase):
    """Integration tests for the HTMX reservation-edit endpoint.

    timezone.now is frozen to 2024-01-01 08:00 UTC throughout patched tests.
    self.reservation = [10:00, 12:00) is future (lower > now).
    In-progress fixtures use [06:00, 09:00): lower < now, upper > now, no overlap with [10:00, 12:00).
    Past fixtures use [04:00, 06:00): upper <= now.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="editor@example.com",
            password="pass",
            first_name="Alice",
            last_name="Smith",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="pass",
            first_name="Bob",
            last_name="Jones",
        )
        self.env = Environment.objects.create(
            name="edit-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user,
        )
        self.reservation = Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=_range(10, 12),
        )

    def _edit_url(self, pk=None):
        return reverse(
            "reservations:edit", args=[pk if pk is not None else self.reservation.pk]
        )

    def _post(self, hours=2, pk=None):
        return self.client.post(self._edit_url(pk), {"hours": str(hours)})

    def test_auth_required(self):
        """Unauthenticated POST redirects to login."""
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_non_owner_404(self, _):
        """POST as a different user returns 404."""
        self.client.login(email="other@example.com", password="pass")
        response = self._post()
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_nonexistent_pk_404(self, _):
        """POST to a non-existent pk returns 404."""
        self.client.login(email="editor@example.com", password="pass")
        response = self._post(pk=99999)
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_happy_path_updates_during(self, _):
        """Valid edit updates the reservation window and returns 200."""
        self.client.login(email="editor@example.com", password="pass")
        response = self._post(hours=4)  # start=10:00, end=14:00
        self.assertEqual(response.status_code, 200)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.during.lower, _dt(10))
        self.assertEqual(self.reservation.during.upper, _dt(14))

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_in_progress_edit_changes_end_keeps_start(self, _):
        """Editing an in-progress reservation changes only the end; start is immutable."""
        # [06:00, 09:00) is in-progress at now=08:00, no overlap with [10:00, 12:00)
        in_progress = Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=_range(6, 9),
        )
        self.client.login(email="editor@example.com", password="pass")
        url = reverse("reservations:edit", args=[in_progress.pk])
        # hours=2.5 → end = 06:00 + 2.5h = 08:30 > now=08:00
        response = self.client.post(url, {"hours": "2.5"})
        self.assertEqual(response.status_code, 200)
        in_progress.refresh_from_db()
        self.assertEqual(in_progress.during.lower, _dt(6))
        self.assertEqual(in_progress.during.upper, _dt(8, 30))

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_in_progress_reject_end_in_past(self, _):
        """Edit that would set end <= now is rejected; original window unchanged."""
        # [06:00, 09:00) in-progress, no overlap with [10:00, 12:00)
        in_progress = Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=_range(6, 9),
        )
        self.client.login(email="editor@example.com", password="pass")
        url = reverse("reservations:edit", args=[in_progress.pk])
        # hours=1 → end = 06:00 + 1h = 07:00 < now=08:00 → form invalid
        response = self.client.post(url, {"hours": "1"})
        self.assertEqual(response.status_code, 200)
        in_progress.refresh_from_db()
        self.assertEqual(in_progress.during.upper, _dt(9))  # unchanged

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_overlap_conflict_names_other_owner_not_self(self, _):
        """Overlap rejection names the conflicting other owner — verifies .exclude(pk=...) in conflict query."""
        # Shorten own reservation to make room for a non-overlapping sibling
        self.reservation.during = _range(10, 11)
        self.reservation.save()
        Reservation.objects.create(
            owner=self.other_user,
            environment=self.env,
            during=_range(13, 16),
        )
        self.client.login(email="editor@example.com", password="pass")
        # hours=4 → [10:00, 14:00) overlaps Bob's [13:00, 16:00)
        response = self._post(hours=4)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Bob Jones", content)  # conflict names the other owner
        self.assertNotIn("Alice Smith", content)  # not a false self-report
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.during.upper, _dt(11)
        )  # original window intact

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_extend_own_window_no_self_conflict(self, _):
        """Extending a reservation to a superset of its old range succeeds (no false self-conflict)."""
        self.client.login(email="editor@example.com", password="pass")
        # hours=4 → [10:00, 14:00); old was [10:00, 12:00); no other reservations
        response = self._post(hours=4)
        self.assertEqual(response.status_code, 200)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.during.upper, _dt(14))

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_past_reservation_404(self, _):
        """Edit on a past (already-ended) reservation returns 404."""
        past = Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=_range(4, 6),
        )
        self.client.login(email="editor@example.com", password="pass")
        url = reverse("reservations:edit", args=[past.pk])
        response = self.client.post(url, {"hours": "2"})
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_overlap_conflict_is_not_500(self, _):
        """Overlap on the edit path returns 200, not 500 — guards the constraint-name string-match.

        Mirrors test_overlap_rejection_is_not_500 on the create path. If the
        'reservation_no_overlap' constraint is renamed, views.py:128 falls to
        `else: raise` and this test catches the resulting 500 before it ships.
        """
        # Shorten own reservation to make room for a non-overlapping sibling
        self.reservation.during = _range(10, 11)
        self.reservation.save()
        Reservation.objects.create(
            owner=self.other_user,
            environment=self.env,
            during=_range(13, 16),
        )
        self.client.login(email="editor@example.com", password="pass")
        # hours=4 → [10:00, 14:00) overlaps Bob's [13:00, 16:00)
        response = self._post(hours=4)
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# View: reservation_cancel
# ---------------------------------------------------------------------------


class ReservationCancelViewTest(TestCase):
    """Integration tests for the HTMX reservation-cancel endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="canceler@example.com",
            password="pass",
        )
        self.other_user = User.objects.create_user(
            email="other2@example.com",
            password="pass",
        )
        self.env = Environment.objects.create(
            name="cancel-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user,
        )
        self.reservation = Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=_range(10, 12),
        )

    def _cancel_url(self, pk=None):
        return reverse(
            "reservations:cancel", args=[pk if pk is not None else self.reservation.pk]
        )

    def _post(self, pk=None):
        return self.client.post(self._cancel_url(pk))

    def test_auth_required(self):
        """Unauthenticated POST redirects to login."""
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_non_owner_404(self, _):
        """POST as a different user returns 404."""
        self.client.login(email="other2@example.com", password="pass")
        response = self._post()
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_nonexistent_pk_404(self, _):
        """POST to a non-existent pk returns 404."""
        self.client.login(email="canceler@example.com", password="pass")
        response = self._post(pk=99999)
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_cancel_deletes_row_and_returns_empty(self, _):
        """Cancel hard-deletes the reservation and returns empty content for HTMX row removal."""
        self.client.login(email="canceler@example.com", password="pass")
        pk = self.reservation.pk
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertFalse(Reservation.objects.filter(pk=pk).exists())

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_past_reservation_404(self, _):
        """Cancel on a past (already-ended) reservation returns 404."""
        past = Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=_range(4, 6),
        )
        self.client.login(email="canceler@example.com", password="pass")
        url = reverse("reservations:cancel", args=[past.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# View: my_reservations (auth + cross-user ownership isolation — Risk #3)
# ---------------------------------------------------------------------------


class MyReservationsViewTest(TestCase):
    """Risk #3: reservations:mine is the only ownership-*filtered* GET.

    Prove (a) anonymous access is denied and (b) one user's list never leaks
    another user's data. The my_reservations template renders each reservation's
    *environment name* (the owner name is never rendered), so isolation is asserted
    on environment-name presence/absence in the rendered list — user A sees only
    their own environment's reservation, never user B's. now is frozen to _FIXED_NOW
    so the future-windowed reservations stay in the upper_bound__gt=now list.
    """

    def setUp(self):
        self.user_a = User.objects.create_user(
            email="alice@example.com",
            password="pass",
            first_name="Alice",
            last_name="Smith",
        )
        self.user_b = User.objects.create_user(
            email="bob@example.com",
            password="pass",
            first_name="Bob",
            last_name="Jones",
        )
        self.env_a = Environment.objects.create(
            name="alice-only-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user_a,
        )
        self.env_b = Environment.objects.create(
            name="bob-only-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user_b,
        )
        self.url = reverse("reservations:mine")

    def test_auth_required(self):
        """Unauthenticated GET redirects to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_lists_only_own_reservations(self, _):
        """A's list shows A's reservation and never B's (the IDOR-shaped gap)."""
        Reservation.objects.create(
            owner=self.user_a,
            environment=self.env_a,
            during=_range(10, 12),
        )
        Reservation.objects.create(
            owner=self.user_b,
            environment=self.env_b,
            during=_range(10, 12),
        )
        self.client.login(email="alice@example.com", password="pass")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("alice-only-env", content)  # own reservation present
        self.assertNotIn("bob-only-env", content)  # other user's data absent


# ---------------------------------------------------------------------------
# Admin override: staff/superuser may edit/cancel any user's reservation
# ---------------------------------------------------------------------------


class ReservationAdminOverrideViewTest(TestCase):
    """Staff/superusers can edit and cancel reservations they do not own.

    timezone.now frozen to 2024-01-01 08:00 UTC. The target reservation
    [10:00, 12:00) is future and owned by `owner`; the admin acts on it.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="pass",
            first_name="Olive",
            last_name="Owner",
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="pass",
            is_staff=True,
        )
        self.env = Environment.objects.create(
            name="override-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.owner,
        )
        self.reservation = Reservation.objects.create(
            owner=self.owner,
            environment=self.env,
            during=_range(10, 12),
        )

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_admin_can_edit_other_users_reservation(self, _):
        """Staff edits another user's reservation duration."""
        self.client.login(email="admin@example.com", password="pass")
        url = reverse("reservations:edit", args=[self.reservation.pk])
        response = self.client.post(url, {"hours": "4"})  # start=10:00, end=14:00
        self.assertEqual(response.status_code, 200)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.during.upper, _dt(14))

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_admin_can_cancel_other_users_reservation(self, _):
        """Staff cancels another user's reservation; row deleted, empty body."""
        self.client.login(email="admin@example.com", password="pass")
        pk = self.reservation.pk
        url = reverse("reservations:cancel", args=[pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertFalse(Reservation.objects.filter(pk=pk).exists())

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_admin_cannot_edit_past_reservation(self, _):
        """The past-block time rule applies to admins too."""
        past = Reservation.objects.create(
            owner=self.owner,
            environment=self.env,
            during=_range(4, 6),
        )
        self.client.login(email="admin@example.com", password="pass")
        url = reverse("reservations:edit", args=[past.pk])
        response = self.client.post(url, {"hours": "2"})
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_admin_cannot_cancel_past_reservation(self, _):
        """The past-block time rule applies to admins on cancel too."""
        past = Reservation.objects.create(
            owner=self.owner,
            environment=self.env,
            during=_range(4, 6),
        )
        self.client.login(email="admin@example.com", password="pass")
        url = reverse("reservations:cancel", args=[past.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_non_admin_still_cannot_edit_others(self, _):
        """Regression guard: a regular non-owner still gets 404 on edit."""
        User.objects.create_user(email="bystander@example.com", password="pass")
        self.client.login(email="bystander@example.com", password="pass")
        url = reverse("reservations:edit", args=[self.reservation.pk])
        response = self.client.post(url, {"hours": "4"})
        self.assertEqual(response.status_code, 404)

    @mock.patch("django.utils.timezone.now", return_value=_FIXED_NOW)
    def test_non_admin_still_cannot_cancel_others(self, _):
        """Regression guard: a regular non-owner still gets 404 on cancel."""
        User.objects.create_user(email="bystander2@example.com", password="pass")
        self.client.login(email="bystander2@example.com", password="pass")
        url = reverse("reservations:cancel", args=[self.reservation.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
