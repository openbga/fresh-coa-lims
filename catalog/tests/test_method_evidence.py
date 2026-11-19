"""Method evidence records and the suitability a method version relies on: who records,
changes, approves and withdraws them, what approval freezes, the database guards, and the
check of the record when a method version that relies on it is approved. Synthetic data."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from catalog import evidence
from catalog.models import (
    MethodEvidence,
    MethodEvidenceCharacteristic,
    MethodRevision,
)
from catalog.services import digest
from core.models import AuditEvent, ElectronicSignature, PINCredential

from .factories import PIN, approve, method_revision

pytestmark = pytest.mark.django_db(transaction=True)

FIELDS = {
    "kind": "validation",
    "title": "Validation of the synthetic assay",
    "procedure_ref": "SOP-SYN-ASSAY rev 2",
    "intended_use": "Assay of the synthetic API in tablets, 80 to 120 % of the label claim.",
    "source": "",
    "transfer_approach": "",
    "protocol_ref": "VP-SYN-001 rev 1",
    "report_ref": "VR-SYN-001 rev 1",
    "report_url": "https://docs.example.invalid/VR-SYN-001",
    "conclusion": "suitable",
    "statement": "The method is suitable for the assay of the synthetic API in tablets.",
    "deviations": "",
}


def values(**overrides):
    data = {**FIELDS, "completed_on": timezone.localdate() - timedelta(days=3)}
    data.update(overrides)
    return data


def record(actor, method, **overrides):
    return evidence.record_evidence(
        actor=actor, method=method, reason="Synthetic evidence", **values(**overrides)
    )


def characteristic(actor, item, outcome="met", **overrides):
    data = {
        "characteristic": "accuracy",
        "detail": "Recovery at 80, 100 and 120 %",
        "criterion": "Mean recovery 98.0 to 102.0 %",
        "result": "99.6 %",
        "outcome": outcome,
    }
    data.update(overrides)
    return evidence.add_characteristic(actor=actor, evidence=item, reason="Report table 4", **data)


def approved(people, method, **overrides):
    item = record(people["analyst"], method, **overrides)
    characteristic(people["analyst"], item)
    item.refresh_from_db()
    return approve_record(item, people["approver"])


def approve_record(item, actor, **overrides):
    item.refresh_from_db()
    kwargs = {
        "actor": actor,
        "pin": PIN,
        "evidence": item,
        "expected_revision": item.revision,
        "reason": "Report checked",
    }
    kwargs.update(overrides)
    return evidence.approve_evidence(**kwargs)


@pytest.fixture
def method(people):
    return method_revision(people["author"]).method


# Recording -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["analyst", "reviewer", "author"])
def test_laboratory_roles_record_a_draft_with_an_audit_event(people, method, role):
    item = record(people[role], method)
    assert item.state == "draft" and item.identifier == f"MEV-{item.pk}"
    event = AuditEvent.objects.get(action="method_evidence.recorded")
    assert event.actor == people[role] and event.reason == "Synthetic evidence"


@pytest.mark.parametrize("role", ["admin", "auditor"])
def test_admin_and_auditor_do_not_record(people, method, role):
    with pytest.raises(PermissionDenied):
        record(people[role], method)
    assert not MethodEvidence.objects.exists()


def test_a_reason_is_required(people, method):
    with pytest.raises(ValidationError, match="reason"):
        evidence.record_evidence(actor=people["analyst"], method=method, reason=" ", **values())


def test_rules_of_each_kind(people, method):
    analyst = people["analyst"]
    with pytest.raises(ValidationError) as caught:
        record(analyst, method, kind="compendial_verification")
    assert "source" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        record(analyst, method, kind="transfer", source="Synthetic Lab B")
    assert "transfer_approach" in caught.value.message_dict
    with pytest.raises(ValidationError) as caught:
        record(analyst, method, completed_on=timezone.localdate() + timedelta(days=1))
    assert "completed_on" in caught.value.message_dict
    # Only a transfer has an approach: anything else is stored without one.
    item = record(analyst, method, transfer_approach="comparative")
    assert item.transfer_approach == ""
    transfer = record(
        analyst, method, kind="transfer", source="Synthetic Lab B", transfer_approach="waiver"
    )
    assert transfer.get_transfer_approach_display() == "Transfer waiver"


def test_change_a_draft_checks_its_revision_and_records_the_change(people, method):
    item = record(people["analyst"], method)
    with pytest.raises(ValidationError, match="Record changed"):
        evidence.change_evidence(
            actor=people["reviewer"],
            evidence=item,
            expected_revision=item.revision + 1,
            reason="Typo",
            **values(title="Changed"),
        )
    with pytest.raises(ValidationError, match="Nothing was changed"):
        evidence.change_evidence(
            actor=people["reviewer"],
            evidence=item,
            expected_revision=item.revision,
            reason="Typo",
            **values(),
        )
    changed = evidence.change_evidence(
        actor=people["reviewer"],
        evidence=item,
        expected_revision=item.revision,
        reason="Typo",
        **values(title="Validation of the synthetic assay, tablets"),
    )
    assert changed.revision == 2 and changed.title.endswith("tablets")
    event = AuditEvent.objects.get(action="method_evidence.changed")
    assert event.before["title"] == FIELDS["title"] and event.actor == people["reviewer"]


def test_characteristics_are_added_and_removed_on_a_draft(people, method):
    item = record(people["analyst"], method)
    with pytest.raises(ValidationError) as caught:
        characteristic(people["analyst"], item, characteristic="other", detail=" ")
    assert "detail" in caught.value.message_dict
    line = characteristic(people["analyst"], item)
    item.refresh_from_db()
    assert item.revision == 2 and line.label.startswith("Accuracy: Recovery")
    evidence.remove_characteristic(actor=people["analyst"], item=line, reason="Wrong row")
    item.refresh_from_db()
    assert item.revision == 3 and not item.characteristics.exists()
    assert {e.action for e in AuditEvent.objects.filter(object_id=str(item.pk))} >= {
        "method_evidence.characteristic_added",
        "method_evidence.characteristic_removed",
    }


def test_at_most_thirty_characteristics(people, method, monkeypatch):
    monkeypatch.setattr(evidence, "MAX_CHARACTERISTICS", 2)
    item = record(people["analyst"], method)
    characteristic(people["analyst"], item)
    characteristic(people["analyst"], item, characteristic="repeatability")
    with pytest.raises(ValidationError, match="at most 2"):
        characteristic(people["analyst"], item, characteristic="specificity")


# Approval --------------------------------------------------------------------------------


def test_approval_freezes_the_record_and_its_characteristics(people, method):
    item = record(people["analyst"], method)
    characteristic(people["analyst"], item)
    characteristic(people["analyst"], item, characteristic="repeatability", result="RSD 0.4 %")
    done = approve_record(item, people["approver"])
    assert done.state == "approved" and done.approved_at is not None
    assert [c["characteristic"] for c in done.content["characteristics"]] == [
        "accuracy",
        "repeatability",
    ]
    assert done.content["report_ref"] == FIELDS["report_ref"]
    assert done.content_hash == digest(done.content)
    signature = ElectronicSignature.objects.get(object_id=str(item.pk))
    assert signature.meaning == "approved" and signature.signer == people["approver"]
    assert signature.content["content_hash"] == done.content_hash


@pytest.mark.parametrize("who", ["recorder", "editor", "characteristic"])
def test_nobody_who_recorded_or_changed_it_approves(people, method, who):
    dual = people["dual"]  # quality, analyst and reviewer
    item = record(dual if who == "recorder" else people["analyst"], method)
    characteristic(dual if who == "characteristic" else people["analyst"], item)
    if who == "editor":
        item.refresh_from_db()
        evidence.change_evidence(
            actor=dual,
            evidence=item,
            expected_revision=item.revision,
            reason="Clarified",
            **values(statement="Suitable, with system suitability checked in every run."),
        )
    with pytest.raises(PermissionDenied, match="another quality person"):
        approve_record(item, dual)
    assert MethodEvidence.objects.get().state == "draft"
    assert not ElectronicSignature.objects.exists()


def test_only_quality_approves(people, method):
    item = record(people["analyst"], method)
    characteristic(people["analyst"], item)
    with pytest.raises(PermissionDenied):
        approve_record(item, people["reviewer"])


def test_what_approval_needs(people, method):
    analyst = people["analyst"]
    empty = record(analyst, method)
    with pytest.raises(ValidationError, match="Add the characteristics"):
        approve_record(empty, people["approver"])
    # A transfer waiver has no experimental characteristics.
    waiver = record(
        analyst, method, kind="transfer", source="Synthetic Lab B", transfer_approach="waiver"
    )
    assert approve_record(waiver, people["approver"]).state == "approved"
    # A criterion not met with the conclusion "suitable" needs the deviations stated.
    unmet = record(analyst, method)
    characteristic(analyst, unmet, outcome="not_met")
    with pytest.raises(ValidationError, match="Deviations"):
        approve_record(unmet, people["approver"])
    unmet.refresh_from_db()
    evidence.change_evidence(
        actor=analyst,
        evidence=unmet,
        expected_revision=unmet.revision,
        reason="Assessment added",
        **values(deviations="Recovery at 80 % was 97.6 %; the range was narrowed to 90-120 %."),
    )
    assert approve_record(unmet, people["approver"]).state == "approved"
    # A record that concludes the method is not suitable is approved as it is.
    failed = record(analyst, method, conclusion="not_suitable")
    characteristic(analyst, failed, outcome="not_met")
    assert approve_record(failed, people["approver"]).conclusion == "not_suitable"


def test_stale_revision_and_wrong_pin_are_refused(people, method):
    item = record(people["analyst"], method)
    characteristic(people["analyst"], item)
    item.refresh_from_db()
    with pytest.raises(ValidationError, match="Record changed"):
        approve_record(item, people["approver"], expected_revision=item.revision - 1)
    with pytest.raises(ValidationError):
        approve_record(item, people["approver"], pin="00000000")
    assert PINCredential.objects.get(user=people["approver"]).failures == 1
    assert AuditEvent.objects.filter(action="signature.denied").exists()
    assert MethodEvidence.objects.get().state == "draft"


def test_approved_record_and_characteristics_are_guarded(people, method):
    item = approved(people, method)
    with pytest.raises(ValidationError, match="draft"):
        characteristic(people["analyst"], item)
    with pytest.raises(ValidationError, match="draft"):
        evidence.change_evidence(
            actor=people["analyst"],
            evidence=item,
            expected_revision=item.revision,
            reason="Late change",
            **values(title="Tampered"),
        )
    line = item.characteristics.get()
    for operation in (
        lambda: MethodEvidence.objects.filter(pk=item.pk).update(title="Tampered"),
        lambda: MethodEvidence.objects.filter(pk=item.pk).update(state="draft"),
        lambda: MethodEvidence.objects.filter(pk=item.pk).delete(),
        lambda: MethodEvidenceCharacteristic.objects.filter(pk=line.pk).update(result="100 %"),
        lambda: MethodEvidenceCharacteristic.objects.filter(pk=line.pk).delete(),
        lambda: MethodEvidenceCharacteristic.objects.create(
            evidence=item,
            characteristic="robustness",
            criterion="x",
            result="y",
            outcome="met",
            created_by=people["analyst"],
        ),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()
    # A draft's method and recorder are fixed too, and a draft is never deleted.
    draft = record(people["analyst"], method)
    other = method_revision(people["author"], code="kf-water").method
    for operation in (
        lambda: MethodEvidence.objects.filter(pk=draft.pk).update(method=other),
        lambda: MethodEvidence.objects.filter(pk=draft.pk).update(recorded_by=people["reviewer"]),
        lambda: MethodEvidence.objects.filter(pk=draft.pk).delete(),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            operation()


# Withdrawal ------------------------------------------------------------------------------


def test_a_draft_is_withdrawn_by_its_recorder_or_quality(people, method):
    item = record(people["analyst"], method)
    with pytest.raises(PermissionDenied, match="recorded this draft"):
        evidence.discard_evidence(
            actor=people["reviewer"], evidence=item, expected_revision=1, reason="Not needed"
        )
    with pytest.raises(ValidationError, match="Record changed"):
        evidence.discard_evidence(
            actor=people["analyst"], evidence=item, expected_revision=2, reason="Not needed"
        )
    done = evidence.discard_evidence(
        actor=people["analyst"], evidence=item, expected_revision=1, reason="Not needed"
    )
    assert done.state == "withdrawn" and done.content is None and done.approved_at is None
    other = record(people["analyst"], method)
    assert (
        evidence.discard_evidence(
            actor=people["author"], evidence=other, expected_revision=1, reason="Duplicate"
        ).state
        == "withdrawn"
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodEvidence.objects.filter(pk=done.pk).update(title="Revived")


def test_quality_withdraws_an_approved_record_with_a_signature(people, method):
    item = approved(people, method)
    with pytest.raises(ValidationError, match="draft"):
        evidence.discard_evidence(
            actor=people["author"],
            evidence=item,
            expected_revision=item.revision,
            reason="Wrong",
        )
    with pytest.raises(PermissionDenied):
        evidence.withdraw_evidence(
            actor=people["analyst"],
            pin=PIN,
            evidence=item,
            expected_revision=item.revision,
            reason="Data integrity finding",
        )
    done = evidence.withdraw_evidence(
        actor=people["author"],
        pin=PIN,
        evidence=item,
        expected_revision=item.revision,
        reason="Data integrity finding",
    )
    assert done.state == "withdrawn" and done.content is not None and done.approved_at
    assert ElectronicSignature.objects.filter(meaning="withdrawn").count() == 1
    with pytest.raises(ValidationError, match="Only an approved record"):
        evidence.withdraw_evidence(
            actor=people["author"],
            pin=PIN,
            evidence=done,
            expected_revision=done.revision,
            reason="Again",
        )


# A method version relying on a record ----------------------------------------------------


def link(revision, actor, item=None, **external):
    return evidence.set_suitability(
        actor=actor, revision=revision, reason="Evidence approved", evidence=item, **external
    )


def test_a_draft_version_relies_on_an_approved_suitable_record(people, method):
    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    linked = link(draft, people["author"], item)
    assert linked.evidence == item
    assert linked.suitability_kind == "validation" and linked.suitability_ref == "VR-SYN-001 rev 1"
    event = AuditEvent.objects.get(action="method_revision.suitability_set")
    assert event.before["evidence"] is None and event.after["evidence"] == item.pk
    with pytest.raises(ValidationError, match="Nothing was changed"):
        link(linked, people["author"], item)
    # The person who set it does not approve the version; another quality approver does.
    with pytest.raises(PermissionDenied):
        approve(linked, people["author"])
    version = approve(linked, people["approver"])
    assert version.approved_content["evidence"] == {
        "id": item.pk,
        "identifier": item.identifier,
        "kind": "validation",
        "conclusion": "suitable",
        "content_hash": item.content_hash,
    }
    # The approved version is immutable, its evidence link with it.
    with pytest.raises(DatabaseError), transaction.atomic():
        MethodRevision.objects.filter(pk=version.pk).update(evidence=None)


def test_records_a_version_cannot_rely_on(people, method):
    draft = MethodRevision.objects.get(method=method)
    other_method = method_revision(people["author"], code="kf-water").method
    cases = {
        "another method": approved(people, other_method),
        "not approved yet": record(people["analyst"], method),
        "not suitable": approved(people, method, conclusion="not_suitable"),
    }
    withdrawn = approved(people, method)
    cases["was withdrawn"] = evidence.withdraw_evidence(
        actor=people["author"],
        pin=PIN,
        evidence=withdrawn,
        expected_revision=withdrawn.revision,
        reason="Superseded by revalidation",
    )
    for words, item in cases.items():
        with pytest.raises(ValidationError, match=words):
            link(draft, people["author"], item)
    assert evidence.relied_on_choices(method).count() == 0


def test_an_external_reference_replaces_the_link(people, method):
    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    link(draft, people["author"], item)
    with pytest.raises(ValidationError) as caught:
        link(draft, people["author"], suitability_kind="", suitability_ref=" ")
    assert set(caught.value.message_dict) == {"suitability_kind", "suitability_ref"}
    external = link(
        draft,
        people["author"],
        suitability_kind="compendial_verification",
        suitability_ref="VER-SYN-7 rev 1 (document system)",
    )
    assert external.evidence is None and external.suitability_kind == "compendial_verification"
    version = approve(external, people["approver"])
    assert "evidence" not in version.approved_content


def test_only_quality_sets_the_suitability_of_a_draft(people, method):
    draft = MethodRevision.objects.get(method=method)
    with pytest.raises(PermissionDenied):
        link(draft, people["analyst"], suitability_kind="validation", suitability_ref="VAL-X")
    version = approve(draft, people["approver"])
    with pytest.raises(ValidationError, match="draft"):
        link(version, people["author"], suitability_kind="validation", suitability_ref="VAL-X")


def test_approval_rechecks_the_record_relied_on(people, method):
    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    link(draft, people["author"], item)
    evidence.withdraw_evidence(
        actor=people["approver"],
        pin=PIN,
        evidence=item,
        expected_revision=item.revision + 0,
        reason="Withdrawn before the version was approved",
    )
    with pytest.raises(ValidationError, match="was withdrawn"):
        approve(draft, people["approver"])
    assert MethodRevision.objects.get(pk=draft.pk).status == "draft"


def test_withdrawing_a_record_leaves_approved_versions_unchanged(people, method):
    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    link(draft, people["author"], item)
    version = approve(draft, people["approver"])
    frozen = dict(version.approved_content)
    item.refresh_from_db()
    evidence.withdraw_evidence(
        actor=people["author"],
        pin=PIN,
        evidence=item,
        expected_revision=item.revision,
        reason="Superseded by revalidation",
    )
    version.refresh_from_db()
    assert version.status == "approved" and version.approved_content == frozen
    assert list(evidence.relying_versions(item)) == [version]


def test_versions_without_a_record_keep_their_content_shape(people, method):
    version = approve(MethodRevision.objects.get(method=method), people["approver"])
    assert "evidence" not in version.approved_content


# Review follow-ups: stale revisions, PINs and the interleaving of approval and withdrawal --


def test_withdrawal_refuses_a_wrong_pin_and_a_stale_revision(people, method):
    item = approved(people, method)
    with pytest.raises(ValidationError):
        evidence.withdraw_evidence(
            actor=people["author"],
            pin="00000000",
            evidence=item,
            expected_revision=item.revision,
            reason="Data integrity finding",
        )
    assert PINCredential.objects.get(user=people["author"]).failures == 1
    with pytest.raises(ValidationError, match="Record changed"):
        evidence.withdraw_evidence(
            actor=people["author"],
            pin=PIN,
            evidence=item,
            expected_revision=item.revision - 1,
            reason="Data integrity finding",
        )
    assert MethodEvidence.objects.get(pk=item.pk).state == "approved"


def test_stale_changes_of_characteristics_and_suitability_are_refused(people, method):
    item = record(people["analyst"], method)
    with pytest.raises(ValidationError, match="Record changed"):
        characteristic(people["analyst"], item, expected_revision=item.revision + 1)
    line = characteristic(people["analyst"], item, expected_revision=item.revision)
    with pytest.raises(ValidationError, match="Record changed"):
        evidence.remove_characteristic(
            actor=people["analyst"], item=line, reason="Wrong row", expected_revision=1
        )
    draft = MethodRevision.objects.get(method=method)
    with pytest.raises(ValidationError, match="Record changed"):
        evidence.set_suitability(
            actor=people["author"],
            revision=draft,
            reason="Changed my mind",
            suitability_kind="validation",
            suitability_ref="VAL-OTHER",
            expected_revision=draft.revision + 1,
        )
    assert MethodRevision.objects.get(pk=draft.pk).suitability_ref == draft.suitability_ref


def test_a_withdrawal_signed_during_the_version_approval_waits_for_it(people, method, monkeypatch):
    from laboratory.tests.helpers import run_interleaved

    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    link(draft, people["author"], item)

    def withdraw():
        return evidence.withdraw_evidence(
            actor=people["author"],
            pin=PIN,
            evidence=item,
            expected_revision=item.revision,
            reason="Withdrawn during the approval",
        )

    # The approval holds the record's lock when it checks it; the withdrawal queues behind it.
    outcome = run_interleaved(
        monkeypatch,
        evidence,
        "evidence_refusal",
        lambda: approve(draft, people["approver"]),
        withdraw,
    )
    version, withdrawn = outcome["first"], outcome["second"]
    assert version.status == "approved", version
    assert withdrawn.state == "withdrawn", withdrawn
    signed = ElectronicSignature.objects.get(
        object_type="catalog.methodrevision", object_id=str(version.pk)
    )
    assert withdrawn.withdrawn_at > signed.signed_at
    assert version.approved_content["evidence"]["identifier"] == item.identifier
