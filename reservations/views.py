from __future__ import annotations

from datetime import datetime
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Func
from django.db.models.fields import DateTimeField
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalog.models import Environment
from catalog.services import build_row_context
from .forms import ReservationEditForm, ReservationForm
from .models import Reservation
from . import services


def _row_response(
    request: HttpRequest,
    env: Environment,
    form: ReservationForm | None = None,
    conflict_message: str | None = None,
    next_free: datetime | None = None,
) -> HttpResponse:
    if form is None:
        form = ReservationForm(initial={"environment": env.pk})
    ctx = build_row_context(env)
    ctx.update({
        "booking_form": form,
        "conflict_message": conflict_message,
        "next_free": next_free,
    })
    return render(request, "catalog/_environment_row.html", ctx)


def _item_context(
    reservation: Reservation,
    form: ReservationEditForm | None = None,
    conflict_message: str | None = None,
) -> dict[str, Any]:
    now = timezone.now()
    if form is None:
        hours = round((reservation.during.upper - reservation.during.lower).total_seconds() / 3600, 2)
        form = ReservationEditForm(initial={"hours": hours}, start=reservation.during.lower)
    return {
        "reservation": reservation,
        "form": form,
        "conflict_message": conflict_message,
        "is_editable": reservation.during.upper > now,
        "is_active": reservation.during.lower <= now,
    }


def _item_response(
    request: HttpRequest,
    reservation: Reservation,
    form: ReservationEditForm | None = None,
    conflict_message: str | None = None,
) -> HttpResponse:
    return render(
        request,
        "reservations/_reservation_item.html",
        _item_context(reservation, form, conflict_message),
    )


@login_required
@require_POST
def reservation_create(request: HttpRequest) -> HttpResponse:
    form = ReservationForm(request.POST)

    if not form.is_valid():
        env_id = request.POST.get("environment")
        env = get_object_or_404(Environment, pk=env_id)
        return _row_response(request, env, form=form)

    env = form.cleaned_data["environment"]
    during = form.cleaned_data["during"]
    start = form.cleaned_data["start"]

    conflict_message = None
    next_free = None

    try:
        with transaction.atomic():
            Reservation.objects.create(
                owner=request.user,  # type: ignore[misc]
                environment=env,
                during=during,
            )
    except IntegrityError as e:
        cause = str(getattr(e, "__cause__", "") or e)
        if "reservation_no_overlap" in cause:
            conflict_message = services.describe_overlap_conflict(env, during)
            next_free = services.next_free_window(env, start)
        elif "reservation_during_bounded" in cause:
            conflict_message = "Invalid reservation range — please check your start time and duration."
        else:
            raise

    return _row_response(request, env, conflict_message=conflict_message, next_free=next_free)


@login_required
def my_reservations(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    reservations = (
        Reservation.objects
        .annotate(
            lower_bound=Func("during", function="lower", output_field=DateTimeField()),
            upper_bound=Func("during", function="upper", output_field=DateTimeField()),
        )
        .filter(owner=request.user, upper_bound__gt=now)  # type: ignore[misc]
        .select_related("environment")
        .order_by("lower_bound")
    )
    items = [_item_context(r) for r in reservations]
    return render(request, "reservations/my_reservations.html", {"items": items})


@login_required
@require_POST
def reservation_edit(request: HttpRequest, pk: int) -> HttpResponse:
    reservation = get_object_or_404(Reservation, pk=pk, owner=request.user)
    now = timezone.now()
    if reservation.during.upper <= now:
        raise Http404

    form = ReservationEditForm(request.POST, start=reservation.during.lower)
    if not form.is_valid():
        return _item_response(request, reservation, form=form)

    during = form.cleaned_data["during"]
    original_during = reservation.during
    conflict_message = None

    try:
        with transaction.atomic():
            reservation.during = during
            reservation.save(update_fields=["during"])
    except IntegrityError as e:
        reservation.during = original_during
        cause = str(getattr(e, "__cause__", "") or e)
        if "reservation_no_overlap" in cause:
            conflict_message = services.describe_overlap_conflict(
                reservation.environment, during, exclude_pk=reservation.pk
            )
        elif "reservation_during_bounded" in cause:
            conflict_message = "Invalid reservation range — please check your duration."
        else:
            raise

    return _item_response(request, reservation, conflict_message=conflict_message)


@login_required
@require_POST
def reservation_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    reservation = get_object_or_404(Reservation, pk=pk, owner=request.user)
    if reservation.during.upper <= timezone.now():
        raise Http404
    reservation.delete()
    return HttpResponse("")
