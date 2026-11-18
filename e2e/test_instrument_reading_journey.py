"""Readings from a connected balance through the pages, in Chromium with a simulated device.

Chromium's Web Serial API is replaced by a synthetic port (``SIMULATED_PORT``) that answers the
MT-SICS requests the way the manufacturer's interface description gives them. Quality sets the
balance's data connection on its page; the analyst reads the sample mass from the balance on the
result form (an unstable weight is refused first), types the other inputs and records; the test
record and the review page show the reading as the device sent it, and the weighing not recorded.
"""

import re

import pytest
from django.urls import reverse
from helpers import field, pick, submit_for_review
from playwright.sync_api import expect, sync_playwright

from analytical.models import InstrumentReading
from laboratory import services as laboratory
from laboratory.models import DeviceConnection
from tests.test_calculation_bench_journey import assign_water, build_world, calibrate
from tests.test_integrated_journey import PASSWORD, PIN

SERIAL = "B123456789"

# A port the page can open, write to and read from; it answers I4 with the serial number and S
# with window.__weight (an MT-SICS balance). window.__sent keeps what the page sent.
SIMULATED_PORT = """
(() => {
  const encoder = new TextEncoder();
  window.__sent = [];
  window.__opened = [];
  window.__weight = 'S S   2500.4 mg';
  const reply = (text) => {
    if (text.startsWith('I4')) return 'I4 A "__SERIAL__"\\r\\n';
    return text.startsWith('S') ? window.__weight + '\\r\\n' : '';
  };
  const port = {
    readable: null,
    writable: null,
    async open(options) {
      window.__opened.push(options);
      let controller;
      this.readable = new ReadableStream({ start(c) { controller = c; } });
      this.writable = new WritableStream({
        write(chunk) {
          const text = new TextDecoder().decode(chunk);
          window.__sent.push(text);
          const answer = reply(text);
          if (answer) setTimeout(() => controller.enqueue(encoder.encode(answer)), 20);
        },
      });
    },
    async close() { this.readable = null; this.writable = null; },
    getInfo() { return {}; },
  };
  Object.defineProperty(navigator, 'serial', {
    configurable: true,
    value: { requestPort: async () => port, getPorts: async () => [port], addEventListener() {} },
  });
})();
""".replace("__SERIAL__", SERIAL)


@pytest.fixture
def world(django_user_model):
    data = build_world(django_user_model)
    people = data["people"]
    balance = laboratory.register_equipment(
        actor=people["analyst"],
        asset_id="SYN-BAL-01",
        description="Synthetic analytical balance",
        category="balance",
        location="Synthetic weighing room",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    calibrate(people, balance)
    data["balance"] = balance
    data["test"] = assign_water(data)
    return data


@pytest.mark.django_db(transaction=True)
def test_a_balance_reading_is_taken_recorded_and_reviewed_through_the_pages(
    live_server, world, artifacts
):
    people, test, balance = world["people"], world["test"], world["balance"]
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(SIMULATED_PORT)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def goto(name, *args):
            page.goto(live_server.url + reverse(name, args=args))

        def login(person):
            goto("login")
            page.get_by_label(re.compile(r"^Username\b")).fill(person.username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page).to_have_url(live_server.url + "/")

        def sign_out():
            page.get_by_role("button", name="Sign out", exact=True).click()

        try:
            # Quality sets the balance's data connection.
            login(people["author"])
            goto("laboratory:equipment_connection_new", balance.pk)
            pick(field(page, "Output format"), "mt_sics")
            field(page, "Serial number").fill(SERIAL)
            field(page, "Verification record").fill("VER-SYN-BAL-01 interface check rev 1")
            field(page, "Reason").fill("Balance connected to the bench computer")
            page.get_by_role("button", name="Set data connection", exact=True).click()
            expect(page.get_by_text("Data connection set.")).to_be_visible()
            expect(page.get_by_text("VER-SYN-BAL-01 interface check rev 1")).to_be_visible()
            sign_out()

            # The analyst reads the sample mass from the balance.
            login(people["analyst"])
            goto("analytical:test_detail", test.pk)
            # The form opens in the dialog over the test record; its script comes with it.
            page.get_by_role("link", name="Record observation", exact=True).click()
            expect(page.locator("#vr-form-dialog.show [data-vr-form-page]")).to_be_visible()
            read = page.get_by_role("button", name="Read from SYN-BAL-01").last
            expect(read).to_be_visible()
            page.evaluate("window.__weight = 'S D   2500.1 mg'")
            read.click()
            expect(
                page.get_by_text("The balance sent a weight it did not report as stable.")
            ).to_be_visible()
            page.evaluate("window.__weight = 'S S   2500.6 mg'")
            read.click()
            mass = page.locator("input[name='input_sample_mass']")
            expect(mass).to_have_value("2500.6")
            # Weighed again: the first stable reading stays on the test, not recorded.
            page.evaluate("window.__weight = 'S S   2500.4 mg'")
            read.click()
            expect(mass).to_have_value("2500.4")
            expect(mass).to_have_attribute("readonly", "")
            expect(page.get_by_text(re.compile(r"Read from SYN-BAL-01 at"))).to_be_visible()
            expect(page.get_by_text('I4 A "B123456789"␍␊S S   2500.4 mg␍␊')).to_be_visible()
            assert page.evaluate("window.__sent") == ["I4\r\n", "S\r\n"] * 3
            assert page.evaluate("window.__opened")[0]["baudRate"] == 9600
            # The balance is ticked among the equipment used.
            expect(page.get_by_label(re.compile(r"SYN-BAL-01"))).to_be_checked()
            page.get_by_label(re.compile(r"SYN-TITRATOR-01")).check()
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            page.locator("input[name='input_titrant_volume']").fill("1.25")
            page.locator("input[name='input_titer']").fill("4.98")
            field(page, "Original record").fill("Balance SYN-BAL-01 and titrator memory, run 4")
            page.screenshot(path=str(artifacts / "instrument-reading-form.png"), full_page=True)
            page.get_by_role("button", name="Record observation", exact=True).click()
            expect(page).to_have_url(
                live_server.url + reverse("analytical:test_detail", args=[test.pk])
            )
            expect(page.get_by_role("status").get_by_text("Observation recorded.")).to_be_visible()
            expect(page.get_by_text("Read from instruments:")).to_be_visible()
            readings = page.locator("table[aria-labelledby='readings-heading'] tbody tr")
            expect(readings).to_have_count(2)
            expect(readings.nth(0)).to_contain_text("Not recorded")
            expect(readings.nth(1)).to_contain_text("Replicate 1")
            page.screenshot(path=str(artifacts / "instrument-reading-recorded.png"), full_page=True)

            # The second replicate is typed.
            goto("analytical:observation_new", test.pk)
            page.locator("input[name='input_titrant_volume']").fill("1.31")
            page.locator("input[name='input_titer']").fill("4.98")
            page.locator("input[name='input_sample_mass']").fill("2498.7")
            page.get_by_label(re.compile(r"SYN-TITRATOR-01")).check()
            page.get_by_label(re.compile(r"SYN-KF-TITRANT-01")).check()
            field(page, "Original record").fill("Notebook SYN-NB-7 page 12")
            page.get_by_role("button", name="Record observation", exact=True).click()
            expect(page.get_by_role("status").get_by_text("Observation recorded.")).to_be_visible()
            submit_for_review(page, "Results complete")
            expect(page.get_by_text("Awaiting review", exact=True)).to_be_visible()
            sign_out()

            login(people["reviewer"])
            goto("analytical:test_detail", test.pk)
            page.get_by_role("link", name="Sign review", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            expect(
                page.get_by_text(re.compile(r"replicate 1 Sample mass 2500\.4 mg from SYN-BAL-01"))
            ).to_be_visible()
            expect(page.get_by_text(re.compile(r"1 reading not recorded"))).to_be_visible()
            expect(page.get_by_text(re.compile(r"read again: agrees"))).to_be_visible()
            page.get_by_label(re.compile(r"^Signing username\b")).fill(people["reviewer"].username)
            page.get_by_label(re.compile(r"^Signature PIN\b")).fill(PIN)
            page.get_by_label(re.compile(r"^Reason\b")).fill("Readings checked against the balance")
            page.get_by_role("button", name="Sign and review", exact=True).click()
            expect(page.get_by_text("Reviewed · conforms", exact=True)).to_be_visible()
        except Exception:
            page.screenshot(path=str(artifacts / "instrument-reading-failure.png"), full_page=True)
            raise
        finally:
            browser.close()
    assert errors == []
    assert DeviceConnection.objects.get().serial_number == SERIAL
    taken = list(InstrumentReading.objects.filter(test=test).order_by("pk"))
    assert [r.value_text for r in taken] == ["2500.6", "2500.4"]
    assert taken[0].observation_id is None and taken[1].observation.replicate == 1


@pytest.mark.django_db(transaction=True)
def test_without_the_web_serial_api_values_are_typed(live_server, world):
    people, test, balance = world["people"], world["test"], world["balance"]
    laboratory.set_connection(
        actor=people["author"],
        equipment=balance,
        reason="Synthetic connection",
        replacing=None,
        device_format="mt_sics",
        baud_rate=9600,
        data_bits=8,
        parity="none",
        stop_bits=1,
        serial_number=SERIAL,
        verification_ref="VER-SYN-BAL-01",
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script(
            "Object.defineProperty(navigator, 'serial', {configurable: true, value: undefined});"
        )
        page = context.new_page()
        try:
            page.goto(live_server.url + reverse("login"))
            page.get_by_label(re.compile(r"^Username\b")).fill(people["analyst"].username)
            page.get_by_label(re.compile(r"^Password\b")).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.goto(live_server.url + reverse("analytical:observation_new", args=[test.pk]))
            expect(
                page.get_by_text(
                    re.compile(r"^Reading from an instrument needs Chrome or Edge")
                ).first
            ).to_be_visible()
            expect(page.get_by_role("button", name="Read from SYN-BAL-01")).to_have_count(0)
        finally:
            browser.close()
