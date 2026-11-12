"""HTTP behaviour: role boundaries, complete UI states and signing through the web form."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import (
    Material,
    Method,
    MethodRevision,
    Specification,
    SpecificationRevision,
)
from core.models import AuditEvent, ElectronicSignature, PINCredential

from .factories import (
    PIN,
    approve,
    commit_first_on_save,
    material,
    method_revision,
    numeric_line,
    specification,
    window,
)

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


def _method_data(code):
    start, end = window()
    return {
        "code": code,
        "title": "Synthetic race method",
        "technique": "HPLC",
        "document_ref": "SOP-SYN rev 1",
        "suitability_kind": "validation",
        "suitability_ref": "VAL-SYN",
        "effective_from": start.strftime("%Y-%m-%dT%H:%M"),
        "effective_until": end.strftime("%Y-%m-%dT%H:%M"),
        "reason": "New",
    }


def _specification_data(code, mat):
    start, end = window()
    return {
        "code": code,
        "title": "Synthetic race spec",
        "material": mat.pk,
        "stage": "incoming",
        "scope": "general",
        "basis": "Synthetic",
        "effective_from": start.strftime("%Y-%m-%dT%H:%M"),
        "effective_until": end.strftime("%Y-%m-%dT%H:%M"),
        "reason": "New",
    }


@pytest.mark.parametrize(
    "kind", ["material code", "method code", "specification code", "applicability"]
)
def test_concurrent_duplicate_is_a_form_error(client, people, monkeypatch, kind):
    """A duplicate committed by another request after every check of this one has passed is
    caught by its database constraint and shown as a conflict, with nothing of this one saved."""
    author = people["author"]
    mat = material(author)
    other = material(author, code="syn-api-002")
    if kind == "material code":
        url, model = reverse("catalog:material_new"), Material
        data = {"code": "syn-race", "name": "Synthetic", "kind": "raw_material", "reason": "New"}

        def competitor():
            Material.objects.create(
                code="syn-race", name="Other request", kind="raw_material", created_by=author
            )
    elif kind == "method code":
        url, data, model = reverse("catalog:method_new"), _method_data("m-race"), Method

        def competitor():
            Method.objects.create(code="m-race", title="Other request", created_by=author)
    else:
        url, model = reverse("catalog:specification_new"), Specification
        data = _specification_data("spec-race", mat)
        code, target = ("spec-race", other) if kind == "specification code" else ("spec-o", mat)

        def competitor():
            Specification.objects.create(
                code=code,
                title="Other request",
                material=target,
                stage="incoming",
                scope="general",
                created_by=author,
            )

    commit_first_on_save(monkeypatch, model, competitor)
    before = AuditEvent.objects.count()
    response = login(client, author).post(url, data)
    assert response.status_code == 422
    assert "Another request saved a conflicting record" in response.content.decode()
    assert model.objects.count() == (3 if model is Material else 1)
    label = "name" if model is Material else "title"
    assert model.objects.filter(**{label: "Other request"}).count() == 1
    assert AuditEvent.objects.count() == before


def _duplicate_audit_event(real):
    def record_event(**kwargs):
        event = real(**kwargs)
        AuditEvent.objects.create(
            id=event.id,
            actor=event.actor,
            action=event.action,
            object_type=event.object_type,
            object_id=event.object_id,
        )
        return event

    return record_event


def _duplicate_material_key(real):
    def record_event(**kwargs):
        obj = kwargs["obj"]
        Material.objects.create(
            pk=obj.pk, code="syn-copy", name="Copy", kind=obj.kind, created_by=obj.created_by
        )
        return real(**kwargs)

    return record_event


@pytest.mark.parametrize("fault", [_duplicate_audit_event, _duplicate_material_key])
def test_unexpected_unique_violation_is_not_reported_as_a_conflict(
    client, people, monkeypatch, fault
):
    """Only the expected concurrent duplicates become the conflict message. Any other unique
    violation, such as a repeated audit event id or primary key, is an integrity fault."""
    from django.db import IntegrityError

    from catalog import services

    monkeypatch.setattr(services, "record_event", fault(services.record_event))
    client = login(client, people["author"])
    before = AuditEvent.objects.count()
    data = {"code": "syn-fault", "name": "Synthetic", "kind": "raw_material", "reason": "New"}
    with pytest.raises(IntegrityError, match="_pkey"):
        client.post(reverse("catalog:material_new"), data)
    assert not Material.objects.exists()
    assert AuditEvent.objects.count() == before


def test_concurrent_duplicate_allowlist_covers_every_racing_unique_constraint():
    """Each allowlisted pair is a real unique constraint, and every other non-key unique
    constraint on catalog and sampling tables is one that is only written under a row lock
    (parent, draft revision or lot) after its own check, so a violation there is a fault."""
    from django.apps import apps
    from django.db import connection

    from catalog.web import CONCURRENT_DUPLICATES

    serialized = {
        "method_version_unique",
        "method_qc_unique",
        "specification_version_unique",
        "specification_test_unique",
        "sampling_plan_version_unique",
        "sampling_deviationreview_record_id_key",
        "sampling_lotassignment_supersedes_id_key",
        "sampling_samplingrecord_corrects_id_key",
    }
    found = set()
    with connection.cursor() as cursor:
        for table, name in CONCURRENT_DUPLICATES:
            info = connection.introspection.get_constraints(cursor, table).get(name)
            assert info and info["unique"] and not info["primary_key"], (table, name)
        for label in ("catalog", "sampling"):
            for model in apps.get_app_config(label).get_models():
                table = model._meta.db_table
                for name, info in connection.introspection.get_constraints(cursor, table).items():
                    if info["unique"] and not info["primary_key"]:
                        found.add((table, name))
    expected = {pair for pair in CONCURRENT_DUPLICATES if not pair[0].startswith("quality_")}
    assert {name for _, name in found - expected} == serialized


def test_non_unique_integrity_error_is_not_reported_as_a_conflict(client, people, monkeypatch):
    """Only a unique violation becomes the conflict message; other integrity faults surface."""
    from django.db import IntegrityError

    from catalog import services

    def fault(**kwargs):
        raise IntegrityError("synthetic foreign-key failure")

    monkeypatch.setattr(services, "create_material", fault)
    client = login(client, people["author"])
    data = {"code": "syn-fault", "name": "Synthetic", "kind": "raw_material", "reason": "New"}
    with pytest.raises(IntegrityError, match="synthetic foreign-key"):
        client.post(reverse("catalog:material_new"), data)
    assert not Material.objects.exists()


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


def test_add_count_and_qualitative_tests_via_web(client, people):
    mat = material(people["author"])
    method = approve(method_revision(people["author"]), people["approver"]).method
    _, revision = specification(people["author"], mat)
    client = login(client, people["author"])
    add = reverse("catalog:test_new", args=[revision.pk])
    form = client.get(add).content.decode()
    assert "Count (whole number)" in form and 'name="expected_result"' in form
    base = {"method": method.pk, "position": 1, "replicates": "1", "max_retests": "0"}
    base.update(required="on", reason="Add")
    # Qualitative without an outcome is refused and keeps the entered criterion.
    bad = client.post(
        add,
        {
            **base,
            "code": "salmonella",
            "name": "Salmonella",
            "result_type": "qualitative",
            "expected_text": "Not detected in 25 g",
        },
    )
    assert bad.status_code == 422
    body = bad.content.decode()
    assert "Choose the expected outcome." in body and "Not detected in 25 g" in body
    # Unticked bound/replicate boxes do not apply to qualitative tests and are stored as set.
    good = client.post(
        add,
        {
            **base,
            "code": "salmonella",
            "name": "Salmonella",
            "result_type": "qualitative",
            "expected_result": "absent",
            "expected_text": "Not detected in 25 g",
        },
    )
    assert good.status_code == 302
    fractional = client.post(
        add,
        {
            **base,
            "code": "tamc",
            "name": "TAMC",
            "result_type": "count",
            "unit": "CFU/g",
            "upper_limit": "10.5",
            "upper_inclusive": "on",
            "lower_inclusive": "on",
        },
    )
    assert fractional.status_code == 422
    assert "Count limits must be whole numbers of 0 or more." in fractional.content.decode()
    count = client.post(
        add,
        {
            **base,
            "code": "tamc",
            "name": "TAMC",
            "result_type": "count",
            "unit": "CFU/g",
            "upper_limit": "10",
            "lower_inclusive": "on",
        },
    )
    assert count.status_code == 302
    line = revision.tests.get(code="salmonella")
    assert (line.expected_result, line.lower_inclusive, line.replicate_limits) == (
        "absent",
        True,
        True,
    )
    page = client.get(reverse("catalog:specification_revision", args=[revision.pk])).content
    page = page.decode()
    assert "Absent: Not detected in 25 g" in page
    assert "&lt; 10 CFU/g" in page and "Count (whole number)" in page
