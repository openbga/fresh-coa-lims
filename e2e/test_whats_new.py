"""What's new counts the changes since a person last looked; reading the list clears the count.

A new account has nothing to catch up on: it sees no count, and the list still shows everything.
"""

import re

import pytest
from django.contrib.auth.models import Group
from helpers import PASSWORD, browser_page, login
from playwright.sync_api import expect

from core.models import UserPreference
from whatsnew import catalogue

pytestmark = pytest.mark.django_db(transaction=True)


def test_open_whats_new_see_entries_and_the_indicator_clears(
    live_server, django_user_model, artifacts
):
    entries, errors = catalogue.load()
    assert len(entries) > 3 and not errors
    ids = sorted(e.id for e in entries)
    unseen = 3  # the person last looked before the three newest changes
    analyst = django_user_model.objects.create_user("whatsnew.analyst", password=PASSWORD)
    analyst.groups.add(Group.objects.get_or_create(name="analyst")[0])
    UserPreference.objects.create(user=analyst, key=catalogue.SEEN_KEY, value=ids[-unseen - 1])
    name = f"What's new: {unseen} new changes"
    with browser_page() as page:
        login(page, live_server, analyst)
        bar = page.locator(".vr-topbar")
        unread = bar.get_by_role("link", name=name, exact=True)
        expect(unread).to_be_visible()
        # The tooltip (Bootstrap moves the title into its own attribute).
        expect(unread).to_have_attribute("data-bs-original-title", name)
        expect(unread.locator("[data-whatsnew-unread]")).to_have_text(str(unseen))
        bar.screenshot(path=str(artifacts / "whats-new-indicator-light.png"))
        page.evaluate("localStorage.setItem('vr-theme', 'dark')")
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
        expect(unread).to_be_visible()  # reloading another page leaves the count as it was
        bar.screenshot(path=str(artifacts / "whats-new-indicator-dark.png"))
        page.evaluate("localStorage.setItem('vr-theme', 'light')")
        page.reload()

        unread.click()
        expect(page.get_by_role("heading", level=1)).to_have_text("What's new")
        expect(page).to_have_title("What's new · OpenBGA QM LIMS")
        newest = max(entries, key=lambda e: e.id)
        expect(page.get_by_role("heading", name=f"{newest.date:%B %Y}", exact=True)).to_be_visible()
        expect(page.locator("[data-whatsnew-entry]")).to_have_count(len(entries))
        expect(page.get_by_text(f"{unseen} changes are new since you last opened")).to_be_visible()
        for entry_id in ids[-unseen:]:
            entry = page.locator(f'[data-whatsnew-entry="{entry_id}"]')
            expect(entry.get_by_text("New", exact=True)).to_be_visible()
        page.locator(f'[data-whatsnew-entry="{ids[-1]}"]').scroll_into_view_if_needed()
        page.screenshot(path=str(artifacts / "whats-new-list-new-light.png"))
        older = page.locator(f'[data-whatsnew-entry="{ids[-unseen - 1]}"]')
        expect(older.get_by_text("New", exact=True)).to_have_count(0)

        # The indicator in the bar is already clear.
        cleared = bar.get_by_role("link", name="What's new", exact=True)
        expect(cleared).to_have_attribute("aria-current", "page")
        expect(cleared.locator("[data-whatsnew-unread]")).to_have_count(0)

        # Technical notes open and close from the keyboard.
        notes = page.locator("[data-whatsnew-notes]").first
        notes.locator("summary").focus()
        page.keyboard.press("Enter")
        expect(notes).to_have_attribute("open", "")
        page.keyboard.press("Enter")
        expect(notes).not_to_have_attribute("open", "")
        page.screenshot(path=str(artifacts / "whats-new-list-light.png"))

        page.evaluate("localStorage.setItem('vr-theme', 'dark')")
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
        # Back on the list, nothing is new any more.
        expect(page.get_by_text(re.compile(r"new since you last"))).to_have_count(0)
        page.screenshot(path=str(artifacts / "whats-new-list-dark.png"))
        page.goto(live_server.url + "/")
        expect(bar.get_by_role("link", name="What's new", exact=True)).to_be_visible()


def test_a_new_account_sees_no_count_and_the_whole_list(live_server, django_user_model):
    entries, _errors = catalogue.load()
    newcomer = django_user_model.objects.create_user("whatsnew.newcomer", password=PASSWORD)
    newcomer.groups.add(Group.objects.get_or_create(name="quality")[0])
    with browser_page() as page:
        login(page, live_server, newcomer)
        link = page.locator(".vr-topbar").get_by_role("link", name="What's new", exact=True)
        expect(link).to_be_visible()
        expect(link.locator("[data-whatsnew-unread]")).to_have_count(0)
        link.click()
        expect(page.locator("[data-whatsnew-entry]")).to_have_count(len(entries))
        expect(page.get_by_text("New", exact=True)).to_have_count(0)
