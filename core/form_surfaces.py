"""Which form pages open in the shared form dialog: presentation, never authorization.

Every form opens in the dialog (docs/ui-standards.md, "Lists, dialogs and notices"):
static/js/form-dialog.js opens a link to one of these routes in #vr-form-dialog over the page it
was clicked on, fetching the page with the X-VR-Form header; the view, its permission checks, its
validation and its signing rules are the same as for the full page. Without JavaScript, or opened
by its address, each stays an ordinary page. tests/test_form_dialog.py proves that every route
whose view takes a form is listed here or in NOT_FORM_PAGES with its reason.

Signing pages are listed too: the signature card opens in the dialog over the record, with the
username, PIN and reason entered afresh for every signature and every check on the server.
"""

import re
from dataclasses import dataclass
from functools import cache

from django.urls import URLResolver, get_resolver

# view name -> (dialog size, roles that may open it). Size by the form's fields: sm one column of
# a few fields; md two columns (the default); lg wide forms, tables of inputs and signing over a
# long record summary. The roles repeat the view's own require_role check; they only decide which
# routes a page lists for the dialog, so no page names a form its viewer may not open (an
# administrator's pages list no scientific form). tests/test_form_dialog.py proves each matches.
EVERYONE = ("admin", "analyst", "auditor", "quality", "reviewer")
FORM_SURFACES = {
    # Account
    "core:pin": ("sm", EVERYONE),
    "accounts:password_change": ("sm", EVERYONE),
    "accounts:announcement_change": ("md", ("admin",)),
    "accounts:two_factor_setup": ("md", EVERYONE),
    "accounts:security_key_add": ("md", EVERYONE),
    "accounts:user_create": ("md", ("admin",)),
    "accounts:user_action": ("md", ("admin",)),
    # Rule sets
    "core:rule_approve": ("lg", ("quality",)),
    # Lots, receipt, certificates, samples, results, disposition
    "quality:lot_new": ("md", ("analyst",)),
    "quality:lot_record": ("md", ("admin", "auditor", "quality")),
    "quality:receipt_new": ("md", ("analyst",)),
    "quality:receipt_correct": ("md", ("analyst",)),
    "quality:lot_dates": ("md", ("analyst", "quality")),
    "quality:reassessment_new": ("md", ("analyst", "quality")),
    "quality:reassessment_tests": ("lg", ("analyst",)),
    "quality:reassessment_conclude": ("lg", ("quality",)),
    "quality:reassessment_withdraw": ("md", ("quality",)),
    "quality:certificate_new": ("md", ("analyst",)),
    "quality:certificate_correct": ("md", ("analyst",)),
    "quality:certificate_withdraw": ("sm", ("analyst",)),
    "quality:acceptance_new": ("md", ("analyst",)),
    "quality:acceptance_accept": ("md", ("reviewer",)),
    "quality:acceptance_withdraw": ("md", ("analyst", "quality", "reviewer")),
    "quality:sample_new": ("sm", ("analyst",)),
    "quality:result_new": ("md", ("analyst",)),
    "quality:review": ("md", ("reviewer",)),
    "quality:disposition": ("md", ("quality",)),
    "quality:lot_reject": ("md", ("quality",)),
    "quality:lot_cancel": ("md", ("quality",)),
    # Testing
    "analytical:observation_new": ("md", ("analyst",)),
    "analytical:observation_correct": ("md", ("analyst",)),
    "analytical:contract_result": ("md", ("analyst",)),
    "analytical:test_batch": ("sm", ("analyst",)),
    "analytical:test_return": ("sm", ("reviewer",)),
    "analytical:test_review": ("md", ("reviewer",)),
    "analytical:test_not_completed": ("md", ("quality",)),
    "analytical:batch_new": ("md", ("analyst",)),
    "analytical:qc_record": ("md", ("analyst",)),
    "analytical:qc_correct": ("md", ("analyst",)),
    "analytical:batch_reject": ("md", ("reviewer",)),
    "analytical:entry_new": ("md", ("analyst", "quality", "reviewer")),
    "analytical:escalate": ("md", ("quality", "reviewer")),
    "analytical:authorize": ("md", ("quality",)),
    "analytical:conclude": ("md", ("quality",)),
    "analytical:raw_file_new": ("md", ("analyst",)),
    "analytical:import_new": ("md", ("analyst",)),
    "analytical:import_file": ("lg", ("analyst",)),
    # Planning
    "planning:plan": ("lg", ("quality", "reviewer")),
    "planning:targets_change": ("md", ("quality",)),
    # Stability and retention
    "stability:protocol_new": ("md", ("analyst", "quality")),
    "stability:condition_new": ("md", ("analyst", "quality")),
    "stability:timepoint_new": ("sm", ("analyst", "quality")),
    "stability:protocol_approve": ("lg", ("quality",)),
    "stability:protocol_withdraw": ("sm", ("analyst", "quality")),
    "stability:study_new": ("md", ("analyst", "quality")),
    "stability:study_close": ("md", ("quality",)),
    "stability:pull_record": ("md", ("analyst",)),
    "stability:pull_tests": ("lg", ("analyst",)),
    "stability:pull_evidence": ("md", ("analyst",)),
    "stability:pull_missed": ("sm", ("analyst", "quality")),
    "stability:pull_accept": ("md", ("reviewer",)),
    "stability:reserve_new": ("md", ("analyst", "quality")),
    "stability:obligation_new": ("md", ("analyst", "quality")),
    "stability:anchor_set": ("sm", ("analyst", "quality")),
    "stability:hold_new": ("md", ("analyst", "quality", "reviewer")),
    "stability:hold_release": ("md", ("quality",)),
    # Sampling and requirements
    "sampling:assign": ("lg", ("analyst", "quality")),
    "sampling:replace": ("lg", ("quality",)),
    "sampling:decide": ("lg", ("quality",)),
    "sampling:sampling_new": ("md", ("analyst",)),
    "sampling:sampling_correct": ("md", ("analyst",)),
    "sampling:deviation_assess": ("md", ("quality",)),
    "sampling:plan_new": ("lg", ("quality",)),
    "sampling:plan_version_new": ("lg", ("quality",)),
    "sampling:plan_approve": ("lg", ("quality",)),
    "sampling:plan_withdraw": ("sm", ("quality",)),
    # Specifications and methods
    "catalog:specification_new": ("lg", ("quality",)),
    "catalog:specification_version_new": ("lg", ("quality",)),
    "catalog:test_new": ("md", ("quality",)),
    "catalog:test_remove": ("sm", ("quality",)),
    "catalog:specification_approve": ("lg", ("quality",)),
    "catalog:specification_withdraw": ("sm", ("quality",)),
    "catalog:method_new": ("md", ("quality",)),
    "catalog:method_version_new": ("md", ("quality",)),
    "catalog:method_approve": ("lg", ("quality",)),
    "catalog:method_withdraw": ("sm", ("quality",)),
    "catalog:qc_check_new": ("md", ("quality",)),
    "catalog:qc_check_remove": ("sm", ("quality",)),
    "catalog:calculation_set": ("lg", ("quality",)),
    "catalog:calculation_clear": ("sm", ("quality",)),
    "catalog:calculation_input_new": ("md", ("quality",)),
    "catalog:calculation_input_remove": ("sm", ("quality",)),
    "catalog:file_import_set": ("lg", ("quality",)),
    "catalog:file_import_clear": ("sm", ("quality",)),
    "catalog:material_new": ("md", ("quality",)),
    # Suppliers
    "suppliers:new": ("md", ("quality",)),
    "suppliers:qualification_approve": ("md", ("quality",)),
    "suppliers:qualification_revoke": ("md", ("quality",)),
    "suppliers:qualification_new": ("md", ("quality",)),
    # Laboratory
    "laboratory:equipment_new": ("md", ("analyst", "quality")),
    "laboratory:calibration_new": ("md", ("analyst", "quality")),
    "laboratory:equipment_out_of_service": ("md", ("analyst", "quality", "reviewer")),
    "laboratory:equipment_return": ("md", ("quality",)),
    "laboratory:equipment_connection_new": ("md", ("quality",)),
    "laboratory:equipment_connection_end": ("sm", ("quality",)),
    "laboratory:equipment_qualification_new": ("md", ("analyst", "quality", "reviewer")),
    "laboratory:calibration_accept": ("md", ("reviewer",)),
    "laboratory:qualification_approve": ("md", ("quality",)),
    "laboratory:qualification_revoke": ("md", ("quality",)),
    "laboratory:contract_approval_approve": ("md", ("quality",)),
    "laboratory:contract_approval_revoke": ("md", ("quality",)),
    "laboratory:qualification_new": ("md", ("analyst", "quality", "reviewer")),
    "laboratory:reagent_new": ("md", ("analyst", "quality")),
    "laboratory:reagent_release": ("md", ("reviewer",)),
    "laboratory:reagent_reject": ("md", ("analyst", "quality", "reviewer")),
    "laboratory:contract_laboratory_new": ("md", ("quality",)),
    "laboratory:contract_approval_new": ("md", ("quality",)),
    "laboratory:use_new": ("md", ("analyst",)),
    # Validation
    "validation:use_new": ("lg", ("quality",)),
    "validation:use_accept": ("md", ("quality",)),
    "validation:use_withdraw": ("sm", ("quality",)),
    "validation:rehearsal_new": ("lg", ("admin", "quality")),
    "validation:rehearsal_file_new": ("md", ("admin", "quality")),
    "validation:rehearsal_accept": ("md", ("quality",)),
    "validation:rehearsal_withdraw": ("sm", ("admin", "quality")),
    # Impact assessments
    "impact:new": ("lg", ("quality",)),
    "impact:find": ("md", ("quality",)),
    "impact:add": ("md", ("quality",)),
    "impact:decide": ("md", ("quality",)),
    "impact:hold": ("sm", ("quality",)),
    "impact:conclude": ("lg", ("quality",)),
    "impact:withdraw": ("md", ("quality",)),
    # Certificates of analysis
    "reporting:new": ("lg", ("quality",)),
    # A lookup: the answer shows in the dialog above the form, which stays open for the next file.
    "reporting:check": ("md", EVERYONE),
    "reporting:issue_sign": ("lg", ("quality",)),
    "reporting:amend_sign": ("lg", ("quality",)),
    "reporting:withdraw": ("md", ("quality",)),
    "reporting:notify": ("md", ("quality",)),
}

# Routes whose view takes a form but whose page is not a form page, with the reason.
NOT_FORM_PAGES = {
    "analytical:instrument_read": "POST-only JSON: the result form's script passes on what a "
    "connected balance or meter sent; it renders no page",
    "login_verify": "a sign-in step: there is no session and no workspace page to open it over",
    "login_passkey": "a sign-in step: there is no session and no workspace page to open it over",
    "accounts:two_factor": "the account's two-factor page, its factors listed; its confirmation "
    "opens in the dialog from the page (data-vr-local-form) and leads on to a setup step",
    "accounts:single_sign_on": "the account's single sign-on page, its link shown; linking or "
    "unlinking opens in the dialog from the page (data-vr-local-form)",
    "core:rules": "a list; its New revision form opens in the dialog from the page "
    "(form_page dialog=)",
    "core:audit": "a list; the review records the events ticked in the list itself",
    "analytical:test_detail": "a record; its Submit for review form opens in the dialog from the "
    "page (form_page dialog=)",
    "analytical:lot_testing": "a record; its only form is a one-button action without fields",
    "planning:take": "POST-only: the Assign to me button of a work list row; it renders no page",
    "certificate_check": "the check without an account: there is no session and no workspace "
    "page to open it over",
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
