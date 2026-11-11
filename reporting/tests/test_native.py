"""Native-testing certificates: frozen assignment, no live fallback, issued content immutable.

Uses the real catalog -> sampling -> analytical -> disposition path from the integrated journey
(no fixture providers), so the evidence is exactly what production disposition freezes.
"""

import copy
import hashlib

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse

from analytical import services as analytical
from core.models import AuditEvent, ElectronicSignature
from reporting import evidence as ev
from reporting import services
from reporting.models import ReportVersion
from tests.test_integrated_journey import PASSWORD, PIN, assign_and_sample, dispose, integrated
from tests.test_integrated_journey import observed_test as observe

pytestmark = pytest.mark.django_db(transaction=True)
__all__ = ["integrated"]  # re-exported pytest fixture


@pytest.fixture
def native(integrated):
    data, people = integrated, integrated["people"]
    sample = assign_and_sample(data)
    test, _ = observe(data, sample, "100.25")
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    lot = dispose(data, people["approver"])
    assert lot.state == "released" and lot.disposition_evidence["assignment_hash"]
    return data, people, lot


def issue(people, lot, **overrides):
    kwargs = {
        "actor": people["approver"],
        "pin": PIN,
        "lot": lot,
        "recipient": "Synthetic native recipient",
        "evidence_hash": services.preview(lot)[1],
        "reason": "Independent synthetic certificate issue",
    }
    kwargs.update(overrides)
    return services.issue_report(**kwargs)


def tamper_payload(assignment_id):
    """Bypass the append-only trigger as a database administrator could (test only)."""
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE sampling_lotassignment DISABLE TRIGGER USER")
        try:
            cursor.execute(
                "UPDATE sampling_lotassignment SET payload = jsonb_set(payload, '{lot,number}', "
                "'\"ALTERED\"') WHERE id = %s",
                [assignment_id],
            )
        finally:
            cursor.execute("ALTER TABLE sampling_lotassignment ENABLE TRIGGER USER")


def test_frozen_assignment_payload_resolves_and_verifies(native, django_user_model):
    data, people, lot = native
    payload = ev.frozen_assignment_payload(lot)
    assert payload["specification"]["code"] == "synthetic-spec"
    assert ev.canonical_hash(payload) == lot.disposition_evidence["assignment_hash"]
    stored = lot.disposition_evidence
    for bad in (
        {**stored, "assignment_hash": "0" * 64},  # hash mismatch
        {**stored, "assignment_id": stored["assignment_id"] + 999},  # unknown assignment
        {**stored, "assignment_id": None},
        {**stored, "assignment_hash": ""},
        {},
    ):
        lot.disposition_evidence = bad
        assert ev.frozen_assignment_payload(lot) is None
    lot.disposition_evidence = stored
    assert ev.frozen_assignment_payload(lot) is not None


def test_assignment_of_another_lot_is_not_accepted(native):
    data, people, lot = native
    other = copy.copy(lot)
    other.pk = lot.pk + 1000  # same stored id/hash presented for a different lot
    assert ev.frozen_assignment_payload(other) is None


def test_altered_payload_fails_digest_verification(native):
    data, people, lot = native
    tamper_payload(lot.disposition_evidence["assignment_id"])
    assert ev.frozen_assignment_payload(lot) is None
    evidence, digest, problems = services.preview(lot)  # holds cleanly, no exception
    assert evidence["methods"] is None and evidence["native"]["assignment_verified"] is False
    assert any("could not be resolved and verified" in p for p in problems)
    with pytest.raises(ValidationError, match="could not be resolved and verified"):
        issue(people, lot, evidence_hash=digest)
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()


def test_unverifiable_assignment_holds_in_preview_without_500(native, client, monkeypatch):
    data, people, lot = native
    monkeypatch.setattr(ev, "frozen_assignment_payload", lambda lot: None)
    assert client.login(username=people["approver"].username, password=PASSWORD)
    page = client.get(reverse("reporting:issue_preview", args=[lot.pk]))
    assert page.status_code == 200
    body = page.content.decode()
    assert "could not be resolved and verified" in body
    assert "Continue to signing" not in body
    with pytest.raises(ValidationError, match="could not be resolved and verified"):
        issue(people, lot, evidence_hash=services.preview(lot)[1])
    assert not ReportVersion.objects.exists()


def test_native_methods_come_only_from_the_frozen_assignment(native):
    data, people, lot = native

    def live(lot):
        raise AssertionError("live requirements must not be consulted for a native lot")

    ev.register_collector("methods", live)
    ev.register_collector("specification", live)
    evidence = ev.collect_evidence(lot)
    payload = ev.frozen_assignment_payload(lot)
    assert evidence["methods"] == [t["method"] for t in payload["tests"] if t["required"]]
    assert evidence["methods"][0]["code"] == "synthetic-assay"
    assert evidence["specification"]["code"] == "synthetic-spec"
    assert "methods" in evidence["sections_supplied"]
    assert ev.blockers(evidence) == []


def test_issued_snapshot_pdf_and_hash_survive_later_live_changes(native, client):
    data, people, lot = native
    version = issue(people, lot).versions.get()
    before = (
        copy.deepcopy(version.snapshot),
        bytes(version.pdf),
        version.pdf_sha256,
        version.snapshot_hash,
        version.evidence_hash,
    )
    # Later, live collectors change: an open hold appears and the methods source misbehaves.
    ev.register_collector(
        "holds", lambda lot: [{"id": "H9", "status": "open", "description": "Late"}]
    )
    ev.register_collector("methods", lambda lot: 1 / 0)
    evidence, digest, problems = services.preview(lot)
    assert digest != version.evidence_hash and any("Open hold" in p for p in problems)
    version.refresh_from_db()
    after = (
        version.snapshot,
        bytes(version.pdf),
        version.pdf_sha256,
        version.snapshot_hash,
        version.evidence_hash,
    )
    assert after == before
    assert hashlib.sha256(after[1]).hexdigest() == version.pdf_sha256
    assert services.read_pdf(actor=people["reviewer"], version=version) == before[1]
    assert client.login(username=people["reviewer"].username, password=PASSWORD)
    page = client.get(reverse("reporting:version", args=[version.report_id, 1])).content.decode()
    assert "Late" not in page and "synthetic-assay version 1" in page
    # The issued certificate can no longer be amended while a hold is open, and nothing is added.
    with pytest.raises(ValidationError, match="Open hold"):
        services.amend_report(
            actor=people["approver"],
            pin=PIN,
            report=version.report,
            expected_version=1,
            evidence_hash=digest,
            reason="Attempt during hold",
        )
    assert ReportVersion.objects.count() == 1


def test_stale_native_preview_is_rejected_without_issue(native):
    data, people, lot = native
    reviewed = services.preview(lot)[1]
    ev.register_collector("holds", lambda lot: [])  # evidence changes after review
    with pytest.raises(ValidationError, match="evidence changed"):
        issue(people, lot, evidence_hash=reviewed)
    assert not ReportVersion.objects.exists()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()
    assert not AuditEvent.objects.filter(action="signed.issued").exists()
    assert issue(people, lot).versions.count() == 1


def test_later_superseding_assignment_does_not_invalidate_the_signed_one(native):
    data, people, lot = native
    signed = ev.frozen_assignment_payload(lot)
    before = services.preview(lot)
    LotAssignment = apps.get_model("sampling", "LotAssignment")
    current = LotAssignment.objects.get(pk=lot.disposition_evidence["assignment_id"])
    LotAssignment.objects.create(  # a later (hold) assignment appended after release
        lot=lot,
        material=data["material"],
        stage="incoming",
        status="hold",
        hold_reasons=["Synthetic later applicability change"],
        reason="Later change",
        assigned_by=people["author"],
        supersedes=current,
    )
    assert ev.frozen_assignment_payload(lot) == signed
    assert services.preview(lot)[1:] == before[1:]  # same hash and blockers
    assert issue(people, lot).versions.count() == 1
