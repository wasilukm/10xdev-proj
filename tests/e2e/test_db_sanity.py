"""Trivial DB-touching test — verifies pytest-django + Postgres wiring only."""

from accounts.models import User


def test_db_round_trip(transactional_db):
    user = User.objects.create_user(
        email="sanity@example.com",
        password="testpass123",
        first_name="Sanity",
        last_name="Check",
    )
    assert User.objects.filter(pk=user.pk).exists()
