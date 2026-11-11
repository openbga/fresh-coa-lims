"""Which named routes must have page documentation.

Every named URL in the root URLconf is a documented page unless it is listed here. Keep the
exemptions few and explain each: they are endpoints that do not render a staff page in the
application shell.
"""

from django.urls import URLPattern, URLResolver, get_resolver

EXEMPT_NAMESPACES = {
    "admin": "Django admin renders its own documented interface outside the application shell.",
}
EXEMPT_NAMES = {
    "health": "JSON process health probe for the platform.",
    "ready": "JSON database readiness probe for the platform.",
    "login": "Entrance page outside the signed-in shell; the panel is not shown before sign-in.",
    "logout": "POST-only sign-out action; redirects without rendering a page.",
    "pagedocs:doc": "The documentation endpoint itself.",
}

# Transitional backlog: namespaces where not every page is documented yet. Docs that do exist in
# these namespaces are still validated. Remove a namespace as soon as it is complete; the coverage
# test fails while a listed namespace has no undocumented page. Do not add to this list to bypass
# a missing doc for a page you are changing.
_BACKLOG = "Pages built before page documentation existed; not yet documented."
PENDING_NAMESPACES = dict.fromkeys((), _BACKLOG)


def named_routes(patterns=None, namespace=""):
    """Yield ``namespace:name`` for every named URL pattern, including nested includes."""
    if patterns is None:
        patterns = get_resolver().url_patterns
    for entry in patterns:
        if isinstance(entry, URLResolver):
            nested = entry.namespace or ""
            full = ":".join(p for p in (namespace, nested) if p)
            yield from named_routes(entry.url_patterns, full)
        elif isinstance(entry, URLPattern) and entry.name:
            yield f"{namespace}:{entry.name}" if namespace else entry.name


def exempt(name):
    return name in EXEMPT_NAMES or name.split(":", 1)[0] in EXEMPT_NAMESPACES and ":" in name


def page_routes():
    """Named routes that are pages and should each be covered by one docs/pages file."""
    return sorted({name for name in named_routes() if not exempt(name)})


def pending(name):
    return ":" in name and name.split(":", 1)[0] in PENDING_NAMESPACES


def documented_routes():
    """Page routes that must already have a doc (pages outside the pending backlog)."""
    return [name for name in page_routes() if not pending(name)]
