"""Equipment, qualification, reagent and use contracts against PostgreSQL."""

from datetime import datetime, time, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature, PINCredential
from laboratory import services
from laboratory.eligibility import (
    affected_uses,
    analyst_eligibility,
    equipment_eligibility,
    equipment_filter,
    equipment_queryset,
    equipment_status,
    reagent_eligibility,
)
from laboratory.models import Calibration, Equipment, Qualification, ReagentLot, ResourceUse

from .helpers import (
    PIN,
    accept_new_calibration,
    make_equipment,
    make_reagent,
    qualify_analyst,
    qualify_equipment,
)

pytestmark = pytest.mark.django_db(transaction=True)


def end_of(day):
    return timezone.make_aware(datetime.combine(day, time(23, 59)))


def start_of(day):
    return timezone.make_aware(datetime.combine(day, time(0, 0)))


# --- Equipment fitness -----------------------------------------------------------------------


def test_ready_equipment_signature_binds_exact_revision(people):
    equipment = make_equipment(people)
    assert equipment_eligibility(equipment).ok
    calibration = Calibration.objects.get()
    signature = ElectronicSignature.objects.get(object_type="laboratory.calibration")
    assert signature.meaning == "reviewed"
    assert signature.signer == people["reviewer"]
    assert signature.revision == calibration.revision == 2
    assert signature.content["state"] == "accepted"
    assert signature.audit_event.action == "signed.reviewed"
    assert signature.audit_event.before["state"] == "recorded"


def test_unaccepted_or_missing_calibration_is_not_fit(people):
    equipment = make_equipment(people, ready=False)
    finding = equipment_eligibility(equipment)
    assert not finding.ok and "No independently accepted calibration" in finding.reasons[0]
    accept_new_calibration(people, equipment, accept=False)
    equipment = Equipment.objects.get(pk=equipment.pk)
    assert any("calibration" in r for r in equipment_eligibility(equipment).reasons)


def test_missing_qualification_blocks_only_when_required(people):
    needs = make_equipment(people, "CH-1", ready=False)
    accept_new_calibration(people, needs)
    assert "qualification" in " ".join(equipment_eligibility(needs).reasons)
    free = make_equipment(people, "CH-2", requires_qualification=False, ready=False)
    accept_new_calibration(people, free)
    assert equipment_eligibility(Equipment.objects.get(pk=free.pk)).ok


def test_calibration_due_date_is_inclusive_and_next_day_blocks(people):
    equipment = make_equipment(people)
    due = Calibration.objects.get().due_date
    assert equipment_eligibility(equipment, end_of(due)).ok
    next_day = equipment_eligibility(equipment, start_of(due + timedelta(days=1)))
    assert not next_day.ok and "expired" in next_day.reasons[0]


def test_recorder_and_non_reviewers_cannot_accept_calibration(people):
    equipment = make_equipment(people, ready=False)
    calibration = accept_new_calibration(people, equipment, accept=False)
    people["analyst"].groups.add(people["reviewer"].groups.get())
    with pytest.raises(PermissionDenied, match="recorded"):
        services.accept_calibration(
            actor=people["analyst"],
            pin=PIN,
            calibration=calibration,
            expected_revision=1,
            reason="Self review",
        )
    with pytest.raises(PermissionDenied):
        services.accept_calibration(
            actor=people["quality"],
            pin=PIN,
            calibration=calibration,
            expected_revision=1,
            reason="Wrong role",
        )
    calibration.refresh_from_db()
    assert calibration.state == "recorded"
    assert not ElectronicSignature.objects.filter(object_type="laboratory.calibration").exists()


def test_stale_revision_and_bad_pin_do_not_accept(people):
    equipment = make_equipment(people, ready=False)
    calibration = accept_new_calibration(people, equipment, accept=False)
    with pytest.raises(ValidationError, match="Record changed"):
        services.accept_calibration(
            actor=people["reviewer"],
            pin=PIN,
            calibration=calibration,
            expected_revision=99,
            reason="Stale",
        )
    with pytest.raises(ValidationError, match="not accepted"):
        services.accept_calibration(
            actor=people["reviewer"],
            pin="00000000",
            calibration=calibration,
            expected_revision=1,
            reason="Wrong PIN",
        )
    calibration.refresh_from_db()
    assert calibration.state == "recorded"
    # The failed attempt survives the rejected transition.
    assert PINCredential.objects.get(user=people["reviewer"]).failures == 1
    assert AuditEvent.objects.filter(actor=people["reviewer"], action="signature.denied").exists()


def test_failed_calibration_removes_from_service_immediately(people):
    equipment = make_equipment(people)
    services.authorize_use(
        actor=qualified_analyst(people),
        context_type="quality.sample",
        context_id=1,
        activity="HPLC-ASSAY",
        equipment=[equipment],
        reason="Synthetic use",
    )
    fail = accept_new_calibration(people, equipment, outcome="fail", accept=False)
    equipment = Equipment.objects.get(pk=equipment.pk)
    assert equipment.state == "out_of_service"
    assert equipment.status_changed_by == people["analyst"]
    finding = equipment_eligibility(equipment)
    assert not finding.ok and "out of service" in finding.reasons[0]
    assert AuditEvent.objects.filter(action="equipment.out_of_service").exists()
    assert fail.state == "recorded"
    assert affected_uses(equipment).count() == 1


def qualified_analyst(people, user_key="analyst"):
    qualify_analyst(people, people[user_key])
    return people[user_key]


def test_return_to_service_needs_new_accepted_calibration_and_independent_signer(people):
    equipment = make_equipment(people)
    accept_new_calibration(people, equipment, outcome="fail", accept=False, performed_hours_ago=0)
    equipment = Equipment.objects.get(pk=equipment.pk)
    kwargs = {
        "pin": PIN,
        "equipment": equipment,
        "expected_revision": equipment.revision,
        "impact_assessment": "No results affected in the synthetic window",
    }
    with pytest.raises(ValidationError, match="passing calibration"):
        services.return_to_service(actor=people["quality"], **kwargs)
    accept_new_calibration(people, equipment, performed_hours_ago=0)
    equipment = Equipment.objects.get(pk=equipment.pk)
    kwargs["equipment"], kwargs["expected_revision"] = equipment, equipment.revision
    people["analyst"].groups.add(people["quality"].groups.get())
    with pytest.raises(PermissionDenied, match="removed equipment"):
        services.return_to_service(actor=people["analyst"], **kwargs)
    restored = services.return_to_service(actor=people["quality"], **kwargs)
    assert restored.state == "in_service"
    signature = ElectronicSignature.objects.get(object_type="laboratory.equipment")
    assert signature.meaning == "approved"
    assert "Affected uses assessed" in signature.audit_event.reason
    assert equipment_eligibility(restored).ok


def test_out_of_service_is_protective_and_audited(people):
    equipment = make_equipment(people)
    services.take_out_of_service(actor=people["reviewer"], equipment=equipment, reason="Drift")
    with pytest.raises(ValidationError, match="already"):
        services.take_out_of_service(actor=people["reviewer"], equipment=equipment, reason="Again")
    with pytest.raises(PermissionDenied):
        services.take_out_of_service(actor=people["auditor"], equipment=equipment, reason="No")
    assert not equipment_eligibility(Equipment.objects.get(pk=equipment.pk)).ok


def test_list_status_filter_agrees_with_eligibility(people):
    today = timezone.localdate()
    ready = make_equipment(people, "E-READY")
    soon = make_equipment(people, "E-SOON", ready=False)
    accept_new_calibration(people, soon, days_valid=10)
    qualify_equipment(people, soon)
    unqualified = make_equipment(people, "E-NOQUAL", ready=False)
    accept_new_calibration(people, unqualified)
    uncalibrated = make_equipment(people, "E-NEW", ready=False)
    failed = make_equipment(people, "E-FAIL")
    accept_new_calibration(people, failed, outcome="fail", accept=False, performed_hours_ago=0)
    stopped = make_equipment(people, "E-STOP")
    services.take_out_of_service(actor=people["analyst"], equipment=stopped, reason="Stopped")
    overdue = make_equipment(people, "E-OVER", ready=False)
    accept_new_calibration(people, overdue, days_valid=-1, performed_hours_ago=240)
    qualify_equipment(people, overdue)
    assert today > overdue.calibrations.get().due_date
    expected = {
        overdue: "overdue",
        ready: "ready",
        soon: "due_soon",
        unqualified: "unfit",
        uncalibrated: "unfit",
        failed: "out_of_service",
        stopped: "out_of_service",
    }
    base = equipment_queryset()
    for equipment, key in expected.items():
        annotated = base.get(pk=equipment.pk)
        assert equipment_status(annotated)[2] == key, equipment.asset_id
        assert equipment_filter(base, key).filter(pk=equipment.pk).exists()
        fresh = Equipment.objects.prefetch_related("calibrations", "qualifications").get(
            pk=equipment.pk
        )
        assert equipment_eligibility(fresh).ok == (key in ("ready", "due_soon"))
        for other in {"ready", "due_soon", "overdue", "unfit", "out_of_service"} - {key}:
            assert not equipment_filter(base, other).filter(pk=equipment.pk).exists()


# --- Qualification ---------------------------------------------------------------------------


def test_qualification_independence_and_validity_window(people):
    user = people["analyst"]
    today = timezone.localdate()
    with pytest.raises(PermissionDenied, match="yourself"):
        services.record_qualification(
            actor=user,
            user=user,
            activity="A",
            scope_note="",
            evidence_ref="T",
            evidence_url="",
            valid_from=today,
            valid_until=today,
            reason="Self",
        )
    qualification = services.record_qualification(
        actor=people["reviewer"],
        user=user,
        activity="HPLC-ASSAY",
        scope_note="",
        evidence_ref="T-1",
        evidence_url="",
        valid_from=today,
        valid_until=today + timedelta(days=2),
        reason="Training record",
    )
    assert not analyst_eligibility(user, "HPLC-ASSAY").ok
    for actor in (people["reviewer"], user):
        people[actor.username].groups.add(people["quality"].groups.get())
        with pytest.raises(PermissionDenied):
            services.approve_qualification(
                actor=actor,
                pin=PIN,
                qualification=qualification,
                expected_revision=1,
                reason="Not independent",
            )
    approved = services.approve_qualification(
        actor=people["quality"],
        pin=PIN,
        qualification=qualification,
        expected_revision=1,
        reason="Independent",
    )
    assert analyst_eligibility(user, "hplc-assay").ok  # activity codes compare case-insensitively
    assert not analyst_eligibility(user, "OTHER-METHOD").ok
    assert analyst_eligibility(user, "HPLC-ASSAY", end_of(approved.valid_until)).ok
    assert not analyst_eligibility(
        user, "HPLC-ASSAY", start_of(approved.valid_until + timedelta(days=1))
    ).ok


def test_revocation_blocks_from_signature_time_and_keeps_history(people):
    user = people["analyst"]
    approved = qualify_analyst(people, user)
    before = timezone.now()
    revoked = services.revoke_qualification(
        actor=people["quality2"],
        pin=PIN,
        qualification=approved,
        expected_revision=approved.revision,
        reason="Competence lapsed",
    )
    assert revoked.state == "revoked"
    assert not analyst_eligibility(user, "HPLC-ASSAY").ok
    assert analyst_eligibility(user, "HPLC-ASSAY", before).ok  # earlier work stays justified
    assert ElectronicSignature.objects.filter(meaning="revoked").exists()
    with pytest.raises(ValidationError, match="Only approved"):
        services.revoke_qualification(
            actor=people["quality2"],
            pin=PIN,
            qualification=revoked,
            expected_revision=revoked.revision,
            reason="Again",
        )


def test_recorded_qualification_does_not_qualify(people):
    today = timezone.localdate()
    services.record_qualification(
        actor=people["reviewer"],
        user=people["analyst"],
        activity="X",
        scope_note="",
        evidence_ref="T",
        evidence_url="",
        valid_from=today,
        valid_until=today,
        reason="Pending",
    )
    assert not analyst_eligibility(people["analyst"], "X").ok


# --- Reagents --------------------------------------------------------------------------------


def test_reagent_release_is_independent_and_blocks_expired(people):
    lot = make_reagent(people, release=False)
    assert not reagent_eligibility(lot).ok
    with pytest.raises(PermissionDenied, match="recorded"):
        people["analyst"].groups.add(people["reviewer"].groups.get())
        services.release_reagent(
            actor=people["analyst"], pin=PIN, reagent=lot, expected_revision=1, reason="Self"
        )
    released = services.release_reagent(
        actor=people["reviewer"], pin=PIN, reagent=lot, expected_revision=1, reason="Checked"
    )
    assert reagent_eligibility(released).ok
    assert reagent_eligibility(released, end_of(released.expiry_date)).ok
    assert not reagent_eligibility(released, start_of(released.expiry_date + timedelta(days=1))).ok
    expired = make_reagent(
        people,
        "RG-OLD",
        release=False,
        received_on=timezone.localdate() - timedelta(days=9),
        expiry_date=timezone.localdate() - timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="expired"):
        services.release_reagent(
            actor=people["reviewer"], pin=PIN, reagent=expired, expected_revision=1, reason="Late"
        )


def test_prepared_solution_lineage_and_rejection_cascade(people):
    parent = make_reagent(
        people, "STD-1", kind="reference_standard", assigned_purity="99.500000", purity_unit="% w/w"
    )
    today = timezone.localdate()
    with pytest.raises(ValidationError, match="source lot"):
        make_reagent(people, "PREP-0", kind="prepared_solution", release=False)
    with pytest.raises(ValidationError, match="outlive"):
        make_reagent(
            people,
            "PREP-1",
            kind="prepared_solution",
            parent=parent,
            release=False,
            expiry_date=parent.expiry_date + timedelta(days=1),
        )
    prep = make_reagent(
        people,
        "PREP-2",
        kind="prepared_solution",
        parent=parent,
        expiry_date=today + timedelta(days=3),
        preparation_note="1:10 in synthetic diluent",
    )
    assert reagent_eligibility(ReagentLot.objects.select_related("parent").get(pk=prep.pk)).ok
    services.reject_reagent(actor=people["analyst"], reagent=parent, reason="Contaminated")
    prep = ReagentLot.objects.select_related("parent").get(pk=prep.pk)
    assert not reagent_eligibility(prep).ok
    with pytest.raises(ValidationError, match="already rejected"):
        services.reject_reagent(actor=people["analyst"], reagent=parent, reason="Again")
    with pytest.raises(ValidationError, match="released"):
        make_reagent(people, "PREP-3", kind="prepared_solution", parent=parent, release=False)


# --- Use gating ------------------------------------------------------------------------------


def test_authorize_use_records_evidence_for_every_resource(people):
    equipment = make_equipment(people)
    reagent = make_reagent(people)
    analyst = qualified_analyst(people)
    uses = services.authorize_use(
        actor=analyst,
        context_type="quality.sample",
        context_id=7,
        activity="HPLC-ASSAY",
        test_code="assay",
        profile_ref="PROFILE-1 r2",
        equipment=[equipment],
        reagents=[reagent],
        reason="Assay run",
    )
    assert {u.resource for u in uses} == {equipment, reagent}
    equipment_use = next(u for u in uses if u.equipment_id)
    assert equipment_use.eligibility["calibration"] == Calibration.objects.get().pk
    assert equipment_use.eligibility["analyst"]["qualification"]
    event = AuditEvent.objects.get(action="resource.used")
    assert event.actor == analyst and event.after["context"] == "quality.sample:7"


@pytest.mark.parametrize("fault", ["expired_reagent", "unqualified", "unfit_equipment"])
def test_blocked_use_writes_nothing_but_the_refusal_audit(people, fault):
    equipment = make_equipment(people, ready=fault != "unfit_equipment")
    reagent = make_reagent(people)
    analyst = people["analyst"]
    if fault != "unqualified":
        qualify_analyst(people, analyst)
    if fault == "expired_reagent":
        reagent = make_reagent(
            people,
            "RG-EXP",
            release=False,
            received_on=timezone.localdate() - timedelta(days=9),
            expiry_date=timezone.localdate() - timedelta(days=1),
        )
    with pytest.raises(services.UseBlocked) as caught:
        services.authorize_use(
            actor=analyst,
            context_type="quality.sample",
            context_id=1,
            activity="HPLC-ASSAY",
            equipment=[equipment],
            reagents=[reagent],
            reason="Attempt",
        )
    assert caught.value.findings and not all(f.ok for f in caught.value.findings)
    assert not ResourceUse.objects.exists()
    refusal = AuditEvent.objects.get(action="resource.use_blocked")
    assert refusal.actor == analyst and refusal.after["refusals"]
    assert not AuditEvent.objects.filter(action="resource.used").exists()


def test_use_requires_analyst_role_and_a_resource(people):
    equipment = make_equipment(people)
    with pytest.raises(PermissionDenied):
        services.authorize_use(
            actor=people["reviewer"],
            context_type="x",
            context_id=1,
            activity="A",
            equipment=[equipment],
            reason="No",
        )
    with pytest.raises(ValidationError, match="at least one"):
        services.authorize_use(
            actor=people["analyst"], context_type="x", context_id=1, activity="A", reason="None"
        )


# --- Database guards -------------------------------------------------------------------------


def test_database_rejects_edits_deletes_and_illegal_transitions(people):
    equipment = make_equipment(people)
    reagent = make_reagent(people)
    qualification = Qualification.objects.get()
    calibration = Calibration.objects.get()
    services.authorize_use(
        actor=qualified_analyst(people),
        context_type="x",
        context_id=1,
        activity="HPLC-ASSAY",
        equipment=[equipment],
        reason="Use",
    )
    attempts = [
        lambda: Equipment.objects.filter(pk=equipment.pk).update(asset_id="CHANGED"),
        lambda: Equipment.objects.filter(pk=equipment.pk).delete(),
        lambda: Calibration.objects.filter(pk=calibration.pk).update(outcome="fail"),
        lambda: Calibration.objects.filter(pk=calibration.pk).update(
            state="recorded", accepted_at=None
        ),
        lambda: Calibration.objects.filter(pk=calibration.pk).delete(),
        lambda: Qualification.objects.filter(pk=qualification.pk).update(valid_until="2099-01-01"),
        lambda: Qualification.objects.filter(pk=qualification.pk).update(state="recorded"),
        lambda: ReagentLot.objects.filter(pk=reagent.pk).update(expiry_date="2099-01-01"),
        lambda: ReagentLot.objects.filter(pk=reagent.pk).update(state="received"),
        lambda: ReagentLot.objects.filter(pk=reagent.pk).delete(),
        lambda: ResourceUse.objects.update(test_code="edited"),
        lambda: ResourceUse.objects.all().delete(),
    ]
    for attempt in attempts:
        with pytest.raises(DatabaseError), transaction.atomic():
            attempt()


# --- Review regressions ----------------------------------------------------------------------


def nested_preparations(people):
    stock = make_reagent(people, "STD-N", kind="reference_standard")
    child = make_reagent(
        people,
        "PREP-N1",
        kind="prepared_solution",
        parent=stock,
        expiry_date=timezone.localdate() + timedelta(days=30),
    )
    grandchild = make_reagent(
        people,
        "PREP-N2",
        kind="prepared_solution",
        parent=child,
        expiry_date=timezone.localdate() + timedelta(days=10),
    )
    return stock, child, grandchild


def fresh_reagent(lot):
    return ReagentLot.objects.select_related("parent").get(pk=lot.pk)


def test_nested_preparation_follows_the_whole_lineage(people):
    stock, child, grandchild = nested_preparations(people)
    assert reagent_eligibility(fresh_reagent(grandchild)).ok
    assert reagent_eligibility(fresh_reagent(grandchild)).evidence["lineage"] == [
        "PREP-N1",
        "STD-N",
    ]
    services.reject_reagent(actor=people["analyst"], reagent=stock, reason="Contaminated stock")
    finding = reagent_eligibility(fresh_reagent(grandchild))
    assert not finding.ok and any("STD-N was rejected" in r for r in finding.reasons)
    analyst = people["analyst"]
    qualify_analyst(people, analyst)
    with pytest.raises(services.UseBlocked):
        services.authorize_use(
            actor=analyst,
            context_type="x",
            context_id=1,
            activity="HPLC-ASSAY",
            reagents=[grandchild],
            reason="Use grandchild",
        )
    assert not ResourceUse.objects.exists()
    with pytest.raises(ValidationError, match="still eligible"):
        make_reagent(people, "PREP-N3", kind="prepared_solution", parent=grandchild, release=False)


def test_future_dated_receipt_is_refused_and_never_eligible(people):
    tomorrow = timezone.localdate() + timedelta(days=1)
    with pytest.raises(ValidationError, match="future"):
        make_reagent(
            people,
            "RG-FUT",
            release=False,
            received_on=tomorrow,
            expiry_date=tomorrow + timedelta(days=30),
        )
    lot = ReagentLot.objects.create(
        identifier="RG-DIRECT",
        kind="reagent",
        name="Direct",
        lot_number="1",
        received_on=tomorrow,
        expiry_date=tomorrow + timedelta(days=30),
        recorded_by=people["analyst"],
        state="released",
        released_at=timezone.now(),
    )
    assert not reagent_eligibility(lot).ok
    assert reagent_eligibility(lot, start_of(tomorrow + timedelta(days=1))).ok is True


def use_equipment(people, equipment):
    qualify_analyst(people, people["analyst"])
    return services.authorize_use(
        actor=people["analyst"],
        context_type="quality.sample",
        context_id=3,
        activity="HPLC-ASSAY",
        equipment=[equipment],
        reason="Run before the failure",
    )[0]


def test_affected_uses_survive_recovery_until_a_signed_assessment(people):
    equipment = make_equipment(people)
    used = use_equipment(people, equipment)
    accept_new_calibration(people, equipment, outcome="fail", accept=False, performed_hours_ago=0)
    accept_new_calibration(people, equipment, performed_hours_ago=0)  # recovery PASS accepted
    equipment = Equipment.objects.get(pk=equipment.pk)
    assert equipment_eligibility(equipment).reasons == ("Equipment is out of service.",)
    assert list(affected_uses(equipment)) == [used]  # the passing calibration did not erase it
    restored = services.return_to_service(
        actor=people["quality"],
        pin=PIN,
        equipment=equipment,
        expected_revision=equipment.revision,
        impact_assessment="Run reviewed; result retested",
    )
    reason = ElectronicSignature.objects.get(object_type="laboratory.equipment").audit_event.reason
    assert f"Affected uses assessed: [{used.pk}]" in reason
    assert "Failed calibrations assessed: [" in reason
    assert restored.state == "in_service"
    assert not affected_uses(restored).exists()  # closed by the signed assessment


def test_second_failure_assesses_only_uses_since_the_last_good_calibration(people):
    equipment = make_equipment(people)
    first_use = use_equipment(people, equipment)
    accept_new_calibration(people, equipment, outcome="fail", accept=False, performed_hours_ago=0)
    accept_new_calibration(people, equipment, performed_hours_ago=0)
    equipment = Equipment.objects.get(pk=equipment.pk)
    services.return_to_service(
        actor=people["quality"],
        pin=PIN,
        equipment=equipment,
        expected_revision=equipment.revision,
        impact_assessment="First failure assessed",
    )
    second_use = services.authorize_use(
        actor=people["analyst"],
        context_type="quality.sample",
        context_id=4,
        activity="HPLC-ASSAY",
        equipment=[Equipment.objects.get(pk=equipment.pk)],
        reason="Run after recovery",
    )[0]
    accept_new_calibration(people, equipment, outcome="fail", accept=False, performed_hours_ago=0)
    assert list(affected_uses(Equipment.objects.get(pk=equipment.pk))) == [second_use]
    assert first_use.pk != second_use.pk


def test_return_to_service_requires_qualification_valid_from(people):
    equipment = make_equipment(people, ready=False)
    accept_new_calibration(people, equipment)
    today = timezone.localdate()
    pending = services.record_qualification(
        actor=people["analyst"],
        equipment=equipment,
        activity="IQ/OQ/PQ",
        scope_note="",
        evidence_ref="Q",
        evidence_url="",
        valid_from=today + timedelta(days=5),
        valid_until=today + timedelta(days=300),
        reason="Future-dated qualification",
    )
    services.approve_qualification(
        actor=people["quality"],
        pin=PIN,
        qualification=pending,
        expected_revision=pending.revision,
        reason="Approved, starts later",
    )
    services.take_out_of_service(actor=people["reviewer"], equipment=equipment, reason="Check")
    equipment = Equipment.objects.get(pk=equipment.pk)
    with pytest.raises(ValidationError, match="qualification evidence"):
        services.return_to_service(
            actor=people["quality"],
            pin=PIN,
            equipment=equipment,
            expected_revision=equipment.revision,
            impact_assessment="No impact",
        )
