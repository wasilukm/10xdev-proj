from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from reservations.forms import ReservationForm
from .models import Environment
from .services import build_row_context, prefetch_reservations_for_list


@login_required
def environment_list(request):
    now = timezone.now()
    envs = (
        Environment.objects
        .select_related("owner")
        .prefetch_related(prefetch_reservations_for_list(now))
        .order_by("name")
    )

    rows = []
    for env in envs:
        row = build_row_context(env, now=now)
        row["booking_form"] = ReservationForm(initial={"environment": env.pk})
        rows.append(row)

    return render(request, "catalog/environment_list.html", {"rows": rows})
