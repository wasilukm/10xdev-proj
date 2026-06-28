from datetime import UTC, datetime, timedelta

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from catalog.services import (
    build_row_context,
    delete_environment,
    filter_environments,
    filter_options,
)
from reservations.models import Reservation
from reservations.services import active_or_upcoming_reservations


def make_dt(hour, minute=0):
    return datetime(2024, 6, 15, hour, minute, tzinfo=UTC)


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
            name="env-a",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user,
        )

    def _reserve(self, start_h, end_h):
        return Reservation.objects.create(
            owner=self.user,
            environment=self.env,
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
        beyond = datetime(2024, 6, 17, 12, 0, tzinfo=UTC)
        beyond_end = datetime(2024, 6, 17, 14, 0, tzinfo=UTC)
        Reservation.objects.create(
            owner=self.user,
            environment=self.env,
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


class FilterEnvironmentsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="filt@example.com", password="pass")
        self.env_alpha = Environment.objects.create(
            name="alpha",
            version="1.0",
            purpose="test",
            project="alpha-proj",
            use_case_tag="ci",
            owner=self.user,
        )
        self.env_beta = Environment.objects.create(
            name="beta",
            version="1.0",
            purpose="staging",
            project="beta-proj",
            use_case_tag="perf",
            owner=self.user,
        )
        self.env_gamma = Environment.objects.create(
            name="gamma",
            version="1.0",
            purpose="test",
            project="alpha-proj",
            use_case_tag="perf",
            owner=self.user,
        )

    def _qs(self):
        return Environment.objects.all()

    def test_filter_by_project(self):
        now = make_dt(10)
        result = list(filter_environments(self._qs(), project="alpha-proj", now=now))
        self.assertIn(self.env_alpha, result)
        self.assertIn(self.env_gamma, result)
        self.assertNotIn(self.env_beta, result)

    def test_filter_by_use_case_tag(self):
        now = make_dt(10)
        result = list(filter_environments(self._qs(), use_case_tag="perf", now=now))
        self.assertIn(self.env_beta, result)
        self.assertIn(self.env_gamma, result)
        self.assertNotIn(self.env_alpha, result)

    def test_filter_availability_free(self):
        now = make_dt(10)
        # Reserve alpha — busy at now
        Reservation.objects.create(
            owner=self.user,
            environment=self.env_alpha,
            during=make_range(9, 12),
        )
        result = list(filter_environments(self._qs(), availability="free", now=now))
        self.assertNotIn(self.env_alpha, result)
        self.assertIn(self.env_beta, result)
        self.assertIn(self.env_gamma, result)

    def test_filter_availability_busy(self):
        now = make_dt(10)
        Reservation.objects.create(
            owner=self.user,
            environment=self.env_alpha,
            during=make_range(9, 12),
        )
        result = list(filter_environments(self._qs(), availability="busy", now=now))
        self.assertIn(self.env_alpha, result)
        self.assertNotIn(self.env_beta, result)
        self.assertNotIn(self.env_gamma, result)

    def test_filter_and_combination(self):
        now = make_dt(10)
        result = list(
            filter_environments(
                self._qs(),
                project="alpha-proj",
                use_case_tag="perf",
                now=now,
            )
        )
        self.assertEqual(result, [self.env_gamma])

    def test_blank_availability_no_constraint(self):
        now = make_dt(10)
        result = list(filter_environments(self._qs(), availability=None, now=now))
        self.assertEqual(len(result), 3)

    def test_unknown_availability_value_no_constraint(self):
        now = make_dt(10)
        result = list(filter_environments(self._qs(), availability="unknown", now=now))
        self.assertEqual(len(result), 3)

    def test_blank_project_no_constraint(self):
        now = make_dt(10)
        result = list(filter_environments(self._qs(), project=None, now=now))
        self.assertEqual(len(result), 3)

    def test_blank_use_case_tag_no_constraint(self):
        now = make_dt(10)
        result = list(filter_environments(self._qs(), use_case_tag=None, now=now))
        self.assertEqual(len(result), 3)


class FilterOptionsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="opts@example.com", password="pass")
        Environment.objects.create(
            name="e1",
            version="1.0",
            purpose="test",
            project="zeta",
            use_case_tag="perf",
            owner=self.user,
        )
        Environment.objects.create(
            name="e2",
            version="1.0",
            purpose="test",
            project="alpha",
            use_case_tag="ci",
            owner=self.user,
        )
        Environment.objects.create(
            name="e3",
            version="1.0",
            purpose="test",
            project="alpha",
            use_case_tag="perf",
            owner=self.user,
        )

    def test_filter_options_distinct_sorted_projects(self):
        opts = filter_options()
        self.assertEqual(opts["projects"], ["alpha", "zeta"])

    def test_filter_options_distinct_sorted_tags(self):
        opts = filter_options()
        self.assertEqual(opts["use_case_tags"], ["ci", "perf"])


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class FilterUITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ui@example.com", password="pass")
        self.client.login(username="ui@example.com", password="pass")
        self.env1 = Environment.objects.create(
            name="ui-alpha",
            version="1.0",
            purpose="test",
            project="alpha",
            use_case_tag="ci",
            owner=self.user,
        )
        self.env2 = Environment.objects.create(
            name="ui-beta",
            version="1.0",
            purpose="staging",
            project="beta",
            use_case_tag="perf",
            owner=self.user,
        )

    def test_full_page_renders_filter_form_with_options(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="availability"', content)
        self.assertIn('name="project"', content)
        self.assertIn('name="use_case_tag"', content)
        self.assertIn("alpha", content)
        self.assertIn("beta", content)
        self.assertIn("ci", content)
        self.assertIn("perf", content)
        self.assertIn("Clear filters", content)

    def test_full_page_renders_table(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("ui-alpha", content)
        self.assertIn("ui-beta", content)
        self.assertIn("<html", content.lower())

    def test_htmx_request_returns_partial_only(self):
        response = self.client.get(reverse("home"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("ui-alpha", content)
        self.assertNotIn("<html", content.lower())
        self.assertNotIn("<nav", content.lower())
        # The swap is self-replacing: the partial must re-emit the wrapper id
        # or subsequent filter swaps lose their #env-results target.
        self.assertIn('id="env-results"', content)

    def test_htmx_filtered_returns_narrowed_rows(self):
        response = self.client.get(
            reverse("home"), {"project": "alpha"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("ui-alpha", content)
        self.assertNotIn("ui-beta", content)

    def test_htmx_zero_match_shows_no_match_message(self):
        response = self.client.get(
            reverse("home"), {"project": "nonexistent"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("No environments match these filters", content)
        self.assertNotIn("No environments found", content)

    def test_unfiltered_full_page_shows_table_not_empty_message(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("No environments found", content)
        self.assertIn("<table", content)

    def test_no_envs_at_all_shows_empty_catalog_message(self):
        Environment.objects.all().delete()
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("No environments found", content)
        self.assertNotIn("No environments match", content)


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
            name="vis-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.owner,
        )

    def test_current_reservation_owner_available(self):
        """Row context exposes owner identity on current reservation."""
        now = make_dt(10)
        Reservation.objects.create(
            owner=self.owner,
            environment=self.env,
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
            owner=self.owner,
            environment=self.env,
            during=Range(lower=make_dt(15), upper=make_dt(17), bounds="[)"),
        )
        ctx = build_row_context(self.env, now=now)
        self.assertEqual(len(ctx["upcoming_reservations"]), 1)
        self.assertEqual(
            ctx["upcoming_reservations"][0].owner.get_full_name(), "Bob Jones"
        )


class EnvironmentAdminUnregisteredTest(TestCase):
    """S-05: Environment is retired from the Django admin; the manage UI owns CRUD."""

    def test_environment_not_registered(self):
        self.assertNotIn(Environment, admin.site._registry)


class ActiveOrUpcomingReservationsTest(TestCase):
    """active_or_upcoming_reservations: excludes past, includes active + upcoming."""

    def setUp(self):
        self.user = User.objects.create_user(email="aou@example.com", password="pass")
        self.env = Environment.objects.create(
            name="aou-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user,
        )

    def _reserve(self, start, end):
        return Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=Range(lower=start, upper=end, bounds="[)"),
        )

    def test_partitions_by_window(self):
        now = timezone.now()
        past = self._reserve(now - timedelta(hours=3), now - timedelta(hours=1))
        active = self._reserve(now - timedelta(hours=1), now + timedelta(hours=1))
        upcoming = self._reserve(now + timedelta(hours=2), now + timedelta(hours=3))

        result = list(active_or_upcoming_reservations(self.env, now=now))

        self.assertEqual(result, [active, upcoming])
        self.assertNotIn(past, result)


class ManageAccessControlTest(TestCase):
    """S-05 FR-005: manage routes are staff-gated."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pass", is_staff=True
        )
        self.plain = User.objects.create_user(
            email="plain@example.com", password="pass"
        )

    def test_anonymous_redirects_to_login(self):
        for name in ("env_manage", "env_create"):
            response = self.client.get(reverse(name))
            self.assertRedirects(
                response,
                f"{reverse('login')}?next={reverse(name)}",
                fetch_redirect_response=False,
            )

    def test_non_staff_forbidden(self):
        self.client.login(username="plain@example.com", password="pass")
        for name in ("env_manage", "env_create"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403)

    def test_staff_gets_200(self):
        self.client.login(username="staff@example.com", password="pass")
        for name in ("env_manage", "env_create"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)


class EnvironmentCreateTest(TestCase):
    """S-05 FR-005: staff create with owner default + selectable; invalid re-renders."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pass", is_staff=True
        )
        self.other = User.objects.create_user(
            email="other@example.com", password="pass"
        )
        self.client.login(username="staff@example.com", password="pass")

    def _payload(self, **overrides):
        data = {
            "name": "new-env",
            "version": "1.0",
            "purpose": "testing",
            "project": "alpha",
            "use_case_tag": "ci",
            "owner": self.staff.pk,
        }
        data.update(overrides)
        return data

    def test_owner_initial_defaults_to_self(self):
        response = self.client.get(reverse("env_create"))
        self.assertEqual(response.context["form"].initial["owner"], self.staff)

    def test_post_creates_one_environment_owner_self(self):
        response = self.client.post(reverse("env_create"), self._payload())
        self.assertRedirects(response, reverse("env_manage"))
        self.assertEqual(Environment.objects.count(), 1)
        env = Environment.objects.get()
        self.assertEqual(env.name, "new-env")
        self.assertEqual(env.owner, self.staff)

    def test_owner_is_selectable_to_another_user(self):
        response = self.client.post(
            reverse("env_create"), self._payload(owner=self.other.pk)
        )
        self.assertRedirects(response, reverse("env_manage"))
        env = Environment.objects.get()
        self.assertEqual(env.owner, self.other)

    def test_invalid_post_re_renders_and_creates_nothing(self):
        response = self.client.post(reverse("env_create"), self._payload(name=""))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Environment.objects.count(), 0)


class EnvironmentEditTest(TestCase):
    """S-05 FR-006: edit with two-step warning over active/upcoming reservations."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pass", is_staff=True
        )
        self.owner = User.objects.create_user(
            email="resowner@example.com",
            password="pass",
            first_name="Carol",
            last_name="Vega",
        )
        self.env = Environment.objects.create(
            name="edit-env",
            version="1.0",
            purpose="testing",
            project="alpha",
            use_case_tag="ci",
            owner=self.staff,
        )
        self.client.login(username="staff@example.com", password="pass")

    def _payload(self, **overrides):
        data = {
            "name": "edit-env",
            "version": "2.0",
            "purpose": "testing",
            "project": "alpha",
            "use_case_tag": "ci",
            "owner": self.staff.pk,
        }
        data.update(overrides)
        return data

    def _reserve_upcoming(self):
        now = timezone.now()
        return Reservation.objects.create(
            owner=self.owner,
            environment=self.env,
            during=Range(
                lower=now + timedelta(hours=1),
                upper=now + timedelta(hours=2),
                bounds="[)",
            ),
        )

    def test_non_staff_forbidden(self):
        self.client.logout()
        self.client.login(username="resowner@example.com", password="pass")
        response = self.client.get(reverse("env_edit", args=[self.env.pk]))
        self.assertEqual(response.status_code, 403)

    def test_edit_without_reservations_saves_one_step(self):
        response = self.client.post(
            reverse("env_edit", args=[self.env.pk]), self._payload(version="2.0")
        )
        self.assertRedirects(response, reverse("env_manage"))
        self.env.refresh_from_db()
        self.assertEqual(self.env.version, "2.0")

    def test_edit_with_active_upcoming_warns_and_does_not_save(self):
        self._reserve_upcoming()
        response = self.client.post(
            reverse("env_edit", args=[self.env.pk]), self._payload(version="9.9")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["needs_confirm"])
        content = response.content.decode()
        self.assertIn("Carol Vega", content)
        self.env.refresh_from_db()
        self.assertEqual(self.env.version, "1.0")

    def test_resubmit_with_confirm_saves(self):
        self._reserve_upcoming()
        response = self.client.post(
            reverse("env_edit", args=[self.env.pk]),
            self._payload(version="9.9", confirm="1"),
        )
        self.assertRedirects(response, reverse("env_manage"))
        self.env.refresh_from_db()
        self.assertEqual(self.env.version, "9.9")


class DeleteEnvironmentServiceTest(TestCase):
    """S-05 FR-007: delete_environment guard + past-reservation cascade."""

    def setUp(self):
        self.user = User.objects.create_user(email="del@example.com", password="pass")
        self.env = Environment.objects.create(
            name="del-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.user,
        )

    def _reserve(self, lower, upper):
        return Reservation.objects.create(
            owner=self.user,
            environment=self.env,
            during=Range(lower=lower, upper=upper, bounds="[)"),
        )

    def test_blocked_when_upcoming_exists(self):
        now = timezone.now()
        res = self._reserve(now + timedelta(hours=1), now + timedelta(hours=2))
        outcome = delete_environment(self.env, now=now)
        self.assertEqual(outcome, "BLOCKED")
        self.assertTrue(Environment.objects.filter(pk=self.env.pk).exists())
        self.assertTrue(Reservation.objects.filter(pk=res.pk).exists())

    def test_blocked_when_active_exists(self):
        now = timezone.now()
        self._reserve(now - timedelta(hours=1), now + timedelta(hours=1))
        outcome = delete_environment(self.env, now=now)
        self.assertEqual(outcome, "BLOCKED")
        self.assertTrue(Environment.objects.filter(pk=self.env.pk).exists())

    def test_cascade_past_reservations(self):
        now = timezone.now()
        past = self._reserve(now - timedelta(hours=3), now - timedelta(hours=1))
        outcome = delete_environment(self.env, now=now)
        self.assertEqual(outcome, "DELETED")
        self.assertFalse(Environment.objects.filter(pk=self.env.pk).exists())
        self.assertFalse(Reservation.objects.filter(pk=past.pk).exists())

    def test_delete_when_no_reservations(self):
        now = timezone.now()
        outcome = delete_environment(self.env, now=now)
        self.assertEqual(outcome, "DELETED")
        self.assertFalse(Environment.objects.filter(pk=self.env.pk).exists())


class EnvironmentDeleteViewTest(TestCase):
    """S-05 FR-007: staff-gated delete confirm + perform."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pass", is_staff=True
        )
        self.plain = User.objects.create_user(
            email="plain@example.com", password="pass"
        )
        self.env = Environment.objects.create(
            name="dv-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.staff,
        )
        self.url = reverse("env_delete", args=[self.env.pk])

    def test_non_staff_forbidden(self):
        self.client.login(username="plain@example.com", password="pass")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_post_deletes_and_redirects(self):
        self.client.login(username="staff@example.com", password="pass")
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("env_manage"))
        self.assertFalse(Environment.objects.filter(pk=self.env.pk).exists())

    def test_post_blocked_re_renders_with_blocking_list(self):
        now = timezone.now()
        Reservation.objects.create(
            owner=self.plain,
            environment=self.env,
            during=Range(
                lower=now + timedelta(hours=1),
                upper=now + timedelta(hours=2),
                bounds="[)",
            ),
        )
        self.client.login(username="staff@example.com", password="pass")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_blocked"])
        self.assertTrue(Environment.objects.filter(pk=self.env.pk).exists())


class AdminInlineControlsTest(TestCase):
    """Phase 2: staff see inline edit/cancel controls on other users' reservations
    in the browse list; non-staff see the unchanged plain-text listing."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="rowowner@example.com",
            password="pass",
            first_name="Bob",
            last_name="Jones",
        )
        self.admin = User.objects.create_user(
            email="rowadmin@example.com",
            password="pass",
            is_staff=True,
        )
        self.plain = User.objects.create_user(
            email="rowplain@example.com",
            password="pass",
        )
        self.env = Environment.objects.create(
            name="row-env",
            version="1.0",
            purpose="test",
            project="proj",
            use_case_tag="ci",
            owner=self.owner,
        )
        # Upcoming reservation within the 24h window (relative to real now).
        now = timezone.now()
        self.reservation = Reservation.objects.create(
            owner=self.owner,
            environment=self.env,
            during=Range(
                lower=now + timedelta(hours=1),
                upper=now + timedelta(hours=3),
                bounds="[)",
            ),
        )
        self.cancel_url = reverse("reservations:cancel", args=[self.reservation.pk])

    def test_staff_sees_inline_controls_for_other_users_reservation(self):
        self.client.login(email="rowadmin@example.com", password="pass")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.cancel_url, content)
        self.assertIn("Update duration", content)

    def test_non_staff_sees_no_controls(self):
        self.client.login(email="rowplain@example.com", password="pass")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(self.cancel_url, content)
        self.assertNotIn("Update duration", content)
