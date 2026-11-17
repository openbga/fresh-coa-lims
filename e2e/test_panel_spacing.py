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

from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

CHECK = (Path(__file__).parent / "panel_spacing.js").read_text()
OPEN_DETAILS = "() => document.querySelectorAll('details').forEach(d => { d.open = true; })"
PAGES = [
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
            path = reverse(name, args=[lot.pk] if with_lot else [])
            page.goto(live_server.url + path)
            page.locator("[data-pagedocs-panel]").wait_for()
            page.wait_for_timeout(100)  # the width observers settle
            problems += [f"{path}: {problem}" for problem in page.evaluate(SIDEWAYS)]
    assert not problems, "\n".join(problems)
