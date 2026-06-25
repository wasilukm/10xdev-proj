from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden


def staff_required(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """Gate a view on staff access.

    Anonymous users are redirected to login (via login_required); authenticated
    non-staff users get 403. Wraps the staff check first so login_required runs
    outermost and handles the anonymous redirect.
    """

    @wraps(view)
    def _wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access required.")
        return view(request, *args, **kwargs)

    return login_required(_wrapped)
