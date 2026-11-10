"""HTTP behaviour: role boundaries, complete UI states and signing through the web form."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Material, MethodRevision, Specification, SpecificationRevision
from core.models import AuditEvent, ElectronicSignature, PINCredential

from .factories import PIN, approve, material, method_revision, numeric_line, specification

pytestmark = pytest.mark.django_db(transaction=True)

LISTS = ["catalog:specifications", "catalog:methods", "catalog:materials"]


def login(client, user):
    client.force_login(user)
    return client


@pytest.mark.parametrize("name", LISTS)
@pytest.mark.parametrize("role", ["analyst", "reviewer", "auditor", "admin", "author"])
def test_lists_readable_by_lab_roles_with_empty_state(client, people, name, role):
    response = login(client, people[role]).get(reverse(name))
    assert response.status_code == 200
    body = response.content.decode()
    assert "vr-empty" in body
    assert ("New " in body) is (role == "author")


@pytest.mark.parametrize("name", LISTS)
def test_lists_denied_without_role(client, name):
    outsider = get_user_model().objects.create_user("outsider", password="x-synthetic-91")
    assert login(client, outsider).get(reverse(name)).status_code == 403


def test_list_filters_and_filtered_empty_state(client, people):
    material(people["author"], code="syn-filter-1")
    url = reverse("catalog:materials")
    client = login(client, people["analyst"])
    assert "syn-filter-1" in client.get(url, {"q": "filter"}).content.decode()
    body = client.get(url, {"q": "nothing-matches"}).content.decode()
    assert "No materials match these filters" in body and "Clear filters" in body


@pytest.mark.parametrize("role", ["analyst", "reviewer", "admin", "auditor"])
def test_non_quality_cannot_open_or_post_create_forms(client, people, role):
    client = login(client, people[role])
    for name in ("catalog:material_new", "catalog:method_new", "catalog:specification_new"):
        assert client.get(reverse(name)).status_code == 403
    response = client.post(
        reverse("catalog:material_new"),
        {"code": "x", "name": "x", "kind": "raw_material", "reason": "x"},
    )
    assert response.status_code == 403
    assert not Material.objects.exists()


def test_create_material_and_form_errors_preserve_input(client, people):
    client = login(client, people["author"])
    response = client.post(
        reverse("catalog:material_new"),
        {
            "code": "Not a slug!",
            "name": "Synthetic kept name",
            "kind": "raw_material",
            "reason": "",
        },
    )
    assert response.status_code == 422
    body = response.content.decode()
    assert "Synthetic kept name" in body and "alert-danger" in body
    response = client.post(
        reverse("catalog:material_new"),
        {"code": "syn-web-1", "name": "Synthetic", "kind": "raw_material", "reason": "New"},
    )
    assert response.status_code == 302
    assert Material.objects.get().created_by == people["author"]


def test_create_specification_flow_and_add_test(client, people):
    mat = material(people["author"])
    method = approve(method_revision(people["author"]), people["approver"]).method
    client = login(client, people["author"])
    response = client.post(
        reverse("catalog:specification_new"),
        {
            "code": "spec-web",
            "title": "Synthetic web spec",
            "material": mat.pk,
            "stage": "incoming",
            "scope": "general",
            "basis": "Synthetic",
            "effective_from": "2026-01-01T00:00",
            "effective_until": "2030-01-01T00:00",
            "reason": "New",
        },
    )
    revision = SpecificationRevision.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("catalog:specification_revision", args=[revision.pk])
    add = reverse("catalog:test_new", args=[revision.pk])
    bad = client.post(
        add,
        {
            "code": "assay",
            "name": "Assay",
            "method": method.pk,
            "position": 1,
            "result_type": "numeric",
            "replicates": "1",
            "max_retests": "0",
            "unit": "",
            "lower_limit": "98.0",
            "reason": "Add",
        },
    )
    assert bad.status_code == 422
    assert "A numeric test needs a unit." in bad.content.decode()
    good = client.post(
        add,
        {
            "code": "assay",
            "name": "Assay",
            "method": method.pk,
            "position": 1,
            "result_type": "numeric",
            "replicates": "1",
            "max_retests": "0",
            "unit": "%",
            "lower_limit": "98.0",
            "lower_inclusive": "on",
            "upper_limit": "102.0",
            "upper_inclusive": "on",
            "required": "on",
            "reason": "Add",
        },
    )
    assert good.status_code == 302
    page = client.get(reverse("catalog:specification_revision", args=[revision.pk]))
    body = page.content.decode()
    assert "98 – 102 %" in body
    assert "another quality approver must sign" in body
    assert reverse("catalog:specification_approve", args=[revision.pk]) not in body


def signing_post(client, url, revision, **overrides):
    data = {
        "reason": "Checked synthetic content",
        "signature_username": overrides.pop("username", None),
        "pin": PIN,
        "expected_revision": revision.revision,
    }
    data.update(overrides)
    return client.post(url, data)


def test_author_sees_blocked_approval_page(client, people):
    revision = method_revision(people["author"])
    url = reverse("catalog:method_approve", args=[revision.pk])
    client = login(client, people["author"])
    response = client.get(url)
    assert response.status_code == 403
    assert "another quality approver must sign" in response.content.decode()
    response = signing_post(client, url, revision, username=people["author"].username)
    assert response.status_code == 403
    assert not ElectronicSignature.objects.exists()


def test_web_approval_requires_own_username_and_pin(client, people):
    revision = method_revision(people["author"])
    url = reverse("catalog:method_approve", args=[revision.pk])
    approver = people["approver"]
    client = login(client, approver)
    page = client.get(url)
    body = page.content.decode()
    assert page.status_code == 200
    assert "Sign and approve" in body and "Signature PIN" in body
    assert 'value="' + PIN not in body

    wrong_user = signing_post(client, url, revision, username=people["author"].username)
    assert wrong_user.status_code == 422
    assert AuditEvent.objects.filter(action="signature.identity_denied", actor=approver).exists()

    bad_pin = signing_post(client, url, revision, username=approver.username, pin="00000000")
    assert bad_pin.status_code == 422
    assert PIN not in bad_pin.content.decode()
    assert "Checked synthetic content" in bad_pin.content.decode()
    assert PINCredential.objects.get(user=approver).failures == 1

    stale = signing_post(
        client, url, revision, username=approver.username, expected_revision=revision.revision - 1
    )
    assert stale.status_code == 422
    assert "Record changed" in stale.content.decode()
    assert MethodRevision.objects.get().status == "draft"

    ok = signing_post(client, url, revision, username=approver.username)
    assert ok.status_code == 302
    signature = ElectronicSignature.objects.get()
    assert signature.signer == approver
    assert signature.authentication_context["channel"] == "web"
    detail = client.get(reverse("catalog:method", args=[revision.method_id])).content.decode()
    assert "Signed" in detail and approver.get_full_name() in detail


def test_frozen_specification_page_has_no_edit_actions(client, people):
    mat = material(people["author"])
    method = approve(method_revision(people["author"]), people["approver"]).method
    _, revision = specification(people["author"], mat)
    numeric_line(people["author"], revision, method)
    approve(revision, people["approver"])
    client = login(client, people["author"])
    body = client.get(reverse("catalog:specification_revision", args=[revision.pk])).content
    body = body.decode()
    assert "cannot be changed" in body
    assert reverse("catalog:test_new", args=[revision.pk]) not in body
    response = client.get(reverse("catalog:test_new", args=[revision.pk]))
    assert response.status_code == 302


def test_withdraw_draft_via_web(client, people):
    revision = method_revision(people["author"])
    client = login(client, people["author"])
    url = reverse("catalog:method_withdraw", args=[revision.pk])
    assert client.post(url, {"expected_revision": 1, "reason": ""}).status_code == 422
    assert client.post(url, {"expected_revision": 1, "reason": "Not needed"}).status_code == 302
    assert MethodRevision.objects.get().status == "withdrawn"


def test_duplicate_specification_applicability_rejected_in_form(client, people):
    mat = material(people["author"])
    specification(people["author"], mat)
    response = login(client, people["author"]).post(
        reverse("catalog:specification_new"),
        {
            "code": "spec-other",
            "title": "Duplicate",
            "material": mat.pk,
            "stage": "incoming",
            "scope": "general",
            "basis": "Synthetic",
            "effective_from": "2026-01-01T00:00",
            "effective_until": "2030-01-01T00:00",
            "reason": "New",
        },
    )
    assert response.status_code == 422
    assert "Create a new version" in response.content.decode()
    assert Specification.objects.count() == 1


def test_qc_check_pages(client, people):
    from catalog import services

    from .factories import window

    start, end = window()
    _, revision = services.create_method(
        actor=people["author"],
        code="hplc-web",
        title="Batch HPLC",
        technique="HPLC",
        document_ref="SOP-SYN rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN",
        requires_batch=True,
        effective_from=start,
        effective_until=end,
        reason="Synthetic",
    )
    client = login(client, people["author"])
    detail = client.get(reverse("catalog:method", args=[revision.method_id])).content.decode()
    assert "No QC checks yet" in detail
    url = reverse("catalog:qc_check_new", args=[revision.pk])
    assert url in detail
    data = {"code": "blank", "name": "Blank", "unit": "%", "upper_limit": "0.05", "reason": "QC"}
    assert client.post(url, {**data, "upper_limit": ""}).status_code == 422
    assert client.post(url, data).status_code == 302
    assert revision.qc_checks.get().code == "blank"
    plain = method_revision(people["author"], code="plain")
    assert client.get(reverse("catalog:qc_check_new", args=[plain.pk])).status_code == 302
    login(client, people["analyst"])
    assert client.get(url).status_code == 403


def test_withdraw_page_redirects_for_approved_version(client, people):
    revision = approve(method_revision(people["author"]), people["approver"])
    response = login(client, people["author"]).get(
        reverse("catalog:method_withdraw", args=[revision.pk])
    )
    assert response.status_code == 302


def test_sort_toggle_descending(client, people):
    material(people["author"], code="syn-a")
    material(people["author"], code="syn-b")
    client = login(client, people["analyst"])
    body = client.get(reverse("catalog:materials"), {"sort": "-name"}).content.decode()
    assert body.index("syn-b") < body.index("syn-a")
