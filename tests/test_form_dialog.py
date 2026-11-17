"""The shared form dialog's transport keeps every server check (core/form_dialog.py).

A request from static/js/form-dialog.js differs from a page request only by the X-VR-Form header:
the same view authorizes, validates and enforces CSRF; a redirect becomes an HTMX instruction.
"""

import inspect
import json
import logging
import re

import pytest
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.http import HttpResponse, HttpResponseRedirect
from django.test import Client, RequestFactory
from django.urls import URLResolver, get_resolver, reverse

from accounts.services import ROLES
from analytical.models import AnalyticalTest
from catalog.models import Material
from core.form_dialog import FormDialogMiddleware
from core.form_surfaces import (
    FORM_SURFACES,
    NOT_FORM_PAGES,
    _route_patterns,
    form_presentation,
    form_route_patterns,
)
from core.models import ElectronicSignature, PINCredential
from tests.test_integrated_journey import PIN, assign_and_sample, observed_test
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

DIALOG = {"X-VR-Form": "1"}
PASSWORD = "Synthetic-dialog-login-2026!"


def transport(response, headers=DIALOG):
    request = RequestFactory().post("/", headers=headers)
    return FormDialogMiddleware(lambda request: response)(request)


@pytest.fixture
def person(django_user_model):
    def make(username, *roles):
        user = django_user_model.objects.create_user(username, password=PASSWORD)
        user.groups.add(*[Group.objects.get_or_create(name=role)[0] for role in roles])
        return user

    return make


def test_redirect_to_another_dialog_form_loads_it_in_the_dialog():
    destination = reverse("catalog:material_new") + "?from=dialog"
    response = transport(HttpResponseRedirect(destination))
    assert response.status_code == 204
    assert "Location" not in response
    assert json.loads(response["HX-Location"]) == {
        "path": destination,
        "target": "#vr-form-content",
        "push": "false",
        "headers": {"X-VR-Form": "1"},
    }
    assert "X-VR-Form" in response["Vary"]


@pytest.mark.parametrize(
    "destination", ["/catalog/materials/", "https://example.invalid/catalog/materials/new/"]
)
def test_redirect_elsewhere_navigates_the_whole_page(destination):
    response = transport(HttpResponseRedirect(destination))
    assert response.status_code == 204
    assert response["HX-Redirect"] == destination
    assert "HX-Location" not in response


def test_page_requests_and_other_responses_pass_unchanged():
    page = transport(HttpResponseRedirect("/catalog/materials/"), headers={})
    assert page.status_code == 302 and page["Location"] == "/catalog/materials/"
    assert "X-VR-Form" in page["Vary"]
    for status in (200, 403, 422):
        assert transport(HttpResponse(status=status)).status_code == status


def routes(resolver=None, namespaces=(), converters=None):
    """(view name, view, {argument: sample value}) for every named route outside the admin."""
    samples = {"int": 1, "slug": "synthetic", "string": "synthetic", "path": "synthetic"}
    for route in (resolver or get_resolver()).url_patterns:
        found = {**(converters or {}), **route.pattern.converters}
        if isinstance(route, URLResolver):
            if route.namespace != "admin":
                spaces = namespaces + ((route.namespace,) if route.namespace else ())
                yield from routes(route, spaces, found)
        elif route.name:
            kwargs = {
                name: samples[type(c).__name__.removesuffix("Converter").lower()]
                for name, c in found.items()
            }
            yield ":".join((*namespaces, route.name)), route.callback, kwargs


POSTED = re.compile(r"request\.POST|request\.method\s*==\s*[\"']POST")


def takes_form(view):
    """The view, or a helper of its module it hands the request to, reads a submitted form."""
    target = getattr(view, "view_class", None) or inspect.unwrap(view)
    try:
        source = inspect.getsource(target)
    except OSError, TypeError:
        return False
    if POSTED.search(source):
        return True
    module = inspect.getmodule(target)
    for name in set(re.findall(r"\b(\w+)\(\s*request\b", source)):
        helper = getattr(module, name, None)
        if inspect.isfunction(helper) and helper is not target:
            try:
                if POSTED.search(inspect.getsource(inspect.unwrap(helper))):
                    return True
            except OSError, TypeError:
                continue
    return False


def test_every_form_opens_in_the_dialog():
    """Every route whose view takes a form is a dialog form, or says why its page is not one."""
    found = {name for name, view, _ in routes() if takes_form(view)}
    unexplained = found - set(FORM_SURFACES) - set(NOT_FORM_PAGES)
    assert not unexplained, f"add to FORM_SURFACES (core/form_surfaces.py): {sorted(unexplained)}"
    assert not set(FORM_SURFACES) & set(NOT_FORM_PAGES)
    named = {name for name, _, _ in routes()}
    assert set(FORM_SURFACES) | set(NOT_FORM_PAGES) <= named, "a listed route no longer exists"
    assert {size for size, _ in FORM_SURFACES.values()} <= {"sm", "md", "lg"}


def test_route_patterns_match_their_own_urls_only():
    patterns = _route_patterns()
    assert len(patterns) == len(FORM_SURFACES)
    paths = {name: reverse(name, kwargs=kwargs) for name, _, kwargs in routes()}
    for name in FORM_SURFACES:
        assert [e for e in patterns if re.fullmatch(e["pattern"], paths[name])], name
    for name in ("catalog:materials", "quality:lot_detail", "analytical:test_detail"):
        assert not any(re.fullmatch(e["pattern"], paths[name]) for e in patterns), name


@pytest.mark.django_db
def test_signed_out_dialog_request_navigates_to_sign_in(client):
    response = client.get(reverse("catalog:material_new"), headers=DIALOG)
    assert response.status_code == 204
    assert response["HX-Redirect"].startswith(reverse("login"))
    assert "next=" in response["HX-Redirect"]
    assert not response.content


@pytest.mark.django_db
def test_dialog_header_does_not_bypass_roles_or_csrf(client, person):
    url = reverse("catalog:material_new")
    client.force_login(person("synthetic_dialog_reviewer", "reviewer"))
    assert client.get(url).status_code == 403
    assert client.get(url, headers=DIALOG).status_code == 403
    denied = client.post(
        url, {"code": "syn-denied", "name": "Denied", "kind": "api"}, headers=DIALOG
    )
    assert denied.status_code == 403
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(person("synthetic_dialog_author", "quality"))
    forged = strict.post(url, {"code": "syn-no-token", "name": "No token"}, headers=DIALOG)
    assert forged.status_code == 403
    assert not Material.objects.filter(code__in=["syn-denied", "syn-no-token"]).exists()


@pytest.mark.django_db
def test_dialog_keeps_validation_and_the_success_message(client, person):
    url = reverse("catalog:material_new")
    client.force_login(person("synthetic_dialog_author", "quality"))
    invalid = client.post(url, {"code": "", "name": "Synthetic kept name"}, headers=DIALOG)
    assert invalid.status_code in (200, 422)
    assert b"Synthetic kept name" in invalid.content
    assert b'aria-invalid="true"' in invalid.content
    assert not Material.objects.filter(name="Synthetic kept name").exists()
    kind = Material._meta.get_field("kind").choices[0][0]
    saved = client.post(
        url,
        {
            "code": "syn-dialog-001",
            "name": "Synthetic dialog material",
            "kind": kind,
            "reason": "Synthetic dialog transport check",
        },
        headers=DIALOG,
    )
    assert saved.status_code == 204, saved.content[:400]
    assert saved["HX-Redirect"] == reverse("catalog:materials")
    assert Material.objects.filter(code="syn-dialog-001").exists()
    destination = client.get(saved["HX-Redirect"])
    assert "Material syn-dialog-001 created." in [
        str(m) for m in get_messages(destination.wsgi_request)
    ]


@pytest.mark.django_db
def test_dialog_presentation_only_for_listed_routes_with_the_header(rf):
    listed = rf.get(reverse("catalog:material_new"), headers=DIALOG)
    listed.resolver_match = type("Match", (), {"view_name": "catalog:material_new"})()
    assert form_presentation(listed)["form_dialog"] is True
    assert form_presentation(listed)["form_surface_layout"] == "layouts/form_fragment.html"
    page = rf.get(reverse("catalog:material_new"))
    page.resolver_match = listed.resolver_match
    assert form_presentation(page)["form_dialog"] is False
    other = rf.get(reverse("catalog:materials"), headers=DIALOG)
    other.resolver_match = type("Match", (), {"view_name": "catalog:materials"})()
    assert form_presentation(other)["form_dialog"] is False


@pytest.mark.django_db
def test_dialog_fragment_has_no_shell_and_no_history(client, person):
    client.force_login(person("synthetic_dialog_author", "quality"))
    url = reverse("catalog:material_new")
    assert b"<!doctype html>" in client.get(url).content
    fragment = client.get(url, headers=DIALOG).content
    assert b"data-vr-form-page" in fragment
    assert b"<!doctype html>" not in fragment
    assert b"vr-timeline" not in fragment and b"vr-history-item" not in fragment


@pytest.mark.django_db
def test_dialog_roles_match_the_views(client, person):
    """Each route's listed roles are exactly the roles its view lets past its role check (a
    missing record then answers 404, a refused role 403)."""
    users = {role: person(f"synthetic_dialog_{role}", role) for role in sorted(ROLES)}
    paths = {name: reverse(name, kwargs=kwargs) for name, _, kwargs in routes()}
    wrong = []
    for name, (_, roles) in sorted(FORM_SURFACES.items()):
        admitted = set()
        for role, user in users.items():
            client.force_login(user)
            if client.get(paths[name]).status_code != 403:
                admitted.add(role)
        if admitted != set(roles):
            wrong.append(f"{name}: view admits {sorted(admitted)}, listed {sorted(roles)}")
    assert not wrong, "\n".join(wrong)


@pytest.mark.django_db
def test_a_page_lists_only_the_dialog_routes_the_user_may_open(person):
    from django.contrib.auth.models import AnonymousUser

    assert form_route_patterns(AnonymousUser()) == []
    admin = person("synthetic_dialog_admin", "admin")
    listed = {e["pattern"] for e in form_route_patterns(admin)}
    expected = {e["pattern"] for e in _route_patterns() if "admin" in FORM_SURFACES[e["name"]][1]}
    assert listed == expected
    assert not any(re.fullmatch(p, reverse("analytical:batch_new")) for p in listed)
    analyst = person("synthetic_dialog_analyst", "analyst")
    assert any(
        re.fullmatch(e["pattern"], reverse("analytical:batch_new"))
        for e in form_route_patterns(analyst)
    )


# Signing in the dialog: the same view and service as the signing page, so every rule holds.
WRONG_PIN = "19283746"
REASON = "Synthetic independent review in the dialog"


@pytest.fixture
def submitted(integrated):
    test, investigation = observed_test(integrated, assign_and_sample(integrated), "100.25")
    assert investigation is None and test.state == "submitted"
    return integrated, test


def sign_in_dialog(client, test, pin, *, username, revision=None):
    return client.post(
        reverse("analytical:test_review", args=[test.pk]),
        {
            "signature_username": username,
            "pin": pin,
            "reason": REASON,
            "expected_revision": test.revision if revision is None else revision,
        },
        headers=DIALOG,
    )


def pin_input(html):
    match = re.search(r"<input[^>]*name=\"pin\"[^>]*>", html)
    assert match, "the signature PIN field is offered again"
    return match.group(0)


@pytest.mark.django_db(transaction=True)
def test_signing_in_the_dialog_keeps_every_signing_rule(client, submitted, caplog):
    data, test = submitted
    reviewer = data["people"]["reviewer"]
    client.force_login(reviewer)
    caplog.set_level(logging.DEBUG)
    signatures = ElectronicSignature.objects.count()

    opened = client.get(reverse("analytical:test_review", args=[test.pk]), headers=DIALOG)
    assert opened.status_code == 200
    html = opened.content.decode()
    assert "data-vr-form-page" in html and "vr-sign-card" in html and "<!doctype" not in html
    assert "value=" not in pin_input(html)

    # A wrong PIN: refused, counted, the PIN field empty again, username and reason kept.
    wrong = sign_in_dialog(client, test, WRONG_PIN, username=reviewer.username)
    assert wrong.status_code == 422
    html = wrong.content.decode()
    assert "Signature PIN was not accepted." in html
    assert "value=" not in pin_input(html)
    assert reviewer.username in html and REASON in html
    assert WRONG_PIN not in html
    assert PINCredential.objects.get(user=reviewer).failures == 1

    # A record changed since the dialog opened is refused, even with the right PIN.
    stale = sign_in_dialog(
        client, test, PIN, username=reviewer.username, revision=test.revision - 1
    )
    assert stale.status_code == 422 and PIN not in stale.content.decode()
    assert "value=" not in pin_input(stale.content.decode())
    assert ElectronicSignature.objects.count() == signatures

    # The right PIN signs; the dialog hands the page back to the record with its message.
    signed = sign_in_dialog(client, test, PIN, username=reviewer.username)
    assert signed.status_code == 204, signed.content[:300]
    record = reverse("analytical:test_detail", args=[test.pk])
    assert signed["HX-Redirect"] == record
    assert ElectronicSignature.objects.count() == signatures + 1
    test.refresh_from_db()
    assert test.state == "reviewed"
    page = client.get(record).content.decode()
    assert f"Signed review recorded for {test.label}." in page

    for text in (PIN, WRONG_PIN):
        assert not any(text in r.getMessage() for r in caplog.records), "a PIN reached a log"


@pytest.mark.django_db(transaction=True)
def test_dialog_signing_locks_after_five_wrong_pins(client, submitted):
    data, test = submitted
    reviewer = data["people"]["reviewer"]
    client.force_login(reviewer)
    for _ in range(5):
        assert (
            sign_in_dialog(client, test, WRONG_PIN, username=reviewer.username).status_code == 422
        )
    locked = sign_in_dialog(client, test, PIN, username=reviewer.username)
    assert locked.status_code == 422
    assert "Signature PIN is temporarily locked." in locked.content.decode()
    assert "value=" not in pin_input(locked.content.decode())
    test.refresh_from_db()
    assert test.state == "submitted"


@pytest.mark.django_db(transaction=True)
def test_dialog_refuses_self_review_before_any_pin(client, submitted):
    data, test = submitted
    producer = data["people"]["analyst"]  # recorded the observation; also holds reviewer
    client.force_login(producer)
    opened = client.get(reverse("analytical:test_review", args=[test.pk]), headers=DIALOG)
    assert opened.status_code == 204
    assert opened["HX-Redirect"] == reverse("analytical:test_detail", args=[test.pk])
    signatures = ElectronicSignature.objects.count()
    refused = sign_in_dialog(client, test, PIN, username=producer.username)
    assert refused.status_code == 204 and "HX-Redirect" in refused
    assert ElectronicSignature.objects.count() == signatures
    assert AnalyticalTest.objects.get(pk=test.pk).state == "submitted"
