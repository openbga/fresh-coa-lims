"""Shared check: every count an overview page links shows exactly the rows of the list it opens
(owner rule, review 1). Used by the stability and laboratory overview tests; the dashboard has
its own (tests/test_dashboard.py)."""

import re
from html import unescape

from django.core.paginator import Page

OVERVIEW_ROW = (
    r'<a class="vr-row-link" href="([^"]+)">([^<]+)</a></th>'
    r'<td class="text-end">(\d+)</td>'
)


def listed(response):
    """The number of rows a list returns over all its pages."""
    for key in ("page_obj", "page"):
        page = response.context.get(key)
        if isinstance(page, Page):
            return page.paginator.count
    raise AssertionError("the list has no page of rows")


def assert_counts_open_their_rows(client, overview_url):
    """{label: count} of the overview after checking each count against its list."""
    html = client.get(overview_url).content.decode()
    shown = re.findall(OVERVIEW_ROW, html)
    assert shown, "the overview shows no counts: did its markup change?"
    for url, label, count in shown:
        response = client.get(unescape(url))
        assert response.status_code == 200, (label, url)
        assert listed(response) == int(count), (label, url, count)
    return {unescape(label): int(count) for _, label, count in shown}
