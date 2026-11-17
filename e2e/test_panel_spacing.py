"""Panel spacing on the main list, record and form pages (docs/ui-standards.md, "Panel spacing").

Visible text and controls inside a panel sit at least --vr-panel-inset from its edge, stacked
blocks in a panel body are at least --vr-stack apart, key facts start on their grid's track
lines, and no fact label or ordinary word breaks across lines. The measurement is
e2e/panel_spacing.js, which any browser check can reuse:
page.evaluate(Path("e2e/panel_spacing.js").read_text()).
"""

from pathlib import Path

import pytest
from django.urls import reverse
from helpers import browser_page, login

from core.form_surfaces import FORM_SURFACES
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

CHECK = (Path(__file__).parent / "panel_spacing.js").read_text()
OPEN_DETAILS = "() => document.querySelectorAll('details').forEach(d => { d.open = true; })"
PAGES = [
    ("quality:dashboard", False),
    ("quality:lot_list", False),
    ("quality:lot_detail", True),
    ("catalog:specifications", False),
    ("catalog:materials", False),
    ("analytical:test_list", False),
    ("stability:overview", False),
    ("suppliers:list", False),
    ("catalog:material_new", False),
]


@pytest.mark.parametrize("width", [1280, 1440])
def test_panels_keep_their_inset_and_stack(live_server, integrated, width):
    lot = integrated["lot"]
    problems, panels = [], 0
    with browser_page({"width": width, "height": 900}) as page:
        login(page, live_server, integrated["people"]["author"])
        for name, with_lot in PAGES:
            path = reverse(name, args=[lot.pk] if with_lot else [])
            page.goto(live_server.url + path)
            page.evaluate(OPEN_DETAILS)
            result = page.evaluate(CHECK)
            panels += result["panels"]
            problems += [f"{path}: {problem}" for problem in result["problems"]]
    assert panels >= len(PAGES), "the crawler measured too few panels: did the pages load?"
    assert not problems, "\n".join(problems)


SIDEWAYS = """() => [...document.querySelectorAll('.vr-main .vr-table-wrap')]
  .filter(w => w.getClientRects().length && w.scrollWidth > w.clientWidth + 1)
  .map(w => `${w.querySelector('table')?.getAttribute('data-vr-grid') || 'table'}: ` +
    `${w.scrollWidth}px in ${w.clientWidth}px`)"""


def test_lists_fit_beside_the_open_help_drawer(live_server, integrated):
    """At 1440 with the help drawer open, low-priority columns give way: no table scrolls
    sideways."""
    lot = integrated["lot"]
    problems = []
    with browser_page({"width": 1440, "height": 900}) as page:
        login(page, live_server, integrated["people"]["author"])
        page.goto(live_server.url + reverse("quality:lot_list"))
        page.locator(".vr-topbar [data-pagedocs-toggle]").click()
        page.locator("[data-pagedocs-panel]").wait_for()
        for name, with_lot in PAGES:
            if name in FORM_SURFACES:  # a form opens in the dialog, over its list
                continue
            path = reverse(name, args=[lot.pk] if with_lot else [])
            page.goto(live_server.url + path)
            if not page.locator("[data-pagedocs-panel]").is_visible():  # open state still saving
                page.locator(".vr-topbar [data-pagedocs-toggle]").click()
            page.locator("[data-pagedocs-panel]").wait_for()
            page.wait_for_timeout(100)  # the width observers settle
            problems += [f"{path}: {problem}" for problem in page.evaluate(SIDEWAYS)]
    assert not problems, "\n".join(problems)


OUTSIDE_PANEL = """() => [...document.querySelectorAll('.vr-main section.card')].flatMap(card => {
  const edge = card.getBoundingClientRect().right + 0.5;
  return [...card.querySelectorAll('*')]
    .filter(el => el.getClientRects().length && el.getBoundingClientRect().right > edge)
    .map(el => `${card.getAttribute('aria-labelledby')}: ${el.className.baseVal ?? el.className}`);
})"""


@pytest.mark.parametrize("width", [1280, 1440, 1700, 1920])
def test_dashboard_fits_its_panels(live_server, integrated, width):
    """The flow band and the six lanes stay inside their panel, with and without the help
    drawer: lanes wrap to rows of three when the panel is too narrow for six."""
    problems = []
    with browser_page({"width": width, "height": 900}) as page:
        login(page, live_server, integrated["people"]["author"])
        page.goto(live_server.url + reverse("quality:dashboard"))
        problems += page.evaluate(OUTSIDE_PANEL)
        page.locator(".vr-topbar [data-pagedocs-toggle]").click()
        page.locator("[data-pagedocs-panel]").wait_for()
        page.wait_for_timeout(100)  # the width observers settle
        problems += [f"help open: {problem}" for problem in page.evaluate(OUTSIDE_PANEL)]
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not problems, "\n".join(problems)


RECORD_GAPS = """() => {
  const record = document.querySelector('.vr-record.vr-record-has-aside');
  if (!record) return ['no record layout with an aside'];
  const aside = record.querySelector(':scope > .vr-record-aside').getBoundingClientRect();
  const stack = parseFloat(getComputedStyle(record.firstElementChild).marginBottom) + 1;
  const panels = [...record.querySelectorAll(
    ':scope > .vr-record-lead > *, :scope > .vr-record-wide > *,'
    + ':scope > :not(.vr-record-lead, .vr-record-aside, .vr-record-wide)')]
    .filter(p => p.getClientRects().length);
  const name = p => (p.querySelector('h2, h3, summary') || p).textContent.trim().slice(0, 30);
  const problems = [];
  panels.forEach((panel, i) => {
    const box = panel.getBoundingClientRect();
    if (box.top < aside.bottom && box.right > aside.left) {
      problems.push(`${name(panel)} runs under the aside`);
    }
    if (i && box.top - panels[i - 1].getBoundingClientRect().bottom > stack) {
      problems.push(`gap above ${name(panel)}`);
    }
  });
  return problems;
}"""


@pytest.mark.parametrize("width", [1440, 1920])
def test_record_panels_stack_beside_the_aside_without_gaps(live_server, integrated, width):
    """Owner rule (review 1): beside a tall aside the following panels keep stacking in the
    left column; none is full width while the aside runs beside it, and none leaves a gap."""
    from tests.test_integrated_journey import assign_and_sample, observed_test

    test, _ = observed_test(integrated, assign_and_sample(integrated), "100.25")
    pages = [
        reverse("analytical:test_detail", args=[test.pk]),
        reverse("quality:lot_detail", args=[integrated["lot"].pk]),
    ]
    problems = []
    with browser_page({"width": width, "height": 900}) as page:
        login(page, live_server, integrated["people"]["author"])
        for path in pages:
            page.goto(live_server.url + path)
            problems += [f"{path}: {problem}" for problem in page.evaluate(RECORD_GAPS)]
    assert not problems, "\n".join(problems)
