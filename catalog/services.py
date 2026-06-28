from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, TypedDict, cast

from django.db import transaction
from django.db.models import Exists, Func, OuterRef, Prefetch, QuerySet
from django.db.models.deletion import ProtectedError
from django.db.models.fields import DateTimeField
from django.utils import timezone
from psycopg.types.range import Range

from reservations.models import Reservation
from reservations.services import active_or_upcoming_reservations

from .models import Environment

DeleteOutcome = Literal["DELETED", "BLOCKED"]


class RowContext(TypedDict):
    """Context for a single env row partial."""

    env: Environment
    is_busy: bool
    current_reservation: Reservation | None
    upcoming_reservations: list[Reservation]


def build_row_context(env: Environment, now: datetime | None = None) -> RowContext:
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
            env.reservations.select_related("owner")
            .filter(during__overlap=window)
            .order_by("during")
        )

    current = next(
        (
            r
            for r in upcoming
            if cast(datetime, r.during.lower) <= now < cast(datetime, r.during.upper)
        ),
        None,
    )

    return {
        "env": env,
        "is_busy": current is not None,
        "current_reservation": current,
        "upcoming_reservations": [r for r in upcoming if r is not current],
    }


def filter_environments(
    queryset: QuerySet[Environment],
    *,
    availability: str | None = None,
    project: str | None = None,
    use_case_tag: str | None = None,
    now: datetime,
) -> QuerySet[Environment]:
    if project:
        queryset = queryset.filter(project=project)
    if use_case_tag:
        queryset = queryset.filter(use_case_tag=use_case_tag)
    if availability in ("free", "busy"):
        # Exists subquery: does a reservation cover this exact instant?
        busy = Reservation.objects.filter(
            environment=OuterRef("pk"), during__contains=now
        )
        queryset = queryset.annotate(_busy=Exists(busy))
        queryset = queryset.filter(_busy=(availability == "busy"))
    return queryset


def filter_options() -> dict[str, list[str]]:
    projects = list(
        Environment.objects.values_list("project", flat=True)
        .distinct()
        .order_by("project")
    )
    use_case_tags = list(
        Environment.objects.values_list("use_case_tag", flat=True)
        .distinct()
        .order_by("use_case_tag")
    )
    return {"projects": projects, "use_case_tags": use_case_tags}


def manage_environments() -> QuerySet[Environment]:
    """Return the environment queryset for the staff manage table."""
    return Environment.objects.select_related("owner").order_by("name")


def prefetch_reservations_for_list(now: datetime) -> Prefetch:
    """Return a Prefetch for the 24h reservation window, for use on an Environment queryset."""
    horizon = now + timedelta(hours=24)
    window = Range(now, horizon, "[)")
    return Prefetch(
        "reservations",
        queryset=(
            Reservation.objects.select_related("owner")
            .filter(during__overlap=window)
            .order_by("during")
        ),
    )


def delete_environment(env: Environment, now: datetime | None = None) -> DeleteOutcome:
    """Delete env iff it has no active/upcoming reservations; cascade its past ones.

    FR-007: an env may only be deleted while no reservation is active or upcoming.
    `Reservation.environment` is PROTECT, so past reservations would otherwise block
    deletion — we delete those past rows first, then the env.

    Race safety: the active/upcoming check and the delete run inside one atomic
    block. If a reservation races in between the check and `env.delete()`, PROTECT
    raises ProtectedError, which we catch and report as BLOCKED — so the guard holds
    without row locking.
    """
    if now is None:
        now = timezone.now()

    with transaction.atomic():
        if active_or_upcoming_reservations(env, now).exists():
            return "BLOCKED"
        # Only past reservations remain; clear them so PROTECT permits the delete.
        Reservation.objects.annotate(
            upper_bound=Func("during", function="upper", output_field=DateTimeField()),
        ).filter(environment=env, upper_bound__lte=now).delete()
        try:
            env.delete()
        except ProtectedError:
            return "BLOCKED"
    return "DELETED"
