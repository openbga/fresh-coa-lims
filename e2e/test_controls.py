"""Shared form controls in Chromium: no browser-default UI, by mouse and keyboard, inside a modal
dialog, after an HTMX swap, under the site's real Content-Security-Policy (static/js/controls.js,
templates/django/forms/widgets/, core/lookups.py, core/preferences.py)."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from helpers import browser_page, field, pick, sign_in, wait_for_enhanced
from playwright.sync_api import expect

from core.models import UserPreference
from quality.models import Lot
from quality.services import current_receipt
from tests.test_lot_receipt import PASSWORD, approved_rules, staff, synthetic_supplier

pytestmark = pytest.mark.django_db(transaction=True)

WATCH = """window.vrViolations = [];
document.addEventListener('securitypolicyviolation', e =>
  window.vrViolations.push(e.violatedDirective + ' ' + e.blockedURI));"""

# A modal <dialog> holding an HTMX target, built with DOM methods.
MODAL = """url => {
  const dialog = document.createElement('dialog');
  dialog.id = 'e2e-dialog';
  const target = document.createElement('div');
  target.id = 'e2e-target';
  dialog.append(target);
  document.body.append(dialog);
  dialog.showModal();
  return htmx.ajax('GET', url, {target: '#e2e-target', select: '#main form'});
}"""


def watch(page, errors):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.add_init_script(WATCH)


def no_violations(page, errors):
    assert page.evaluate("window.vrViolations") == []
    assert errors == []


def native_controls(page):
    """Native pickers the browser would draw: none may be visible."""
    return page.evaluate(
        """() => [...document.querySelectorAll(
            'select, input[type=date], input[type=datetime-local], input[type=number]')]
          .filter(el => el.offsetParent !== null && !el.closest('.ts-wrapper'))
          .map(el => el.name || el.id)"""
    )


def labelled(scope, name):
    return scope.get_by_label(re.compile(rf"^{re.escape(name)}\s*\*?$")).first


def test_receipt_form_by_mouse_and_keyboard(live_server, django_user_model):
    people = staff(django_user_model)
    approved_rules(people)
    synthetic_supplier(people)
    errors = []
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    with browser_page() as page:
        watch(page, errors)
        sign_in(page, live_server.url, "analyst", PASSWORD)
        response = page.goto(live_server.url + reverse("quality:lot_new"))
        policy = response.headers["content-security-policy"]
        assert "script-src 'self'" in policy and "style-src 'self'" in policy
        assert "unsafe-inline" not in policy
        wait_for_enhanced(field(page, "Rule set"))
        assert native_controls(page) == []

        field(page, "Lot number").fill("SYN-CTL-001")
        field(page, "Material").fill("Synthetic powder")
        pick(field(page, "Rule set"), label="synthetic v1")

        # Keyboard on a short list: Space opens it, Escape closes it, typing jumps to an option.
        source = field(page, "Source")
        wait_for_enhanced(source)
        source.focus()
        page.keyboard.press(" ")
        menu = page.locator(".ts-dropdown:visible")
        expect(menu).to_be_visible()
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        source.focus()
        page.keyboard.type("Rec")
        expect(source).to_contain_text("Received from a supplier")

        # Remote select: options come from the permission-scoped lookup as the user types.
        supplier = field(page, "Supplier")
        native = wait_for_enhanced(supplier)
        assert native.locator("option").count() == 1  # only the empty choice is in the page
        with page.expect_response(lambda r: "/lookups/suppliers/" in r.url) as answer:
            supplier.click()
        assert answer.value.status == 200
        page.keyboard.press("Escape")
        expect(page.locator(".ts-dropdown:visible")).to_have_count(0)
        # Keyboard: Enter opens a remote list too; Escape before its page arrives keeps it shut.
        native.evaluate("select => select.tomselect.focus_node.focus()")
        page.keyboard.press("Enter")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)  # longer than the lookup takes on the live server
        expect(page.locator(".ts-dropdown:visible")).to_have_count(0)
        expect(page).to_have_url(re.compile(r"/lots/new/$"))
        page.keyboard.press("S")  # typing opens the list and starts the search
        expect(page.locator(".ts-dropdown:visible input.dropdown-input")).to_have_value("S")
        page.locator(".ts-dropdown:visible input.dropdown-input").fill("Ingredients")
        page.locator(".ts-dropdown:visible").get_by_role(
            "option", name="sup-syn-001 · Synthetic Ingredients Supply"
        ).click()
        expect(supplier).to_contain_text("sup-syn-001")
        expect(native).to_have_value(re.compile(r"^\d+$"))

        # Date: typed entry, a format error beside the field, the calendar's shortcut, Escape.
        received = field(page, "Date received")
        hidden = wait_for_enhanced(received)
        received.fill("2026/3/4")
        received.press("Tab")
        expect(received).to_have_value("2026-03-04")
        expect(hidden).to_have_value("2026-03-04")
        received.fill("not a date")
        received.press("Tab")
        expect(page.locator(".vr-date-error")).to_contain_text("Enter a date as YYYY-MM-DD.")
        received.fill("")
        received.press("Alt+ArrowDown")
        calendar = page.locator(".vr-datepicker:not([hidden])")
        expect(calendar).to_be_visible()
        first_day = calendar.locator("[data-vc-week-day]").first
        expect(first_day).to_have_text(re.compile(r"^S"))  # weeks start on Sunday
        calendar.get_by_role("button", name="Yesterday", exact=True).click()
        expect(calendar).to_have_count(0)
        expect(hidden).to_have_value(yesterday)
        received.press("Alt+ArrowDown")
        expect(calendar).to_be_visible()
        page.keyboard.press("Escape")
        expect(calendar).to_have_count(0)
        expect(received).to_be_focused()

        # Decimal: text without a spinner; the exact typed string reaches the server.
        quantity = field(page, "Quantity received")
        assert quantity.get_attribute("type") == "text"
        quantity.fill("125.5000")
        pick(field(page, "Quantity unit"), label="kg")
        field(page, "Number of containers").fill("5")
        field(page, "Supplier lot number").fill("SUP-SYN-7")
        field(page, "Delivery or batch document").fill("DN-SYN-0042")
        field(page, "Containers").fill("25 kg fibre drums")
        pick(field(page, "Examination on receipt"), index=1)
        field(page, "Reason").fill("Synthetic delivery received")
        page.get_by_role("button", name="Receive lot", exact=True).click()
        expect(page.locator(".vr-page-title")).to_have_text("SYN-CTL-001")
        no_violations(page, errors)

    receipt = current_receipt(Lot.objects.get(number="SYN-CTL-001"))
    assert receipt.quantity == Decimal("125.5000")
    assert receipt.received_on.isoformat() == yesterday
    assert receipt.supplier.code == "sup-syn-001"


def test_controls_inside_a_modal_dialog_after_an_htmx_swap(live_server, django_user_model):
    people = staff(django_user_model)
    approved_rules(people)
    errors = []
    with browser_page() as page:
        watch(page, errors)
        sign_in(page, live_server.url, "analyst", PASSWORD)
        page.goto(live_server.url + reverse("quality:lot_list"))  # a page without the form

        # The receipt form, swapped in by HTMX inside a modal dialog: controls initialise on
        # htmx:load, their menus float above the dialog, and Escape closes the menu or the
        # calendar without closing the dialog.
        page.evaluate(MODAL, reverse("quality:lot_new"))
        dialog = page.locator("#e2e-dialog")
        rules = labelled(dialog, "Rule set")
        wait_for_enhanced(rules)
        assert dialog.locator("select.tomselected").count() >= 4
        rules.click()
        menu = dialog.locator(".ts-dropdown:visible")
        expect(menu).to_be_visible()
        menu.get_by_role("option", name="synthetic v1").click()  # pointer works over the dialog
        expect(rules).to_contain_text("synthetic v1")
        rules.focus()
        page.keyboard.press(" ")
        expect(menu).to_be_visible()
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        expect(dialog).to_have_attribute("open", "")

        received = labelled(dialog, "Date received")
        hidden = wait_for_enhanced(received)
        received.press("Alt+ArrowDown")
        calendar = dialog.locator(".vr-datepicker:not([hidden])")
        expect(calendar).to_be_visible()
        box = calendar.bounding_box()
        assert box and box["height"] > 100  # not clipped by the dialog
        calendar.get_by_role("button", name="Today", exact=True).click()
        expect(hidden).to_have_value(timezone.localdate().isoformat())
        received.press("Alt+ArrowDown")
        expect(calendar).to_be_visible()
        page.keyboard.press("Escape")
        expect(calendar).to_have_count(0)
        expect(dialog).to_have_attribute("open", "")
        page.keyboard.press("Escape")  # with nothing open, Escape is the dialog's again
        expect(dialog).not_to_have_attribute("open", "")
        no_violations(page, errors)


def test_sidebar_collapse_follows_the_person(live_server, django_user_model):
    people = staff(django_user_model)
    errors = []
    with browser_page() as page:
        watch(page, errors)
        sign_in(page, live_server.url, "analyst", PASSWORD)
        toggle = page.locator("[data-vr-nav-toggle]")
        expect(toggle).to_have_attribute("aria-expanded", "true")
        with page.expect_response(lambda r: r.url.endswith("/preferences/")) as saved:
            toggle.click()
        assert saved.value.status == 204
        expect(page.locator(".vr-shell.vr-nav-collapsed")).to_have_count(1)
        expect(toggle).to_have_attribute("aria-label", "Expand menu")
        page.locator("#vr-nav .vr-navlink").first.focus()
        expect(page.locator(".tooltip.vr-nav-tooltip")).to_be_visible()  # the label, on focus
        page.reload()  # the server renders the saved state
        expect(page.locator(".vr-shell.vr-nav-collapsed")).to_have_count(1)
        no_violations(page, errors)
    assert UserPreference.objects.get(user=people["analyst"], key="nav.collapsed").value is True
    with browser_page() as page:  # another person on the same workstation
        sign_in(page, live_server.url, "analyst2", PASSWORD)
        expect(page.locator(".vr-shell.vr-nav-collapsed")).to_have_count(0)
        # Rapid changes of one setting: requests can arrive in any order, the last one wins.
        posts = []
        page.on("request", lambda r: posts.append(r) if r.url.endswith("/preferences/") else None)
        page.evaluate(
            """async () => {
              const prefs = window.vrPreferences;
              prefs.set("pagedocs.open", true);
              prefs.set("pagedocs.open", false);
              prefs.set("pagedocs.open", true);
              await prefs.set("pagedocs.open", false);
            }"""
        )
        assert len(posts) == 2  # the first value, then only the latest of those that waited
    last = UserPreference.objects.get(user=people["analyst2"], key="pagedocs.open")
    assert last.value is False
