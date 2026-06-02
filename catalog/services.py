from django.utils import timezone
from django.db.models import Prefetch
from psycopg.types.range import Range

from reservations.models import Reservation


def build_row_context(env, now=None):
    """Return context dict for a single env row partial."""
    if now is None:
        now = timezone.now()

    horizon = now + timezone.timedelta(hours=24)
    window = Range(now, horizon, "[)")

    # In the list view the 24h window is already loaded by
    # prefetch_reservations_for_list; reuse that cache instead of re-querying
    # per env (avoids N+1). The create view calls this without a prefetch, so
    # fall back to a filtered query for the single-env case.
    if "reservations" in getattr(env, "_prefetched_objects_cache", {}):
        upcoming = list(env.reservations.all())
    else:
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
