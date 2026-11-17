"""Controlled replacement of a lot's requirements during testing, and the supersession of
approved versions that makes it necessary.

Uses the production adapters and service-created approvals only (synthetic data).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.models import AnalyticalTest, Observation
from catalog import services as catalog
from catalog.models import Method, Specification
from core.models import AuditEvent, ElectronicSignature, PINCredential, RuleSet
from core.services import approve_rule, save_rule
from quality import services as quality
from quality.models import Lot
from reporting import services as reporting
from sampling import services as sampling
from sampling.models import LotAssignment
from tests.test_integrated_journey import PIN, approve, dispose
from tests.test_result_types_journey import (
    assign_sample_tests,
    build_world,
    record,
    review,
    submit,
)

pytestmark = pytest.mark.django_db(transaction=True)

STATE = AnalyticalTest.State
READINGS = {
    "identity": "conforms",
    "salmonella": "absent",
    "tamc": "<10",
    "impurity": "4.20",
    "assay": "99.60",
}
REASON = "Change record CC-SYN-014: assay limits tightened"


@pytest.fixture
def world(django_user_model):
    """The mixed result-type world with an assay, plus a second quality person who authored
    nothing (the world's analyst also holds the quality and reviewer roles)."""
    data = build_world(django_user_model, with_assay=True)
    data["tests"] = assign_sample_tests(data)
    data["lot"].refresh_from_db()
    return data


def later(minutes=0):
    return timezone.now() + timedelta(minutes=minutes)


def new_specification_version(data, *, start=None, drop=(), add=(), approved=True, **limits):
    """Draft the next version of the world's specification, change the assay limits (and
    optionally drop or add lines), and have it approved unless ``approved`` is false.
    Returns the version."""
    people = data["people"]
    spec = Specification.objects.get(code="synthetic-rt-spec")
    revision = catalog.new_specification_revision(
        actor=people["author"],
        specification=spec,
        basis="Synthetic revised limits",
        effective_from=start or timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic revision",
    )
    method = Method.objects.get(code="synthetic-rt-method")
    for line in revision.tests.filter(code__in=["assay", *drop]):
        catalog.remove_test_line(actor=people["author"], line=line, reason="Revise the line")
    if "assay" not in drop:
        catalog.add_test_line(
            actor=people["author"],
            revision=revision,
            reason="Revised limits",
            code="assay",
            name="Assay",
            method=method,
            result_type="numeric",
            unit="%",
            lower_limit=Decimal(limits.get("low", "98.5")),
            upper_limit=Decimal(limits.get("high", "101.5")),
            reporting_decimals=2,
            required=True,
            replicates=1,
            max_retests=0,
        )
    for code in add:
        catalog.add_test_line(
            actor=people["author"],
            revision=revision,
            reason="New line",
            code=code,
            name=code.title(),
            method=method,
            result_type="numeric",
            unit="%",
            upper_limit=Decimal("0.5"),
            required=True,
            replicates=1,
            max_retests=0,
        )
    return approve(revision, people["approver"]) if approved else revision


def complete(data, *codes, reviewed=True):
    """Record, submit and (by default) review the named tests with conforming readings."""
    for code in codes:
        test = data["tests"][code]
        record(data, test, READINGS[code])
        submit(data, test)
        if reviewed:
            review(data, test)
        test.refresh_from_db()


def replace(data, who="approver", **changes):
    lot = Lot.objects.get(pk=data["lot"].pk)
    kwargs = {
        "actor": data["people"][who],
        "pin": PIN,
        "lot": lot,
        "expected_revision": lot.revision,
        "reason": REASON,
        "basis": sampling.replacement_preview(lot).basis,
    }
    kwargs.update(changes)
    return sampling.replace_requirements(**kwargs)


def states(data):
    return {
        (t.test_code, t.kind): t.state
        for t in AnalyticalTest.objects.filter(lot=data["lot"]).order_by("pk")
    }


def test_a_revised_specification_replaces_a_lots_requirements_during_testing(world):
    """Unchanged requirements carry their tests over; the changed one is superseded and
    repeated; everything stays in the record and the lot is released and certified."""
    people, lot = world["people"], world["lot"]
    complete(world, "identity", "salmonella", "assay")
    complete(world, "tamc", reviewed=False)
    first = sampling.current_assignment(lot)
    version_two = new_specification_version(world)

    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert preview.possible, (preview.blocker, preview.reasons)
    assert {row["code"]: row["change"] for row in preview.lines} == {
        "identity": "unchanged",
        "salmonella": "unchanged",
        "tamc": "unchanged",
        "impurity": "unchanged",
        "assay": "changed",
    }
    assert {row["test_code"]: row["effect"] for row in preview.tests} == {
        "identity": "carried",
        "salmonella": "carried",
        "tamc": "carried",
        "impurity": "carried",
        "assay": "superseded",
    }

    before = Lot.objects.get(pk=lot.pk).revision
    replaced = replace(world)
    assert replaced.revision == before + 1 and replaced.state == "quarantine"
    current = sampling.current_assignment(lot)
    assert current.origin == "replaced" and current.supersedes == first
    assert current.assigned_by == people["approver"] and current.reason == REASON
    assert current.specification_revision_id == version_two.pk
    assert current.plan_revision_id == first.plan_revision_id  # samples were taken under it
    assert current.payload["sampling_plan"] == first.payload["sampling_plan"]
    assert current.payload_hash != first.payload_hash
    evidence = current.replacement
    assert evidence["replaces"] == {"assignment": first.pk, "payload_hash": first.payload_hash}
    assert evidence["lot_revision"] == replaced.revision
    assert [r["label"] for r in evidence["tests"] if r["effect"] == "superseded"] == [
        world["tests"]["assay"].label
    ]
    first.refresh_from_db()
    assert first.origin == "assigned" and first.replacement is None  # untouched

    signature = ElectronicSignature.objects.get(object_type="quality.lot", object_id=str(lot.pk))
    assert signature.meaning == "requirements_replaced"
    assert signature.signer == people["approver"] and signature.revision == replaced.revision
    event = AuditEvent.objects.get(action="lot.requirements_replaced")
    assert event.object_id == str(current.pk) and event.reason == REASON
    assert event.after["tests_superseded"] == [world["tests"]["assay"].label]
    assert len(event.after["tests_carried"]) == 4

    assay = world["tests"]["assay"]
    assay.refresh_from_db()
    assert assay.state == STATE.SUPERSEDED
    assert assay.reportable_display == "99.60" and assay.conforms is True  # kept as recorded
    assert Observation.objects.filter(test=assay).count() == 1
    superseded = AuditEvent.objects.get(action="test.superseded")
    assert superseded.object_id == str(assay.pk) and superseded.before == {"state": "reviewed"}
    assert states(world)[("identity", "original")] == STATE.REVIEWED
    assert states(world)[("tamc", "original")] == STATE.SUBMITTED

    blockers = gates.lot_blockers(lot)
    assert any("no assay test under the lot's current requirements" in b for b in blockers)
    assert not any("identity" in b or "salmonella" in b for b in blockers)

    sample = assay.sample
    created, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Repeat superseded tests"
    )
    assert holds == [] and [t.test_code for t in created] == ["assay"]
    repeat = created[0]
    assert repeat.kind == "revised" and repeat.parent == assay and repeat.sample == sample
    assert repeat.spec.lower == Decimal("98.5") and repeat.spec.upper == Decimal("101.5")
    assert AnalyticalTest.objects.filter(lot=lot).count() == 6
    again, _ = analytical.assign_tests(actor=people["analyst"], sample=sample, reason="Again")
    assert again == []

    world["tests"]["assay"] = repeat
    complete(world, "assay", "impurity")
    review(world, world["tests"]["tamc"])
    assert gates.lot_blockers(lot) == []
    (notice,) = quality.disposition_notices(lot)
    assert "requirements were replaced during testing" in notice and REASON in notice
    assert f"not part of this evidence: {assay.label} assay." in notice

    released = dispose(world, people["approver"])
    assert released.state == "released"
    lab = released.disposition_evidence["analytical"]
    assert released.disposition_evidence["assignment_id"] == current.pk
    assert sorted(r["test_code"] for r in lab["results"]) == sorted(READINGS)
    assay_result = next(r for r in lab["results"] if r["test_code"] == "assay")
    assert assay_result["test"] == repeat.pk and assay_result["lower_limit"] == "98.5"
    assert {"test": assay.pk, "test_code": "assay", "kind": "original", "state": "superseded"} in (
        lab["excluded_tests"]
    )
    evidence, evidence_hash, blockers = reporting.preview(released)
    assert blockers == [], blockers
    report = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=released,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    html = render_to_string(
        "reporting/_certificate.html", {"snapshot": report.versions.get(number=1).snapshot}
    )
    flat = " ".join(html.split())
    assert "98.5" in flat and "101.5" in flat and "synthetic-rt-spec" in flat


def unchanged(data):
    """Nothing of a refused replacement is kept."""
    lot = data["lot"]
    return (
        LotAssignment.objects.filter(lot=lot).count() == 1
        and not ElectronicSignature.objects.filter(object_type="quality.lot").exists()
        and not AnalyticalTest.objects.filter(lot=lot, state=STATE.SUPERSEDED).exists()
        and not AuditEvent.objects.filter(action="lot.requirements_replaced").exists()
    )


def test_only_a_quality_person_who_authored_nothing_of_the_lot_replaces(world):
    people, lot = world["people"], world["lot"]
    complete(world, "assay")
    new_specification_version(world)
    # The world's analyst also holds the quality role, and received and tested the lot.
    assert sampling.replacement_denial(people["analyst"], lot) == sampling.SELF_REPLACEMENT
    assert sampling.replacement_denial(people["approver"], lot) == ""
    with pytest.raises(PermissionDenied, match="authored none of it"):
        replace(world, who="analyst")
    with pytest.raises(PermissionDenied, match="role"):
        replace(world, who="reviewer")
    assert unchanged(world)
    assert replace(world, who="author").rules_id == lot.rules_id  # reviewing is not authorship


def test_a_wrong_pin_or_a_stale_page_replaces_nothing(world):
    people = world["people"]
    complete(world, "assay")
    new_specification_version(world)
    with pytest.raises(ValidationError, match="PIN"):
        replace(world, pin="00000000")
    assert PINCredential.objects.get(user=people["approver"]).failures == 1
    assert AuditEvent.objects.filter(action="signature.denied", actor=people["approver"]).exists()
    lot = Lot.objects.get(pk=world["lot"].pk)
    with pytest.raises(ValidationError, match="Record changed"):
        replace(world, expected_revision=lot.revision - 1)
    with pytest.raises(ValidationError, match="reason"):
        replace(world, reason=" ")
    # The page was opened, then another version was approved: what was shown is not applied.
    shown = sampling.replacement_preview(lot).basis
    new_specification_version(world, low="98.6")
    with pytest.raises(ValidationError, match="changed after this page was opened"):
        replace(world, basis=shown)
    # The page was opened, then a result was recorded: the lot revision it showed is stale.
    shown = sampling.replacement_preview(lot)
    record(world, world["tests"]["impurity"], "4.20")
    with pytest.raises(ValidationError, match="Record changed"):
        replace(world, expected_revision=lot.revision, basis=shown.basis)
    assert unchanged(world)


def test_before_testing_starts_requirements_are_assigned_again_without_a_signature(
    django_user_model,
):
    data = build_world(django_user_model, with_assay=True)
    people, lot = data["people"], data["lot"]
    first = sampling.assign_requirements(
        actor=people["analyst"],
        lot=lot,
        material=data["material"],
        stage="incoming",
        reason="Assign approved synthetic policy",
    )
    version_two = new_specification_version(data)
    lot.refresh_from_db()
    assert sampling.replacement_preview(lot).blocker == sampling.NOT_STARTED
    with pytest.raises(ValidationError, match="Testing has not started"):
        replace(data, basis="")
    again = sampling.assign_requirements(
        actor=people["analyst"],
        lot=lot,
        material=data["material"],
        stage="incoming",
        reason="Specification revised before testing",
    )
    assert again.supersedes == first and again.origin == "assigned"
    assert again.specification_revision_id == version_two.pk


def test_once_testing_has_started_requirements_are_not_assigned_again(world):
    new_specification_version(world)
    with pytest.raises(ValidationError, match="Quality can replace them with a signature"):
        sampling.assign_requirements(
            actor=world["people"]["analyst"],
            lot=world["lot"],
            material=world["material"],
            stage="incoming",
            reason="Not this way",
        )
    assert unchanged(world)


def test_nothing_to_replace_while_the_frozen_versions_are_in_force(world):
    lot = Lot.objects.get(pk=world["lot"].pk)
    preview = sampling.replacement_preview(lot)
    assert preview.blocker == sampling.NOTHING_TO_REPLACE and not preview.possible
    with pytest.raises(ValidationError, match="nothing to replace"):
        replace(world, basis="")
    assert unchanged(world)


def test_a_released_lot_keeps_its_requirements(world):
    people = world["people"]
    complete(world, *READINGS)
    released = dispose(world, people["approver"])
    new_specification_version(world)
    assert "Only quarantined lots" in sampling.replacement_preview(released).blocker
    with pytest.raises(ValidationError, match="Only quarantined lots"):
        replace(world, basis="")
    assert LotAssignment.objects.filter(lot=released).count() == 1
    assert not AnalyticalTest.objects.filter(state=STATE.SUPERSEDED).exists()


def test_an_incomplete_resolution_refuses_and_records_no_hold(world):
    """A version in force that the rule set does not accept is a reason, never a hold put on
    a lot that is being tested."""
    complete(world, "assay")
    new_specification_version(world, drop=["impurity"])  # the rule set requires impurity
    lot = Lot.objects.get(pk=world["lot"].pk)
    preview = sampling.replacement_preview(lot)
    assert not preview.blocker and not preview.possible
    assert preview.reasons == ["Rule set requires tests missing from the specification: impurity"]
    with pytest.raises(ValidationError, match="missing from the specification: impurity"):
        replace(world, basis="")
    assert unchanged(world)
    assert sampling.current_assignment(lot).status == "ready"


def test_an_open_investigation_refuses_the_replacement(world):
    """A failing result is investigated against the requirement it was tested under: wider
    limits approved meanwhile do not make it disappear."""
    assay = world["tests"]["assay"]
    record(world, assay, "97.00")
    _, investigation = submit(world, assay)
    assert investigation is not None
    new_specification_version(world, low="96.0")
    lot = Lot.objects.get(pk=world["lot"].pk)
    preview = sampling.replacement_preview(lot)
    assert not preview.possible
    assert any(f"{investigation.label} is open on this lot" in r for r in preview.reasons)
    with pytest.raises(ValidationError, match="is open on this lot"):
        replace(world)
    assert unchanged(world)
    assay.refresh_from_db()
    assert assay.state == STATE.SUBMITTED and assay.conforms is False


def conclude_confirmed(data, investigation):
    people = data["people"]
    review(data, investigation.test)
    analytical.add_entry(
        actor=people["reviewer"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic laboratory assessment: no assignable cause found.",
    )
    investigation.refresh_from_db()
    return analytical.conclude(
        actor=people["approver"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="confirmed",
        assignable_cause="",
        reason="Synthetic conclusion: result confirmed",
    )


def test_a_confirmed_out_of_specification_result_still_blocks_after_a_replacement(world):
    people, lot = world["people"], world["lot"]
    assay = world["tests"]["assay"]
    record(world, assay, "97.00")
    _, investigation = submit(world, assay)
    conclude_confirmed(world, investigation)
    new_specification_version(world, low="96.0")
    replace(world, who="author")
    assay.refresh_from_db()
    assert assay.state == STATE.SUPERSEDED and assay.conforms is False
    repeat = analytical.assign_tests(
        actor=people["analyst"], sample=assay.sample, reason="Repeat superseded tests"
    )[0][0]
    world["tests"]["assay"] = repeat
    complete(world, *READINGS)
    assert gates.lot_blockers(lot) == [
        f"{investigation.label} confirmed an out-of-specification result."
    ]
    with pytest.raises(ValidationError, match="confirmed an out-of-specification result"):
        dispose(world, people["approver"])


def test_results_that_were_not_submitted_are_not_set_aside(world):
    """An open test with recorded results is completed against its own requirement first."""
    assay = world["tests"]["assay"]
    record(world, assay, "97.00")  # recorded, not submitted, and outside the old limits
    new_specification_version(world, low="96.0")
    lot = Lot.objects.get(pk=world["lot"].pk)
    preview = sampling.replacement_preview(lot)
    assert preview.reasons == [
        f"{assay.label} assay holds results or raw-data files that were not submitted, and its "
        "requirement would change. Complete and submit it first, or have quality record that it "
        "cannot be completed, so that what was recorded is evaluated against the requirement it "
        "was tested under."
    ]
    with pytest.raises(ValidationError, match="holds results or raw-data files that were not"):
        replace(world)
    assert unchanged(world)
    # An unchanged requirement's open test with results simply carries over.
    new_specification_version(world, low="98", high="102")  # the assay as it was frozen
    record(world, world["tests"]["impurity"], "4.20")
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert preview.possible and not preview.superseded
    replace(world)
    assay.refresh_from_db()
    assert assay.state == STATE.OPEN
    assert sampling.current_assignment(lot).origin == "replaced"


def test_a_superseded_test_takes_no_more_work_and_cannot_be_changed(world):
    people = world["people"]
    complete(world, "identity")
    complete(world, "assay", reviewed=False)
    untouched = world["tests"]["impurity"]
    new_specification_version(world)
    method = Method.objects.get(code="synthetic-rt-method")
    replace(world)
    assay = world["tests"]["assay"]
    assay.refresh_from_db()
    assert assay.state == STATE.SUPERSEDED and assay.submitted_by_id is not None
    with pytest.raises(ValidationError, match="not accepting observations"):
        record(world, assay, "99.70")
    with pytest.raises(ValidationError):
        analytical.review_test(
            actor=people["reviewer"],
            pin=PIN,
            test=assay,
            expected_revision=assay.revision,
            reason="Review a superseded test",
        )
    with pytest.raises(ValidationError):
        analytical.return_test(
            actor=people["reviewer"], test=assay, expected_revision=assay.revision, reason="Back"
        )
    for change in ({"state": "open"}, {"state": "reviewed"}, {"conforms": False}):
        with pytest.raises(DatabaseError, match="Superseded tests are immutable"):
            with transaction.atomic():
                AnalyticalTest.objects.filter(pk=assay.pk).update(**change)
    with pytest.raises(DatabaseError, match="cannot be deleted"):
        with transaction.atomic():
            AnalyticalTest.objects.filter(pk=untouched.pk).delete()
    # Superseding changes the state and the record revision only, whatever the state was.
    with pytest.raises(DatabaseError, match="keeps everything recorded on it"):
        with transaction.atomic():
            AnalyticalTest.objects.filter(pk=untouched.pk).update(
                state="superseded", test_code="other"
            )
    reviewed = world["tests"]["identity"]
    with pytest.raises(DatabaseError, match="keeps everything recorded on it"):
        with transaction.atomic():
            AnalyticalTest.objects.filter(pk=reviewed.pk).update(state="superseded", conforms=False)
    assert method.revisions.count() == 1


def test_a_revised_method_supersedes_every_test_that_uses_it(world):
    people = world["people"]
    complete(world, "identity")
    method = Method.objects.get(code="synthetic-rt-method")
    revision = catalog.new_method_revision(
        actor=people["author"],
        method=method,
        technique="Gravimetry",
        document_ref="SOP-SYN-RT rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-RT rev 2",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic method revision",
    )
    approve(revision, people["approver"])
    lot = Lot.objects.get(pk=world["lot"].pk)
    preview = sampling.replacement_preview(lot)
    assert preview.possible
    assert {row["change"] for row in preview.lines} == {"changed"}
    assert all("method synthetic-rt-method v2" in row["after"] for row in preview.lines)
    assert {row["effect"] for row in preview.tests} == {"superseded"}
    replace(world)
    current = sampling.current_assignment(lot)
    # The specification version is the same; only the method version it resolves to changed.
    assert current.specification_revision_id == world["spec"].pk
    assert {t["method"]["version"] for t in current.payload["tests"]} == {2}
    assert set(states(world).values()) == {STATE.SUPERSEDED}
    created, _ = analytical.assign_tests(
        actor=people["analyst"], sample=world["tests"]["assay"].sample, reason="Repeat all"
    )
    assert sorted(t.test_code for t in created) == sorted(READINGS)
    assert {t.kind for t in created} == {"revised"}
    assert {t.spec.method.revision for t in created} == {2}


def test_added_and_dropped_requirements(world):
    """A line the new version adds gets a test when tests are assigned; a line it drops has
    its tests superseded as no longer required."""
    people, lot = world["people"], world["lot"]
    new_specification_version(world, low="98", high="102", add=["water"])
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert {r["code"]: r["change"] for r in preview.lines}["water"] == "added"
    assert not preview.superseded
    replace(world)
    sample = world["tests"]["assay"].sample
    created, _ = analytical.assign_tests(actor=people["analyst"], sample=sample, reason="Water")
    assert [(t.test_code, t.kind) for t in created] == [("water", "original")]
    water = created[0]
    analytical.record_observation(
        actor=people["analyst"],
        test=water,
        value=Decimal("0.2"),
        raw_reference="RAW-SYN-W rev 1",
        reason="Synthetic original observation",
    )
    water.refresh_from_db()
    submit(world, water)
    new_specification_version(world, low="98", high="102", drop=["water"])
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert {r["code"]: r["change"] for r in preview.lines}["water"] == "removed"
    assert [(r["test_code"], r["why"]) for r in preview.superseded] == [("water", "not_required")]
    replace(world, who="author")
    water.refresh_from_db()
    assert water.state == STATE.SUPERSEDED
    again, _ = analytical.assign_tests(actor=people["analyst"], sample=sample, reason="Again")
    assert again == []
    assert not any("water" in b for b in gates.lot_blockers(lot))
    assert LotAssignment.objects.filter(lot=lot, origin="replaced").count() == 2


def new_rule_version(data, *, required=None, start=None):
    people = data["people"]
    current = Lot.objects.get(pk=data["lot"].pk).rules
    draft = save_rule(
        actor=people["author"],
        code=current.code,
        segment=current.segment,
        policy={**current.policy, "required_tests": required or current.policy["required_tests"]},
        effective_from=start or timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic rule revision",
    )
    return approve_rule(
        actor=people["approver"],
        pin=PIN,
        rule=draft,
        expected_revision=draft.revision,
        reason="Independent synthetic policy review",
    )


def test_a_superseded_rule_version_holds_the_lot_until_its_requirements_are_replaced(world):
    """The lot follows the version of its own rule set in force; every test carries over."""
    people, lot = world["people"], world["lot"]
    complete(world, "identity", "salmonella", "tamc", "impurity")
    complete(world, "assay", reviewed=False)
    first = Lot.objects.get(pk=lot.pk).rules
    second = new_rule_version(world)
    first.refresh_from_db()
    assert first.superseded_by == second and first.superseded_from <= timezone.now()
    with pytest.raises(ValidationError, match="approved, effective rule"):
        analytical.assign_tests(
            actor=people["analyst"], sample=world["tests"]["assay"].sample, reason="More tests"
        )
    with pytest.raises(ValidationError, match="approved, effective rule"):
        dispose(world, people["approver"])
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert preview.possible and preview.rules == second
    assert {row["change"] for row in preview.lines} == {"unchanged"}
    assert not preview.superseded and len(preview.carried) == 5
    replaced = replace(world)
    assert replaced.rules == second
    assert sampling.current_assignment(lot).payload["rules"]["version"] == 2
    assert sampling.current_assignment(lot).replacement["rules"] == {
        "before": {"id": first.pk, "label": str(first)},
        "after": {"id": second.pk, "label": str(second)},
    }
    review(world, world["tests"]["assay"])
    assert dispose(world, people["approver"]).state == "released"


def test_a_retired_rule_version_never_strands_an_investigation(world):
    """A failing result is reviewed and its investigation concluded under the rule version the
    lot has, in force or not; only then are the requirements replaced. Without this a rule
    version approved during an investigation left the lot with no legal move."""
    lot = world["lot"]
    assay = world["tests"]["assay"]
    record(world, assay, "97.00")
    _, investigation = submit(world, assay)
    second = new_rule_version(world)
    # The replacement waits for the investigation; the investigation does not wait for it.
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert any("is open on this lot" in reason for reason in preview.reasons)
    concluded = conclude_confirmed(world, investigation)  # reviews the failing result first
    assert concluded.phase == "closed"
    assay.refresh_from_db()
    assert assay.state == STATE.REVIEWED and assay.conforms is False
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert preview.possible and preview.rules == second and len(preview.carried) == 5
    assert replace(world, who="author").rules == second
    # The confirmed result still blocks the lot, under whatever rule version.
    assert f"{investigation.label} confirmed an out-of-specification result." in (
        gates.lot_blockers(lot)
    )


def test_database_keeps_a_lot_on_its_own_rule_set(world):
    lot = world["lot"]
    other = RuleSet.objects.create(
        code="synthetic-other-rules",
        segment="chemical",
        author=world["people"]["author"],
        status="approved",
        effective_from=timezone.now() - timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=30),
        policy=lot.rules.policy,
    )
    draft = save_rule(
        actor=world["people"]["author"],
        code=lot.rules.code,
        segment=lot.rules.segment,
        policy=lot.rules.policy,
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=30),
        reason="Synthetic draft",
    )
    for rules in (other, draft):
        with pytest.raises(DatabaseError, match="A lot keeps its rule set"):
            with transaction.atomic():
                Lot.objects.filter(pk=lot.pk).update(rules=rules)
    with pytest.raises(DatabaseError, match="Lot identity"):
        with transaction.atomic():
            Lot.objects.filter(pk=lot.pk).update(material="Another material")


def test_database_refuses_a_replacement_without_its_evidence(world):
    lot = world["lot"]
    current = sampling.current_assignment(lot)
    fields = {
        "lot": lot,
        "material": current.material,
        "stage": current.stage,
        "scope": current.scope,
        "status": "ready",
        "payload": current.payload,
        "payload_hash": current.payload_hash,
        "specification_revision": current.specification_revision,
        "plan_revision": current.plan_revision,
        "reason": "Synthetic",
        "assigned_by": world["people"]["approver"],
    }
    for bad in (
        {"origin": "replaced", "supersedes": current},  # no evidence
        {"origin": "replaced", "replacement": {"schema": "x"}},  # replaces nothing
        {"origin": "assigned", "supersedes": current, "replacement": {"schema": "x"}},
    ):
        with pytest.raises(DatabaseError, match="lot_assignment_origin"):
            with transaction.atomic():
                LotAssignment.objects.create(**fields, **bad)
    with pytest.raises(DatabaseError, match="Historical evidence"):
        with transaction.atomic():
            LotAssignment.objects.filter(pk=current.pk).update(origin="replaced")


@pytest.mark.parametrize("first", ["replacement", "observation"])
def test_a_replacement_and_an_observation_at_once(world, monkeypatch, first):
    """Both lock the test before the lot: exactly one stands, and neither deadlocks."""
    from analytical import services as testing
    from laboratory.tests.helpers import run_interleaved

    assay = world["tests"]["assay"]
    new_specification_version(world)
    lot = Lot.objects.get(pk=world["lot"].pk)
    shown = sampling.replacement_preview(lot).basis  # the page was opened before either

    def sign():
        return replace(world, expected_revision=lot.revision, basis=shown)

    def observe():
        return record(world, assay, "99.60")

    if first == "replacement":
        # Reached once the replacement holds the tests and the lot and has passed its checks.
        outcome = run_interleaved(monkeypatch, sampling, "replacement_denial", sign, observe)
    else:
        outcome = run_interleaved(monkeypatch, testing, "_touch", observe, sign)
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    assay.refresh_from_db()
    replaced = LotAssignment.objects.filter(lot=lot, origin="replaced").count()
    observations = Observation.objects.filter(test=assay).count()
    assert (replaced, observations) == ((1, 0) if first == "replacement" else (0, 1))
    assert assay.state == (STATE.SUPERSEDED if first == "replacement" else STATE.OPEN)


def test_a_test_assigned_while_the_replacement_waits_makes_it_stale(world, monkeypatch):
    """A test created after the lot's tests were locked is not locked out of order: the
    replacement is refused, first because it is not what the signer was shown and, were that
    the same, because the test was never locked."""
    from analytical import replacement

    people = world["people"]
    new_specification_version(world, add=["water"])
    replace(world)  # the lot now requires water, and no sample has a water test yet
    new_specification_version(world, low="98.7")
    lot = Lot.objects.get(pk=world["lot"].pk)
    sample = world["tests"]["assay"].sample
    real = replacement.lock

    def lock_then_assign(lot):
        held = real(lot)
        # Another analyst's request commits between the two locks (simulated in line: the
        # lot row is not locked yet).
        AnalyticalTest.objects.create(
            lot=lot,
            sample=sample,
            test_code="water",
            requirement=sampling.test_requirements(lot)["water"],
            requirement_hash="0" * 64,
            created_by=people["analyst"],
        )
        return held

    monkeypatch.setattr(replacement, "lock", lock_then_assign)
    before = LotAssignment.objects.filter(lot=lot).count()
    superseded = AnalyticalTest.objects.filter(lot=lot, state=STATE.SUPERSEDED).count()
    with pytest.raises(ValidationError, match="lot's tests changed after this page was opened"):
        replace(world, who="author")
    assert LotAssignment.objects.filter(lot=lot).count() == before
    assert not AnalyticalTest.objects.filter(lot=lot, test_code="water").exists()  # rolled back
    monkeypatch.setattr(replacement, "lock", real)
    requirements = sampling.replacement_preview(lot).requirements
    with transaction.atomic():
        held = real(lot)
        with pytest.raises(ValidationError, match="tests changed after the replacement was"):
            replacement.apply(
                actor=people["author"],
                lot=lot,
                requirements=requirements,
                reason="Synthetic",
                locked=held[:-1],
            )
    assert AnalyticalTest.objects.filter(lot=lot, state=STATE.SUPERSEDED).count() == superseded


def test_an_accepted_supplier_result_stops_standing_when_the_requirements_are_replaced(
    django_user_model,
):
    """An acceptance was signed against the requirements being replaced: it is named before
    the signature and blocks the disposition afterwards, until it is withdrawn."""
    from tests.test_supplier_reliance import (
        accept,
        build_reliance_world,
        certify,
        fully_stated,
        propose,
        qualify,
        sampled_tests,
    )

    data = build_reliance_world(django_user_model)
    lot = data["lot"]
    qualify(data)
    certificate = certify(data, fully_stated(), lot=lot)
    data["tests"] = sampled_tests(data)
    acceptance = accept(data, propose(data, certificate))
    complete(data, "identity")
    assert not any(acceptance.label in b for b in gates.lot_blockers(lot))
    new_specification_version(data, drop=[], low="98", high="102", add=["water"])
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert preview.possible
    assert preview.supplier_results == [{"test_code": "assay", "label": acceptance.label}]
    replace(data, who="quality")
    acceptance.refresh_from_db()
    assert acceptance.state == "accepted"  # nothing rewritten
    blockers = gates.lot_blockers(lot)
    assert any(acceptance.label in b for b in blockers), blockers
    # The laboratory test left untouched for the accepted result carried over, still open.
    assert data["tests"]["assay"].__class__.objects.get(pk=data["tests"]["assay"].pk).state == (
        STATE.OPEN
    )


def test_a_new_sampling_plan_version_retires_the_old_one_and_the_lot_keeps_its_plan(world):
    """Samples were taken under the frozen plan: a replacement keeps it."""
    from sampling.models import SamplingPlan, SamplingPlanRevision

    people, lot = world["people"], world["lot"]
    plan = SamplingPlan.objects.get(code="synthetic-rt-plan")
    first = plan.revisions.get(version=1)
    draft = sampling.new_plan_revision(
        actor=people["author"],
        plan=plan,
        basis="fixed",
        parameter=Decimal("2"),
        minimum_quantity=Decimal("20"),
        quantity_unit="g",
        instructions="Take two identified samples.",
        rationale="Synthetic revised plan",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic plan revision",
    )
    second = approve(draft, people["approver"])
    first.refresh_from_db()
    assert first.superseded_by == second and first.superseded_from is not None
    assert catalog.effective_revision(SamplingPlanRevision, plan, timezone.now()) == second
    event = AuditEvent.objects.get(action="revision.superseded")
    assert (event.object_type, event.object_id) == ("sampling.samplingplanrevision", str(first.pk))
    # A revised plan alone is nothing to replace for a lot already sampled.
    assert sampling.replacement_preview(Lot.objects.get(pk=lot.pk)).blocker == (
        sampling.NOTHING_TO_REPLACE
    )
    new_specification_version(world)
    replace(world)
    current = sampling.current_assignment(lot)
    assert current.plan_revision == first and current.payload["sampling_plan"]["version"] == 1
    assert sampling.lot_blockers(lot) == []
    with pytest.raises(DatabaseError, match="Approved or withdrawn revisions are immutable"):
        with transaction.atomic():
            SamplingPlanRevision.objects.filter(pk=first.pk).update(superseded_from=None)


def test_before_testing_a_lot_moves_to_its_rule_version_in_force_by_assignment(
    django_user_model,
):
    """A lot received under a rule version that was retired before any test exists is not
    stranded: assigning its requirements again applies the version in force."""
    data = build_world(django_user_model, with_assay=True)
    people, lot = data["people"], data["lot"]
    first = lot.rules
    assign = {
        "actor": people["analyst"],
        "lot": lot,
        "material": data["material"],
        "stage": "incoming",
        "reason": "Assign approved synthetic policy",
    }
    assert sampling.assign_requirements(**assign).payload["rules"]["id"] == first.pk
    second = new_rule_version(data)
    lot.refresh_from_db()
    before = lot.revision
    again = sampling.assign_requirements(**assign)
    lot.refresh_from_db()
    assert again.status == "ready" and again.payload["rules"]["id"] == second.pk
    assert lot.rules == second and lot.revision == before + 1
    event = AuditEvent.objects.filter(action="lot.requirements_assigned").order_by("-occurred_at")[
        0
    ]
    assert event.before["rules"] == first.pk and event.after["rules"] == second.pk
    data["tests"] = assign_sample_tests(data)  # assigning and testing proceed under it
    assert set(data["tests"]) == set(READINGS)


def test_a_hold_does_not_move_the_lot_to_another_rule_version(django_user_model):
    data = build_world(django_user_model, with_assay=True)
    people, lot = data["people"], data["lot"]
    first = lot.rules
    new_rule_version(data, required=[*first.policy["required_tests"], "water"])
    held = sampling.assign_requirements(
        actor=people["analyst"],
        lot=lot,
        material=data["material"],
        stage="incoming",
        reason="Assign approved synthetic policy",
    )
    lot.refresh_from_db()
    assert held.status == "hold"
    assert held.hold_reasons == ["Rule set requires tests missing from the specification: water"]
    assert lot.rules == first


def test_a_second_replacement_supersedes_the_repeat_and_links_the_next_one(world):
    people, lot = world["people"], world["lot"]
    assay = world["tests"]["assay"]
    complete(world, "assay")
    new_specification_version(world)
    replace(world)
    first_repeat = analytical.assign_tests(
        actor=people["analyst"], sample=assay.sample, reason="Repeat superseded tests"
    )[0][0]
    new_specification_version(world, low="98.7")
    replace(world, who="author")
    first_repeat.refresh_from_db()
    assert first_repeat.state == STATE.SUPERSEDED  # open and untouched: nothing to set aside
    created, _ = analytical.assign_tests(
        actor=people["analyst"], sample=assay.sample, reason="Repeat superseded tests"
    )
    assert [(t.kind, t.parent_id) for t in created] == [("revised", first_repeat.pk)]
    assert created[0].spec.lower == Decimal("98.7")
    assert AnalyticalTest.objects.filter(lot=lot, test_code="assay").count() == 3
    world["tests"]["assay"] = created[0]
    complete(world, *READINGS)
    assert gates.lot_blockers(lot) == []
    evidence = dispose(world, people["approver"]).disposition_evidence["analytical"]
    assert [r["test"] for r in evidence["results"] if r["test_code"] == "assay"] == [created[0].pk]
    assert sorted(t["test"] for t in evidence["excluded_tests"]) == [assay.pk, first_repeat.pk]
    assert len(quality.disposition_notices(lot)) == 2


def test_raw_data_files_that_were_not_submitted_are_not_set_aside(world):
    """A raw-data file is laboratory work, as it is for a supplier's result: an open test that
    holds one is completed against its own requirement before that requirement is replaced."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from analytical.models import RawDataFile
    from analytical.rawdata import attach_raw_file

    lot, assay = world["lot"], world["tests"]["assay"]
    attach_raw_file(
        actor=world["people"]["analyst"],
        test=assay,
        upload=SimpleUploadedFile("assay-run-1.csv", b"replicate,value\n1,97.10\n", "text/csv"),
        description="Synthetic instrument export of the assay run",
    )
    assert gates.tested_here(lot, "assay")
    new_specification_version(world, low="97.0", high="103.0")  # wider limits
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    row = next(r for r in preview.tests if r["test_code"] == "assay")
    assert row["effect"] == "superseded" and row["has_results"] is True
    assert not preview.possible
    assert "holds results or raw-data files that were not submitted" in preview.reasons[0]
    with pytest.raises(ValidationError, match="raw-data files that were not submitted"):
        replace(world)
    assert unchanged(world)
    assert RawDataFile.objects.filter(test=assay).count() == 1


def test_assigning_tests_and_a_second_replacement_at_once_do_not_deadlock(world, monkeypatch):
    """Assigning a repeat links it to the superseded test it follows, so it takes the lot's
    tests before the lot, the order the replacement uses. Whichever comes first, the other
    waits and then finds the record changed; neither is aborted by a lock cycle."""
    import threading

    from django.db import connection

    people = world["people"]
    assay = world["tests"]["assay"]
    new_specification_version(world)
    replace(world)  # the assay test is superseded and not yet repeated
    new_specification_version(world, low="98.7")
    lot = Lot.objects.get(pk=world["lot"].pk)
    shown = sampling.replacement_preview(lot).basis
    tests_locked, assigning = threading.Event(), threading.Event()
    real_testing = sampling._testing()

    class Paused:
        """The replacement holds the lot's tests and pauses before it takes the lot."""

        def effects(self, *args, **kwargs):
            return real_testing.effects(*args, **kwargs)

        def apply(self, **kwargs):
            return real_testing.apply(**kwargs)

        def lock(self, the_lot):
            held = real_testing.lock(the_lot)
            tests_locked.set()
            assigning.wait(10)
            threading.Event().wait(0.5)  # let the assignment queue on the tests
            return held

    monkeypatch.setattr(sampling, "_testing", lambda: Paused())
    outcomes = {}

    def replacement():
        try:
            outcomes["replace"] = sampling.replace_requirements(
                actor=people["author"],
                pin=PIN,
                lot=lot,
                expected_revision=lot.revision,
                reason=REASON,
                basis=shown,
            )
        except Exception as exc:  # reported to the asserting test
            outcomes["replace"] = exc
        finally:
            connection.close()

    def assignment():
        tests_locked.wait(10)
        assigning.set()
        try:
            outcomes["assign"] = analytical.assign_tests(
                actor=people["analyst"], sample=assay.sample, reason="Repeat superseded tests"
            )
        except Exception as exc:  # reported to the asserting test
            outcomes["assign"] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=replacement), threading.Thread(target=assignment)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any("deadlock" in str(outcome) for outcome in outcomes.values()), outcomes
    assert isinstance(outcomes["replace"], Lot), outcomes
    created, holds = outcomes["assign"]  # the assignment waited and ran after the replacement
    assert holds == [] and [(t.test_code, t.kind) for t in created] == [("assay", "revised")]
    assert created[0].spec.lower == Decimal("98.7") and created[0].parent == assay


def test_the_disposition_signer_is_told_when_newer_versions_are_in_force(world):
    """A lot keeps its frozen versions unless quality replaces them: the signer of its
    disposition sees that a later version exists."""
    people, lot = world["people"], world["lot"]
    complete(world, *READINGS)
    assert quality.disposition_notices(lot) == []
    new_specification_version(world)
    (notice,) = quality.disposition_notices(lot)
    assert notice == (
        "The versions in force now are not the ones frozen for this lot: specification "
        "synthetic-rt-spec v2, 1 requirement changed. The lot is dispositioned against its "
        "frozen requirements unless quality replaces them first. This does not block the "
        "disposition."
    )
    released = dispose(world, people["approver"])
    assert released.state == "released"
    assert sampling.newer_versions(released) is None
    assert quality.disposition_notices(released) == []
