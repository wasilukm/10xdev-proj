from django.utils import timezone
from django.db.models import Prefetch
from psycopg.types.range import Range

from reservations.models import Reservation


def _now_horizon(now):
    return now, now + timezone.timedelta(hours=24)


def build_row_context(env, now=None):
    """Return context dict for a single env row partial."""
    if now is None:
        now = timezone.now()

    horizon = now + timezone.timedelta(hours=24)
    window = Range(now, horizon, "[)")

    upcoming = list(
        env.reservations
        .select_related("owner")
        .filter(during__overlap=window)
        .order_by("during")
    )

    current = next(
        (r for r in upcoming if r.during.lower <= now < r.during.upper),
        None,
    )

    return {
        "env": env,
        "is_busy": current is not None,
        "current_reservation": current,
        "upcoming_reservations": [r for r in upcoming if r is not current],
    }


def prefetch_reservations_for_list(now):
    """Return a Prefetch for the 24h reservation window, for use on an Environment queryset."""
    horizon = now + timezone.timedelta(hours=24)
    window = Range(now, horizon, "[)")
    return Prefetch(
        "reservations",
        queryset=(
            Reservation.objects
            .select_related("owner")
            .filter(during__overlap=window)
            .order_by("during")
        ),
    )
