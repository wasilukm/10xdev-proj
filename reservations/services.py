from datetime import timedelta

from django.db.models import Func
from django.db.models.fields import DateTimeField

from .models import Reservation

MAX_DURATION = timedelta(hours=4)


def _qs_starting_at_or_after(env, start):
    """Return a queryset of reservations for env with lower bound >= start, ordered by lower bound.

    DateTimeRangeField does not support 'lower__gte' — use lower() via Func annotation instead.
    """
    return (
        Reservation.objects
        .annotate(lower_bound=Func("during", function="lower", output_field=DateTimeField()))
        .filter(environment=env, lower_bound__gte=start)
        .order_by("lower_bound")
    )


def next_reservation_after(env, start):
    """Return the first reservation for env whose lower bound is >= start, or None."""
    return _qs_starting_at_or_after(env, start).first()


def compute_end(env, start, duration_choice, custom_hours=None):
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
        return start + timedelta(hours=float(custom_hours))
    if duration_choice == "until_next":
        cap = start + MAX_DURATION
        nxt = next_reservation_after(env, start)
        if nxt is None:
            return cap
        # Half-open: [start, nxt.lower) is adjacent to [nxt.lower, ...) — not an overlap.
        return min(nxt.during.lower, cap)
    raise ValueError(f"Unknown duration_choice: {duration_choice!r}")


def describe_overlap_conflict(env, during, exclude_pk=None):
    """Return a human-readable conflict message for a reservation_no_overlap violation, or None."""
    qs = (
        Reservation.objects
        .select_related("owner")
        .filter(environment=env, during__overlap=during)
        .order_by("during")
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    conflict = qs.first()
    if conflict is None:
        return None
    owner_label = conflict.owner.get_full_name() or conflict.owner.email
    return (
        f"Conflicts with {owner_label}'s reservation "
        f"({conflict.during.lower:%Y-%m-%d %H:%M} – {conflict.during.upper:%Y-%m-%d %H:%M})"
    )


def next_free_window(env, after):
    """Return the earliest datetime at or after `after` when env has no reservation.

    Follows contiguous or back-to-back blocks to find the true gap start.
    """
    containing = (
        Reservation.objects
        .filter(environment=env, during__contains=after)
        .first()
    )

    free = containing.during.upper if containing else after

    for r in _qs_starting_at_or_after(env, after):
        if r.during.lower <= free:
            if r.during.upper > free:
                free = r.during.upper
        else:
            break

    return free
