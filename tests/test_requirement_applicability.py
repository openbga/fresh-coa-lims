"""Several sets of requirements on one lot: scopes, additional rule sets, and the signed
decision where the specifications that apply state a test differently.

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
from analytical.models import AnalyticalTest
from catalog import services as catalog
from catalog.models import Method, Specification
from core.models import AuditEvent, ElectronicSignature, RuleSet
from core.services import approve_rule, save_rule, validate_policy
from quality import services as quality
from quality.forms import LotForm
from quality.models import Lot
from reporting import services as reporting
from reporting.evidence import iso
from sampling import services as sampling
from sampling.models import LotAssignment
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import PIN, approve, dispose
from tests.test_result_types_journey import build_world, record, review, submit

pytestmark = pytest.mark.django_db(transaction=True)

STATE = AnalyticalTest.State
REASON = "A result within 99 to 101 % also meets the general limits; agreement QA-SYN-7"
READINGS = {
    "identity": "conforms",
    "salmonella": "absent",
    "tamc": "<10",
    "impurity": "4.20",
    "assay": "99.60",
    "water": "0.20",
}
ASSAY = {
    "code": "assay",
    "name": "Assay",
    "result_type": "numeric",
    "unit": "%",
    "lower_limit": Decimal("98"),
    "upper_limit": Decimal("102"),
    "reporting_decimals": 2,
}
TIGHT = {**ASSAY, "lower_limit": Decimal("99"), "upper_limit": Decimal("101")}
WATER = {
    "code": "water",
    "name": "Water",
    "result_type": "numeric",
    "unit": "%",
    "upper_limit": Decimal("0.5"),
    "reporting_decimals": 2,
}
POLICY = {"review_meaning": "reviewed", "disposition_meaning": "approved"}
CONFLICT = (
    "Specifications synthetic-rt-spec v1 (general) and synthetic-rt-eu-market v1 (eu-market) "
    "state different requirements for assay. Quality decides which one applies to this lot."
)


@pytest.fixture
def world(django_user_model):
    """A lot received by an analyst who also holds the quality role, a general specification
    with an assay of 98 to 102 %, and two quality people who recorded nothing of the lot."""
    return build_world(django_user_model, with_assay=True)


def _lines(data, revision, lines):
    method = Method.objects.get(code="synthetic-rt-method")
    for line in lines:
        catalog.add_test_line(
            actor=data["people"]["author"],
            revision=revision,
            reason="Synthetic line",
            method=method,
            **{"required": True, "replicates": 1, "max_retests": 0, **line},
        )


def overlay(data, scope, *lines, approved=True):
    """A specification of the world's material for a market or customer scope."""
    _, revision = catalog.create_specification(
        actor=data["people"]["author"],
        code=f"synthetic-rt-{scope}",
        title=f"Synthetic {scope} specification",
        material=data["material"],
        stage="incoming",
        scope=scope,
        basis="Synthetic overlay limits",
        effective_from=timezone.now() - timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=365),
        reason="Synthetic overlay",
    )
    _lines(data, revision, lines)
    return approve(revision, data["people"]["approver"]) if approved else revision


def revise(data, code, *lines):
    """Approve the next version of a specification with exactly these lines changed in."""
    people = data["people"]
    revision = catalog.new_specification_revision(
        actor=people["author"],
        specification=Specification.objects.get(code=code),
        basis="Synthetic revised limits",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic revision",
    )
    for line in revision.tests.filter(code__in=[line["code"] for line in lines]):
        catalog.remove_test_line(actor=people["author"], line=line, reason="Revise the line")
    _lines(data, revision, lines)
    return approve(revision, people["approver"])


def extra_rules(data, code, where, required, *, approved=True, **policy):
    """A rule set that applies in addition to a lot's own."""
    people = data["people"]
    rule = save_rule(
        actor=people["author"],
        code=code,
        segment="chemical",
        policy=POLICY | {"required_tests": list(required), "applies_to": where} | policy,
        effective_from=timezone.now() - timedelta(minutes=5),
        effective_until=timezone.now() + timedelta(days=365),
        reason="Synthetic additional policy",
    )
    if not approved:
        return rule
    return approve_rule(
        actor=people["approver"],
        pin=PIN,
        rule=rule,
        expected_revision=rule.revision,
        reason="Independent synthetic policy review",
    )


def assign(data, *scopes, who="analyst"):
    return sampling.assign_requirements(
        actor=data["people"][who],
        lot=data["lot"],
        material=data["material"],
        stage="incoming",
        reason="Assign approved synthetic policy",
        scopes=list(scopes) or None,
    )


def lot_of(data):
    return Lot.objects.get(pk=data["lot"].pk)


def decide(data, who="approver", **changes):
    lot = lot_of(data)
    kwargs = {
        "actor": data["people"][who],
        "pin": PIN,
        "lot": lot,
        "expected_revision": lot.revision,
        "reason": REASON,
        "choices": {"assay": "eu-market"},
        "basis": sampling.decision_preview(lot).basis,
    }
    kwargs.update(changes)
    return sampling.decide_conflicts(**kwargs)


def replace(data, who="approver", choices=None, **changes):
    lot = lot_of(data)
    kwargs = {
        "actor": data["people"][who],
        "pin": PIN,
        "lot": lot,
        "expected_revision": lot.revision,
        "reason": "Change record CC-SYN-021",
        "basis": sampling.replacement_preview(lot, choices=choices).basis,
        "choices": choices,
    }
    kwargs.update(changes)
    return sampling.replace_requirements(**kwargs)


def sample_and_tests(data):
    analyst = data["people"]["analyst"]
    sample = sampling.record_sampling(
        actor=analyst,
        lot=data["lot"],
        reference="SYN-RT-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    data["sample"] = sample
    return assign_tests(data)


def assign_tests(data):
    tests, holds = analytical.assign_tests(
        actor=data["people"]["analyst"], sample=data["sample"], reason="Assign required tests"
    )
    assert holds == [], holds
    return {t.test_code: t for t in tests}


def complete(data, tests):
    for code, test in tests.items():
        record(data, test, READINGS[code])
        submit(data, test)
        review(data, test)


def conflicting(data):
    """The lot assigned under the general scope and a market scope whose specification
    states the assay more tightly: held for a decision."""
    overlay(data, "eu-market", TIGHT)
    held = assign(data, "general", "eu-market")
    assert held.status == "hold", held.hold_reasons
    return held


def refused(call, text, kind=ValidationError):
    with pytest.raises(kind) as caught:
        call()
    found = (
        caught.value.messages if isinstance(caught.value, ValidationError) else [str(caught.value)]
    )
    assert any(text in message for message in found), found


# One scope, as before ----------------------------------------------------------------------


def test_one_scope_freezes_the_requirements_it_always_did(world):
    assignment = assign(world)
    payload = assignment.payload
    assert assignment.status == "ready" and assignment.origin == "assigned"
    assert payload["schema"] == "oq.requirements/1"
    assert not {"scopes", "specifications", "additional_rules", "decisions"} & set(payload)
    assert all("sources" not in line for line in payload["tests"])
    assert (assignment.scope, assignment.scopes, assignment.scope_list) == (
        "general",
        ["general"],
        ["general"],
    )
    spec = world["spec"]
    source = sampling.test_requirements(world["lot"])["assay"]["source"]
    assert source == (
        f"catalog:synthetic-rt-spec@v1#rev{spec.pk}/lot-req:{assignment.payload_hash[:16]}"
    )
    assert sampling.applied_rules(lot_of(world)) == [world["lot"].rules]
    # A row written before several scopes could be named reads as its one scope.
    assert LotAssignment(scope="eu-market").scope_list == ["eu-market"]


def test_scopes_are_named_once_general_first_and_as_slugs(world):
    assert sampling.clean_scopes(["eu-market", "general", "eu-market"]) == [
        "general",
        "eu-market",
    ]
    assert sampling.clean_scopes([" cust-a ", "b2"]) == ["b2", "cust-a"]
    for bad in ([], ["eu market"], ["x" * 61], [f"s{i}" for i in range(13)], ["général"]):
        with pytest.raises(ValidationError):
            sampling.clean_scopes(bad)
    with pytest.raises(ValidationError):
        assign(world, "eu market")
    assert not LotAssignment.objects.filter(lot=world["lot"]).exists()


# Several scopes ----------------------------------------------------------------------------


def test_every_specification_named_applies_and_a_line_stated_alike_counts_once(world):
    eu = overlay(world, "eu-market", ASSAY, WATER)
    assignment = assign(world, "eu-market", "general")
    assert assignment.status == "ready", assignment.hold_reasons
    payload = assignment.payload
    assert payload["schema"] == "oq.requirements/2"
    assert payload["scopes"] == ["general", "eu-market"] == assignment.scopes
    assert assignment.scope == "general"
    assert [(s["scope"], s["code"], s["version"]) for s in payload["specifications"]] == [
        ("general", "synthetic-rt-spec", 1),
        ("eu-market", "synthetic-rt-eu-market", 1),
    ]
    # The first specification stays where readers of one specification look for it.
    assert payload["specification"]["revision_id"] == world["spec"].pk
    assert assignment.specification_revision_id == world["spec"].pk
    sources = {line["code"]: line["sources"] for line in payload["tests"]}
    assert sources == {
        "identity": ["general"],
        "salmonella": ["general"],
        "tamc": ["general"],
        "impurity": ["general"],
        "assay": ["general", "eu-market"],
        "water": ["eu-market"],
    }
    assert payload["decisions"] == [] and payload["additional_rules"] == []
    required = sampling.test_requirements(world["lot"])
    assert set(required) == set(sources)
    assert required["water"]["source"].startswith(f"catalog:synthetic-rt-eu-market@v1#rev{eu.pk}/")
    assert required["assay"]["source"].startswith("catalog:synthetic-rt-spec@v1#")
    tests = sample_and_tests(world)
    assert set(tests) == set(sources)
    event = AuditEvent.objects.get(action="lot.requirements_assigned", object_id=assignment.pk)
    assert event.after["scopes"] == ["general", "eu-market"]


def test_a_scope_with_nothing_configured_holds_the_lot(world):
    held = assign(world, "general", "us-market")
    assert held.status == "hold" and held.scopes == ["general", "us-market"]
    assert held.hold_reasons == [
        "No specification exists for synthetic-rt-material at stage incoming and scope us-market."
    ]
    # Nothing a quality decision could settle: the configuration is incomplete.
    preview = sampling.decision_preview(lot_of(world))
    assert preview.blocker == sampling.NO_CONFLICT


def test_specifications_that_state_a_test_differently_hold_the_lot(world):
    held = conflicting(world)
    assert held.hold_reasons == [CONFLICT]
    assert held.payload is None and held.origin == "assigned"
    event = AuditEvent.objects.get(action="lot.requirements_held", object_id=held.pk)
    assert event.after["conflicts"] == ["assay"]
    lot = lot_of(world)
    assert sampling.lot_blockers(lot) == [f"Applicability hold: {CONFLICT}"]
    refused(
        lambda: sampling.record_sampling(
            actor=world["people"]["analyst"],
            lot=lot,
            reference="SYN-RT-S009",
            sampled_at=timezone.now(),
            containers_total=1,
            containers_sampled=1,
            container_ids="SYN-C001",
            quantity=Decimal("10"),
            quantity_unit="g",
            location="Synthetic sampling booth",
            reason="Synthetic controlled sampling",
        ),
        "state different requirements for assay",
    )
    preview = sampling.decision_preview(lot)
    assert preview.possible and preview.reasons == []
    (conflict,) = preview.conflicts
    assert conflict["code"] == "assay" and conflict["reason"] == CONFLICT
    assert [
        (c["scope"], c["scopes"], c["specification"]["code"], c["text"])
        for c in conflict["candidates"]
    ] == [
        (
            "general",
            ["general"],
            "synthetic-rt-spec",
            "98 – 102 % · rounded to 2 decimals · method synthetic-rt-method v1",
        ),
        (
            "eu-market",
            ["eu-market"],
            "synthetic-rt-eu-market",
            "99 – 101 % · rounded to 2 decimals · method synthetic-rt-method v1",
        ),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"reporting_decimals": 1},
        {"replicates": 2},
        {"required": False},
        {"name": "Assay by titration"},
        {"upper_inclusive": False},
        {"max_retests": 1},
    ],
)
def test_any_difference_in_a_requirement_is_a_conflict_never_a_merge(world, change):
    overlay(world, "eu-market", {**ASSAY, **change})
    held = assign(world, "general", "eu-market")
    assert held.status == "hold" and "different requirements for assay" in held.hold_reasons[0]


def test_quality_decides_which_requirement_applies_with_a_signature(world):
    held = conflicting(world)
    before = lot_of(world).revision
    decided = decide(world)
    assert decided.revision == before + 1
    current = sampling.current_assignment(decided)
    assert (current.status, current.origin, current.supersedes_id) == ("ready", "decided", held.pk)
    assert current.assigned_by == world["people"]["approver"] and current.reason == REASON
    assert current.scopes == ["general", "eu-market"]
    payload = current.payload
    (item,) = payload["decisions"]
    assert (item["code"], item["scope"], item["scopes"]) == ("assay", "eu-market", ["eu-market"])
    assert item["specification"]["code"] == "synthetic-rt-eu-market"
    assert item["text"].startswith("99 – 101 %")
    (alternative,) = item["alternatives"]
    assert alternative["scope"] == "general" and alternative["text"].startswith("98 – 102 %")
    line = next(t for t in payload["tests"] if t["code"] == "assay")
    assert (line["lower_limit"], line["upper_limit"], line["sources"]) == (
        "99",
        "101",
        ["eu-market"],
    )
    assert current.decision == {
        "schema": "oq.requirement-decision/1",
        "decides": {"assignment": held.pk},
        "choices": payload["decisions"],
        "lot_revision": decided.revision,
    }
    signature = ElectronicSignature.objects.get(
        object_type="quality.lot", object_id=str(decided.pk), meaning="requirements_decided"
    )
    assert signature.revision == decided.revision and signature.signer == current.assigned_by
    event = AuditEvent.objects.get(action="lot.requirements_decided", object_id=current.pk)
    assert event.reason == REASON
    assert event.after["decisions"] == [
        {
            "code": "assay",
            "scope": "eu-market",
            "specification": item["specification"],
            "applies": item["text"],
            "not_applied": [alternative["text"]],
        }
    ]
    # The lot is tested against the requirement that was chosen.
    tests = sample_and_tests(world)
    assert tests["assay"].requirement["lower_limit"] == "99"
    assert tests["assay"].requirement["source"].startswith("catalog:synthetic-rt-eu-market@v1#")
    # The hold itself stays in the record, unchanged.
    held.refresh_from_db()
    assert held.status == "hold" and held.hold_reasons == [CONFLICT]
    (notice,) = sampling.decision_notices(decided)
    assert "state assay differently" in notice and REASON in notice
    assert "synthetic-rt-eu-market v1 (eu-market) applies" in notice
    assert "not applied: synthetic-rt-spec v1 (general), 98 – 102 %" in notice
    notices = quality.disposition_notices(decided)
    assert notice in notices
    assert (
        "The lot's requirements were assigned under the scopes general, eu-market: "
        "specifications synthetic-rt-spec v1 (general), synthetic-rt-eu-market v1 (eu-market). "
        "A market or customer the lot is for and that is not named here was not applied."
    ) in notices


def test_the_other_statement_can_be_the_one_that_applies(world):
    conflicting(world)
    decided = decide(world, choices={"assay": "general"})
    payload = sampling.current_assignment(decided).payload
    assert payload["decisions"][0]["scope"] == "general"
    line = next(t for t in payload["tests"] if t["code"] == "assay")
    assert (line["lower_limit"], line["sources"]) == ("98", ["general"])


def test_a_decision_is_refused_without_authority_independence_or_a_choice(world):
    held = conflicting(world)
    lot = lot_of(world)

    def unchanged():
        assert sampling.current_assignment(lot).pk == held.pk
        assert Lot.objects.get(pk=lot.pk).revision == lot.revision

    # A reviewer holds no quality role.
    refused(lambda: decide(world, who="reviewer"), "role does not permit", PermissionDenied)
    # The person who received the lot also holds the quality role: not independent.
    assert sampling.decision_denial(world["people"]["analyst"], lot) == sampling.SELF_DECISION
    assert sampling.decision_denial(world["people"]["approver"], lot) == ""
    refused(lambda: decide(world, who="analyst"), "authored none of it", PermissionDenied)
    for choices in ({}, None, {"assay": "us-market"}, {"assay": "eu-market", "water": "general"}):
        refused(lambda choices=choices: decide(world, choices=choices), "Choose which requirement")
    refused(lambda: decide(world, reason="  "), "Meaning and reason are required")
    refused(lambda: decide(world, expected_revision=lot.revision - 1), "Record changed")
    refused(lambda: decide(world, basis="0" * 64), "changed after this page was opened")
    unchanged()
    denied = AuditEvent.objects.filter(action="signature.denied").count()
    refused(lambda: decide(world, pin="00000000"), "PIN was not accepted")
    # The failed attempt is kept although the decision was refused.
    assert AuditEvent.objects.filter(action="signature.denied").count() == denied + 1
    unchanged()
    assert not ElectronicSignature.objects.filter(meaning="requirements_decided").exists()


def test_a_decision_made_on_other_versions_than_shown_is_refused(world):
    conflicting(world)
    lot = lot_of(world)
    shown = sampling.decision_preview(lot).basis
    revise(world, "synthetic-rt-eu-market", {**TIGHT, "lower_limit": Decimal("99.5")})
    refused(lambda: decide(world, basis=shown), "changed after this page was opened")
    # Reviewed again, the decision is made on the versions now in force.
    decided = decide(world)
    assert (
        sampling.current_assignment(decided)
        .payload["decisions"][0]["text"]
        .startswith("99.5 – 101 %")
    )


def test_a_decision_settles_only_what_the_specifications_state_differently(world):
    conflicting(world)
    # Something else now holds the lot too: a rule set requires a test nothing states.
    extra_rules(world, "synthetic-eu-rules", {"scopes": ["eu-market"]}, ["water"])
    preview = sampling.decision_preview(lot_of(world))
    assert not preview.possible and len(preview.conflicts) == 1
    assert preview.reasons == [
        "Rule set synthetic-eu-rules v1 requires tests that no specification applying to "
        "the lot requires: water"
    ]
    refused(lambda: decide(world), "requires tests that no specification")
    assert sampling.current_assignment(world["lot"]).status == "hold"


def test_only_a_held_lot_before_testing_is_decided_here(world):
    lot = lot_of(world)
    assert sampling.decision_preview(lot).blocker == sampling.NO_DECISION
    assign(world)
    assert sampling.decision_preview(lot_of(world)).blocker == sampling.NO_DECISION
    refused(lambda: decide(world, basis=""), sampling.NO_DECISION)
    sample_and_tests(world)
    assert sampling.decision_preview(lot_of(world)).blocker == sampling.DECISION_IN_TESTING
    Lot.objects.filter(pk=lot.pk).update(state="released")
    assert "quarantined" in sampling.decision_preview(lot_of(world)).blocker


def test_requirements_assigned_again_are_decided_again(world):
    conflicting(world)
    decide(world)
    again = assign(world, "general", "eu-market")
    # An unsigned assignment never applies a signed decision by itself.
    assert again.status == "hold" and again.hold_reasons == [CONFLICT]
    decided = decide(world, who="author", choices={"assay": "general"})
    assert sampling.current_assignment(decided).payload["decisions"][0]["scope"] == "general"


def test_a_requirement_made_information_only_by_the_choice_leaves_the_rule_set_uncovered(world):
    overlay(world, "eu-market", {**ASSAY, "required": False})
    assign(world, "general", "eu-market")
    refused(
        lambda: decide(world),
        "Rule set synthetic-result-types v1 requires tests that no specification applying to "
        "the lot requires: assay",
    )
    assert decide(world, choices={"assay": "general"}).revision


def test_database_keeps_a_decided_assignment_whole(world):
    conflicting(world)
    decided = decide(world)
    current = sampling.current_assignment(decided)
    fields = {
        "lot": current.lot,
        "material": current.material,
        "stage": current.stage,
        "status": "ready",
        "payload": current.payload,
        "payload_hash": current.payload_hash,
        "specification_revision": current.specification_revision,
        "plan_revision": current.plan_revision,
        "reason": "Synthetic direct write",
        "assigned_by": current.assigned_by,
    }
    for broken in (
        {"origin": "decided", "supersedes": current},  # no decision evidence
        {"origin": "decided", "decision": current.decision},  # follows no assignment
        {"origin": "assigned", "decision": current.decision, "supersedes": current},
        {
            "origin": "replaced",
            "replacement": {"schema": "x"},
            "decision": current.decision,
            "supersedes": current,
        },
    ):
        with pytest.raises(DatabaseError, match="lot_assignment_origin"), transaction.atomic():
            LotAssignment.objects.create(**fields, **broken)
    with pytest.raises(DatabaseError), transaction.atomic():
        LotAssignment.objects.filter(pk=current.pk).update(decision={"schema": "edited"})
    with pytest.raises(DatabaseError), transaction.atomic():
        LotAssignment.objects.filter(pk=current.pk).delete()


def test_a_decided_lot_goes_to_a_certificate_that_names_what_applied(world):
    conflicting(world)
    decide(world)
    complete(world, sample_and_tests(world))
    assert gates.lot_blockers(world["lot"]) == []
    # Deciding which requirement applies is not authorship of the lot's data.
    lot = dispose(world, world["people"]["approver"])
    assert lot.state == "released"
    evidence, evidence_hash, blockers = reporting.preview(lot)
    assert blockers == [], blockers
    native = evidence["native"]
    assert native["scopes"] == ["general", "eu-market"]
    assert [(s["scope"], s["code"]) for s in native["specifications"]] == [
        ("general", "synthetic-rt-spec"),
        ("eu-market", "synthetic-rt-eu-market"),
    ]
    assert native["additional_rules"] == []
    decided = sampling.current_assignment(lot)
    assert native["decided"] == {
        "by": "Synthetic Approver",
        "at": iso(decided.assigned_at),
        "reason": REASON,
        "with": "decision",
    }
    assert native["decisions"] == [
        {
            "code": "assay",
            "applies": {
                "specification": "synthetic-rt-eu-market version 1",
                "scopes": ["eu-market"],
                "requirement": "99 – 101 % · rounded to 2 decimals · method synthetic-rt-method v1",
            },
            "not_applied": [
                {
                    "specification": "synthetic-rt-spec version 1",
                    "scopes": ["general"],
                    "requirement": "98 – 102 % · rounded to 2 decimals · method "
                    "synthetic-rt-method v1",
                }
            ],
        }
    ]
    report = reporting.issue_report(
        actor=world["people"]["author"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    snapshot = report.versions.get(number=1).snapshot
    flat = " ".join(render_to_string("reporting/_certificate.html", {"snapshot": snapshot}).split())
    assert "synthetic-rt-spec version 1 (scope general)" in flat
    assert "synthetic-rt-eu-market version 1 (scope eu-market)" in flat
    assert "assay: synthetic-rt-eu-market version 1 (eu-market) applies, 99 – 101 %" in flat
    assert "Not applied: synthetic-rt-spec version 1 (general), 98 – 102 %" in flat
    assert "Synthetic Approver of the laboratory's quality unit decided on" in flat
    assert f"Reason: {REASON}" in flat and "<dt>Specifications</dt>" in flat


def test_a_lot_under_one_specification_keeps_the_evidence_it_always_had(world):
    assign(world)
    complete(world, sample_and_tests(world))
    lot = dispose(world, world["people"]["approver"])
    evidence, evidence_hash, _ = reporting.preview(lot)
    native = evidence["native"]
    assert not {"scopes", "specifications", "additional_rules", "decisions", "decided"} & set(
        native
    )
    report = reporting.issue_report(
        actor=world["people"]["author"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    html = render_to_string(
        "reporting/_certificate.html", {"snapshot": report.versions.get(number=1).snapshot}
    )
    assert "<dt>Specification</dt>" in html and "Specifications" not in html
    assert sampling.applicability_notices(lot) == [] == sampling.decision_notices(lot)


def test_resolution_states_every_scope_and_never_guesses(world):
    """The catalog contract directly, without a lot or a rule set."""
    material = world["material"]
    overlay(world, "eu-market", TIGHT, WATER)
    common = {"material": material, "stage": "incoming"}
    one = catalog.resolve_requirements(**common)
    assert one["schema"] == "oq.requirements/1" and one["scope"] == "general"
    assert catalog.resolve_requirements(**common, scopes=["eu-market"])["scope"] == "eu-market"
    with pytest.raises(catalog.ApplicabilityHold) as held:
        catalog.resolve_requirements(**common, scopes=["eu-market", "general", "cust-a"])
    hold = held.value
    assert hold.blocking == [
        "No specification exists for synthetic-rt-material at stage incoming and scope cust-a."
    ]
    assert [c["code"] for c in hold.conflicts] == ["assay"]
    assert hold.reasons == [*hold.blocking, CONFLICT]
    # A choice that names a scope which does not state the test decides nothing.
    for wrong in ({"assay": "cust-a"}, {"water": "eu-market"}, {"assay": ""}):
        with pytest.raises(catalog.ApplicabilityHold) as held:
            catalog.resolve_requirements(**common, scopes=["general", "eu-market"], decisions=wrong)
        assert [c["code"] for c in held.value.conflicts] == ["assay"]
    payload = catalog.resolve_requirements(
        **common, scopes=["general", "eu-market"], decisions={"assay": "general", "water": "x"}
    )
    assert payload["schema"] == "oq.requirements/2" and payload["rules"] is None
    assert [d["code"] for d in payload["decisions"]] == ["assay"]
    assert [t["code"] for t in payload["tests"]][-1] == "water"
    assert len(payload["tests"]) == 6


def test_an_assignment_made_before_scopes_were_kept_is_replaced_under_its_one_scope(world):
    """A row written by an earlier release names one scope and holds no list of them."""
    from django.db import connection

    first = assign(world)
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE sampling_lotassignment DISABLE TRIGGER USER")
        try:
            LotAssignment.objects.filter(pk=first.pk).update(scopes=[])
        finally:
            cursor.execute("ALTER TABLE sampling_lotassignment ENABLE TRIGGER USER")
    first.refresh_from_db()
    assert first.scopes == [] and first.scope_list == ["general"]
    complete(world, sample_and_tests(world))
    assert sampling.newer_versions(lot_of(world)) is None
    revise(world, "synthetic-rt-spec", {**ASSAY, "lower_limit": Decimal("98.5")})
    preview = sampling.replacement_preview(lot_of(world))
    assert preview.possible and preview.payload["schema"] == "oq.requirements/1"
    assert [row["test_code"] for row in preview.superseded] == ["assay"]
    replaced = replace(world)
    current = sampling.current_assignment(replaced)
    assert current.scopes == ["general"] and "versions" in current.replacement
    assert "decisions" not in current.replacement


def test_two_decisions_at_once_leave_one(world, monkeypatch):
    from laboratory.tests.helpers import run_interleaved

    conflicting(world)
    lot = lot_of(world)
    shown = sampling.decision_preview(lot).basis

    def sign(who, scope):
        return decide(
            world,
            who=who,
            choices={"assay": scope},
            expected_revision=lot.revision,
            basis=shown,
        )

    # Reached once the first signer holds the lot and has passed the checks.
    outcome = run_interleaved(
        monkeypatch,
        sampling,
        "_check_choices",
        lambda: sign("approver", "eu-market"),
        lambda: sign("author", "general"),
    )
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    assert "Record changed" in outcome["second"].messages[0]
    decided = LotAssignment.objects.filter(lot=lot, origin="decided")
    assert decided.count() == 1 and decided.get().payload["decisions"][0]["scope"] == "eu-market"
    assert ElectronicSignature.objects.filter(meaning="requirements_decided").count() == 1


def test_a_decision_and_an_assignment_by_the_same_person_do_not_deadlock(world, monkeypatch):
    """Both take the account before the lot. The assignment waits, then records the hold
    again: an unsigned assignment never keeps a signed decision."""
    from laboratory.tests.helpers import run_interleaved

    conflicting(world)
    outcome = run_interleaved(
        monkeypatch,
        sampling,
        "_check_choices",
        lambda: decide(world),
        lambda: assign(world, "general", "eu-market", who="approver"),
    )
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert not isinstance(outcome["second"], Exception), outcome["second"]
    current = sampling.current_assignment(world["lot"])
    assert current.status == "hold" and current.supersedes.origin == "decided"


# Additional rule sets ------------------------------------------------------------------------


def test_a_rule_policy_may_say_where_the_rule_set_applies(world):
    base = POLICY | {"required_tests": ["identity"]}
    for where in (
        {"scopes": ["eu-market"]},
        {"materials": ["synthetic-rt-material"], "stages": ["incoming"], "scopes": ["a", "b"]},
    ):
        validate_policy(base | {"applies_to": where})
    for where in (
        {},
        [],
        "eu-market",
        {"scopes": []},
        {"scopes": "eu-market"},
        {"scopes": ["eu-market", "eu-market"]},
        {"scopes": [" eu-market"]},
        {"scopes": [""]},
        {"scopes": [1]},
        {"markets": ["eu"]},
        {"scopes": ["eu-market"], "sites": ["plant-1"]},
    ):
        with pytest.raises(ValidationError, match="applies_to must say where"):
            validate_policy(base | {"applies_to": where})


def test_an_additional_rule_set_names_known_materials_and_stages(world):
    refused(
        lambda: extra_rules(world, "synthetic-x", {"materials": ["no-such-material"]}, ["assay"]),
        "applies_to names unknown materials: no-such-material.",
    )
    refused(
        lambda: extra_rules(world, "synthetic-x", {"stages": ["release"]}, ["assay"]),
        "applies_to names unknown stages: release.",
    )
    assert not RuleSet.objects.filter(code="synthetic-x").exists()


def test_a_rule_set_never_changes_between_a_lots_own_and_an_additional_one(world):
    extra_rules(world, "synthetic-eu-rules", {"scopes": ["eu-market"]}, ["assay"])
    people = world["people"]
    common = {
        "actor": people["author"],
        "segment": "chemical",
        "effective_from": timezone.now(),
        "effective_until": timezone.now() + timedelta(days=30),
        "reason": "Synthetic next version",
    }
    plain = POLICY | {"required_tests": ["assay"]}
    refused(
        lambda: save_rule(code="synthetic-eu-rules", policy=plain, **common),
        "every version states applies_to",
    )
    refused(
        lambda: save_rule(
            code="synthetic-result-types",
            policy=plain | {"applies_to": {"scopes": ["eu-market"]}},
            **common,
        ),
        "no version states applies_to",
    )
    assert RuleSet.objects.filter(code="synthetic-eu-rules").count() == 1
    assert RuleSet.objects.filter(code="synthetic-result-types").count() == 1


def test_a_lot_is_never_received_under_an_additional_rule_set(world):
    extra = extra_rules(world, "synthetic-eu-rules", {"scopes": ["eu-market"]}, ["assay"])
    refused(
        lambda: quality.receive_lot(
            actor=world["people"]["analyst"],
            number="SYN-RT-002",
            material="Synthetic",
            rules=extra,
            reason="Synthetic receipt",
            receipt=on_site_receipt(),
        ),
        "applies in addition to a lot's own rule set",
    )
    assert not Lot.objects.filter(number="SYN-RT-002").exists()
    offered = set(LotForm().fields["rules"].queryset)
    assert offered == {world["lot"].rules}


def test_an_additional_rule_set_applies_by_scope_material_and_stage(world):
    overlay(world, "eu-market", ASSAY, WATER)
    extra = extra_rules(
        world,
        "synthetic-eu-rules",
        {"scopes": ["eu-market"], "materials": ["synthetic-rt-material"], "stages": ["incoming"]},
        ["water", "assay"],
    )
    # None of these names the lot: another scope, another stage, or no approval yet.
    extra_rules(world, "synthetic-us-rules", {"scopes": ["us-market"]}, ["never"])
    extra_rules(world, "synthetic-finished", {"stages": ["finished"]}, ["never"])
    extra_rules(world, "synthetic-draft", {"scopes": ["eu-market"]}, ["never"], approved=False)
    plain = assign(world)
    assert plain.payload["schema"] == "oq.requirements/1"
    assert sampling.applied_rules(lot_of(world)) == [world["lot"].rules]

    assignment = assign(world, "general", "eu-market")
    assert assignment.status == "ready", assignment.hold_reasons
    (frozen,) = assignment.payload["additional_rules"]
    assert frozen == {
        "id": extra.pk,
        "code": "synthetic-eu-rules",
        "version": 1,
        "segment": "chemical",
        "required_tests": ["water", "assay"],
        "applies_to": extra.policy["applies_to"],
    }
    assert assignment.payload["rules"]["id"] == world["lot"].rules.pk
    assert sampling.applied_rules(lot_of(world)) == [world["lot"].rules, extra]
    event = AuditEvent.objects.get(action="lot.requirements_assigned", object_id=assignment.pk)
    assert event.after["additional_rules"] == [extra.pk]


def test_a_rule_set_alone_can_stand_for_a_scope(world):
    """A customer agreement that requires tests the general specification already states."""
    extra = extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay"])
    assignment = assign(world, "general", "cust-a")
    assert assignment.status == "ready", assignment.hold_reasons
    payload = assignment.payload
    assert payload["schema"] == "oq.requirements/2" and payload["scopes"] == ["general", "cust-a"]
    assert [s["scope"] for s in payload["specifications"]] == ["general"]
    assert [r["id"] for r in payload["additional_rules"]] == [extra.pk]
    # Without any specification there is nothing to test against.
    alone = assign(world, "cust-a")
    assert alone.status == "hold"
    assert alone.hold_reasons[0] == (
        "No specification applies to synthetic-rt-material at stage incoming: cust-a selects "
        "rule sets only."
    )


def test_a_rule_set_that_applies_by_material_needs_no_scope(world):
    extra = extra_rules(
        world, "synthetic-material-rules", {"materials": ["synthetic-rt-material"]}, ["assay"]
    )
    assignment = assign(world)
    assert assignment.status == "ready", assignment.hold_reasons
    assert assignment.payload["schema"] == "oq.requirements/2"
    assert assignment.payload["scopes"] == ["general"]
    assert [r["id"] for r in assignment.payload["additional_rules"]] == [extra.pk]
    assert all(line["sources"] == ["general"] for line in assignment.payload["tests"])


def test_a_test_an_additional_rule_set_requires_and_nothing_states_holds_the_lot(world):
    extra_rules(world, "synthetic-eu-rules", {"scopes": ["eu-market"]}, ["water"])
    held = assign(world, "general", "eu-market")
    assert held.status == "hold"
    assert held.hold_reasons == [
        "Rule set synthetic-eu-rules v1 requires tests that no specification applying to "
        "the lot requires: water"
    ]
    overlay(world, "eu-market", WATER)
    assert assign(world, "general", "eu-market").status == "ready"


def test_a_retired_additional_rule_version_stops_tests_and_disposition(world):
    """Like the lot's own rule set: the version in force is needed, and assigning the
    requirements again (before testing) or replacing them (during testing) brings it."""
    first = extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay"])
    assign(world, "general", "cust-a")
    lot = lot_of(world)
    assert sampling.additional_rule_problems(lot) == []
    second = extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay", "tamc"])
    first.refresh_from_db()
    assert first.superseded_by == second
    (problem,) = sampling.additional_rule_problems(lot)
    assert "Rule set synthetic-cust-rules v1, which applies to this lot in addition" in problem
    sample = sampling.record_sampling(
        actor=world["people"]["analyst"],
        lot=lot,
        reference="SYN-RT-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    world["sample"] = sample
    refused(lambda: assign_tests(world), "synthetic-cust-rules v1")
    assert not AnalyticalTest.objects.filter(lot=lot).exists()
    # Before testing: assigned again, the version in force is frozen.
    again = assign(world, "general", "cust-a")
    assert [r["id"] for r in again.payload["additional_rules"]] == [second.pk]
    complete(world, assign_tests(world))
    # During testing: a third version retires the second; the disposition waits for the
    # replacement, which carries every test over.
    third = extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay"])
    refused(lambda: dispose(world, world["people"]["approver"]), "synthetic-cust-rules v2")
    newer = sampling.newer_versions(lot_of(world))
    assert newer["rules"] and not newer["own_rules"]
    assert newer["items"] == ["rule set synthetic-cust-rules v3"]
    notice, under = sampling.replacement_notices(lot_of(world))
    assert notice.startswith(
        "A rule set version that applies to this lot in addition to its own is no longer in "
        "force: rule set synthetic-cust-rules v3 in force now."
    )
    assert under == (
        "The lot's requirements were assigned under the scopes general, cust-a: specification "
        "synthetic-rt-spec v1 (general); additional rule sets applied: synthetic-cust-rules "
        "v2. A market or customer the lot is for and that is not named here was not applied."
    )
    preview = sampling.replacement_preview(lot_of(world))
    assert preview.possible, (preview.blocker, preview.reasons)
    assert preview.versions == [
        {
            "kind": "rule set",
            "code": "synthetic-cust-rules",
            "before": "synthetic-cust-rules v2",
            "after": "synthetic-cust-rules v3",
        }
    ]
    assert len(preview.carried) == 5 and not preview.superseded
    replaced = replace(world)
    current = sampling.current_assignment(replaced)
    assert [r["id"] for r in current.payload["additional_rules"]] == [third.pk]
    assert current.replacement["versions"] == preview.versions
    assert dispose(world, world["people"]["approver"]).state == "released"


def test_an_additional_rule_set_that_ended_is_dropped_by_the_replacement(world):
    extra = extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay"])
    assign(world, "general", "cust-a")
    complete(world, sample_and_tests(world))
    end_rule(extra)
    refused(lambda: dispose(world, world["people"]["approver"]), "synthetic-cust-rules v1")
    # The scope now selects nothing: the configuration is incomplete, and says so.
    preview = sampling.replacement_preview(lot_of(world))
    assert preview.reasons == [
        "No specification exists for synthetic-rt-material at stage incoming and scope cust-a."
    ]
    overlay(world, "cust-a", ASSAY)
    preview = sampling.replacement_preview(lot_of(world))
    assert preview.possible, (preview.blocker, preview.reasons)
    assert preview.versions == [
        {
            "kind": "rule set",
            "code": "synthetic-cust-rules",
            "before": "synthetic-cust-rules v1",
            "after": "",
        },
        {
            "kind": "specification",
            "code": "synthetic-rt-cust-a",
            "before": "",
            "after": "synthetic-rt-cust-a v1",
        },
    ]
    replace(world)
    assert sampling.applied_rules(lot_of(world)) == [world["lot"].rules]
    assert dispose(world, world["people"]["approver"]).state == "released"


# Replacement during testing ------------------------------------------------------------------


def test_a_replacement_carries_the_decision_while_its_scope_still_states_the_test(world):
    conflicting(world)
    decide(world)
    tests = sample_and_tests(world)
    complete(world, tests)
    revise(world, "synthetic-rt-spec", {**ASSAY, "lower_limit": Decimal("98.5")})
    lot = lot_of(world)
    preview = sampling.replacement_preview(lot)
    assert preview.possible, (preview.blocker, preview.reasons, preview.conflicts)
    assert preview.choices == {"assay": "eu-market"}
    # The requirement that applies is still the market's: every test carries over.
    assert all(row["change"] == "unchanged" for row in preview.lines)
    assert len(preview.carried) == 5 and not preview.superseded
    (item,) = preview.payload["decisions"]
    assert item["scope"] == "eu-market" and item["alternatives"][0]["text"].startswith("98.5 –")
    replaced = replace(world)
    current = sampling.current_assignment(replaced)
    assert current.origin == "replaced" and current.scopes == ["general", "eu-market"]
    assert current.replacement["decisions"] == current.payload["decisions"]
    assert current.replacement["versions"] == [
        {
            "kind": "specification",
            "code": "synthetic-rt-spec",
            "before": "synthetic-rt-spec v1",
            "after": "synthetic-rt-spec v2",
        }
    ]
    event = AuditEvent.objects.get(action="lot.requirements_replaced", object_id=current.pk)
    assert event.after["decisions"] == [{"code": "assay", "scope": "eu-market"}]
    assert "state assay differently" in sampling.decision_notices(replaced)[0]
    # The certificate says that the replacement confirmed the choice, and who signed it.
    released = dispose(world, world["people"]["author"])
    assert reporting.preview(released)[0]["native"]["decided"]["with"] == "replacement"


def test_a_requirement_chosen_before_testing_is_changed_by_a_signed_replacement(world):
    """Nothing was revised, so there is nothing to replace; another choice is one."""
    conflicting(world)
    decide(world)
    tests = sample_and_tests(world)
    complete(world, tests)
    lot = lot_of(world)
    unchanged = sampling.replacement_preview(lot)
    assert unchanged.blocker == sampling.NOTHING_TO_REPLACE
    assert unchanged.payload["decisions"][0]["scope"] == "eu-market"
    assert sampling.newer_versions(lot) is None
    refused(lambda: replace(world, basis=""), sampling.NOTHING_TO_REPLACE)
    other = {"assay": "general"}
    preview = sampling.replacement_preview(lot, choices=other)
    assert preview.possible and preview.versions == []
    assert [row["test_code"] for row in preview.superseded] == ["assay"]
    replaced = replace(world, choices=other)
    current = sampling.current_assignment(replaced)
    assert current.origin == "replaced" and current.payload["decisions"][0]["scope"] == "general"
    assert "versions" not in current.replacement
    tests["assay"].refresh_from_db()
    assert tests["assay"].state == STATE.SUPERSEDED


def test_a_conflict_that_arises_during_testing_is_decided_with_the_replacement(world):
    overlay(world, "eu-market", ASSAY)
    assert assign(world, "general", "eu-market").status == "ready"
    tests = sample_and_tests(world)
    complete(world, tests)
    revise(world, "synthetic-rt-eu-market", TIGHT)
    lot = lot_of(world)
    preview = sampling.replacement_preview(lot)
    assert not preview.possible and preview.reasons == [] and preview.basis == ""
    assert [c["code"] for c in preview.conflicts] == ["assay"]
    newer = sampling.newer_versions(lot)
    assert not newer["rules"]
    assert newer["items"] == [
        "the specifications in force state assay differently, which quality decides with "
        "the replacement"
    ]
    # The lot keeps its frozen requirements and can still be dispositioned against them.
    assert "This does not block the disposition." in sampling.replacement_notices(lot)[0]
    refused(lambda: replace(world), "Choose which requirement applies")
    refused(lambda: replace(world, choices={"assay": "us-market"}), "Choose which requirement")
    assert sampling.current_assignment(lot).origin == "assigned"

    chosen = {"assay": "eu-market"}
    preview = sampling.replacement_preview(lot, choices=chosen)
    assert preview.possible, (preview.blocker, preview.reasons)
    assert {row["code"]: row["change"] for row in preview.lines}["assay"] == "changed"
    assert [row["test_code"] for row in preview.superseded] == ["assay"]
    # A signature prepared for one choice does not sign another.
    refused(
        lambda: replace(world, choices={"assay": "general"}, basis=preview.basis),
        "changed after this page was opened",
    )
    replaced = replace(world, choices=chosen)
    current = sampling.current_assignment(replaced)
    assert current.payload["decisions"][0]["scope"] == "eu-market"
    tests["assay"].refresh_from_db()
    assert tests["assay"].state == STATE.SUPERSEDED
    (repeat,) = assign_tests(world).values()
    assert repeat.kind == "revised" and repeat.requirement["lower_limit"] == "99"


def test_choosing_the_statement_already_tested_under_carries_the_test_over(world):
    overlay(world, "eu-market", ASSAY)
    assign(world, "general", "eu-market")
    complete(world, sample_and_tests(world))
    revise(world, "synthetic-rt-eu-market", TIGHT)
    chosen = {"assay": "general"}
    preview = sampling.replacement_preview(lot_of(world), choices=chosen)
    assert preview.possible and len(preview.carried) == 5 and not preview.superseded
    replaced = replace(world, choices=chosen)
    (item,) = sampling.current_assignment(replaced).payload["decisions"]
    assert item["scope"] == "general" and item["alternatives"][0]["scope"] == "eu-market"


def test_a_replacement_with_a_decision_still_needs_an_independent_quality_signer(world):
    overlay(world, "eu-market", ASSAY)
    assign(world, "general", "eu-market")
    complete(world, sample_and_tests(world))
    revise(world, "synthetic-rt-eu-market", TIGHT)
    chosen = {"assay": "eu-market"}
    refused(
        lambda: replace(world, who="analyst", choices=chosen),
        "authored none of it",
        PermissionDenied,
    )
    refused(
        lambda: replace(world, who="reviewer", choices=chosen),
        "role does not permit",
        PermissionDenied,
    )
    assert sampling.current_assignment(world["lot"]).origin == "assigned"


# Reliance on supplier results ------------------------------------------------------------------


def test_every_rule_set_a_lot_is_under_must_allow_a_supplier_result(django_user_model):
    from quality import reliance
    from tests import test_supplier_reliance as supplied

    data = supplied.build_reliance_world(django_user_model)
    lot, people = data["lot"], data["people"]
    supplied.qualify(data)

    def reassign():
        assignment = sampling.assign_requirements(
            actor=people["analyst"],
            lot=lot,
            material=data["material"],
            stage="incoming",
            reason="Assign approved synthetic policy",
        )
        assert assignment.status == "ready", assignment.hold_reasons
        lot.refresh_from_db()

    # An additional rule set that says nothing about supplier results allows none.
    silent = extra_rules(
        data, "synthetic-material-rules", {"materials": ["synthetic-rt-material"]}, ["assay"]
    )
    reassign()
    certificate = supplied.certify(data, supplied.fully_stated(), lot=lot)
    with pytest.raises(reliance.RelianceRefused, match="does not allow a supplier's result") as no:
        supplied.propose(data, certificate, "impurity")
    assert "synthetic-material-rules v1" in no.value.messages[0]
    # Its next version allows reliance and keeps the assay with the laboratory.
    allowing = extra_rules(
        data,
        "synthetic-material-rules",
        {"materials": ["synthetic-rt-material"]},
        ["assay"],
        supplier_results={"own_tests": ["assay"]},
    )
    silent.refresh_from_db()
    assert silent.superseded_by == allowing
    with pytest.raises(ValidationError, match="approved, effective rule revision"):
        supplied.propose(data, certificate, "impurity")  # the retired version is still frozen
    reassign()
    certificate = supplied.certify(data, supplied.fully_stated(), lot=lot, number="COA-SYN-0002")
    with pytest.raises(reliance.RelianceRefused, match="requires the laboratory to perform assay"):
        supplied.propose(data, certificate, "assay")
    proposal = supplied.propose(data, certificate, "impurity")
    assert proposal.evidence["rules"]["code"] == "synthetic-reliance"
    assert proposal.evidence["additional_rules"] == [
        {
            "id": allowing.pk,
            "code": "synthetic-material-rules",
            "version": 1 + silent.version,
            "own_tests": ["assay"],
        }
    ]
    accepted = supplied.accept(data, proposal)
    assert accepted.state == "accepted"


def end_rule(rule):
    """An approved version whose effective period has passed. The guard on approved rules
    allows no such edit, so the test lifts it for this one statement."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE core_ruleset DISABLE TRIGGER USER")
        try:
            RuleSet.objects.filter(pk=rule.pk).update(
                effective_from=timezone.now() - timedelta(days=3),
                effective_until=timezone.now() - timedelta(minutes=1),
            )
        finally:
            cursor.execute("ALTER TABLE core_ruleset ENABLE TRIGGER USER")
