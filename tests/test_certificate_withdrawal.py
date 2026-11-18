"""The signed withdrawal of an issued certificate of analysis and the evidence that its recipients
were told: the transition and its refusals, what stays exactly as issued, a later certificate
for the same lot and recipient, recipient notifications, the database guards and the lot's
exported record (synthetic data only)."""

import hashlib
import json
import threading
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    connection,
    connections,
    transaction,
)
from django.utils import timezone

from analytical import services as analytical
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import set_pin
from reporting import lot_record
from reporting import services as reporting
from reporting.models import RecipientNotification, Report, ReportVersion
from tests.test_integrated_journey import PASSWORD, PIN, assign_and_sample, dispose, observed_test
from tests.test_integrated_journey import integrated as integrated  # noqa: F401
from tests.test_lot_record_export import unpack

pytestmark = pytest.mark.django_db(transaction=True)

RECIPIENT = "Synthetic Customer A"
REASON = "Synthetic: the assay result was transcribed wrongly onto the certificate"


def released(data):
    """The integrated journey to a signed QC disposition."""
    people = data["people"]
    test, _ = observed_test(data, assign_and_sample(data), "100.25")
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    return dispose(data, people["approver"])


def issue(world, recipient=RECIPIENT, who="approver"):
    _, evidence_hash, blockers = reporting.preview(world["lot"])
    assert blockers == [], blockers
    return reporting.issue_report(
        actor=world["people"][who],
        pin=PIN,
        lot=world["lot"],
        recipient=recipient,
        evidence_hash=evidence_hash,
        reason="Synthetic certificate issue",
    )


def amend(world, report, who="approver"):
    report.refresh_from_db()
    _, evidence_hash, _ = reporting.preview(report.lot)
    return reporting.amend_report(
        actor=world["people"][who],
        pin=PIN,
        report=report,
        expected_version=report.version_count,
        evidence_hash=evidence_hash,
        reason="Synthetic wording correction",
    )


@pytest.fixture
def world(integrated, django_user_model):
    people = integrated["people"]
    for name, roles in {"auditor": ["auditor"], "admin": ["admin"]}.items():
        user = django_user_model.objects.create_user(
            username=f"synthetic_{name}", password=PASSWORD, first_name="Synthetic", last_name=name
        )
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        people[name] = user
    world = {**integrated, "lot": released(integrated)}
    world["report"] = issue(world)
    return world


def fresh(report):
    return Report.objects.get(pk=report.pk)


def withdraw(world, report=None, who="approver", **values):
    report = fresh(report or world["report"])
    arguments = {
        "actor": world["people"][who],
        "pin": PIN,
        "report": report,
        "expected_revision": report.revision,
        "reason": REASON,
        "reference": "IA-3",
        **values,
    }
    return reporting.withdraw_report(**arguments)


def notify(world, report=None, who="approver", **values):
    arguments = {
        "actor": world["people"][who],
        "report": report or world["report"],
        "recipient": RECIPIENT,
        "notified_on": timezone.localdate(),
        "means": "email",
        "evidence_ref": "SYN-MAIL-0001, complaint file SYN-CF-7",
        "note": "",
        **values,
    }
    return reporting.record_notification(**arguments)


def versions_of(report):
    return list(
        ReportVersion.objects.filter(report=report)
        .order_by("number")
        .values_list("number", "pdf_sha256", "snapshot_hash", "pdf_size")
    )


def test_withdrawal_is_signed_audited_and_keeps_every_issued_version(world):
    people = world["people"]
    report = amend(world, world["report"])  # two versions: both must stay as issued
    before = fresh(report)
    issued = versions_of(report)
    stored = {v.number: bytes(v.pdf) for v in report.versions.all()}

    withdrawn = withdraw(world)  # the issuer may withdraw: no independence rule

    assert (withdrawn.state, withdrawn.status_label, withdrawn.tone) == (
        "withdrawn",
        "Withdrawn",
        "danger",
    )
    assert withdrawn.revision == before.revision + 1
    assert (withdrawn.withdrawal_reason, withdrawn.withdrawal_reference) == (REASON, "IA-3")
    assert (
        withdrawn.version_count,
        withdrawn.current_pdf_sha256,
        withdrawn.current_snapshot_hash,
    ) == (before.version_count, before.current_pdf_sha256, before.current_snapshot_hash)
    signature = ElectronicSignature.objects.get(
        object_type="reporting.report", object_id=str(report.pk), meaning="withdrawn"
    )
    assert signature.signer == people["approver"]
    assert signature.revision == withdrawn.revision
    assert signature.signed_at == withdrawn.withdrawn_at
    assert signature.content["state"] == "withdrawn"
    assert signature.content["withdrawal_reference"] == "IA-3"
    assert reporting.withdrawal_signature(withdrawn) == signature
    event = AuditEvent.objects.get(action="signed.withdrawn", object_id=str(report.pk))
    assert (event.actor, event.reason) == (people["approver"], REASON)
    assert (event.before["state"], event.after["state"]) == ("issued", "withdrawn")
    assert signature.audit_event == event
    assert withdrawn.awaiting_notification is True
    # Every issued version and its bytes are exactly as issued, and still readable.
    assert versions_of(report) == issued
    for version in report.versions.all():
        data = reporting.read_pdf(actor=people["reviewer"], version=version)
        assert data == stored[version.number]
        assert hashlib.sha256(data).hexdigest() == version.pdf_sha256
    assert AuditEvent.objects.filter(action="report.downloaded").count() == 2
    # The issue and amendment signatures are untouched.
    assert reporting.signature_for(report.versions.get(number=1)).meaning == "issued"
    assert reporting.signature_for(report.versions.get(number=2)).meaning == "amended"


@pytest.mark.parametrize("who", ["reviewer", "receiver", "auditor", "admin"])
def test_only_quality_may_withdraw(world, who):
    with pytest.raises(PermissionDenied):
        withdraw(world, who=who)
    report = fresh(world["report"])
    assert report.state == "issued" and report.withdrawn_at is None
    assert not ElectronicSignature.objects.filter(meaning="withdrawn").exists()


def test_withdrawal_needs_an_issued_current_record_and_a_reason(world):
    draft = reporting.open_report(
        actor=world["people"]["approver"], lot=world["lot"], recipient="Synthetic Customer B"
    )
    with pytest.raises(ValidationError, match="Only an issued certificate can be withdrawn"):
        withdraw(world, report=draft)
    with pytest.raises(ValidationError, match="Record changed"):
        withdraw(world, expected_revision=fresh(world["report"]).revision - 1)
    with pytest.raises(ValidationError, match="reason"):
        withdraw(world, reason="   ")
    assert fresh(world["report"]).state == "issued"
    assert fresh(draft).state == "draft"
    withdraw(world)
    with pytest.raises(ValidationError, match="already withdrawn"):
        withdraw(world)
    assert ElectronicSignature.objects.filter(meaning="withdrawn").count() == 1


def test_wrong_pin_is_counted_and_audited_but_nothing_is_withdrawn(world):
    approver = world["people"]["approver"]
    with pytest.raises(ValidationError, match="not accepted"):
        withdraw(world, pin="00000000")
    assert PINCredential.objects.get(user=approver).failures == 1
    assert AuditEvent.objects.filter(action="signature.denied", actor=approver).exists()
    report = fresh(world["report"])
    assert (report.state, report.withdrawn_at, report.withdrawal_reason) == ("issued", None, "")
    assert not ElectronicSignature.objects.filter(meaning="withdrawn").exists()
    assert not AuditEvent.objects.filter(action="signed.withdrawn").exists()


def test_a_withdrawn_certificate_is_never_amended(world):
    withdraw(world)
    with pytest.raises(ValidationError, match="withdrawn; it is not amended"):
        amend(world, world["report"])
    assert world["report"].versions.count() == 1
    assert not ElectronicSignature.objects.filter(meaning="amended").exists()


def test_a_new_certificate_for_the_same_recipient_is_a_new_numbered_series(world):
    lot, old = world["lot"], world["report"]
    issued = versions_of(old)
    withdraw(world)
    again = issue(world)
    assert again.pk != old.pk
    assert (again.number, again.sequence) == (f"CoA-{lot.number}-2", 2)
    assert (again.recipient, again.state, again.version_count) == (RECIPIENT, "issued", 1)
    assert fresh(old).state == "withdrawn"
    assert versions_of(old) == issued  # unchanged, and its own
    assert again.versions.count() == 1
    # The current series for the recipient is the new one; it is not issued twice.
    assert (
        reporting.open_report(actor=world["people"]["approver"], lot=lot, recipient=RECIPIENT)
        == again
    )
    with pytest.raises(ValidationError, match="already issued"):
        issue(world)
    assert Report.objects.filter(lot=lot).count() == 2


def test_a_notification_is_evidence_and_leaves_the_signed_head_alone(world):
    people, report = world["people"], world["report"]
    with pytest.raises(ValidationError, match="only for a withdrawn certificate"):
        notify(world)
    withdraw(world)
    head = fresh(report)
    signatures = ElectronicSignature.objects.count()
    notification = notify(world, report=head)
    assert notification.recorded_by == people["approver"]
    assert (notification.recipient, notification.means) == (RECIPIENT, "email")
    after = fresh(report)
    assert (after.revision, after.state) == (head.revision, "withdrawn")
    assert after.awaiting_notification is False
    assert ElectronicSignature.objects.count() == signatures
    event = AuditEvent.objects.get(action="report.recipient_notified")
    assert (event.object_type, event.object_id) == ("reporting.report", str(report.pk))
    assert event.actor == people["approver"]
    assert event.after["notification"] == notification.pk
    assert event.after["evidence_ref"] == "SYN-MAIL-0001, complaint file SYN-CF-7"
    assert event.after["notified_on"] == timezone.localdate().isoformat()
    # Another recipient, told another way, is a further notification.
    other = notify(world, recipient="Synthetic Consignee", means="other", note="Courier note")
    assert list(after.notifications.all()) == [notification, other]


def test_notification_refusals_are_field_errors(world):
    withdraw(world)
    today = timezone.localdate()
    cases = {
        "notified_on": {"notified_on": today + timedelta(days=1)},
        "recipient": {"recipient": "   "},
        "evidence_ref": {"evidence_ref": " "},
        "note": {"means": "other", "note": ""},
        "means": {"means": "carrier pigeon"},
    }
    for field, values in cases.items():
        with pytest.raises(ValidationError) as refused:
            notify(world, **values)
        assert list(refused.value.message_dict) == [field], field
    with pytest.raises(ValidationError) as refused:
        notify(world, notified_on=today - timedelta(days=1))
    assert "cannot be earlier" in refused.value.message_dict["notified_on"][0]
    with pytest.raises(PermissionDenied):
        notify(world, who="reviewer")
    with pytest.raises(PermissionDenied):
        notify(world, who="admin")
    assert not RecipientNotification.objects.exists()
    assert not AuditEvent.objects.filter(action="report.recipient_notified").exists()


def test_the_certificate_head_is_guarded_by_the_database(world):
    report = world["report"]
    issued = Report.objects.filter(pk=report.pk)
    now = timezone.now()
    head = fresh(report)
    with pytest.raises(DatabaseError, match="set only by the withdrawal"), transaction.atomic():
        issued.update(withdrawal_reference="IA-9")
    with pytest.raises(DatabaseError, match="set only by the withdrawal"), transaction.atomic():
        issued.update(withdrawn_at=now, withdrawal_reason=REASON)
    # A withdrawal outside a signed revision, or one that touches the versions, is refused.
    with pytest.raises(DatabaseError, match="one signed revision"), transaction.atomic():
        issued.update(state="withdrawn", withdrawn_at=now, withdrawal_reason=REASON)
    with pytest.raises(DatabaseError, match="one signed revision"), transaction.atomic():
        issued.update(
            state="withdrawn",
            withdrawn_at=now,
            withdrawal_reason=REASON,
            revision=head.revision + 1,
            version_count=0,
        )
    with pytest.raises(DatabaseError, match="one signed revision"), transaction.atomic():
        issued.update(
            state="withdrawn",
            withdrawn_at=None,
            withdrawal_reason=REASON,
            revision=head.revision + 1,
        )
    draft = reporting.open_report(
        actor=world["people"]["approver"], lot=world["lot"], recipient="Synthetic Customer B"
    )
    with pytest.raises(DatabaseError, match="one signed revision"), transaction.atomic():
        Report.objects.filter(pk=draft.pk).update(
            state="withdrawn", withdrawn_at=now, withdrawal_reason=REASON, revision=2
        )
    # A second current series for the same lot and recipient is refused.
    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            lot=world["lot"],
            recipient=RECIPIENT,
            sequence=9,
            number="CoA-SYN-DUPLICATE-9",
            created_by=world["people"]["approver"],
        )
    withdrawn = withdraw(world)
    final = Report.objects.filter(pk=report.pk)
    for change in (
        {"withdrawal_reason": "Rewritten later"},
        {"withdrawal_reference": "IA-4"},
        {"state": "issued", "revision": withdrawn.revision + 1},
        {"revision": withdrawn.revision + 1},
        {"recipient": "Someone else"},
    ):
        with pytest.raises(DatabaseError, match="final"), transaction.atomic():
            final.update(**change)
    with pytest.raises(DatabaseError, match="cannot be deleted"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM reporting_report WHERE id = %s", [report.pk])
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        ReportVersion.objects.filter(report=report).update(pdf=b"%PDF-forged")
    assert fresh(report).withdrawal_reason == REASON


def test_notifications_are_append_only_and_only_for_a_withdrawn_certificate(world):
    report, approver = world["report"], world["people"]["approver"]

    def row(**values):
        return RecipientNotification.objects.create(
            report=report,
            recipient=values.get("recipient", RECIPIENT),
            notified_on=timezone.localdate(),
            means=values.get("means", "letter"),
            evidence_ref=values.get("evidence_ref", "SYN-LETTER-0001"),
            recorded_by=approver,
        )

    with pytest.raises(DatabaseError, match="only for a withdrawn"), transaction.atomic():
        row()  # the certificate is still issued
    withdraw(world)
    with pytest.raises(DatabaseError, match="names who was notified"), transaction.atomic():
        row(evidence_ref="  ")
    with pytest.raises(DatabaseError, match="names who was notified"), transaction.atomic():
        row(recipient=" ")
    with pytest.raises(IntegrityError), transaction.atomic():
        row(means="other")  # Other needs a note
    notification = notify(world)
    stored = RecipientNotification.objects.filter(pk=notification.pk)
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        stored.update(evidence_ref="SYN-ELSEWHERE")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        stored.delete()
    assert stored.get().evidence_ref == "SYN-MAIL-0001, complaint file SYN-CF-7"


def test_a_notification_waits_for_a_withdrawal_being_signed(world):
    """The insert guard reads the certificate under a share lock: while a withdrawal holds the
    certificate's row, a notification waits instead of judging the state it would replace."""
    report = world["report"]
    locked, release = threading.Event(), threading.Event()

    def withdrawal_in_progress():
        try:
            with transaction.atomic():
                Report.objects.select_for_update().get(pk=report.pk)
                locked.set()
                release.wait(10)
        finally:
            connections.close_all()

    holder = threading.Thread(target=withdrawal_in_progress)
    holder.start()
    try:
        assert locked.wait(10)
        with pytest.raises(OperationalError, match="lock timeout"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '300ms'")
            RecipientNotification.objects.create(
                report=report,
                recipient=RECIPIENT,
                notified_on=timezone.localdate(),
                means="email",
                evidence_ref="SYN-MAIL-0002",
                recorded_by=world["people"]["approver"],
            )
    finally:
        release.set()
        holder.join()
    assert not RecipientNotification.objects.exists()


def test_the_exported_lot_record_holds_the_withdrawal_and_its_notifications(world):
    withdraw(world)
    notification = notify(world)
    package = lot_record.export_lot_record(
        actor=world["people"]["auditor"],
        lot_pk=world["lot"].pk,
        purpose="Synthetic inspection request INS-SYN-002",
    )
    _, _, members = unpack(package)
    record = json.loads(members["record.json"])
    sections = {s["key"]: s for s in record["sections"]}
    fields = sections["reports"]["records"][0]["fields"]
    assert (fields["state"], fields["withdrawal_reference"]) == ("withdrawn", "IA-3")
    assert fields["withdrawal_reason"] == REASON and fields["withdrawn_at"]
    rows = sections["report_notifications"]["records"]
    assert [r["id"] for r in rows] == [notification.pk]
    assert rows[0]["fields"]["evidence_ref"] == notification.evidence_ref
    assert "reporting.recipientnotification" in record["types"]
    signed = {(s["fields"]["object_type"], s["fields"]["meaning"]) for s in record["signatures"]}
    assert ("reporting.report", "withdrawn") in signed
    # The issued certificate is in the package byte for byte.
    version = world["report"].versions.get(number=1)
    assert members[f"files/certificates/{world['report'].number}-v1.pdf"] == bytes(version.pdf)
