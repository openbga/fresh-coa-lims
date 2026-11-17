"""Rehearsals of recovery, downtime and upgrades: recording, evidence, independent acceptance,
withdrawal and the history kept in the database."""

import datetime
import hashlib

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from catalog.tests.factories import PIN, person
from core.models import AuditEvent, ElectronicSignature
from validation import services
from validation.models import Rehearsal, RehearsalFile

pytestmark = pytest.mark.django_db(transaction=True)


def rehearse(actor, **changes):
    data = {
        "actor": actor,
        "kind": "recovery",
        "title": "Synthetic restore of the nightly backup",
        "performed_on": timezone.localdate(),
        "release": "abc1234",
        "environment": "Isolated synthetic copy",
        "procedure_ref": "SOP-SYN-IT-007 rev 2",
        "acceptance_criteria": "Restore check passes; recovery within 4 hours.",
        "outcome": "met",
        "observations": "Restored in 52 minutes; every check passed.",
        "reason": "Annual synthetic rehearsal",
    }
    data.update(changes)
    return services.record_rehearsal(**data)


def upload(content=b'{"result": "passed"}', name="restore-check.json"):
    return SimpleUploadedFile(name, content, content_type="application/json")


def attach(actor, rehearsal, content=b'{"result": "passed"}', name="restore-check.json"):
    return services.attach_rehearsal_file(
        actor=actor,
        rehearsal=rehearsal,
        upload=upload(content, name),
        description="Restore check report",
    )


def accept(rehearsal, actor, **changes):
    rehearsal.refresh_from_db()
    data = {
        "actor": actor,
        "pin": PIN,
        "rehearsal": rehearsal,
        "expected_revision": rehearsal.revision,
        "reason": "Evidence reviewed",
    }
    data.update(changes)
    return services.accept_rehearsal(**data)


@pytest.mark.parametrize("role", ["author", "admin"])
def test_quality_or_the_system_administrator_records_a_rehearsal(people, role):
    recorded = rehearse(people[role])
    assert recorded.state == "recorded" and recorded.label == f"RH-{recorded.pk}"
    event = AuditEvent.objects.get(action="rehearsal.recorded")
    assert event.actor == people[role] and event.after["procedure_ref"] == "SOP-SYN-IT-007 rev 2"


@pytest.mark.parametrize("role", ["analyst", "reviewer", "auditor"])
def test_other_roles_do_not_record_rehearsals(people, role):
    with pytest.raises(PermissionDenied):
        rehearse(people[role])
    assert not Rehearsal.objects.exists()


def test_a_rehearsal_is_recorded_as_it_took_place(people):
    actor = people["author"]
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    with pytest.raises(ValidationError, match="after it took place"):
        rehearse(actor, performed_on=tomorrow)
    with pytest.raises(ValidationError, match="release before it"):
        rehearse(actor, kind="upgrade")
    with pytest.raises(ValidationError, match="actions taken or planned"):
        rehearse(actor, outcome="not_met")
    with pytest.raises(ValidationError):
        rehearse(actor, acceptance_criteria="  ")
    with pytest.raises(ValidationError, match="reason is required"):
        rehearse(actor, reason="")
    with pytest.raises(ValidationError):
        rehearse(actor, kind="fire-drill")
    assert not Rehearsal.objects.exists()
    upgrade = rehearse(actor, kind="upgrade", previous_release="0.1.0", release="0.2.0")
    failed = rehearse(
        actor, outcome="not_met", issues_and_actions="Two paper records not reconciled; CAPA-9."
    )
    assert upgrade.previous_release == "0.1.0" and failed.outcome == "not_met"


def test_the_recorder_attaches_evidence_while_it_awaits_acceptance(people):
    recorded = rehearse(people["admin"])
    stored = attach(people["admin"], recorded)
    assert stored.sha256 == hashlib.sha256(b'{"result": "passed"}').hexdigest()
    assert stored.size == 20 and stored.filename == "restore-check.json"
    recorded.refresh_from_db()
    assert recorded.revision == 2
    event = AuditEvent.objects.get(action="rehearsal.file_attached")
    assert event.object_id == str(recorded.pk) and event.after["sha256"] == stored.sha256
    with pytest.raises(ValidationError, match="already attached"):
        attach(people["admin"], recorded)
    with pytest.raises(ValidationError, match="Only the person who recorded"):
        attach(people["author"], recorded, content=b"other")
    with pytest.raises(ValidationError, match="empty"):
        attach(people["admin"], recorded, content=b"")
    with pytest.raises(PermissionDenied):
        attach(people["analyst"], recorded, content=b"analyst")
    with pytest.raises(ValidationError, match="Describe"):
        services.attach_rehearsal_file(
            actor=people["admin"], rehearsal=recorded, upload=upload(b"x"), description=" "
        )
    assert RehearsalFile.objects.count() == 1


def test_a_different_quality_person_accepts_it_with_its_evidence(people):
    recorded = rehearse(people["admin"])
    assert services.rehearsal_denial(people["author"], recorded, accept=True).startswith(
        "Attach the evidence"
    )
    with pytest.raises(ValidationError, match="Attach the evidence"):
        accept(recorded, people["author"])
    attach(people["admin"], recorded)
    with pytest.raises(PermissionDenied):
        accept(recorded, people["admin"])  # the system administrator is not quality
    accepted = accept(recorded, people["author"])
    assert accepted.state == "accepted" and accepted.accepted_at and accepted.revision == 3
    signature = ElectronicSignature.objects.get(object_type="validation.rehearsal")
    assert (signature.signer, signature.meaning) == (people["author"], "accepted")
    assert services.rehearsal_status(accepted) == ("Accepted: criteria met", "success")
    with pytest.raises(ValidationError, match="only while the rehearsal awaits acceptance"):
        attach(people["admin"], accepted, content=b"late")


def test_no_one_accepts_a_rehearsal_they_recorded(people):
    recorded = rehearse(people["dual"])
    attach(people["dual"], recorded)
    with pytest.raises(PermissionDenied, match="you recorded"):
        accept(recorded, people["dual"])
    failed = rehearse(
        people["author"], outcome="not_met", issues_and_actions="Restore took 7 hours; CAPA-12."
    )
    attach(people["author"], failed)
    accepted = accept(failed, people["approver"])
    assert services.rehearsal_status(accepted) == ("Accepted: criteria not met", "danger")


def test_evidence_attached_after_the_page_opened_makes_it_stale(people):
    recorded = rehearse(people["admin"])
    attach(people["admin"], recorded)
    recorded.refresh_from_db()
    opened = recorded.revision
    attach(people["admin"], recorded, content=b"a later file")
    with pytest.raises(ValidationError, match="Record changed"):
        accept(recorded, people["author"], expected_revision=opened)


def test_withdrawal(people):
    recorded = rehearse(people["admin"])
    other_admin = person("admin-b", "admin")
    with pytest.raises(PermissionDenied, match="Only the person who recorded"):
        services.withdraw_rehearsal(
            actor=other_admin, rehearsal=recorded, expected_revision=1, reason="Not mine"
        )
    with pytest.raises(ValidationError, match="Record changed"):
        services.withdraw_rehearsal(
            actor=people["admin"], rehearsal=recorded, expected_revision=3, reason="Typo"
        )
    withdrawn = services.withdraw_rehearsal(
        actor=people["author"], rehearsal=recorded, expected_revision=1, reason="Wrong date"
    )
    assert withdrawn.state == "withdrawn" and withdrawn.revision == 2
    with pytest.raises(ValidationError, match="awaits acceptance"):
        attach(people["admin"], withdrawn)
    mine = rehearse(people["admin"])
    assert (
        services.withdraw_rehearsal(
            actor=people["admin"], rehearsal=mine, expected_revision=1, reason="Duplicate"
        ).state
        == "withdrawn"
    )
    accepted = rehearse(people["admin"])
    attach(people["admin"], accepted)
    accept(accepted, people["author"])
    with pytest.raises(ValidationError, match="accepted"):
        services.withdraw_rehearsal(
            actor=people["author"], rehearsal=accepted, expected_revision=3, reason="No"
        )


def raw(sql, *params):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_the_database_keeps_rehearsals_and_their_evidence(people):
    recorded = rehearse(people["admin"])
    stored = attach(people["admin"], recorded)
    with pytest.raises(DatabaseError, match="append-only"):
        raw("UPDATE validation_rehearsalfile SET description = 'x' WHERE id = %s", stored.pk)
    with pytest.raises(DatabaseError, match="append-only"):
        raw("DELETE FROM validation_rehearsalfile WHERE id = %s", stored.pk)
    with pytest.raises(DatabaseError, match="immutable"):
        raw(
            "UPDATE validation_rehearsal SET outcome = 'not_met', revision = revision + 1 "
            "WHERE id = %s",
            recorded.pk,
        )
    with pytest.raises(DatabaseError, match="cannot be deleted"):
        raw("DELETE FROM validation_rehearsal WHERE id = %s", recorded.pk)
    accept(recorded, people["author"])
    with pytest.raises(DatabaseError, match="awaits acceptance"):
        raw(
            "INSERT INTO validation_rehearsalfile (rehearsal_id, filename, content_type, size, "
            "sha256, content, description, uploaded_by_id, uploaded_at) VALUES "
            "(%s, 'late.txt', '', 4, 'x', 'late'::bytea, 'Late', %s, now())",
            recorded.pk,
            people["admin"].pk,
        )
    with pytest.raises(DatabaseError, match="accepted or withdrawn once"):
        raw(
            "UPDATE validation_rehearsal SET state = 'withdrawn', withdrawn_at = now(), "
            "revision = revision + 1 WHERE id = %s",
            recorded.pk,
        )


def test_the_acceptance_freezes_the_evidence_it_was_shown(people):
    recorded = rehearse(people["admin"])
    first = attach(people["admin"], recorded)
    recorded.refresh_from_db()
    shown = recorded.revision
    # A file written past the service still advances the revision: the page is stale.
    RehearsalFile.objects.create(
        rehearsal=recorded,
        filename="unseen.bin",
        size=6,
        sha256="1" * 64,
        content=b"unseen",
        description="Not shown to the signer",
        uploaded_by=people["admin"],
    )
    recorded.refresh_from_db()
    assert recorded.revision == shown + 1
    with pytest.raises(ValidationError, match="Record changed"):
        accept(recorded, people["author"], expected_revision=shown)
    accepted = accept(recorded, people["author"])
    assert [e["sha256"] for e in accepted.evidence] == [first.sha256, "1" * 64]
    signature = ElectronicSignature.objects.get(object_type="validation.rehearsal")
    assert signature.content["evidence"] == accepted.evidence


def test_no_file_reaches_a_rehearsal_accepted_meanwhile(people):
    import threading
    import time

    recorded = rehearse(people["admin"])
    attach(people["admin"], recorded)
    holding = threading.Event()
    outcome = {}

    def acceptor():
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE validation_rehearsal SET state = 'accepted', accepted_at = now(), "
                    "evidence = '[]'::jsonb, revision = revision + 1 WHERE id = %s",
                    [recorded.pk],
                )
                holding.set()
                time.sleep(1)
        finally:
            connection.close()

    def inserter():
        holding.wait(10)
        try:
            with transaction.atomic():
                RehearsalFile.objects.create(
                    rehearsal_id=recorded.pk,
                    filename="late.bin",
                    size=4,
                    sha256="0" * 64,
                    content=b"late",
                    description="Added while it was accepted",
                    uploaded_by=people["admin"],
                )
            outcome["inserted"] = True
        except Exception as exc:  # reported to the asserting test
            outcome["error"] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=acceptor), threading.Thread(target=inserter)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert "awaits acceptance" in str(outcome.get("error")), outcome
    assert not RehearsalFile.objects.filter(filename="late.bin").exists()
