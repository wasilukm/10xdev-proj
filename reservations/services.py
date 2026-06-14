from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, cast

from django.db.models import Func, QuerySet
from django.db.models.fields import DateTimeField
from psycopg.types.range import Range

from catalog.models import Environment

from .models import Reservation

MAX_DURATION = timedelta(hours=4)


def _qs_starting_at_or_after(
    env: Environment, start: datetime
) -> QuerySet[Reservation]:
    """Return a queryset of reservations for env with lower bound >= start, ordered by lower bound.

    DateTimeRangeField does not support 'lower__gte' — use lower() via Func annotation instead.
    """
    return (
        Reservation.objects.annotate(
            lower_bound=Func("during", function="lower", output_field=DateTimeField())
        )
        .filter(environment=env, lower_bound__gte=start)
        .order_by("lower_bound")
    )


def next_reservation_after(env: Environment, start: datetime) -> Reservation | None:
    """Return the first reservation for env whose lower bound is >= start, or None."""
    return _qs_starting_at_or_after(env, start).first()


def compute_end(
    env: Environment,
    start: datetime,
    duration_choice: Literal["1h", "2h", "4h", "custom", "until_next"],
    custom_hours: Decimal | None = None,
) -> datetime:
    """Return end datetime for a reservation given a duration choice.

    duration_choice values: '1h', '2h', '4h', 'custom', 'until_next'
    For 'until_next': end = min(next reservation start, start + MAX_DURATION),
    falling back to start + MAX_DURATION when no subsequent reservation exists.
    """
    if duration_choice == "1h":
        return start + timedelta(hours=1)
    if duration_choice == "2h":
        return start + timedelta(hours=2)
    if duration_choice == "4h":
        return start + timedelta(hours=4)
    if duration_choice == "custom":
        assert custom_hours is not None
        return start + timedelta(hours=float(custom_hours))
    if duration_choice == "until_next":
        cap = start + MAX_DURATION
        nxt = next_reservation_after(env, start)
        if nxt is None:
            return cap
        # Half-open: [start, nxt.lower) is adjacent to [nxt.lower, ...) — not an overlap.
        return min(cast(datetime, nxt.during.lower), cap)
    raise ValueError(f"Unknown duration_choice: {duration_choice!r}")


def describe_overlap_conflict(
    env: Environment,
    during: Range[datetime],
    exclude_pk: int | None = None,
) -> str | None:
    """Return a human-readable conflict message for a reservation_no_overlap violation, or None."""
    qs = (
        Reservation.objects.select_related("owner")
        .filter(environment=env, during__overlap=during)
        .order_by("during")
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    conflict = qs.first()
    if conflict is None:
        return None
    owner_label = conflict.owner.get_full_name() or conflict.owner.email
    lower = cast(datetime, conflict.during.lower)
    upper = cast(datetime, conflict.during.upper)
    return (
        f"Conflicts with {owner_label}'s reservation "
        f"({lower:%Y-%m-%d %H:%M} – {upper:%Y-%m-%d %H:%M})"
    )


def next_free_window(env: Environment, after: datetime) -> datetime:
    """Return the earliest datetime at or after `after` when env has no reservation.

    Follows contiguous or back-to-back blocks to find the true gap start.
    """
    containing = Reservation.objects.filter(
        environment=env, during__contains=after
    ).first()

    free: datetime = cast(datetime, containing.during.upper) if containing else after

    for r in _qs_starting_at_or_after(env, after):
        lower = cast(datetime, r.during.lower)
        upper = cast(datetime, r.during.upper)
        if lower <= free:
            if upper > free:
                free = upper
        else:
            break

    return free
