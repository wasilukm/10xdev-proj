from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from catalog.models import Environment
from catalog.services import build_row_context
from .forms import ReservationForm
from .models import Reservation
from . import services


def _row_response(request, env, form=None, conflict_message=None, next_free=None):
    if form is None:
        form = ReservationForm(initial={"environment": env.pk})
    ctx = build_row_context(env)
    ctx.update({
        "booking_form": form,
        "conflict_message": conflict_message,
        "next_free": next_free,
    })
    return render(request, "catalog/_environment_row.html", ctx)


@login_required
@require_POST
def reservation_create(request):
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
                owner=request.user,
                environment=env,
                during=during,
            )
    except IntegrityError as e:
        cause = str(getattr(e, "__cause__", "") or e)
        if "reservation_no_overlap" in cause:
            conflict = (
                Reservation.objects
                .select_related("owner")
                .filter(environment=env, during__overlap=during)
                .first()
            )
            if conflict:
                owner_label = conflict.owner.get_full_name() or conflict.owner.email
                conflict_message = (
                    f"Conflicts with {owner_label}'s reservation "
                    f"({conflict.during.lower:%Y-%m-%d %H:%M} – {conflict.during.upper:%Y-%m-%d %H:%M})"
                )
            next_free = services.next_free_window(env, start)
        else:
            conflict_message = "Invalid reservation range — please check your start time and duration."

    return _row_response(request, env, conflict_message=conflict_message, next_free=next_free)
