"""Which dedicated form pages open in the shared form dialog: presentation, never authorization.

static/js/form-dialog.js opens a link to one of these routes in the dialog (#vr-form-dialog) and
fetches the page with the X-VR-Form header; the view, its permission checks and its validation
are the same as for the full page. Without JavaScript every link stays an ordinary page.

Only plain data-entry pages are listed. Signing pages (username, PIN and reason) stay on their
own page and the signature dialog, so a signature is never collected inside the form dialog
(tests/test_form_dialog.py renders every listed page and checks it has no PIN field).
"""

import re
from dataclasses import dataclass
from functools import cache

from django.urls import URLResolver, get_resolver

# view name -> (dialog size, roles that may open it). lg: one column of fields; xl: wide forms
# and entry grids. The roles repeat the view's own require_role check; they only decide which
# routes a page lists for the dialog, so a role never sees a create action it lacks, and the view
# still authorizes every request. tests/test_form_dialog.py proves each list matches its view.
QUALITY = ("quality",)
FORM_SURFACES = {
    "quality:lot_new": ("lg", ("analyst",)),
    "analytical:batch_new": ("lg", ("analyst",)),
    "sampling:plan_new": ("xl", QUALITY),
    "catalog:specification_new": ("xl", QUALITY),
    "catalog:method_new": ("lg", QUALITY),
    "catalog:material_new": ("lg", QUALITY),
    "suppliers:new": ("lg", QUALITY),
    "stability:protocol_new": ("lg", ("analyst", "quality")),
    "stability:study_new": ("lg", ("analyst", "quality")),
    "stability:reserve_new": ("lg", ("analyst", "quality")),
    "stability:obligation_new": ("lg", ("analyst", "quality")),
    "stability:hold_new": ("lg", ("analyst", "reviewer", "quality")),
    "laboratory:equipment_new": ("lg", ("analyst", "quality")),
    "laboratory:qualification_new": ("lg", ("analyst", "reviewer", "quality")),
    "laboratory:reagent_new": ("lg", ("analyst", "quality")),
    "laboratory:contract_laboratory_new": ("lg", QUALITY),
    "laboratory:use_new": ("lg", ("analyst",)),
    "validation:rehearsal_new": ("lg", ("quality", "admin")),
    "reporting:new": ("lg", QUALITY),
}

FORM_HEADER = "X-VR-Form"


@dataclass(frozen=True)
class FormSurface:
    size: str


def surface_for_request(request):
    """Presentation metadata for an already resolved request, or None."""
    match = getattr(request, "resolver_match", None)
    surface = FORM_SURFACES.get(match.view_name) if match is not None else None
    return FormSurface(surface[0]) if surface else None


def is_dialog_request(request):
    return request.headers.get(FORM_HEADER) == "1"


def form_route_patterns(user=None):
    """The listed routes the user's roles may open (none when signed out), for the page."""
    if user is None or not user.is_authenticated:
        return []
    roles = set(user.groups.values_list("name", flat=True))
    return [
        {"pattern": route["pattern"], "size": route["size"]}
        for route in _route_patterns()
        if roles & set(FORM_SURFACES[route["name"]][1])
    ]


@cache
def _route_patterns():
    """JavaScript-compatible path regexes of the listed routes, from Django's own routes.

    The application's converters use regex syntax shared by Python and JavaScript; Python's
    named-group spelling and end anchor are rewritten. Callers match URL.pathname, without its
    query string or fragment.
    """
    result = []

    def visit(resolver, prefix="", namespaces=()):
        for route in resolver.url_patterns:
            regex = route.pattern.regex.pattern.removeprefix("^")
            if isinstance(route, URLResolver):
                child = namespaces + ((route.namespace,) if route.namespace else ())
                visit(route, prefix + regex, child)
                continue
            name = ":".join((*namespaces, route.name)) if route.name else ""
            if name not in FORM_SURFACES:
                continue
            pattern = re.sub(r"\(\?P<[^>]+>", "(?:", prefix + regex).replace(r"\Z", "$")
            if not pattern.endswith("$"):
                pattern += "$"
            result.append({"name": name, "pattern": "^/" + pattern, "size": FORM_SURFACES[name][0]})

    visit(get_resolver())
    return result


def form_presentation(request):
    """Context processor: the dialog's route list and how this response is framed.

    form_dialog is true when this response fills the shared form dialog; the page then renders
    in layouts/form_fragment.html (no shell, no history panels) instead of layouts/document.html.
    """
    surface = surface_for_request(request)
    form_dialog = bool(surface and is_dialog_request(request))
    return {
        "form_surface": surface,
        "form_route_patterns": form_route_patterns(getattr(request, "user", None)),
        "form_dialog": form_dialog,
        "form_surface_layout": (
            "layouts/form_fragment.html" if form_dialog else "layouts/document.html"
        ),
    }
