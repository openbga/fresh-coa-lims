"""Labels sit centred in their box (docs/ui-standards.md, "Alignment").

Buttons, navigation items, status labels and table cells centre their label vertically. The check
measures ink, not layout boxes: icons are hidden and the label set in capitals (through the
element's own style, which the content security policy allows), the element is screenshotted,
and the rows holding ink must leave equal space above and below, within the tolerance. When the
chosen typeface sits off-centre, the fix is its ascent/descent overrides at @font-face in
static/css/app.css, not per-component nudges.
"""

import io

import pytest
from django.urls import reverse
from helpers import browser_page, login
from PIL import Image

from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

TOLERANCE = 2  # device pixels

PROBE = """el => {
  el.querySelectorAll('svg').forEach(svg => { svg.style.visibility = 'hidden'; });
  el.style.textTransform = 'uppercase';
  el.style.transition = 'none';
}"""

# (page, selector) pairs: one of each kind of labelled box.
TARGETS = [
    ("catalog:materials", ".vr-page-actions .btn-primary"),
    ("quality:lot_list", ".vr-sidenav a.vr-navlink:not([aria-current])"),
    ("quality:lot_list", ".vr-topbar .vr-topbar-btn"),
    ("quality:lot_list", ".vr-table .vr-status"),
    ("quality:lot_list", ".vr-table > tbody > tr > td:not(:has(a, .vr-status, svg))"),
]


def ink_gaps(png: bytes) -> tuple[int, int]:
    """Rows of empty space above and below the label's ink, inside the element's box."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    width, height = image.size
    sample = [
        image.getpixel((x, y))
        for x in range(width // 4, 3 * width // 4, 3)
        for y in range(height // 4, 3 * height // 4, 2)
    ] or [image.getpixel((0, 0))]
    background = max(set(sample), key=sample.count)
    left, right = min(12, width // 4), max(width - 12, 3 * width // 4)

    def inked(y):
        marks = sum(
            sum(abs(a - b) for a, b in zip(image.getpixel((x, y)), background, strict=True)) > 90
            for x in range(left, right)
        )
        # A row inked almost edge to edge is a border or a neighbour's edge, not the label.
        return 0 < marks < 0.9 * (right - left)

    rows = [y for y in range(height) if inked(y)]
    assert rows, "no ink found"
    return rows[0], height - 1 - rows[-1]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_labels_are_centred_in_their_box(live_server, integrated, theme):
    problems = []
    with browser_page({"width": 1440, "height": 900}) as page:
        login(page, live_server, integrated["people"]["author"])
        for name, selector in TARGETS:
            page.goto(live_server.url + reverse(name))
            page.evaluate(f"document.documentElement.setAttribute('data-bs-theme', '{theme}')")
            element = page.locator(selector + ":visible").first
            element.evaluate(PROBE)
            page.wait_for_timeout(50)
            top, bottom = ink_gaps(element.screenshot())
            if abs(top - bottom) > TOLERANCE:
                problems.append(f"{selector}: {top}px above, {bottom}px below the ink")
    assert not problems, "\n".join(problems)
