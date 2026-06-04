from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from reservations.forms import ReservationForm
from .models import Environment
from .services import build_row_context, filter_environments, filter_options, prefetch_reservations_for_list


@login_required
def environment_list(request):
    now = timezone.now()

    availability = request.GET.get("availability", "")
    project = request.GET.get("project", "")
    use_case_tag = request.GET.get("use_case_tag", "")
    filters = {"availability": availability, "project": project, "use_case_tag": use_case_tag}

    envs = (
        Environment.objects
        .select_related("owner")
        .prefetch_related(prefetch_reservations_for_list(now))
        .order_by("name")
    )
    envs = filter_environments(
        envs,
        availability=availability or None,
        project=project or None,
        use_case_tag=use_case_tag or None,
        now=now,
    )

    rows = []
    for env in envs:
        row = build_row_context(env, now=now)
        row["booking_form"] = ReservationForm(initial={"environment": env.pk})
        rows.append(row)

    return render(request, "catalog/environment_list.html", {
        "rows": rows,
        "filters": filters,
        "options": filter_options(),
    })
