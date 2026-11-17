"""Approving a later version retires the approved versions it overlaps (PostgreSQL)."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.urls import reverse
from django.utils import timezone

from catalog import services
from catalog.models import MethodRevision, SpecificationRevision
from catalog.services import ApplicabilityHold, resolve_requirements
from core.models import AuditEvent, ElectronicSignature

from .factories import (
    PIN,
    approve,
    approved_specification,
    material,
    method_revision,
    numeric_line,
)

pytestmark = pytest.mark.django_db(transaction=True)


def pick(method, at=None):
    return services.effective_revision(MethodRevision, method, at or timezone.now())


def signed_at(revision):
    return ElectronicSignature.objects.get(
        object_type=revision._meta.label_lower, object_id=str(revision.pk)
    ).signed_at


def test_a_version_whose_start_has_passed_retires_the_earlier_one_when_it_is_signed(people):
    v1 = approve(method_revision(people["author"], start_days=-10, end_days=10), people["approver"])
    frozen = (v1.approved_content, v1.approved_hash, v1.revision, v1.effective_until)
    draft = method_revision(people["author"], method=v1.method, start_days=-2, end_days=30)
    assert [
        (other.pk, moment > draft.effective_from) for other, moment in (services.retirements(draft))
    ] == [(v1.pk, True)]
    before = timezone.now()
    v2 = approve(draft, people["approver"])
    v1.refresh_from_db()
    # Never retroactively: v1 applied until v2 was signed, not until v2's nominal start.
    assert v1.superseded_by == v2 and v1.superseded_from == signed_at(v2) >= before
    assert v1.applies_until == v1.superseded_from and not v1.never_applied
    assert (v1.approved_content, v1.approved_hash, v1.revision, v1.effective_until) == frozen
    assert v1.status == "approved"
    assert ElectronicSignature.objects.filter(object_id=str(v1.pk)).count() == 1
    assert pick(v1.method) == v2
    assert pick(v1.method, v1.superseded_from - timedelta(microseconds=1)) == v2  # latest wins
    assert not v1.is_effective(timezone.now()) and v2.is_effective(timezone.now())
    assert v1.is_effective(v2.effective_from - timedelta(days=1))
    event = AuditEvent.objects.get(action="revision.superseded")
    assert event.object_id == str(v1.pk) and event.actor == people["approver"]
    assert event.before == {"superseded_from": None, "superseded_by": None}
    assert event.after == {
        "superseded_from": v1.superseded_from.isoformat(),
        "superseded_by": v2.pk,
    }
    assert f"Superseded by the approval of {v2}" in event.reason


def test_a_version_that_starts_later_retires_the_earlier_one_from_its_start(people):
    v1 = approve(method_revision(people["author"], start_days=-10, end_days=60), people["approver"])
    v2 = approve(
        method_revision(people["author"], method=v1.method, start_days=20, end_days=90),
        people["approver"],
    )
    v1.refresh_from_db()
    assert v1.superseded_from == v2.effective_from and v1.superseded_by == v2
    assert pick(v1.method) == v1  # until the new version starts
    assert pick(v1.method, v2.effective_from) == v2
    assert pick(v1.method, v2.effective_from - timedelta(microseconds=1)) == v1
    # A third version that starts before the second one takes over from both.
    v3 = approve(
        method_revision(people["author"], method=v1.method, start_days=5, end_days=90),
        people["approver"],
    )
    v1.refresh_from_db()
    v2.refresh_from_db()
    assert (v1.superseded_from, v1.superseded_by) == (v3.effective_from, v3)
    assert (v2.superseded_from, v2.superseded_by) == (v2.effective_from, v3)
    assert v2.never_applied and not v2.is_effective(v2.effective_from)
    assert pick(v1.method, v2.effective_from + timedelta(days=1)) == v3
    assert AuditEvent.objects.filter(action="revision.superseded").count() == 3


def test_a_draft_cannot_retire_a_later_approved_version(people):
    v1 = approve(method_revision(people["author"], start_days=-10, end_days=60), people["approver"])
    stale = method_revision(people["author"], method=v1.method, start_days=5, end_days=90)
    v3 = approve(
        method_revision(people["author"], method=v1.method, start_days=20, end_days=90),
        people["approver"],
    )
    with pytest.raises(ValidationError, match="Version 3 is already approved for these dates"):
        services.retirements(stale)
    with pytest.raises(ValidationError, match="Version 3 is already approved for these dates"):
        approve(stale, people["approver"])
    stale.refresh_from_db()
    v3.refresh_from_db()
    assert stale.status == "draft" and v3.superseded_from is None
    assert not ElectronicSignature.objects.filter(object_id=str(stale.pk)).exists()


def test_a_refused_approval_retires_nothing(people):
    v1 = approve(method_revision(people["author"], start_days=-10, end_days=60), people["approver"])
    draft = method_revision(people["author"], method=v1.method, start_days=-1, end_days=90)
    with pytest.raises(ValidationError, match="PIN"):
        approve(draft, people["approver"], pin="00000000")
    with pytest.raises(ValidationError, match="Record changed"):
        approve(draft, people["approver"], expected_revision=draft.revision + 3)
    v1.refresh_from_db()
    assert v1.superseded_from is None
    assert not AuditEvent.objects.filter(action="revision.superseded").exists()


def test_requirements_resolve_to_the_version_that_took_over(people):
    author, approver = people["author"], people["approver"]
    mat = material(author)
    spec_v1 = approved_specification(author, approver, mat)
    spec = spec_v1.specification
    first = resolve_requirements(material=mat, stage="incoming")
    assert first["specification"]["version"] == 1
    method = spec_v1.tests.first().method
    method_v2 = approve(method_revision(author, method=method, start_days=-1), approver)
    second = resolve_requirements(material=mat, stage="incoming")
    assert second["specification"]["version"] == 1
    versions = {t["method"]["code"]: t["method"]["version"] for t in second["tests"]}
    assert versions[method.code] == 2 and method_v2.method_id == method.pk
    draft = services.new_specification_revision(
        actor=author,
        specification=spec,
        basis="Synthetic revised limits",
        effective_from=timezone.now() + timedelta(days=5),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic revision",
    )
    spec_v2 = approve(draft, approver)
    spec_v1.refresh_from_db()
    assert spec_v1.superseded_from == spec_v2.effective_from
    assert resolve_requirements(material=mat, stage="incoming")["specification"]["version"] == 1
    at = spec_v2.effective_from + timedelta(seconds=1)
    assert (
        resolve_requirements(material=mat, stage="incoming", at=at)["specification"]["version"] == 2
    )
    with pytest.raises(ApplicabilityHold):
        resolve_requirements(material=mat, stage="incoming", at=spec_v2.effective_until)


def test_only_the_version_that_applies_is_offered_for_a_new_qc_batch(people):
    author, approver = people["author"], people["approver"]
    start, end = timezone.now() - timedelta(days=5), timezone.now() + timedelta(days=60)
    method, v1 = services.create_method(
        actor=author,
        code="gc-batch",
        title="Synthetic batch GC",
        technique="GC",
        document_ref="SOP-SYN-GC rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-GC",
        requires_batch=True,
        effective_from=start,
        effective_until=end,
        reason="Synthetic method",
    )
    services.add_qc_check(
        actor=author, revision=v1, reason="QC", code="blank", name="Blank", unit="%", upper_limit=1
    )
    approve(v1, approver)
    assert [m["version"] for m in services.effective_batch_methods()] == [1]
    v2 = services.new_method_revision(
        actor=author,
        method=method,
        technique="GC",
        document_ref="SOP-SYN-GC rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-GC-2",
        requires_batch=True,
        effective_from=timezone.now() - timedelta(days=1),
        effective_until=end + timedelta(days=30),
        reason="Synthetic method revision",
    )
    approve(v2, approver)
    offered = services.effective_batch_methods()
    assert [(m["code"], m["version"]) for m in offered] == [("gc-batch", 2)]


def test_database_lets_a_supersession_only_be_set_or_brought_forward(people):
    author, approver = people["author"], people["approver"]
    v1 = approve(method_revision(author, start_days=-10, end_days=60), approver)
    v2 = approve(method_revision(author, method=v1.method, start_days=20, end_days=90), approver)
    v1.refresh_from_db()
    retired = v1.superseded_from
    table = MethodRevision.objects.filter(pk=v1.pk)
    for change in (
        {"superseded_from": None, "superseded_by": None},  # cleared
        {"superseded_from": retired + timedelta(days=1)},  # delayed
        {"superseded_from": retired - timedelta(days=1), "technique": "Other"},
        {"technique": "Other"},
        {"status": "draft"},
        {"effective_until": retired},
    ):
        with pytest.raises(DatabaseError, match="Approved or withdrawn revisions are immutable"):
            with transaction.atomic():
                table.update(**change)
    elsewhere = approve(method_revision(author, code="gc-other", end_days=400), approver)
    for successor in (elsewhere, v1):  # another method; the version itself
        with pytest.raises(DatabaseError, match="only by a later version of the same document"):
            with transaction.atomic():
                table.update(superseded_from=retired - timedelta(days=1), superseded_by=successor)
    with transaction.atomic():
        table.update(superseded_from=retired - timedelta(days=1))  # brought forward
    draft = method_revision(author, method=v1.method, start_days=100, end_days=200)
    with pytest.raises(DatabaseError, match="fixed at creation|methodrevision_superseded"):
        with transaction.atomic():
            MethodRevision.objects.filter(pk=draft.pk).update(
                superseded_from=draft.effective_from, superseded_by=v2
            )
    for moment in (v2.effective_from - timedelta(days=1), v2.effective_until):
        with pytest.raises(DatabaseError, match="methodrevision_superseded"):
            with transaction.atomic():
                MethodRevision.objects.filter(pk=v2.pk).update(  # outside its own period
                    superseded_from=moment, superseded_by=draft
                )
    with pytest.raises(DatabaseError, match="cannot be deleted"):
        with transaction.atomic():
            table.delete()


def test_approval_page_lists_what_the_signature_retires(client, people):
    author, approver = people["author"], people["approver"]
    mat = material(author)
    spec_v1 = approved_specification(author, approver, mat)
    draft = services.new_specification_revision(
        actor=author,
        specification=spec_v1.specification,
        basis="Synthetic revised limits",
        effective_from=timezone.now() - timedelta(hours=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic revision",
    )
    client.force_login(approver)
    url = reverse("catalog:specification_approve", args=[draft.pk])
    page = " ".join(client.get(url).content.decode().split())
    assert "Your signature also retires it" in page
    assert (
        f"<strong>{spec_v1}</strong> stops applying at the moment of your signature, because "
        "this version's start has already passed." in page
    )
    assert "Lots keep the versions frozen when their requirements were assigned" in page
    response = client.post(
        url,
        {
            "reason": "Independent review of the revision",
            "signature_username": approver.username,
            "pin": PIN,
            "expected_revision": draft.revision,
        },
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    spec_v1.refresh_from_db()
    assert spec_v1.superseded_by_id == draft.pk
    detail = " ".join(
        client.get(reverse("catalog:specification", args=[spec_v1.specification_id]))
        .content.decode()
        .split()
    )
    assert "Superseded" in detail and "by version 2 from" in detail
    # A draft overtaken by a later approved version is told so before any PIN is asked for.
    stale = services.new_specification_revision(
        actor=author,
        specification=spec_v1.specification,
        basis="Synthetic stale draft",
        effective_from=timezone.now() + timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=300),
        reason="Synthetic revision",
    )
    numeric_line(author, stale, spec_v1.tests.first().method, code="water", low=None, high="0.5")
    newer = services.new_specification_revision(
        actor=author,
        specification=spec_v1.specification,
        basis="Synthetic newer version",
        effective_from=timezone.now() + timedelta(days=2),
        effective_until=timezone.now() + timedelta(days=300),
        reason="Synthetic revision",
    )
    stale_url = reverse("catalog:specification_revision", args=[stale.pk])
    approve_url = reverse("catalog:specification_approve", args=[stale.pk])
    assert approve_url in client.get(stale_url).content.decode()  # offered while it would pass
    approve(newer, approver)
    # Once overtaken, the version page no longer offers it and says why instead.
    shown = " ".join(client.get(stale_url).content.decode().split())
    assert approve_url not in shown
    assert 'data-refused="approve">Version 4 is already approved for these dates' in shown
    page = " ".join(
        client.get(reverse("catalog:specification_approve", args=[stale.pk]))
        .content.decode()
        .split()
    )
    assert "Cannot be approved" in page and "Version 4 is already approved for these dates" in page
    assert 'name="pin"' not in page and "Sign and approve" not in page
    signatures = ElectronicSignature.objects.count()
    response = client.post(
        reverse("catalog:specification_approve", args=[stale.pk]),
        {
            "reason": "Sign anyway",
            "signature_username": approver.username,
            "pin": "00000000",
            "expected_revision": stale.revision,
        },
    )
    assert "Cannot be approved" in response.content.decode()
    assert not AuditEvent.objects.filter(action="signature.denied").exists()  # no PIN was tried
    assert ElectronicSignature.objects.count() == signatures
    assert SpecificationRevision.objects.get(pk=stale.pk).status == "draft"
