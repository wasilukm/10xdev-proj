"""Risk #2 — the find → filter → reserve → appears-without-reload critical path.

This file is both the project's Risk #2 e2e coverage (test-plan.md §2 Risk #2,
§6.3 reference) and the `/10x-e2e` *seed exemplar* — the test every future e2e is
modeled on. What it demonstrates, future generations inherit:

  * role-based, row-scoped locators (never CSS / XPath / DOM structure);
  * wait for state via expect(...), never page.wait_for_timeout();
  * auth without the UI (injected session cookie fixture);
  * unique, collision-free seed data (uuid-suffixed fixtures);
  * assertions that fail when the risk materializes (verified by deliberate break).

Two cases — both mandated by test-plan §6.6:
  1. happy path  — a real reservation appears in the live DOM with no full reload;
  2. conflict    — an overlapping attempt is refused in-page with the *named*
                   conflict message, and no second row is silently written.

Row scoping is non-negotiable here: every row reuses the same booking-form ids
({{ booking_form.as_p }}) and the nav renders the logged-in user's name globally
(base.html), so a page-wide locator would match the wrong element.
"""

import re
from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import Page, expect

from reservations.models import Reservation


def test_reservation_appears_without_reload(
    live_server,
    transactional_db,
    page: Page,
    auth_cookie_and_user,
    bookable_environment,
):
    cookie, user = auth_cookie_and_user
    env = bookable_environment

    page.context.add_cookies([cookie])
    page.goto(live_server.url)

    # A full page reload wipes window state; an HTMX swap does not. This marker,
    # checked at the end, is the direct proof of "without a full page reload".
    page.evaluate("window.__noReload = true")

    # find → filter: narrow to this env by its unique project (HTMX swaps #env-results).
    page.get_by_label("Project").select_option(env.project)
    page.get_by_role("button", name="Filter").click()
    row = page.locator(f"#env-row-{env.pk}")
    expect(row).to_be_visible()

    # pick → reserve: a future slot within the 24h window so the new reservation
    # renders in this row's "Upcoming" cell (build_row_context only surfaces
    # reservations overlapping [now, now+24h)).
    start = (timezone.localtime() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    row.get_by_label("Start").fill(start)
    row.get_by_label("Duration").select_option("1h")
    row.get_by_role("button", name="Book").click()

    # appears: the reserve action swaps the row in place (HTMX outerHTML) and the
    # new reservation — owned by the logged-in booker, whose name was NOT in this
    # row before — is now visible, with no full reload.
    expect(
        page.locator(f"#env-row-{env.pk}").get_by_text(user.get_full_name())
    ).to_be_visible()
    assert page.evaluate("window.__noReload") is True


def test_overlapping_reservation_rejected_with_named_conflict(
    live_server,
    transactional_db,
    page: Page,
    auth_cookie,
    reserved_environment,
):
    env = reserved_environment

    page.context.add_cookies([auth_cookie])
    page.goto(live_server.url)

    row = page.locator(f"#env-row-{env.pk}")
    expect(row).to_be_visible()

    # Attempt a booking that overlaps the existing far-future reservation.
    row.get_by_label("Start").fill("2030-01-01T12:00")
    row.get_by_label("Duration").select_option("2h")
    row.get_by_role("button", name="Book").click()

    # The row is swapped to show the NAMED conflict message in-page — naming the
    # other owner — never a 500 and never a silently committed second row.
    expect(
        page.locator(f"#env-row-{env.pk}").get_by_text(
            re.compile(r"Conflicts with .+'s reservation")
        )
    ).to_be_visible()
    assert Reservation.objects.filter(environment=env).count() == 1
