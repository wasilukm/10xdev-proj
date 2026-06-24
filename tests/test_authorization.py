"""Cross-cutting authorization guards (test-plan §3 Phase 2, Risk #3).

This module lives at project level because it spans both `catalog` and
`reservations` routes — it has no single owning app (test-plan §6.2).

The route inventory below is the explicit, hand-maintained list of every gated
(`@login_required`) route. It is the antidote to the "siblings are guarded too"
anti-pattern: a newly added view that forgets its decorator stays invisible until
someone remembers to test it. Keep this list in sync with `catalog/urls.py` and
`reservations/urls.py` — **add every new `@login_required` route here.**
"""

import unittest

from django.test import TestCase
from django.urls import reverse

# Every gated route, as (reverse-able name, kwargs). A synthetic pk is fine for
# parameterized routes: `@login_required` is the outermost decorator, so the
# anonymous request is denied before the object lookup ever runs (it never
# reaches the 404). Keep aligned with catalog/urls.py + reservations/urls.py.
GATED_ROUTES = [
    ("home", {}),
    ("reservations:create", {}),
    ("reservations:mine", {}),
    ("reservations:edit", {"pk": 1}),
    ("reservations:cancel", {"pk": 1}),
]


class GatedRouteAuthTest(TestCase):
    """Assert every inventoried gated route denies anonymous access."""

    def _anon_denied(self, url):
        """Issue an anonymous request and assert it is denied.

        Tries GET first; on a 405 (a `@require_POST` route) retries with POST so
        the inventory needs no per-route method column. Because `login_required`
        is outermost, the auth redirect fires for either method before
        `require_POST` can return its 405 — the retry only matters if a future
        route flips that ordering. Denial is a login redirect (302/301 whose
        Location names the login URL) or a hard 403/404.
        """
        resp = self.client.get(url)
        if resp.status_code == 405:
            resp = self.client.post(url)
        if resp.status_code in (301, 302):
            self.assertIn(
                reverse("login"),
                resp["Location"],
                msg=f"{url} redirected, but not to login",
            )
        else:
            self.assertIn(
                resp.status_code,
                (403, 404),
                msg=f"{url} returned {resp.status_code}; expected login redirect or 403/404",
            )

    def test_inventory_non_empty(self):
        """Guard against an empty inventory silently passing every other test."""
        self.assertGreater(len(GATED_ROUTES), 0)

    def test_all_gated_routes_deny_anonymous(self):
        """Anonymous access to every gated route is denied (data-driven)."""
        for name, kwargs in GATED_ROUTES:
            url = reverse(name, kwargs=kwargs)
            with self.subTest(route=name):
                self._anon_denied(url)

    @unittest.skip(
        "admin-vs-non-admin boundary lands with roadmap S-06 "
        "(admin-reservation-override); no first-party admin surface exists yet — "
        "see test-plan §7"
    )
    def test_admin_only_action_rejects_non_admin(self):
        """Deferred: admin-only actions must reject non-admins (Risk #3 clause).

        Filled when S-06 introduces the first first-party admin surface; until
        then this records the open clause in test output rather than omitting it.
        """
        self.fail("placeholder — implement when S-06 admin surface exists")
