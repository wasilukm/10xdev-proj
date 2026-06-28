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

from . import services
from .forms import ReservationEditForm, ReservationForm
from .models import Reservation


def _row_response(
    request: HttpRequest,
    env: Environment,
    form: ReservationForm | None = None,
    conflict_message: str | None = None,
    next_free: datetime | None = None,
    edit_pk: int | None = None,
    edit_form: ReservationEditForm | None = None,
) -> HttpResponse:
    if form is None:
        form = ReservationForm(initial={"environment": env.pk})
    ctx: dict[str, Any] = dict(build_row_context(env))
    ctx.update(
        {
            "booking_form": form,
            "conflict_message": conflict_message,
            "next_free": next_free,
        }
    )
    ctx.update(admin_row_items(request, ctx, edit_pk=edit_pk, edit_form=edit_form))
    return render(request, "catalog/_environment_row.html", ctx)


def _reservation_for_request(request: HttpRequest, pk: int) -> Reservation:
    """Fetch a reservation the request is allowed to mutate.

    Admins (staff/superuser) may manage any reservation; everyone else is
    scoped to their own. A non-admin requesting another user's reservation
    gets a 404 via the owner filter.
    """
    if services.is_reservation_admin(request.user):
        return get_object_or_404(Reservation, pk=pk)
    return get_object_or_404(Reservation, pk=pk, owner=request.user)


def _is_row_request(request: HttpRequest) -> bool:
    """True when an admin acts on a reservation from the browse env-row.

    The inline env-row controls post a hidden ``row`` field; on those requests
    edit/cancel re-render the whole env row instead of the item partial, so the
    Busy/Free badge and owner/time line update in place.
    """
    return bool(request.POST.get("row")) and services.is_reservation_admin(request.user)


def build_reservation_item(
    reservation: Reservation,
    form: ReservationEditForm | None = None,
    conflict_message: str | None = None,
) -> dict[str, Any]:
    now = timezone.now()
    if form is None:
        hours = round(
            (reservation.during.upper - reservation.during.lower).total_seconds()
            / 3600,
            2,
        )
        form = ReservationEditForm(
            initial={"hours": hours}, start=reservation.during.lower
        )
    return {
        "reservation": reservation,
        "form": form,
        "conflict_message": conflict_message,
        "is_editable": reservation.during.upper > now,
        "is_active": reservation.during.lower <= now,
    }


def admin_row_items(
    request: HttpRequest,
    row_ctx: dict[str, Any],
    edit_pk: int | None = None,
    edit_form: ReservationEditForm | None = None,
) -> dict[str, Any]:
    """Build per-reservation item contexts for the env row, for admin viewers only.

    Returns {current_item, upcoming_items} so the row template can render the
    edit/cancel controls inline. Non-admins get an empty dict (template falls
    back to the plain-text listing).

    When ``edit_pk``/``edit_form`` are given, the matching reservation's item
    uses that bound form instead of a fresh one, so a rejected inline edit
    re-renders the whole row with the validation error still attached.
    """
    if not services.is_reservation_admin(request.user):
        return {}
    current = row_ctx.get("current_reservation")
    upcoming = row_ctx.get("upcoming_reservations", [])

    def _item(reservation: Reservation) -> dict[str, Any]:
        form = edit_form if edit_pk is not None and reservation.pk == edit_pk else None
        return build_reservation_item(reservation, form=form)

    return {
        "current_item": _item(current) if current else None,
        "upcoming_items": [_item(r) for r in upcoming],
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
        build_reservation_item(reservation, form, conflict_message),
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
            conflict_message = (
                "Invalid reservation range — please check your start time and duration."
            )
        else:
            raise

    return _row_response(
        request, env, conflict_message=conflict_message, next_free=next_free
    )


@login_required
def my_reservations(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    reservations = (
        Reservation.objects.annotate(
            lower_bound=Func("during", function="lower", output_field=DateTimeField()),
            upper_bound=Func("during", function="upper", output_field=DateTimeField()),
        )
        .filter(owner=request.user, upper_bound__gt=now)  # type: ignore[misc]
        .select_related("environment")
        .order_by("lower_bound")
    )
    items = [build_reservation_item(r) for r in reservations]
    return render(request, "reservations/my_reservations.html", {"items": items})


@login_required
@require_POST
def reservation_edit(request: HttpRequest, pk: int) -> HttpResponse:
    reservation = _reservation_for_request(request, pk)
    now = timezone.now()
    if reservation.during.upper <= now:
        raise Http404

    form = ReservationEditForm(request.POST, start=reservation.during.lower)
    if not form.is_valid():
        if _is_row_request(request):
            return _row_response(
                request,
                reservation.environment,
                edit_pk=reservation.pk,
                edit_form=form,
            )
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

    if _is_row_request(request):
        return _row_response(
            request, reservation.environment, conflict_message=conflict_message
        )
    return _item_response(request, reservation, conflict_message=conflict_message)


@login_required
@require_POST
def reservation_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    reservation = _reservation_for_request(request, pk)
    if reservation.during.upper <= timezone.now():
        raise Http404
    environment = reservation.environment
    reservation.delete()
    if _is_row_request(request):
        return _row_response(request, environment)
    return HttpResponse("")
