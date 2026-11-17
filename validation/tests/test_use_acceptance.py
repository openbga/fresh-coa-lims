"""Acceptance of the system for the laboratory's intended use: who records and accepts it, what
the signature freezes, supersession, withdrawal and the history kept in the database."""

import hashlib
import json
import threading

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction

from catalog.models import MethodRevision
from catalog.tests.factories import PIN, approve, method_revision, person
from core.models import AuditEvent, ElectronicSignature, PINCredential
from validation import services
from validation.models import UseAcceptance

pytestmark = pytest.mark.django_db(transaction=True)


def record(people, actor=None, codes=("ftir-identity", "hplc-assay"), **changes):
    data = {
        "actor": actor or people["author"],
        "title": "Synthetic QC release testing",
        "intended_use": "Release testing of synthetic incoming materials.",
        "method_codes": list(codes),
        "process_owner": people["author"],
        "system_owner": people["admin"],
        "validation_ref": "VAL-SYN-001 rev 1",
        "reason": "Synthetic validation completed",
    }
    data.update(changes)
    return services.record_use_acceptance(**data)


def token_for(acceptance):
    return services.acceptance_token(
        acceptance,
        services.configuration_in_force(),
        services.running_release(),
        services.current_acceptance(),
    )


def accept(acceptance, actor, **changes):
    acceptance.refresh_from_db()
    data = {
        "actor": actor,
        "pin": PIN,
        "acceptance": acceptance,
        "expected_revision": acceptance.revision,
        "reason": "Validation report reviewed",
        "token": token_for(acceptance),
    }
    data.update(changes)
    return services.accept_use(**data)


def test_quality_records_the_intended_use_with_an_audit_event(people, configured):
    recorded = record(people, exclusions="Stability studies are kept elsewhere.")
    assert recorded.state == "recorded" and recorded.label == f"UA-{recorded.pk}"
    assert recorded.method_codes == ["ftir-identity", "hplc-assay"]
    event = AuditEvent.objects.get(action="use_acceptance.recorded")
    assert event.actor == people["author"] and event.object_id == str(recorded.pk)
    assert event.after["validation_ref"] == "VAL-SYN-001 rev 1"
    assert event.reason == "Synthetic validation completed"


@pytest.mark.parametrize("role", ["analyst", "reviewer", "admin", "auditor"])
def test_only_quality_records_the_intended_use(people, configured, role):
    with pytest.raises(PermissionDenied):
        record(people, actor=people[role])
    assert not UseAcceptance.objects.exists()


def test_recording_needs_a_reason_assays_in_force_and_active_owners(people, configured):
    with pytest.raises(ValidationError, match="reason is required"):
        record(people, reason="  ")
    with pytest.raises(ValidationError, match="supported assay"):
        record(people, codes=())
    with pytest.raises(ValidationError, match="no approved version in force"):
        record(people, codes=("ftir-identity", "not-a-method"))
    draft = method_revision(people["author"], code="draft-only")
    with pytest.raises(ValidationError, match="draft-only has no approved version in force"):
        record(people, codes=(draft.method.code,))
    people["admin"].is_active = False
    people["admin"].save()
    with pytest.raises(ValidationError, match="active account"):
        record(people)
    outsider = person("no-role-owner")
    with pytest.raises(ValidationError, match="active account"):
        record(people, system_owner=outsider)
    with pytest.raises(ValidationError):
        record(people, validation_ref=" ", system_owner=people["reviewer"])
    assert not UseAcceptance.objects.exists()


def test_acceptance_freezes_the_configuration_in_force_and_the_release(
    people, configured, monkeypatch
):
    monkeypatch.setenv("SOURCE_REVISION", "abc1234synthetic")
    recorded = record(people)
    accepted = accept(recorded, people["approver"])
    assert accepted.state == "accepted" and accepted.revision == 2
    assert accepted.accepted_release == "abc1234synthetic"
    frozen = accepted.configuration
    assert [e["code"] for e in frozen["methods"]] == ["ftir-identity", "hplc-assay"]
    assert [e["code"] for e in frozen["supported_assays"]] == ["ftir-identity", "hplc-assay"]
    assert [e["code"] for e in frozen["rule_sets"]] == [configured["rules"].code]
    spec = configured["specification"]
    assert frozen["specifications"] == [
        {
            "id": spec.pk,
            "code": spec.specification.code,
            "version": 1,
            "hash": spec.approved_hash,
        }
    ]
    canonical = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
    assert accepted.configuration_hash == hashlib.sha256(canonical).hexdigest()
    signature = ElectronicSignature.objects.get(object_type="validation.useacceptance")
    assert (signature.signer, signature.meaning, signature.revision) == (
        people["approver"],
        "accepted",
        2,
    )
    assert signature.content["configuration"] == frozen
    assert AuditEvent.objects.filter(action="signed.accepted").count() == 1


def test_no_one_accepts_what_they_recorded_whatever_their_roles(people, configured):
    mine = record(people, actor=people["dual"])
    with pytest.raises(PermissionDenied, match="you recorded"):
        accept(mine, people["dual"])
    assert services.use_denial(people["dual"], mine, accept=True) == services.SELF_ACCEPTANCE
    for role in ("analyst", "reviewer", "admin", "auditor"):
        with pytest.raises(PermissionDenied):
            accept(mine, people[role])
    mine.refresh_from_db()
    assert mine.state == "recorded"
    assert not ElectronicSignature.objects.filter(object_type="validation.useacceptance").exists()


def test_a_wrong_pin_counts_and_accepts_nothing(people, configured):
    recorded = record(people)
    with pytest.raises(ValidationError, match="PIN was not accepted"):
        accept(recorded, people["approver"], pin="00000000")
    assert PINCredential.objects.get(user=people["approver"]).failures == 1
    recorded.refresh_from_db()
    assert recorded.state == "recorded" and recorded.configuration is None


def test_a_stale_revision_or_page_is_refused(people, configured):
    recorded = record(people)
    with pytest.raises(ValidationError, match="Record changed"):
        accept(recorded, people["approver"], expected_revision=recorded.revision + 1)
    stale = token_for(recorded)
    # A new version of a supported method is approved after the page was opened.
    revised = method_revision(
        people["author"],
        method=MethodRevision.objects.get(method__code="hplc-assay").method,
        start_days=-1,
    )
    approve(revised, people["approver"])
    with pytest.raises(ValidationError, match="changed since this page was opened"):
        accept(recorded, people["approver"], token=stale)
    recorded.refresh_from_db()
    assert recorded.state == "recorded"
    accepted = accept(recorded, people["approver"])
    hplc = next(e for e in accepted.configuration["methods"] if e["code"] == "hplc-assay")
    assert hplc["version"] == 2


def test_another_running_release_makes_the_page_stale(people, configured, monkeypatch):
    monkeypatch.setenv("SOURCE_REVISION", "before-deploy")
    recorded = record(people)
    stale = token_for(recorded)
    monkeypatch.setenv("SOURCE_REVISION", "after-deploy")
    with pytest.raises(ValidationError, match="running release"):
        accept(recorded, people["approver"], token=stale)


def test_a_supported_assay_without_a_version_in_force_cannot_be_accepted(
    people, configured, monkeypatch
):
    recorded = record(people)
    real = services.configuration_in_force

    def identity_retired(at=None):
        found = real(at)
        found["methods"] = [e for e in found["methods"] if e["code"] != "ftir-identity"]
        return found

    monkeypatch.setattr(services, "configuration_in_force", identity_retired)
    with pytest.raises(ValidationError, match="ftir-identity no longer has an approved version"):
        accept(recorded, people["approver"])
    recorded.refresh_from_db()
    assert recorded.state == "recorded"
    # The way forward: withdraw it and record the intended use again.
    services.withdraw_use(
        actor=people["approver"],
        acceptance=recorded,
        expected_revision=recorded.revision,
        reason="Identity method retired",
    )
    monkeypatch.setattr(services, "method_choices", lambda at=None: {"hplc-assay": "HPLC"})
    again = record(people, codes=("hplc-assay",))
    assert accept(again, people["approver"]).state == "accepted"


def test_accepting_a_newer_record_supersedes_the_one_before(people, configured):
    first = accept(record(people), people["approver"])
    second = record(people, title="Synthetic QC release testing, second site")
    stale = services.acceptance_token(
        second, services.configuration_in_force(), services.running_release(), None
    )
    with pytest.raises(ValidationError, match="current acceptance"):
        accept(second, people["approver"], token=stale)
    accept(second, people["approver"])
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.state, first.superseded_by, first.revision) == ("superseded", second, 3)
    assert first.superseded_at == second.accepted_at
    assert list(UseAcceptance.objects.filter(state="accepted")) == [second]
    event = AuditEvent.objects.get(action="use_acceptance.superseded")
    assert event.object_id == str(first.pk) and event.actor == people["approver"]
    assert event.reason.startswith(f"Superseded by {second.label}.")
    assert services.current_acceptance() == second


def test_concurrent_acceptances_serialize(people, configured):
    third = person("qa-third", "quality")
    one, two = record(people), record(people, title="Second synthetic use")
    tokens = {r.pk: token_for(r) for r in (one, two)}
    barrier = threading.Barrier(2)
    outcomes = {}

    def sign(acceptance, actor):
        barrier.wait(10)
        try:
            outcomes[acceptance.pk] = services.accept_use(
                actor=actor,
                pin=PIN,
                acceptance=acceptance,
                expected_revision=acceptance.revision,
                reason="Concurrent synthetic acceptance",
                token=tokens[acceptance.pk],
            )
        except Exception as exc:  # reported to the asserting test
            outcomes[acceptance.pk] = exc
        finally:
            connection.close()

    threads = [
        threading.Thread(target=sign, args=(one, people["approver"])),
        threading.Thread(target=sign, args=(two, third)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(40)
    results = list(outcomes.values())
    accepted = [r for r in results if isinstance(r, UseAcceptance)]
    refused = [r for r in results if isinstance(r, Exception)]
    assert len(accepted) == 1 and len(refused) == 1, outcomes
    # The second signer was shown no current acceptance; the page is stale, never a fault.
    assert isinstance(refused[0], ValidationError), refused
    assert "current acceptance" in str(refused[0])
    assert UseAcceptance.objects.filter(state="accepted").count() == 1


def test_withdrawal(people, configured):
    recorded = record(people)
    with pytest.raises(PermissionDenied):
        services.withdraw_use(
            actor=people["admin"], acceptance=recorded, expected_revision=1, reason="No"
        )
    with pytest.raises(ValidationError, match="Record changed"):
        services.withdraw_use(
            actor=people["author"], acceptance=recorded, expected_revision=5, reason="Typo"
        )
    with pytest.raises(ValidationError, match="reason is required"):
        services.withdraw_use(
            actor=people["author"], acceptance=recorded, expected_revision=1, reason=""
        )
    withdrawn = services.withdraw_use(
        actor=people["author"], acceptance=recorded, expected_revision=1, reason="Wrong owner"
    )
    assert withdrawn.state == "withdrawn" and withdrawn.withdrawn_at and withdrawn.revision == 2
    assert AuditEvent.objects.get(action="use_acceptance.withdrawn").reason == "Wrong owner"
    with pytest.raises(ValidationError, match="awaiting acceptance"):
        accept(withdrawn, people["approver"])
    accepted = accept(record(people), people["approver"])
    with pytest.raises(ValidationError, match="accepted"):
        services.withdraw_use(
            actor=people["author"], acceptance=accepted, expected_revision=2, reason="No"
        )


def test_changes_since_acceptance(people, configured):
    accepted = accept(record(people), people["approver"])
    current = services.configuration_in_force()
    assert services.configuration_changes(accepted.configuration, current) == []
    hplc = MethodRevision.objects.get(method__code="hplc-assay").method
    approve(method_revision(people["author"], method=hplc), people["approver"])
    approve(method_revision(people["author"], code="kf-water"), people["approver"])
    rows = services.configuration_changes(accepted.configuration, services.configuration_in_force())
    assert [(r["kind"], r["code"], r["accepted"], r["now"], r["change"]) for r in rows] == [
        ("Method", "hplc-assay", "v1", "v2", "Another version in force"),
        ("Method", "kf-water", "", "v1", "Newly in force"),
    ]
    assert services.outside_assays(accepted.method_codes, services.configuration_in_force()) == [
        "kf-water"
    ]


def raw_update(sql, *params):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_the_database_keeps_records_as_recorded_and_signed(people, configured):
    recorded = record(people)
    with pytest.raises(DatabaseError, match="immutable"):
        raw_update(
            "UPDATE validation_useacceptance SET title = 'Edited', revision = revision + 1 "
            "WHERE id = %s",
            recorded.pk,
        )
    with pytest.raises(DatabaseError, match="cannot be deleted"):
        raw_update("DELETE FROM validation_useacceptance WHERE id = %s", recorded.pk)
    with pytest.raises(DatabaseError, match="advances its revision"):
        raw_update(
            "UPDATE validation_useacceptance SET state = 'withdrawn', withdrawn_at = now() "
            "WHERE id = %s",
            recorded.pk,
        )
    accepted = accept(recorded, people["approver"])
    with pytest.raises(DatabaseError, match="superseded by another record"):
        raw_update(
            "UPDATE validation_useacceptance SET revision = revision + 1, "
            "state = 'superseded', superseded_at = now(), superseded_by_id = id WHERE id = %s",
            accepted.pk,
        )
    other = record(people)
    with pytest.raises(DatabaseError, match="immutable"):
        raw_update(
            "UPDATE validation_useacceptance SET configuration = '{}'::jsonb, "
            "revision = revision + 1, state = 'superseded', superseded_at = now(), "
            "superseded_by_id = %s WHERE id = %s",
            other.pk,
            accepted.pk,
        )
    with pytest.raises(DatabaseError, match="accepted or withdrawn once"):
        raw_update(
            "UPDATE validation_useacceptance SET state = 'recorded', revision = revision + 1 "
            "WHERE id = %s",
            accepted.pk,
        )
    with pytest.raises(DatabaseError, match="starts awaiting acceptance"):
        raw_update(
            "INSERT INTO validation_useacceptance (title, intended_use, exclusions, "
            "method_codes, process_owner_id, system_owner_id, other_responsibilities, "
            "validation_ref, validation_url, open_issues, recorded_by_id, recorded_at, state, "
            "configuration, configuration_hash, accepted_release, accepted_at, revision) "
            "VALUES ('T', 'U', '', '[\"m\"]', %s, %s, '', 'V', '', '', %s, now(), 'accepted', "
            "'{}', '', '', now(), 1)",
            people["author"].pk,
            people["admin"].pk,
            people["author"].pk,
        )
    with pytest.raises(DatabaseError, match="names its supported assays"):
        raw_update(
            "INSERT INTO validation_useacceptance (title, intended_use, exclusions, "
            "method_codes, process_owner_id, system_owner_id, other_responsibilities, "
            "validation_ref, validation_url, open_issues, recorded_by_id, recorded_at, state, "
            "configuration_hash, accepted_release, revision) "
            "VALUES ('T', 'U', '', '[\" \"]', %s, %s, '', 'V', '', '', %s, now(), 'recorded', "
            "'', '', 1)",
            people["author"].pk,
            people["admin"].pk,
            people["author"].pk,
        )


def test_owners_must_still_be_active_when_it_is_accepted(people, configured):
    recorded = record(people)
    people["admin"].is_active = False
    people["admin"].save()
    with pytest.raises(ValidationError, match="system owner named is no longer an active"):
        accept(recorded, people["approver"])
    assert services.owner_refusal(recorded).startswith("The system owner")
    recorded.refresh_from_db()
    assert recorded.state == "recorded"
    services.withdraw_use(
        actor=people["approver"],
        acceptance=recorded,
        expected_revision=recorded.revision,
        reason="System owner left",
    )


def test_a_recorded_row_never_carries_what_a_signature_writes(people, configured):
    accepted = accept(record(people), people["approver"])
    for column, value in (
        ("superseded_by_id", accepted.pk),
        ("configuration_hash", "'x'"),
        ("accepted_release", "'x'"),
    ):
        with pytest.raises(DatabaseError, match="starts awaiting acceptance"):
            raw_update(
                "INSERT INTO validation_useacceptance (title, intended_use, exclusions, "
                "method_codes, process_owner_id, system_owner_id, other_responsibilities, "
                "validation_ref, validation_url, open_issues, recorded_by_id, recorded_at, "
                "state, configuration_hash, accepted_release, revision"
                + (", superseded_by_id" if column == "superseded_by_id" else "")
                + ") VALUES ('T', 'U', '', '[\"m\"]', %s, %s, '', 'V', '', '', %s, now(), "
                "'recorded', "
                + ("'x'" if column == "configuration_hash" else "''")
                + ", "
                + ("'x'" if column == "accepted_release" else "''")
                + ", 1"
                + (f", {value}" if column == "superseded_by_id" else "")
                + ")",
                people["author"].pk,
                people["admin"].pk,
                people["author"].pk,
            )
