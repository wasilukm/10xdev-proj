from datetime import UTC, datetime, timedelta

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from psycopg.types.range import Range

from accounts.models import User
from catalog.models import Environment
from catalog.services import build_row_context, filter_environments, filter_options
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
