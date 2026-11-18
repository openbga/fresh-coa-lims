"""The impact assessment of a failure: the records found from its cause, the decision on each,
protective holds placed through it, the independent signed conclusion, withdrawal and the
database guards (synthetic data only)."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin
from impact import scope, services
from impact.models import Assessment, Item
from laboratory import services as laboratory
from laboratory.models import ReagentLot, ResourceUse
from quality import services as quality
from reporting import services as reporting
from stability import services as stability
from stability.models import Hold
from suppliers.models import Supplier
from tests.receipts import supplier_receipt
from tests.test_integrated_journey import (
    PASSWORD,
    PIN,
    dispose,
    integrated,  # noqa: F401  (fixture)
)
from tests.test_result_types_journey import build_world, review, run

pytestmark = pytest.mark.django_db(transaction=True)

KIND, DECISION = Item.Kind, Item.Decision


def today():
    return timezone.localdate()


def fresh(obj):
    return type(obj).objects.get(pk=obj.pk)


def reviewed_world(django_user_model):
    """A lot in quarantine whose four tests are reviewed, and a balance (synthetic)."""
    world = build_world(django_user_model)
    world["tests"] = {code: test for code, (test, _) in run(world).items()}
    for test in world["tests"].values():
        review(world, test)
    world["balance"] = laboratory.register_equipment(
        actor=world["people"]["analyst"],
        asset_id="SYN-BAL-07",
        description="Synthetic analytical balance",
        category="balance",
        location="Synthetic laboratory",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    return world


def used(world, test, equipment=None, reagent=None):
    """Evidence that the resource was used for the test (as the bench writes it)."""
    return ResourceUse.objects.create(
        equipment=equipment if reagent is None else None,
        reagent_lot=reagent,
        context_type="analytical.analyticaltest",
        context_id=str(test.pk),
        activity="synthetic-rt-method",
        test_code=test.test_code,
        used_by=world["people"]["analyst"],
        eligibility={"synthetic": True},
    )


def released(world):
    world["lot"] = dispose(world, world["people"]["approver"])
    evidence, digest, blockers = reporting.preview(world["lot"])
    assert blockers == []
    world["report"] = reporting.issue_report(
        actor=world["people"]["approver"],
        pin=PIN,
        lot=world["lot"],
        recipient="Synthetic customer",
        evidence_hash=digest,
        reason="Synthetic certificate",
    )
    return world


@pytest.fixture
def world(django_user_model):
    return reviewed_world(django_user_model)


def begin(world, who="author", cause="equipment", **values):
    named = {}
    if cause == "equipment":
        named["equipment"] = values.pop("equipment", world["balance"])
    return services.start(
        actor=world["people"][who],
        cause=cause,
        title=values.pop("title", "Balance failed its calibration check"),
        description=values.pop("description", "Synthetic: the weekly check was out of tolerance."),
        found_on=values.pop("found_on", today()),
        period_from=values.pop("period_from", today() - timedelta(days=7)),
        period_until=values.pop("period_until", today()),
        quality_reference=values.pop("quality_reference", "DEV-SYN-0042"),
        **named,
        **values,
    )


def decide(world, item, decision=DECISION.NOT_AFFECTED, who="author", **values):
    item = fresh(item)
    return services.decide(
        actor=world["people"][who],
        item=item,
        expected_revision=item.revision,
        decision=decision,
        rationale=values.pop("rationale", "Synthetic: result within the check's margin"),
        follow_up=values.pop(
            "follow_up", "Retest under investigation" if decision == DECISION.AFFECTED else ""
        ),
        **values,
    )


def decide_all(world, assessment, **values):
    for item in fresh(assessment).items.all():
        decide(world, item, **values)
    return fresh(assessment)


def conclude(world, assessment, who="approver", reason="Synthetic conclusion"):
    assessment = fresh(assessment)
    return services.conclude(
        actor=world["people"][who],
        pin=PIN,
        assessment=assessment,
        expected_revision=assessment.revision,
        reason=reason,
    )


def kinds(assessment):
    return sorted((item.kind, item.target_id) for item in fresh(assessment).items.all())


# Finding the records ---------------------------------------------------------------------------


def test_equipment_finds_its_tests_their_lot_and_its_certificates(world):
    world = released(world)
    tests = world["tests"]
    used(world, tests["impurity"], world["balance"])
    used(world, tests["tamc"], world["balance"])
    assessment = begin(world)
    assert kinds(assessment) == sorted(
        [
            (KIND.TEST, tests["impurity"].pk),
            (KIND.TEST, tests["tamc"].pk),
            (KIND.LOT, world["lot"].pk),
            (KIND.CERTIFICATE, world["report"].pk),
        ]
    )
    items = {item.kind: item for item in assessment.items.all()}
    assert items[KIND.TEST].origin == Item.Origin.FOUND
    assert items[KIND.TEST].basis.startswith(f"SYN-BAL-07 used on {today().isoformat()}")
    assert items[KIND.LOT].basis.startswith("Its test T-")
    assert items[KIND.CERTIFICATE].basis == f"Issued for lot {world['lot'].number}."
    actions = list(
        AuditEvent.objects.filter(action__startswith="impact.").values_list("action", flat=True)
    )
    assert actions == ["impact.started", "impact.records_found"]
    found = AuditEvent.objects.get(action="impact.records_found")
    assert len(found.after["records"]) == 4
    # Nothing the assessment names changes: the lot stays released with its certificate.
    assert fresh(world["lot"]).state == "released"
    assert fresh(world["report"]).state == "issued"


def test_uses_outside_the_period_or_of_other_equipment_are_not_found(world):
    other = laboratory.register_equipment(
        actor=world["people"]["analyst"],
        asset_id="SYN-BAL-08",
        description="Another synthetic balance",
        category="balance",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    used(world, world["tests"]["impurity"], other)
    used(world, world["tests"]["tamc"], world["balance"])
    yesterday = today() - timedelta(days=1)
    assert (
        kinds(
            begin(
                world,
                period_from=yesterday - timedelta(days=5),
                period_until=yesterday,
                found_on=yesterday,
            )
        )
        == []
    )
    assessment = begin(world)
    assert kinds(assessment) == sorted(
        [(KIND.TEST, world["tests"]["tamc"].pk), (KIND.LOT, world["lot"].pk)]
    )


def test_a_reagent_lot_includes_the_solutions_prepared_from_it(world):
    people = world["people"]
    stock = ReagentLot.objects.create(
        identifier="SYN-STD-01",
        kind=ReagentLot.Kind.STANDARD,
        name="Synthetic reference standard",
        lot_number="RS-SYN-1",
        received_on=today(),
        expiry_date=today() + timedelta(days=90),
        recorded_by=people["analyst"],
    )
    solution = ReagentLot.objects.create(
        identifier="SYN-SOL-01",
        kind=ReagentLot.Kind.PREPARED,
        name="Synthetic working solution",
        lot_number="WS-SYN-1",
        parent=stock,
        received_on=today(),
        expiry_date=today() + timedelta(days=7),
        recorded_by=people["analyst"],
    )
    assert scope.reagent_lineage(stock.pk) == {stock.pk, solution.pk}
    used(world, world["tests"]["impurity"], reagent=solution)
    assessment = begin(world, cause="reagent", reagent_lot=stock)
    assert (KIND.TEST, world["tests"]["impurity"].pk) in kinds(assessment)
    # The solution alone does not lead back to its stock.
    assert scope.reagent_lineage(solution.pk) == {solution.pk}


def test_a_supplier_finds_the_lots_received_from_it_in_the_period(world):
    people = world["people"]
    supplier = Supplier.objects.create(
        code="syn-supplier",
        name="Synthetic Supplies",
        location="Nowhere",
        created_by=people["author"],
    )
    supplied = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-IA-SUP-001",
        material=world["material"].name,
        rules=world["lot"].rules,
        reason="Synthetic receipt",
        receipt=supplier_receipt(supplier),
    )
    quality.receive_lot(
        actor=people["analyst"],
        number="SYN-IA-SUP-002",
        material=world["material"].name,
        rules=world["lot"].rules,
        reason="Synthetic receipt",
        receipt=supplier_receipt(supplier, received_on=today() - timedelta(days=30)),
    )
    assessment = begin(world, cause="supplier", supplier=supplier)
    assert kinds(assessment) == [(KIND.LOT, supplied.pk)]
    assert fresh(assessment).items.get().basis == (
        f"Received from syn-supplier on {today().isoformat()}."
    )


# Starting --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values, field",
    [
        ({"equipment": None}, "equipment"),
        ({"cause": "other"}, "equipment"),
        ({"title": " "}, "title"),
        ({"found_on": today() + timedelta(days=1)}, "found_on"),
        ({"period_until": today() + timedelta(days=1)}, "period_until"),
        ({"period_from": today() + timedelta(days=1), "period_until": today()}, "period_until"),
        (
            {
                "found_on": today() - timedelta(days=3),
                "period_from": today() - timedelta(days=2),
            },
            "period_from",
        ),
    ],
)
def test_start_refuses_an_incomplete_or_inconsistent_assessment(world, values, field):
    cause = values.pop("cause", "equipment")
    extra = {"equipment": world["balance"]} if cause == "other" else {}
    with pytest.raises(ValidationError) as refused:
        if cause == "other":
            services.start(
                actor=world["people"]["author"],
                cause=cause,
                title="Synthetic",
                description="Synthetic",
                found_on=today(),
                period_from=today(),
                period_until=today(),
                **extra,
            )
        else:
            begin(world, **values)
    assert field in refused.value.message_dict
    assert not Assessment.objects.exists()


def test_only_quality_starts_and_acts_on_an_assessment(world):
    with pytest.raises(PermissionDenied):
        begin(world, who="reviewer")
    assessment = begin(world, cause="other")
    with pytest.raises(PermissionDenied):
        services.add_record(
            actor=world["people"]["reviewer"],
            assessment=assessment,
            expected_revision=assessment.revision,
            kind=KIND.LOT,
            identifier=world["lot"].number,
            reason="Synthetic",
        )


def test_another_cause_starts_empty_and_quality_adds_the_records(world):
    world = released(world)
    assessment = begin(world, cause="other", title="Mislabelled diluent", equipment=None)
    assert kinds(assessment) == []
    item = services.add_record(
        actor=world["people"]["author"],
        assessment=assessment,
        expected_revision=assessment.revision,
        kind=KIND.LOT,
        identifier=world["lot"].number,
        reason="Synthetic: the diluent was used for this lot's preparation",
    )
    assert (item.origin, item.basis) == (
        Item.Origin.ADDED,
        "Synthetic: the diluent was used for this lot's preparation",
    )
    assessment = fresh(assessment)
    assert assessment.revision == 2
    # The lot's certificate follows from the lot added and must be in the assessment too.
    (missing,) = scope.missing(assessment)
    assert missing.key == (KIND.CERTIFICATE, world["report"].pk)
    created = services.find_records(
        actor=world["people"]["author"],
        assessment=assessment,
        expected_revision=assessment.revision,
    )
    assert [c.report_id for c in created] == [world["report"].pk]
    with pytest.raises(ValidationError, match="already in the assessment"):
        services.add_record(
            actor=world["people"]["author"],
            assessment=fresh(assessment),
            expected_revision=fresh(assessment).revision,
            kind=KIND.LOT,
            identifier=world["lot"].number,
            reason="Again",
        )
    with pytest.raises(ValidationError, match="No stability study is called SYN-NONE"):
        services.add_record(
            actor=world["people"]["author"],
            assessment=fresh(assessment),
            expected_revision=fresh(assessment).revision,
            kind=KIND.STUDY,
            identifier="SYN-NONE",
            reason="Synthetic",
        )
    # A test is named by its number, with or without the T- prefix.
    test = world["tests"]["identity"]
    assert services.resolve(KIND.TEST, test.label) == test
    assert services.resolve(KIND.TEST, str(test.pk)) == test
    with pytest.raises(ValidationError):
        services.add_record(
            actor=world["people"]["author"],
            assessment=fresh(assessment),
            expected_revision=assessment.revision,  # stale
            kind=KIND.TEST,
            identifier=test.label,
            reason="Synthetic",
        )


# Decisions -------------------------------------------------------------------------------------


def test_a_decision_needs_its_reasons_and_is_kept_in_the_audit_trail(world):
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    item = assessment.items.get(kind=KIND.TEST)
    with pytest.raises(ValidationError) as refused:
        decide(world, item, DECISION.AFFECTED, follow_up="")
    assert "follow_up" in refused.value.message_dict
    with pytest.raises(ValidationError) as refused:
        decide(world, item, rationale=" ")
    assert "rationale" in refused.value.message_dict
    first = decide(
        world, item, DECISION.AFFECTED, follow_up="Retest under INV", follow_up_reference="INV-SYN"
    )
    assert (first.decision, first.decided_by, first.revision) == (
        DECISION.AFFECTED,
        world["people"]["author"],
        2,
    )
    assert fresh(assessment).revision == assessment.revision + 1
    second = decide(world, first, who="approver")
    assert second.decision == DECISION.NOT_AFFECTED and second.follow_up == ""
    events = AuditEvent.objects.filter(action="impact.record_decided").order_by("occurred_at")
    assert [e.after["decision"] for e in events] == ["affected", "not_affected"]
    assert events.last().before["decision"] == "affected"
    with pytest.raises(ValidationError, match="changed since you opened it"):
        services.decide(
            actor=world["people"]["author"],
            item=second,
            expected_revision=first.revision,
            decision=DECISION.NOT_AFFECTED,
            rationale="Stale",
        )


# Holds -----------------------------------------------------------------------------------------


def test_a_hold_through_the_assessment_blocks_the_disposition(world):
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    item = assessment.items.get(kind=KIND.LOT)
    test_item = assessment.items.get(kind=KIND.TEST)
    with pytest.raises(ValidationError, match="A hold is placed on a lot"):
        services.place_hold(
            actor=world["people"]["author"],
            item=test_item,
            expected_revision=test_item.revision,
            reason="Synthetic",
        )
    assert quality.disposition_blockers(fresh(world["lot"])) == []
    hold = services.place_hold(
        actor=world["people"]["author"],
        item=item,
        expected_revision=item.revision,
        reason="Synthetic: hold until the impact is known",
    )
    assert (hold.kind, hold.reference, hold.state) == (
        "quality",
        f"IA-{assessment.pk} · DEV-SYN-0042",
        "active",
    )
    assert fresh(item).hold == hold
    assert quality.disposition_blockers(fresh(world["lot"]))
    with pytest.raises(ValidationError, match="was placed through this assessment"):
        services.place_hold(
            actor=world["people"]["author"],
            item=fresh(item),
            expected_revision=fresh(item).revision,
            reason="Again",
        )
    # Withdrawal waits for the hold: release it with an independent signature first.
    assert "is active" in services.withdrawal_refusal(fresh(assessment))
    with pytest.raises(ValidationError, match="is active"):
        services.withdraw(
            actor=world["people"]["approver"],
            pin=PIN,
            assessment=fresh(assessment),
            expected_revision=fresh(assessment).revision,
            reason="Started on the wrong balance",
        )
    stability.release_hold(
        actor=world["people"]["approver"],
        pin=PIN,
        hold=hold,
        expected_revision=hold.revision,
        reason="Synthetic: impact assessed, nothing affected",
    )
    done = services.withdraw(
        actor=world["people"]["approver"],
        pin=PIN,
        assessment=fresh(assessment),
        expected_revision=fresh(assessment).revision,
        reason="Started on the wrong balance",
    )
    assert done.state == Assessment.State.WITHDRAWN and done.evidence == {}
    assert ElectronicSignature.objects.filter(
        object_type="impact.assessment", object_id=str(done.pk), meaning="withdrawn"
    ).exists()


def test_a_hold_on_a_released_lot_stops_its_certificates(world):
    world = released(world)
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    item = assessment.items.get(kind=KIND.LOT)
    services.place_hold(
        actor=world["people"]["author"],
        item=item,
        expected_revision=item.revision,
        reason="Synthetic: problem found after release",
    )
    _, _, blockers = reporting.preview(fresh(world["lot"]))
    assert blockers, "an active hold refuses a certificate"
    assert fresh(world["lot"]).state == "released"


# Conclusion ------------------------------------------------------------------------------------


def test_the_conclusion_is_independent_complete_and_frozen(world):
    world = released(world)
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    people = world["people"]
    # Undecided records refuse it.
    with pytest.raises(ValidationError, match="have no decision"):
        conclude(world, assessment)
    items = list(assessment.items.order_by("pk"))
    for item in items:
        decide(
            world,
            item,
            DECISION.AFFECTED if item.kind == KIND.CERTIFICATE else DECISION.NOT_AFFECTED,
            follow_up="Withdraw the certificate",
        )
    # The starter and the decider ("author") cannot conclude, nor a data author of a test.
    with pytest.raises(PermissionDenied):
        conclude(world, assessment, who="author")
    with pytest.raises(PermissionDenied):
        conclude(world, assessment, who="analyst")
    # A record the cause finds since must be added first.
    used(world, world["tests"]["tamc"], world["balance"])
    with pytest.raises(ValidationError, match="find affected records again"):
        conclude(world, assessment)
    services.find_records(
        actor=people["author"],
        assessment=fresh(assessment),
        expected_revision=fresh(assessment).revision,
    )
    decide_all(world, assessment)
    # A stale page is refused.
    with pytest.raises(ValidationError, match="Record changed"):
        services.conclude(
            actor=people["approver"],
            pin=PIN,
            assessment=fresh(assessment),
            expected_revision=assessment.revision,
            reason="Stale",
        )
    # A wrong PIN is refused and the failure is kept.
    denied = AuditEvent.objects.filter(action="signature.denied").count()
    with pytest.raises(ValidationError):
        services.conclude(
            actor=people["approver"],
            pin="999999",
            assessment=fresh(assessment),
            expected_revision=fresh(assessment).revision,
            reason="Wrong PIN",
        )
    assert AuditEvent.objects.filter(action="signature.denied").count() == denied + 1
    assert fresh(assessment).state == Assessment.State.OPEN
    done = conclude(world, assessment, reason="Synthetic: no result affected")
    assert done.state == Assessment.State.CONCLUDED
    evidence = done.evidence
    assert evidence["schema"] == services.EVIDENCE_SCHEMA
    assert evidence["assessment"] == done.label
    assert len(evidence["records"]) == 4
    assert evidence["affected"] == 0 and evidence["not_affected"] == 4
    assert people["author"].pk in evidence["author_ids"]
    assert people["analyst"].pk in evidence["author_ids"]
    signature = ElectronicSignature.objects.get(
        object_type="impact.assessment", object_id=str(done.pk), meaning="impact_assessed"
    )
    assert signature.signer == people["approver"] and signature.revision == done.revision
    # Closed: nothing more is decided, added or held.
    with pytest.raises(ValidationError, match="no longer open"):
        decide(world, items[0])
    with pytest.raises(ValidationError, match="no longer open"):
        services.find_records(
            actor=people["author"], assessment=done, expected_revision=done.revision
        )


def test_the_hold_state_is_frozen_with_the_conclusion(world):
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    item = assessment.items.get(kind=KIND.LOT)
    hold = services.place_hold(
        actor=world["people"]["author"], item=item, expected_revision=item.revision, reason="Hold"
    )
    decide_all(world, assessment, decision=DECISION.AFFECTED, follow_up="Held pending retest")
    done = conclude(world, assessment)
    (lot_row,) = [r for r in done.evidence["records"] if r["kind"] == "lot"]
    assert lot_row["hold"] == {"id": hold.pk, "state": "active"}
    assert done.evidence["affected"] == 2
    # The hold outlives the conclusion and is released on its own page.
    assert Hold.objects.get(pk=hold.pk).state == "active"


# Database guards -------------------------------------------------------------------------------


def raw(sql, params):
    with pytest.raises(DatabaseError):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)


def test_the_database_keeps_what_was_assessed(world):
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    item = assessment.items.get(kind=KIND.TEST)
    raw("UPDATE impact_assessment SET title = 'Edited' WHERE id = %s", [assessment.pk])
    raw("DELETE FROM impact_assessment WHERE id = %s", [assessment.pk])
    raw("UPDATE impact_item SET basis = 'Edited', revision = revision + 1 WHERE id = %s", [item.pk])
    raw("DELETE FROM impact_item WHERE id = %s", [item.pk])
    raw(
        "UPDATE impact_item SET decision = 'not_affected', rationale = 'x', decided_at = now(), "
        "decided_by_id = %s WHERE id = %s",
        [world["people"]["author"].pk, item.pk],
    )  # the revision must advance
    raw(
        "UPDATE impact_assessment SET state = 'concluded', decided_at = now(), "
        "decision_reason = 'x' WHERE id = %s",
        [assessment.pk],
    )  # nothing frozen
    decide_all(world, assessment)
    done = conclude(world, assessment)
    raw("UPDATE impact_assessment SET revision = revision + 1 WHERE id = %s", [done.pk])
    raw(
        "UPDATE impact_item SET rationale = 'Edited', revision = revision + 1 WHERE id = %s",
        [item.pk],
    )
    raw(
        "INSERT INTO impact_item (assessment_id, kind, lot_id, origin, basis, added_by_id, "
        "added_at, decision, rationale, follow_up, follow_up_reference, revision) VALUES "
        "(%s, 'lot', %s, 'added', 'Late', %s, now(), '', '', '', '', 1)",
        [done.pk, world["lot"].pk, world["people"]["author"].pk],
    )


def test_a_contract_laboratory_finds_the_results_it_reported(integrated):  # noqa: F811
    from tests.test_contract_laboratory_journey import approved_laboratory, assigned_test, report

    data = integrated
    test = assigned_test(data)
    laboratory_, _ = approved_laboratory(data)
    report(data, test, laboratory_id=laboratory_.pk)
    assessment = services.start(
        actor=data["people"]["author"],
        cause="contract_laboratory",
        contract_laboratory=laboratory_,
        title="Contract laboratory's balance out of calibration",
        description="Synthetic: notified by the contract laboratory",
        found_on=today(),
        period_from=today() - timedelta(days=3),
        period_until=today(),
    )
    assert (KIND.TEST, test.pk) in kinds(assessment)


def test_withdrawal_and_conclusion_need_quality_and_a_reason(world, django_user_model):
    assessment = begin(world, cause="other", equipment=None)
    outsider = django_user_model.objects.create_user("syn_ia_reviewer", password=PASSWORD)
    outsider.groups.add(Group.objects.get_or_create(name="reviewer")[0])
    set_pin(actor=outsider, pin=PIN, password=PASSWORD)
    with pytest.raises(PermissionDenied):
        services.withdraw(
            actor=outsider,
            pin=PIN,
            assessment=assessment,
            expected_revision=assessment.revision,
            reason="Synthetic",
        )
    with pytest.raises(ValidationError):
        services.withdraw(
            actor=world["people"]["approver"],
            pin=PIN,
            assessment=assessment,
            expected_revision=assessment.revision,
            reason=" ",
        )
    # An assessment of nothing is concluded by someone who did not start it.
    done = conclude(world, assessment, reason="Synthetic: nothing was affected")
    assert done.evidence["records"] == []


def test_a_chamber_finds_the_studies_with_pulls_stored_in_it(integrated):  # noqa: F811
    from tests.test_calculation_bench_journey import calibrate
    from tests.test_stability_testing import released as release_with_certificate
    from tests.test_stability_testing import shelf_life_of, study_of

    data, people = integrated, integrated["people"]
    lot, _ = release_with_certificate(data)
    study = study_of(data, lot, shelf_life_of(data))
    chamber = laboratory.register_equipment(
        actor=people["analyst"],
        asset_id="SYN-CHAMBER-25-60",
        description="Synthetic stability chamber 25 °C / 60 % RH",
        category="chamber",
        requires_qualification=False,
        reason="Synthetic equipment",
    )
    calibrate(people, chamber)
    pull = study.pulls.get(timepoint__interval_days=0)
    stability.record_pull(
        actor=people["receiver"],
        pull=pull,
        pulled_on=today(),
        quantity="5",
        quantity_unit="g",
        storage_location="Synthetic stability shelf",
        chamber=chamber,
        reason="Synthetic pull",
    )
    assessment = services.start(
        actor=people["author"],
        cause="equipment",
        equipment=chamber,
        title="Chamber humidity excursion",
        description="Synthetic: humidity above its limit for six hours",
        found_on=today(),
        period_from=today() - timedelta(days=1),
        period_until=today(),
    )
    found = {(item.kind, item.target_id): item.basis for item in assessment.items.all()}
    assert found[(KIND.STUDY, study.pk)] == "Pulls of this study were stored in SYN-CHAMBER-25-60."
    # A study names no lot record of its own here: the lot is not found through the chamber.
    assert (KIND.LOT, lot.pk) not in found


def test_the_lot_record_export_includes_its_impact_assessments(world):
    import json

    from reporting import lot_record
    from tests.test_lot_record_export import section, unpack

    world = released(world)
    used(world, world["tests"]["impurity"], world["balance"])
    assessment = begin(world)
    item = assessment.items.get(kind=KIND.LOT)
    services.place_hold(
        actor=world["people"]["author"], item=item, expected_revision=item.revision, reason="Hold"
    )
    decide_all(world, assessment)
    done = conclude(world, assessment)
    package = lot_record.export_lot_record(
        actor=world["people"]["approver"], lot_pk=world["lot"].pk, purpose="Synthetic review"
    )
    _, _, members = unpack(package)
    record = json.loads(members["record.json"])
    records = {r["id"] for r in section(record, "impact_records")["records"]}
    assert records == set(done.items.values_list("pk", flat=True))
    assert [r["id"] for r in section(record, "impact_assessments")["records"]] == [done.pk]
    holds = {r["id"] for r in section(record, "holds")["records"]}
    assert fresh(item).hold_id in holds
