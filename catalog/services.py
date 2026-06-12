from datetime import timedelta

from django.utils import timezone
from django.db.models import Exists, OuterRef, Prefetch
from psycopg.types.range import Range

from reservations.models import Reservation

from .models import Environment


def build_row_context(env, now=None):
    """Return context dict for a single env row partial."""
    if now is None:
        now = timezone.now()

    horizon = now + timedelta(hours=24)
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


def filter_environments(queryset, *, availability=None, project=None, use_case_tag=None, now):
    if project:
        queryset = queryset.filter(project=project)
    if use_case_tag:
        queryset = queryset.filter(use_case_tag=use_case_tag)
    if availability in ("free", "busy"):
        # Exists subquery: does a reservation cover this exact instant?
        busy = Reservation.objects.filter(environment=OuterRef("pk"), during__contains=now)
        queryset = queryset.annotate(_busy=Exists(busy))
        queryset = queryset.filter(_busy=(availability == "busy"))
    return queryset


def filter_options():
    projects = list(
        Environment.objects.values_list("project", flat=True).distinct().order_by("project")
    )
    use_case_tags = list(
        Environment.objects.values_list("use_case_tag", flat=True).distinct().order_by("use_case_tag")
    )
    return {"projects": projects, "use_case_tags": use_case_tags}


def prefetch_reservations_for_list(now):
    """Return a Prefetch for the 24h reservation window, for use on an Environment queryset."""
    horizon = now + timedelta(hours=24)
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
