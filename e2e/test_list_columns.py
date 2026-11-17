"""A list's column layout is saved per user on the server: a column hidden in one browser stays
hidden after signing out and signing in again in another browser context."""

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from helpers import db_call, sign_in
from playwright.sync_api import expect, sync_playwright

from core.models import RuleSet
from quality.models import Lot

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-columns-2026!"


def test_hidden_column_follows_the_user(live_server, django_user_model):
    def fixture():
        user = django_user_model.objects.create_user("columns-reader", password=PASSWORD)
        user.groups.add(Group.objects.get_or_create(name="auditor")[0])
        rules = RuleSet.objects.create(
            code="columns-rules",
            segment="synthetic",
            status="approved",
            effective_from=timezone.now(),
            author=user,
        )
        Lot.objects.create(
            number="SYN-COLUMNS-001", material="Synthetic", rules=rules, created_by=user
        )

    db_call(fixture)
    supplier = 'th[data-vr-col="supplier"]'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        first = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        sign_in(first, live_server.url, "columns-reader", PASSWORD)
        first.goto(live_server.url + "/lots/")
        expect(first.locator(supplier)).to_be_visible()
        first.get_by_role("button", name="Columns", exact=True).click()
        dialog = first.get_by_role("dialog", name="Columns")
        dialog.get_by_role("checkbox", name="Supplier", exact=True).uncheck()
        with first.expect_response(
            lambda r: "/preferences" in r.url and r.request.method == "POST"
        ):
            dialog.get_by_role("button", name="Done", exact=True).click()
        expect(first.locator(supplier)).to_have_count(0)
        first.get_by_role("button", name="Sign out", exact=True).click()
        first.context.close()

        second = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        sign_in(second, live_server.url, "columns-reader", PASSWORD)
        second.goto(live_server.url + "/lots/")
        expect(second.locator('th[data-vr-col="lot"]')).to_be_visible()
        expect(second.locator(supplier)).to_have_count(0)
        browser.close()
