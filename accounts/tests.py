from django.test import TestCase
from django.urls import reverse

from .models import AllowedEmailDomain, User


class UserManagerTests(TestCase):
    def test_create_user_email_identity(self):
        user = User.objects.create_user(
            email="alice@example.com",
            password="pass1234",
            first_name="Alice",
            last_name="Smith",
        )
        self.assertEqual(user.email, "alice@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("pass1234"))

    def test_create_user_normalises_email(self):
        user = User.objects.create_user(email="Alice@EXAMPLE.COM", password="x")
        self.assertEqual(user.email, "Alice@example.com")

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="x")

    def test_create_superuser(self):
        su = User.objects.create_superuser(
            email="admin@example.com",
            password="admin1234",
            first_name="Admin",
            last_name="User",
        )
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)

    def test_create_superuser_rejects_is_staff_false(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="bad@example.com", password="x", is_staff=False
            )

    def test_create_superuser_rejects_is_superuser_false(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="bad2@example.com", password="x", is_superuser=False
            )


class AllowedEmailDomainTests(TestCase):
    def test_domain_lowercased_on_save(self):
        obj = AllowedEmailDomain.objects.create(domain="Example.COM")
        self.assertEqual(obj.domain, "example.com")

    def test_domain_uniqueness(self):
        AllowedEmailDomain.objects.create(domain="acme.com")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            AllowedEmailDomain.objects.create(domain="acme.com")


class SignUpFormTests(TestCase):
    def _form_data(self, email="user@allowed.com"):
        return {
            "email": email,
            "first_name": "Test",
            "last_name": "User",
            "password1": "N0t-a-simple-pass!",
            "password2": "N0t-a-simple-pass!",
        }

    def test_accepts_any_domain_when_table_empty(self):
        from .forms import SignUpForm
        form = SignUpForm(data=self._form_data("user@anydomain.org"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_accepts_matching_domain(self):
        AllowedEmailDomain.objects.create(domain="allowed.com")
        from .forms import SignUpForm
        form = SignUpForm(data=self._form_data("user@allowed.com"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_disallowed_domain(self):
        AllowedEmailDomain.objects.create(domain="allowed.com")
        from .forms import SignUpForm
        form = SignUpForm(data=self._form_data("user@other.com"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_first_and_last_name_required(self):
        from .forms import SignUpForm
        data = self._form_data()
        data["first_name"] = ""
        form = SignUpForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)


class SignUpViewTests(TestCase):
    SIGNUP_URL = "/accounts/signup/"

    def _post(self, email="user@example.com", first="Alice", last="Smith"):
        return self.client.post(self.SIGNUP_URL, {
            "email": email,
            "first_name": first,
            "last_name": last,
            "password1": "N0t-a-simple-pass!",
            "password2": "N0t-a-simple-pass!",
        }, secure=True)

    def test_successful_signup_creates_user_with_names(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="user@example.com")
        self.assertEqual(user.first_name, "Alice")
        self.assertEqual(user.last_name, "Smith")

    def test_successful_signup_logs_user_in(self):
        self._post()
        user = User.objects.get(email="user@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_disallowed_domain_returns_form_error(self):
        AllowedEmailDomain.objects.create(domain="allowed.com")
        response = self._post(email="user@other.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "approved email domains")


class AuthFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alice@example.com",
            password="N0t-a-simple-pass!",
            first_name="Alice",
            last_name="Smith",
        )

    def test_unauthenticated_root_redirects_to_login(self):
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_login_redirects_to_home(self):
        response = self.client.post("/accounts/login/", {
            "username": "alice@example.com",
            "password": "N0t-a-simple-pass!",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_logout_ends_session_and_home_gates(self):
        self.client.force_login(self.user)
        response = self.client.post("/accounts/logout/", secure=True)
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
