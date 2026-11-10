"""Keeps docs/pages in step with the URLconf. See .agents/skills/page-documentation/SKILL.md."""

from collections import Counter

import pytest
from django.apps import apps
from django.template.loader import get_template
from django.utils.module_loading import import_string

from pagedocs.coverage import (
    EXEMPT_NAMES,
    PENDING_NAMESPACES,
    documented_routes,
    named_routes,
    page_routes,
)
from pagedocs.docs import REQUIRED_SECTIONS, all_docs

DOCS = all_docs()
ROUTES = set(named_routes())
SKILL = "Use the page-documentation skill (.agents/skills/page-documentation/SKILL.md)."


def test_every_page_route_has_a_doc():
    covered = {name for doc in DOCS for name in doc.urls}
    missing = [name for name in documented_routes() if name not in covered]
    assert not missing, f"Pages without docs/pages entries: {missing}. {SKILL}"


def test_doc_urls_exist_and_are_unique():
    counts = Counter(name for doc in DOCS for name in doc.urls)
    assert not [n for n, c in counts.items() if c > 1], "A URL name is documented twice"
    unknown = sorted(name for name in counts if name not in ROUTES)
    assert not unknown, f"Docs reference URL names that do not exist: {unknown}. {SKILL}"


def test_pending_namespaces_still_have_undocumented_pages():
    covered = {name for doc in DOCS for name in doc.urls}
    for namespace in PENDING_NAMESPACES:
        routes = [n for n in page_routes() if n.startswith(f"{namespace}:")]
        if routes:  # a namespace not routed yet may stay listed until it is integrated
            assert set(routes) - covered, (
                f"'{namespace}' is fully documented: remove it from PENDING_NAMESPACES"
            )


def test_exemptions_are_live_routes():
    stale = sorted(name for name in EXEMPT_NAMES if name not in ROUTES)
    assert not stale, f"Remove stale exemptions from pagedocs/coverage.py: {stale}"


@pytest.mark.parametrize("doc", DOCS, ids=[d.path.name for d in DOCS])
def test_doc_structure_and_references(doc):
    assert doc.title and doc.urls, "title and urls are required"
    assert len(doc.reviewed) == 10 and doc.reviewed[4] == "-", "reviewed must be YYYY-MM-DD"
    sections = doc.sections
    absent = [s for s in REQUIRED_SECTIONS if s not in sections]
    assert not absent, f"{doc.path.name} lacks sections {absent}"
    order = [sections.index(s) for s in REQUIRED_SECTIONS]
    assert order == sorted(order), f"{doc.path.name}: sections out of order"
    for view in doc.meta.get("views", ()):
        assert callable(import_string(view)), view
    for name in doc.meta.get("templates", ()):
        get_template(name)
    for label in doc.meta.get("models", ()):
        apps.get_model(label)
    assert "<script" not in doc.html.lower()
