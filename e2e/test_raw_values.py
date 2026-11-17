"""No raw machine values reach the screen (docs/ui-standards.md, "Language and accessibility").

Every staff page without a record in its address, and the first records linked from each list,
are rendered with history and audit events present; their visible text must hold no Python repr
of a dict, list, Decimal or model object, no bare True/False, no unformatted ISO timestamp and no
raw audit action code. The scan is e2e/raw_values.js.
"""

from pathlib import Path

import pytest
from django.urls import URLResolver, get_resolver, reverse
from helpers import browser_page, login, ready_test

from tests.test_integrated_journey import assign_and_sample
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

SCAN = (Path(__file__).parent / "raw_values.js").read_text()
# Addresses that leave the page, download a file or would change state on GET-less forms.
SKIP = ("logout", "export", "download", ".pdf", "/admin/", "page-docs", "two-factor/setup")
RECORD_LINKS = "els => els.slice(0, 2).map(e => e.getAttribute('href'))"


def staff_paths():
    """Every named route without arguments, as a path."""
    paths = []

    def visit(resolver, namespaces=()):
        for route in resolver.url_patterns:
            if isinstance(route, URLResolver):
                if route.namespace == "admin":
                    continue
                visit(route, namespaces + ((route.namespace,) if route.namespace else ()))
            elif route.name and not route.pattern.converters and "<" not in str(route.pattern):
                try:
                    paths.append(reverse(":".join((*namespaces, route.name))))
                except Exception:  # a route that needs arguments some other way
                    continue

    visit(get_resolver())
    return sorted({p for p in paths if not any(part in p for part in SKIP)})


def test_pages_show_no_raw_values(live_server, integrated):
    data = integrated
    ready_test(data, assign_and_sample(data))  # a signed review and its audit events
    hits = []
    with browser_page({"width": 1440, "height": 900}) as page:
        login(page, live_server, data["people"]["author"])
        queue = staff_paths()
        for path in list(queue):
            response = page.goto(live_server.url + path)
            if response and response.status == 200:
                queue += page.eval_on_selector_all(".vr-table tbody a[href^='/']", RECORD_LINKS)
        seen = set()
        for path in queue:
            if path in seen or any(part in path for part in SKIP) or "/sign" in path:
                continue
            seen.add(path)
            response = page.goto(live_server.url + path)
            if not response or response.status != 200:
                continue
            hits += [
                f"{path}: {hit['check']} {hit['text']!r} at {hit['where']}"
                for hit in page.evaluate(SCAN)
            ]
    assert len(seen) > 30, "the crawl reached too few pages"
    assert not hits, "\n".join(hits)
