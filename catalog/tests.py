from django.test import TestCase

from accounts.models import User
from catalog.models import Environment


class EnvironmentModelTest(TestCase):
    def test_create_and_str(self):
        user = User.objects.create_user(username="owner", password="pass")
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
