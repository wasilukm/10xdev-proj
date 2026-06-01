from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

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

    rows = [build_row_context(env, now=now) for env in envs]

    return render(request, "catalog/environment_list.html", {"rows": rows})
