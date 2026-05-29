from django.test import TestCase

from .models import User


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
