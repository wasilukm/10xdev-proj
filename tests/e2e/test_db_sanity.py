"""Trivial DB-touching test — verifies pytest-django + Postgres wiring only."""

import pytest

from accounts.models import User


@pytest.mark.django_db(transaction=True)
def test_db_round_trip():
    user = User.objects.create_user(
        email="sanity@example.com",
        password="testpass123",
        first_name="Sanity",
        last_name="Check",
    )
    assert User.objects.filter(pk=user.pk).exists()
