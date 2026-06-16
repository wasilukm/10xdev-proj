"""Harness smoke test — proves live_server + auth cookie + seeded row cooperate.

Not the Risk #2 test: asserts nothing about the HTMX filter/reserve swap.
The Risk #2 test (find → filter → reserve → appears) is owned by /10x-e2e.
"""

import re

from playwright.sync_api import Page, expect


def test_smoke_authenticated(
    live_server, transactional_db, page: Page, auth_cookie, seeded_environment
):
    page.context.add_cookies([auth_cookie])
    page.goto(live_server.url)
    expect(page.get_by_text(seeded_environment.name)).to_be_visible()


def test_smoke_unauthenticated(live_server, transactional_db, page: Page):
    page.goto(live_server.url)
    expect(page).to_have_url(re.compile(r"/login"))
