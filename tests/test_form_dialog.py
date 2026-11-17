"""The shared form dialog's transport keeps every server check (core/form_dialog.py).

A request from static/js/form-dialog.js differs from a page request only by the X-VR-Form header:
the same view authorizes, validates and enforces CSRF; a redirect becomes an HTMX instruction.
"""

import json
import re

import pytest
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.http import HttpResponse, HttpResponseRedirect
from django.test import Client, RequestFactory
from django.urls import reverse

from accounts.services import ROLES
from catalog.models import Material
from core.form_dialog import FormDialogMiddleware
from core.form_surfaces import (
    FORM_SURFACES,
    _route_patterns,
    form_presentation,
    form_route_patterns,
)

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


def test_route_patterns_match_their_own_urls_only():
    patterns = _route_patterns()
    assert len(patterns) == len(FORM_SURFACES)
    for name in FORM_SURFACES:
        path = reverse(name)
        assert [e for e in patterns if re.fullmatch(e["pattern"], path)], name
    assert not any(re.fullmatch(e["pattern"], reverse("catalog:materials")) for e in patterns)


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
@pytest.mark.parametrize("name", sorted(FORM_SURFACES))
def test_every_dialog_form_renders_without_a_signature(client, person, name):
    """A signature is never collected in the form dialog: listed pages carry no PIN field."""
    client.force_login(
        person("synthetic_dialog_all", "analyst", "reviewer", "quality", "admin", "auditor")
    )
    for headers in ({}, DIALOG):
        response = client.get(reverse(name), headers=headers)
        assert response.status_code == 200, (name, response.status_code)
        html = response.content.decode()
        assert not re.search(r"""name=["']pin["']|data-signature-dialog""", html), name


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
@pytest.mark.parametrize("name", sorted(FORM_SURFACES))
def test_dialog_roles_match_the_view(client, person, name):
    """Each route's listed roles are exactly the roles its view lets in."""
    allowed = set(FORM_SURFACES[name][1])
    for role in sorted(allowed):
        client.force_login(person(f"synthetic_dialog_{role}", role))
        assert client.get(reverse(name)).status_code == 200, (name, role)
    others = sorted(ROLES - allowed)
    client.force_login(person("synthetic_dialog_others", *others))
    assert client.get(reverse(name)).status_code == 403, (name, others)


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
