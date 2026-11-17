"""The signing form is shown before its deferred dialog script runs. Text someone is already
typing must stay in the field they are typing in when the script moves the form into the
dialog, rather than continue in the PIN field."""

import re
import time

import pytest
from django.urls import reverse
from playwright.sync_api import expect
from test_workflow_guards import browser_page, login, ready_test

from tests.test_integrated_journey import assign_and_sample
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.before_page_scripts
def test_dialog_script_keeps_the_field_being_typed_in(live_server, integrated):
    data = integrated
    ready_test(data, assign_and_sample(data))
    held = []
    with browser_page() as page:
        login(page, live_server, data["people"]["approver"])
        page.route(re.compile(r"/signature-dialog[^/]*\.js$"), lambda route: held.append(route))
        page.goto(
            live_server.url + reverse("quality:disposition", args=[data["lot"].pk]),
            wait_until="commit",
        )
        reason = page.get_by_label(re.compile(r"^Reason\b"))
        reason.fill("Typed before the dialog opened")
        deadline = time.monotonic() + 10
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert held, "the dialog script was not requested"
        expect(page.get_by_role("dialog")).to_have_count(0)

        held[0].continue_()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.keyboard.type(", and after")

        expect(reason).to_have_value("Typed before the dialog opened, and after")
        expect(page.get_by_label(re.compile(r"^Signature PIN\b"))).to_have_value("")
        assert page.evaluate("document.activeElement.name") == "reason"
