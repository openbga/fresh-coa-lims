"""Shared helpers for the browser suite: sessions, sign-in, signing and enhanced controls.

Fixture data goes through domain services; the action a journey is about happens in the browser.
Import as ``from helpers import ...`` (e2e/pytest.ini puts this directory on the path).
"""

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import urlsplit

from django.db import connections
from django.urls import reverse
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect, sync_playwright

from analytical import gates
from analytical import services as analytical
from tests.test_integrated_journey import PASSWORD, PIN, observed_test

DESKTOP = {"width": 1280, "height": 900}
ACTION_TIMEOUT_MS = 10_000  # a missing element fails in seconds, not after half a minute


def db_call(callback):
    """Keep Django ORM work off Playwright's synchronous event-loop thread.

    Django refuses database queries from a thread running an event loop (SynchronousOnlyOperation);
    the callback runs in a worker thread, which closes its connections when done.
    """

    def work():
        try:
            return callback()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(work).result()


@contextmanager
def browser_page(viewport=DESKTOP):
    """A fresh headless Chromium page. Browser testing never drives a visible window."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        page.set_default_timeout(ACTION_TIMEOUT_MS)
        try:
            yield page
        finally:
            browser.close()


def sign_in(page: Page, base_url: str, username: str, password: str = PASSWORD, *, home=True):
    """Fill the sign-in form; ``home`` waits for the workspace home page."""
    page.goto(base_url + reverse("login"))
    page.get_by_label(re.compile(r"^Username\b")).fill(username)
    page.get_by_label(re.compile(r"^Password\b")).fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    if home:
        expect(page).to_have_url(base_url + "/")
        page.wait_for_load_state("domcontentloaded")  # the page's deferred scripts have run


def login(page: Page, live_server, person, password: str = PASSWORD):
    """Sign ``person`` (a user) in through the live server and wait for the home page."""
    sign_in(page, live_server.url, person.username, password)


def fill_signature(scope, username: str, pin: str = PIN, reason: str | None = None):
    """Fill the signing fields (username, PIN and, when given, the reason) of a form or dialog."""
    if reason is not None:
        scope.get_by_label(re.compile(r"^Reason\b")).fill(reason)
    scope.get_by_label(re.compile(r"^Signing username\b")).fill(username)
    scope.get_by_label(re.compile(r"^Signature PIN\b")).fill(pin)


def dialog_form(page: Page):
    """The form page open in the shared form dialog, or None."""
    shown = page.locator("#vr-form-dialog.show [data-vr-form-page]")
    return shown if shown.count() else None


def submit_signed(page: Page, button: str, path: str | None = None) -> int:
    """Click the signing button and return the HTTP status of the POST to ``path`` (default: the
    form open in the form dialog, else the current page). A redirect is 302 either way: in the
    form dialog it arrives as 204 with HX-Redirect or HX-Location (core/form_dialog.py)."""
    shown = dialog_form(page)
    if path is None:
        path = urlsplit(shown.get_attribute("data-vr-form-url") if shown else page.url).path
    scope = shown or page
    with page.expect_response(
        lambda response: urlsplit(response.url).path == path and response.request.method == "POST"
    ) as response:
        scope.get_by_role("button", name=button, exact=True).click()
    headers = response.value.headers
    if response.value.status == 204 and ("hx-redirect" in headers or "hx-location" in headers):
        return 302
    return response.value.status


def expect_form(page: Page, url: str):
    """The form at ``url`` is open: in the shared form dialog over the page it was opened from
    (or, opened by its address, over its own page)."""
    path = re.escape(urlsplit(url).path)
    expect(page.locator("#vr-form-dialog.show [data-vr-form-page]")).to_have_attribute(
        "data-vr-form-url", re.compile(rf"^{path}(\?|$)")
    )


def open_page_form(page: Page):
    """Open the form a record or account page offers in the form dialog (its one opener)."""
    page.locator(".vr-main [data-vr-local-opener]").click()
    expect(page.locator("#vr-form-dialog.show form")).to_have_count(1)


def submit_for_review(page: Page, reason: str):
    """Open a test's Submit for review form (in the form dialog) and submit it with ``reason``."""
    page.get_by_role("button", name="Submit for review", exact=True).click()
    shown = page.locator("#vr-form-dialog.show")
    expect(shown.locator("[data-vr-form-page], form")).not_to_have_count(0)
    shown.get_by_label(re.compile(r"^Reason\b")).fill(reason)
    shown.get_by_role("button", name="Submit for review", exact=True).click()


def sign(page: Page, username: str, button: str, reason: str, pin: str = PIN, path=None) -> int:
    """Fill the signature and submit it; returns the POST status."""
    fill_signature(page, username, pin, reason)
    return submit_signed(page, button, path)


def ready_test(data, sample):
    """An observed, independently reviewed conforming test, leaving the lot without blockers."""
    test, investigation = observed_test(data, sample, "100.25")
    assert investigation is None
    test = analytical.review_test(
        actor=data["people"]["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent browser-guard fixture review",
    )
    assert test.state == "reviewed" and test.conforms
    assert gates.lot_blockers(data["lot"]) == []
    return test


def field(scope, name: str):
    """A form control by its exact label text; the required-field marker may follow it.

    An enhanced select also labels its menu (listbox): the control comes first. Controls behind
    an open dialog are inert and never match (form-dialog.js renames their ids "vr-background-…").
    """
    page = scope if isinstance(scope, Page) else scope.page
    labelled = scope.get_by_label(re.compile(rf"^{re.escape(name)}\s*\*?$"))
    return labelled.and_(page.locator(":not([id^='vr-background-'])")).first


def wait_for_enhanced(control):
    """The element holding the value the form submits for a labelled control.

    That is the <select> behind a Tom Select, the hidden server-format input of a date field
    (static/js/controls.js), or the control itself. It first waits until controls.js has
    enhanced the field, because before that a labelled locator finds the native element and
    after it the enhanced one: without the wait the answer depends on how fast the page is (an
    HTMX swap, a slow CI runner). The element is resolved now and marked, so a later locator for
    the same label cannot drift to another element.
    """
    handle = control.first.element_handle()
    control.page.wait_for_function(
        """el => {
            if (!el.isConnected || el.closest('.ts-wrapper')) return true;
            const enhanced = el.classList.contains('tomselected');
            if (el.matches('select:not([data-vr-native])')) return enhanced;
            if (el.matches('input[data-vr-date]')) return Boolean(el.vrDateField);
            if (el.matches('input[data-vr-suggest]')) return enhanced;
            return true;
        }""",
        arg=handle,
    )
    mark = handle.evaluate(
        """el => {
            const wrapper = el.closest('.ts-wrapper');
            const target = wrapper ? wrapper.previousElementSibling
                : el.vrDateField ? el.vrDateField.hidden : el;
            target.dataset.e2eNative = target.dataset.e2eNative || String(Math.random()).slice(2);
            return target.dataset.e2eNative;
        }"""
    )
    return control.page.locator(f"[data-e2e-native='{mark}']")


def pick(control, value=None, *, label=None, index=None) -> None:
    """Choose options the way a user does: open the menu, type into its search box when it has
    one, and click the option. ``control`` is the labelled combobox or the <select>; options are
    given as for ``select_option``. A form that re-renders meanwhile is found again once."""
    try:
        _pick(control, value, label, index, timeout=4_000)
    except PlaywrightError:
        _pick(control, value, label, index, timeout=None)


def _pick(control, value, label, index, timeout) -> None:
    select = wait_for_enhanced(control)
    page = select.page
    wrapper = select.locator("xpath=following-sibling::div[contains(@class, 'ts-wrapper')][1]")
    if not wrapper.count():  # not enhanced: the browser's own select
        select.select_option(value, label=label, index=index)
        return
    combobox = wrapper.locator("[role=combobox]").first
    combobox.wait_for(timeout=timeout)
    if label is not None:
        labels = [label] if isinstance(label, str) else list(label)
    else:
        if index is not None:
            options = [select.locator("option").nth(index)]
        else:
            values = [value] if isinstance(value, str) else list(value)
            options = [select.locator(f"option[value='{v}']") for v in values]
        labels = [" ".join(option.text_content().split()) for option in options]
    menu = wrapper.locator(".ts-dropdown-content")
    search = wrapper.locator("input.dropdown-input")
    for text in labels:
        if not menu.is_visible():
            combobox.click(timeout=timeout)
        words = text.split()[:1]  # the first word narrows the menu; the click picks the option
        if search.count():
            search.fill(" ".join(words))
        elif combobox.evaluate("el => el.tagName === 'INPUT'"):
            combobox.fill(" ".join(words))
        menu.get_by_role("option", name=text, exact=True).click(timeout=timeout)
    # Close a menu that stays open (multi-select) only while it is still open, so the Escape
    # never reaches a dialog around it.
    if wrapper.evaluate("w => w.classList.contains('dropdown-active')"):
        page.keyboard.press("Escape")
