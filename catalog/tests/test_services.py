"""Controlled specification/method contracts against PostgreSQL."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from catalog import services
from catalog.models import (
    Material,
    MethodQCCheck,
    MethodRevision,
    SpecificationRevision,
    SpecificationTest,
)
from catalog.services import ApplicabilityHold, conforms, digest, resolve_requirements
from core.models import AuditEvent, ElectronicSignature, PINCredential

from .factories import (
    PIN,
    approve,
    approved_rules,
    approved_specification,
    material,
    method_revision,
    numeric_line,
    qualitative_line,
    specification,
    window,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_method_approval_is_signed_frozen_and_hashed(people):
    revision = method_revision(people["author"])
    approved = approve(revision, people["approver"])
    assert approved.status == "approved"
    assert approved.approved_hash == digest(approved.approved_content)
    assert approved.approved_content["document_ref"] == "SOP-SYN-hplc-assay rev 1"
    signature = ElectronicSignature.objects.get(object_type="catalog.methodrevision")
    assert signature.signer == people["approver"]
    assert signature.meaning == "approved"
    assert signature.revision == approved.revision
    assert signature.content["approved_hash"] == approved.approved_hash


@pytest.mark.parametrize("who", ["author", "editor", "dual"])
def test_no_self_review_for_author_editor_or_multi_role(people, who):
    mat = material(people["author"])
    method = approve(method_revision(people["author"]), people["approver"]).method
    author = people["dual"] if who == "dual" else people["author"]
    _, revision = specification(author, mat)
    if who == "editor":
        numeric_line(people["approver"], revision, method)
        actor = people["approver"]
    else:
        numeric_line(author, revision, method)
        actor = author
    with pytest.raises(PermissionDenied):
        approve(revision, actor)
    revision.refresh_from_db()
    assert revision.status == "draft"
    assert not ElectronicSignature.objects.filter(object_type="catalog.specificationrevision")


def test_role_boundaries(people):
    revision = method_revision(people["author"])
    for role in ("analyst", "reviewer", "admin", "auditor"):
        with pytest.raises(PermissionDenied):
            approve(revision, people[role])
        with pytest.raises(PermissionDenied):
            material(people[role], code=f"denied-{role}")
    assert not Material.objects.filter(code__startswith="denied").exists()


def test_bad_pin_and_stale_revision_do_not_approve(people):
    revision = method_revision(people["author"])
    with pytest.raises(ValidationError, match="PIN"):
        approve(revision, people["approver"], pin="00000000")
    assert PINCredential.objects.get(user=people["approver"]).failures == 1
    with pytest.raises(ValidationError, match="Record changed"):
        approve(revision, people["approver"], expected_revision=revision.revision + 5)
    revision.refresh_from_db()
    assert revision.status == "draft"


def test_line_edit_makes_open_approval_stale(people):
    mat = material(people["author"])
    method = approve(method_revision(people["author"]), people["approver"]).method
    _, revision = specification(people["author"], mat)
    numeric_line(people["author"], revision, method)
    revision.refresh_from_db()
    seen = revision.revision
    numeric_line(people["author"], revision, method, code="water", low=None, high="0.5")
    with pytest.raises(ValidationError, match="Record changed"):
        services.approve_revision(
            actor=people["approver"],
            pin=PIN,
            revision=revision,
            expected_revision=seen,
            reason="Reviewed older content",
        )


def test_specification_requires_tests_and_effective_approved_methods(people):
    mat = material(people["author"])
    draft_method = method_revision(people["author"])
    _, revision = specification(people["author"], mat)
    with pytest.raises(ValidationError, match="at least one test"):
        approve(revision, people["approver"])
    numeric_line(people["author"], revision, draft_method.method)
    with pytest.raises(ValidationError, match="No approved method revision"):
        approve(revision, people["approver"])
    approve(draft_method, people["approver"])
    approved = approve(revision, people["approver"])
    test = approved.approved_content["tests"][0]
    assert test["lower_limit"] == "98" and test["upper_limit"] == "102"
    assert test["unit"] == "%"


def test_overlapping_versions_rejected_and_boundaries_half_open(people):
    method_v1 = method_revision(people["author"], start_days=-10, end_days=10)
    approve(method_v1, people["approver"])
    overlap = method_revision(people["author"], method=method_v1.method, start_days=5, end_days=30)
    with pytest.raises(ValidationError, match="overlap"):
        approve(overlap, people["approver"])
    adjacent = services.new_method_revision(
        actor=people["author"],
        method=method_v1.method,
        technique="HPLC-UV",
        document_ref="SOP-SYN rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-2",
        effective_from=method_v1.effective_until,
        effective_until=method_v1.effective_until + timedelta(days=30),
        reason="Next version",
    )
    v2 = approve(adjacent, people["approver"])
    boundary = method_v1.effective_until
    pick = services.effective_revision
    assert pick(MethodRevision, method_v1.method, boundary - timedelta(microseconds=1)).version == 1
    assert pick(MethodRevision, method_v1.method, boundary).pk == v2.pk
    assert pick(MethodRevision, method_v1.method, v2.effective_until) is None
    assert pick(MethodRevision, method_v1.method, method_v1.effective_from).version == 1
    assert (
        pick(MethodRevision, method_v1.method, method_v1.effective_from - timedelta(seconds=1))
        is None
    )


def test_invalid_interval_rejected(people):
    with pytest.raises(ValidationError, match="effective end"):
        method_revision(people["author"], start_days=5, end_days=5)


@pytest.mark.parametrize(
    "fields, field",
    [
        ({"unit": ""}, "unit"),
        ({"low": None, "high": None}, "lower_limit"),
        ({"low": "5", "high": "1"}, "upper_limit"),
        ({"expected_text": "Conforms"}, "expected_text"),
    ],
)
def test_numeric_line_shape_validation(people, fields, field):
    mat = material(people["author"])
    method = method_revision(people["author"]).method
    _, revision = specification(people["author"], mat)
    low, high = fields.pop("low", "1"), fields.pop("high", "2")
    with pytest.raises(ValidationError) as caught:
        numeric_line(people["author"], revision, method, low=low, high=high, **fields)
    assert field in caught.value.message_dict
    assert not SpecificationTest.objects.exists()


def test_database_rejects_invalid_line_shape_bypassing_services(people):
    mat = material(people["author"])
    method = method_revision(people["author"]).method
    _, revision = specification(people["author"], mat)
    with pytest.raises(IntegrityError), transaction.atomic():
        SpecificationTest.objects.create(
            specification_revision=revision,
            code="bad",
            name="Bad",
            method=method,
            result_type="qualitative",
            lower_limit=Decimal("1"),
            created_by=people["author"],
        )


def test_approved_specification_and_lines_are_immutable_in_database(people):
    mat = material(people["author"])
    approved = approved_specification(people["author"], people["approver"], mat)
    line = approved.tests.first()
    for operation in (
        lambda: SpecificationRevision.objects.filter(pk=approved.pk).update(basis="tampered"),
        lambda: SpecificationRevision.objects.filter(pk=approved.pk).delete(),
        lambda: SpecificationTest.objects.filter(pk=line.pk).update(upper_limit=Decimal("200")),
        lambda: SpecificationTest.objects.filter(pk=line.pk).delete(),
        lambda: Material.objects.filter(pk=mat.pk).update(name="tampered"),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()
    with pytest.raises(ValidationError, match="draft"):
        numeric_line(people["author"], approved, line.method, code="late")
    with pytest.raises(DatabaseError), transaction.atomic():
        SpecificationTest.objects.create(
            specification_revision=approved,
            code="sneaky",
            name="Sneaky",
            method=line.method,
            result_type="qualitative",
            expected_text="Conforms",
            created_by=people["author"],
        )
    approved.refresh_from_db()
    assert approved.basis.startswith("Synthetic")
    assert approved.tests.count() == 2


def test_draft_header_fixed_but_lines_editable(people):
    mat = material(people["author"])
    method = method_revision(people["author"]).method
    _, revision = specification(people["author"], mat)
    with pytest.raises(DatabaseError), transaction.atomic():
        SpecificationRevision.objects.filter(pk=revision.pk).update(basis="changed")
    line = numeric_line(people["author"], revision, method)
    services.remove_test_line(actor=people["author"], line=line, reason="Wrong test")
    assert not revision.tests.exists()
    removed = AuditEvent.objects.get(action="specification_revision.test_removed")
    assert removed.before["code"] == "assay"


def test_withdrawn_draft_cannot_be_edited_or_approved(people):
    revision = method_revision(people["author"])
    services.withdraw_revision(
        actor=people["author"], revision=revision, expected_revision=1, reason="Superseded draft"
    )
    with pytest.raises(ValidationError, match="draft"):
        approve(revision, people["approver"])
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=revision.pk).update(status="draft")


def test_new_version_copies_lines_as_draft(people):
    mat = material(people["author"])
    approved = approved_specification(people["author"], people["approver"], mat)
    start = approved.effective_until
    revision = services.new_specification_revision(
        actor=people["author"],
        specification=approved.specification,
        basis="Revised synthetic basis",
        effective_from=start,
        effective_until=start + timedelta(days=365),
        reason="Annual revision",
    )
    assert revision.version == 2
    assert revision.status == "draft"
    assert sorted(revision.tests.values_list("code", flat=True)) == ["assay", "identity"]
    assert approved.tests.count() == 2


def test_resolve_requirements_payload(people):
    mat = material(people["author"])
    approved = approved_specification(people["author"], people["approver"], mat)
    rules = approved_rules(people["author"])
    payload = resolve_requirements(material=mat, stage="incoming", rules=rules)
    assert payload["schema"] == "oq.requirements/1"
    assert payload["specification"]["revision_id"] == approved.pk
    assert payload["specification"]["approved_hash"] == approved.approved_hash
    assert payload["rules"]["required_tests"] == ["identity"]
    assay = next(t for t in payload["tests"] if t["code"] == "assay")
    assert assay["method"]["code"] == "hplc-assay"
    assert assay["method"]["suitability_ref"] == "VAL-SYN-hplc-assay"
    assert assay["reporting_decimals"] == 1


def test_missing_applicability_holds_with_all_reasons(people):
    mat = material(people["author"])
    rules = approved_rules(people["author"], required=("identity", "heavy-metals"))
    with pytest.raises(ApplicabilityHold) as caught:
        resolve_requirements(material=mat, stage="incoming", rules=rules)
    assert "No specification" in caught.value.reasons[0]
    approved_specification(people["author"], people["approver"], mat)
    with pytest.raises(ApplicabilityHold) as caught:
        resolve_requirements(material=mat, stage="incoming", rules=rules)
    assert caught.value.reasons == [
        "Rule set requires tests missing from the specification: heavy-metals"
    ]
    with pytest.raises(ApplicabilityHold, match="scope eu-market"):
        resolve_requirements(material=mat, stage="incoming", scope="eu-market")
    future = timezone.now() + timedelta(days=400)
    with pytest.raises(ApplicabilityHold, match="no approved version effective"):
        resolve_requirements(material=mat, stage="incoming", at=future)


def test_unapproved_rules_hold(people):
    mat = material(people["author"])
    approved_specification(people["author"], people["approver"], mat)
    rules = approved_rules(people["author"])
    rules.status = "draft"
    with pytest.raises(ApplicabilityHold, match="not approved and effective"):
        resolve_requirements(material=mat, stage="incoming", rules=rules)


def test_expired_method_holds_requirements(people):
    mat = material(people["author"])
    identity = approve(
        method_revision(people["author"], code="id-short", end_days=30), people["approver"]
    )
    spec_rev = specification(people["author"], mat)[1]
    qualitative_line(people["author"], spec_rev, identity.method)
    approve(spec_rev, people["approver"])
    resolve_requirements(material=mat, stage="incoming")
    with pytest.raises(ApplicabilityHold, match="Method id-short"):
        resolve_requirements(material=mat, stage="incoming", at=timezone.now() + timedelta(days=31))


@pytest.mark.parametrize(
    "line, value, expected",
    [
        ({"lower_limit": "98", "upper_limit": "102"}, "98.0", True),
        ({"lower_limit": "98", "upper_limit": "102"}, "97.99999999", False),
        ({"lower_limit": "98", "upper_limit": "102"}, "102", True),
        ({"lower_limit": "98", "upper_limit": "102", "reporting_decimals": 1}, "97.95", True),
        ({"lower_limit": "98", "upper_limit": "102", "reporting_decimals": 1}, "97.94", False),
        ({"lower_limit": None, "upper_limit": "0.5", "upper_inclusive": False}, "0.5", False),
        ({"lower_limit": None, "upper_limit": "0.5"}, "0.5", True),
        ({"lower_limit": "1", "upper_limit": None, "lower_inclusive": False}, "1", False),
        ({"lower_limit": "1", "upper_limit": None}, None, False),
    ],
)
def test_conforms_exact_decimal(line, value, expected):
    test = {
        "result_type": "numeric",
        "unit": "%",
        "lower_inclusive": True,
        "upper_inclusive": True,
        "reporting_decimals": None,
        "expected_text": "",
        **line,
    }
    assert conforms(test, value) is expected


def test_conforms_qualitative_and_rejects_non_finite():
    test = {"result_type": "qualitative", "expected_text": "Conforms"}
    assert conforms(test, " conforms ")
    assert not conforms(test, "Does not conform")
    numeric = {
        "result_type": "numeric",
        "lower_limit": "1",
        "upper_limit": "2",
        "lower_inclusive": True,
        "upper_inclusive": True,
        "reporting_decimals": None,
    }
    with pytest.raises(ValidationError):
        conforms(numeric, "NaN")
    with pytest.raises(ValidationError):
        conforms(numeric, "abc")


def test_audit_never_contains_pin(people):
    approve(method_revision(people["author"]), people["approver"])
    for event in AuditEvent.objects.all():
        assert PIN not in str([event.before, event.after, event.reason])


def test_batch_method_needs_qc_checks_and_freezes_them(people):
    start, end = window()
    _, revision = services.create_method(
        actor=people["author"],
        code="hplc-batch",
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
    with pytest.raises(ValidationError, match="at least one QC check"):
        approve(revision, people["approver"])
    with pytest.raises(ValidationError):
        services.add_qc_check(
            actor=people["author"],
            revision=revision,
            reason="x",
            code="blank",
            name="Blank",
            unit="%",
        )
    check = services.add_qc_check(
        actor=people["author"],
        revision=revision,
        reason="Add QC",
        code="blank",
        name="Blank",
        unit="%",
        upper_limit=Decimal("0.05"),
    )
    approved = approve(revision, people["approver"])
    assert approved.approved_content["requires_batch"] is True
    assert approved.approved_content["qc_checks"] == [
        {"code": "blank", "name": "Blank", "unit": "%", "lower_limit": None, "upper_limit": "0.05"}
    ]
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodQCCheck.objects.filter(pk=check.pk).update(upper_limit=Decimal("5"))
    with pytest.raises(ValidationError, match="draft"):
        services.add_qc_check(
            actor=people["author"],
            revision=approved,
            reason="x",
            code="c2",
            name="C",
            unit="%",
            lower_limit=Decimal("1"),
        )


def test_non_batch_method_rejects_qc_checks(people):
    revision = method_revision(people["author"])
    with pytest.raises(ValidationError, match="QC batch"):
        services.add_qc_check(
            actor=people["author"],
            revision=revision,
            reason="x",
            code="c",
            name="C",
            unit="%",
            lower_limit=Decimal("1"),
        )


def test_replication_fields_validated_and_published(people):
    mat = material(people["author"])
    method = approve(method_revision(people["author"]), people["approver"]).method
    _, revision = specification(people["author"], mat)
    with pytest.raises(ValidationError) as caught:
        numeric_line(people["author"], revision, method, replicates=11)
    assert "replicates" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        numeric_line(people["author"], revision, method, max_retests=4)
    assert "max_retests" in caught.value.message_dict
    numeric_line(
        people["author"], revision, method, replicates=2, replicate_limits=False, max_retests=1
    )
    approve(revision, people["approver"])
    payload = resolve_requirements(material=mat, stage="incoming")
    test = payload["tests"][0]
    assert (test["replicates"], test["replicate_limits"], test["max_retests"]) == (2, False, 1)
    assert test["method"]["requires_batch"] is False and test["method"]["qc_checks"] == []


def test_effective_batch_methods_lists_only_approved_effective_batch_methods(people):
    start, end = window()
    fields = {
        "technique": "HPLC",
        "document_ref": "SOP-SYN rev 1",
        "suitability_kind": "validation",
        "suitability_ref": "VAL-SYN",
        "effective_from": start,
        "effective_until": end,
        "reason": "Synthetic",
    }
    _, batch = services.create_method(
        actor=people["author"], code="batch-a", title="A", requires_batch=True, **fields
    )
    services.add_qc_check(
        actor=people["author"],
        revision=batch,
        reason="QC",
        code="blank",
        name="Blank",
        unit="%",
        upper_limit=Decimal("0.1"),
    )
    services.create_method(
        actor=people["author"], code="batch-draft", title="B", requires_batch=True, **fields
    )
    approve(method_revision(people["author"], code="plain-a"), people["approver"])
    assert services.effective_batch_methods() == []
    approve(batch, people["approver"])
    [payload] = services.effective_batch_methods()
    assert payload["code"] == "batch-a" and payload["qc_checks"][0]["code"] == "blank"
