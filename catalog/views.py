from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reservations.forms import ReservationForm
from reservations.services import active_or_upcoming_reservations

from .forms import EnvironmentForm
from .models import Environment
from .permissions import staff_required
from .services import (
    build_row_context,
    delete_environment,
    filter_environments,
    filter_options,
    manage_environments,
    prefetch_reservations_for_list,
)


@login_required
def environment_list(request: HttpRequest) -> HttpResponse:
    now = timezone.now()

    availability = request.GET.get("availability", "")
    project = request.GET.get("project", "")
    use_case_tag = request.GET.get("use_case_tag", "")
    filters = {
        "availability": availability,
        "project": project,
        "use_case_tag": use_case_tag,
    }

    envs = (
        Environment.objects.select_related("owner")
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
        row: dict[str, Any] = dict(build_row_context(env, now=now))
        row["booking_form"] = ReservationForm(initial={"environment": env.pk})
        rows.append(row)

    if request.headers.get("HX-Request"):
        return render(
            request,
            "catalog/_environment_results.html",
            {
                "rows": rows,
                "filters": filters,
            },
        )

    return render(
        request,
        "catalog/environment_list.html",
        {
            "rows": rows,
            "filters": filters,
            "options": filter_options(),
        },
    )


@staff_required
def environment_manage(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "catalog/environment_manage.html",
        {"environments": manage_environments()},
    )


@staff_required
def environment_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = EnvironmentForm(request.POST)
        if form.is_valid():
            env = form.save()
            messages.success(request, f"Environment “{env.name}” created.")
            return redirect("env_manage")
    else:
        form = EnvironmentForm(initial={"owner": request.user})

    return render(
        request,
        "catalog/environment_form.html",
        {"form": form, "mode": "create"},
    )


# Number of affected reservations to list inline in the edit warning before
# collapsing the remainder into a "+N more" note.
_AFFECTED_PREVIEW = 5


@staff_required
def environment_edit(request: HttpRequest, pk: int) -> HttpResponse:
    env = get_object_or_404(Environment, pk=pk)

    if request.method == "POST":
        form = EnvironmentForm(request.POST, instance=env)
        if form.is_valid():
            affected = active_or_upcoming_reservations(env)
            # Two-step warning: when active/upcoming reservations exist and the
            # staff user hasn't yet confirmed, re-render the form with the list
            # of affected reservations and a hidden confirm flag instead of saving.
            if not request.POST.get("confirm") and affected.exists():
                preview = list(affected[:_AFFECTED_PREVIEW])
                more = max(affected.count() - _AFFECTED_PREVIEW, 0)
                return render(
                    request,
                    "catalog/environment_form.html",
                    {
                        "form": form,
                        "mode": "edit",
                        "env": env,
                        "affected": preview,
                        "affected_more": more,
                        "needs_confirm": True,
                    },
                )
            env = form.save()
            messages.success(request, f"Environment “{env.name}” updated.")
            return redirect("env_manage")
    else:
        form = EnvironmentForm(instance=env)

    return render(
        request,
        "catalog/environment_form.html",
        {"form": form, "mode": "edit", "env": env},
    )


@staff_required
def environment_delete(request: HttpRequest, pk: int) -> HttpResponse:
    env = get_object_or_404(Environment, pk=pk)
    blocking = active_or_upcoming_reservations(env)

    if request.method == "POST":
        outcome = delete_environment(env)
        if outcome == "DELETED":
            messages.success(request, f"Environment “{env.name}” deleted.")
            return redirect("env_manage")
        # BLOCKED: a reservation is (or raced into being) active/upcoming.
        blocking = active_or_upcoming_reservations(env)

    return render(
        request,
        "catalog/environment_confirm_delete.html",
        {"env": env, "blocking": list(blocking), "is_blocked": blocking.exists()},
    )
