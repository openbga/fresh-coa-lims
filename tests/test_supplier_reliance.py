"""Reliance on a supplier's results: a signed supplier qualification, a rule set that allows it,
and an acceptance signed on the lot let a certificate result stand in for a test.

Uses the production adapters and service-created approvals only (synthetic data).
"""

import datetime
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.models import AnalyticalTest, Observation
from core.models import AuditEvent, ElectronicSignature
from core.services import approve_rule, save_rule, set_pin, validate_policy
from quality import certificates, reliance
from quality import services as quality
from quality.models import SupplierResultAcceptance
from reporting import services as reporting
from sampling import services as sampling
from suppliers import qualification as qualifying
from suppliers.models import SupplierQualification
from tests.receipts import on_site_receipt, supplier_receipt
from tests.test_integrated_journey import PASSWORD, PIN, dispose
from tests.test_result_types_journey import record, submit
from tests.test_supplier_certificates import (
    assign,
    build_supplied_world,
    certify,
    correct,
    sample_and_test,
    stated,
    withdraw,
)

pytestmark = pytest.mark.django_db(transaction=True)

RELIED = ["assay", "impurity", "salmonella", "tamc"]
POLICY = {"review_meaning": "reviewed", "disposition_meaning": "approved"}
STATE = SupplierResultAcceptance.State


def today():
    return timezone.localdate()


def fully_stated(**changes):
    """Every requirement as a certificate states it, each with its method and its limits."""
    results = {
        "identity": stated(
            "identity",
            outcome="conforms",
            wording="Complies",
            method="Supplier IR-01",
            limits="Conforms to reference",
        ),
        "salmonella": stated(
            "salmonella",
            outcome="absent",
            wording="Negative in 25 g",
            method="Supplier MB-02",
            limits="Absent in 25 g",
        ),
        "tamc": stated("tamc", "10", less=True, method="Supplier MB-01", limits="NMT 200 CFU/g"),
        "impurity": stated("impurity", "4.20", method="Supplier HPLC-09", limits="NMT 5 mg/g"),
        "assay": stated("assay", "99.60", method="Supplier HPLC-07", limits="98.0 - 102.0 %"),
    }
    results.update(changes)
    return [item for item in results.values() if item is not None]


def reliance_rules(data, *, code="synthetic-reliance", own=("identity",), allow=True):
    people = data["people"]
    policy = POLICY | {"required_tests": ["identity", *RELIED]}
    if allow:
        policy["supplier_results"] = {"own_tests": list(own)}
    rules = save_rule(
        actor=people["author"],
        code=code,
        segment="chemical",
        policy=policy,
        effective_from=timezone.now() - timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=365),
        reason="Synthetic policy that allows reliance on a qualified supplier",
    )
    return approve_rule(
        actor=people["approver"],
        pin=PIN,
        rule=rules,
        expected_revision=rules.revision,
        reason="Independent synthetic policy review",
    )


def receive(data, rules, number="SYN-REL-001", **receipt):
    lot = quality.receive_lot(
        actor=data["people"]["analyst2"],
        number=number,
        material=data["material"].name,
        rules=rules,
        reason="Synthetic receipt",
        receipt=supplier_receipt(data["supplier"], **receipt),
    )
    assign(data, lot)
    lot.refresh_from_db()
    return lot


def build_reliance_world(django_user_model):
    """A lot received from a supplier under a rule set that allows reliance and keeps identity
    with the laboratory. ``plain_lot`` is under the rule set that allows none."""
    data = build_supplied_world(django_user_model)
    data["plain_lot"] = data["lot"]
    data["rules"] = reliance_rules(data)
    data["lot"] = receive(data, data["rules"])
    return data


@pytest.fixture
def world(django_user_model):
    return build_reliance_world(django_user_model)


def qualify(data, *, codes=RELIED, sign=True, supplier=None, **dates):
    people = data["people"]
    qualification = qualifying.record_qualification(
        actor=people["author"],
        supplier=supplier or data["supplier"],
        material=data["material"],
        test_codes=list(codes),
        basis="Three synthetic lots tested in full and compared with the certificates",
        evidence_ref="SQR-SYN-001 rev 1",
        valid_from=dates.get("valid_from", today() - timedelta(days=30)),
        valid_until=dates.get("valid_until", today() + timedelta(days=300)),
        reason="Synthetic supplier qualification",
    )
    if sign:
        qualification = sign_qualification(data, qualification)
    return qualification


def sign_qualification(data, qualification, who="approver"):
    return qualifying.approve_qualification(
        actor=data["people"][who],
        pin=PIN,
        qualification=qualification,
        expected_revision=qualification.revision,
        reason="Independent review of the qualification evidence",
    )


def revoke(data, qualification, who="author"):
    qualification.refresh_from_db()
    return qualifying.revoke_qualification(
        actor=data["people"][who],
        pin=PIN,
        qualification=qualification,
        expected_revision=qualification.revision,
        reason="Synthetic discrepancy found on re-confirmation",
    )


def line(certificate, code):
    return certificate.results.get(test_code=code)


def shown_basis(result):
    """The token of what the proposal page would show, or "" when it would show a refusal."""
    try:
        return reliance.basis_token(reliance.proposal_basis(result.certificate.lot, result))
    except ValidationError:
        return ""  # The service refuses for the same reason, and audits it where it should.


def propose(data, certificate, code="assay", who="analyst", **changes):
    result = line(certificate, code)
    return reliance.propose_acceptance(
        actor=data["people"][who],
        result=result,
        basis=changes.pop("basis", None) or shown_basis(result),
        reason="Supplier qualified for this test",
    )


def accept(data, acceptance, who="reviewer", **changes):
    acceptance.refresh_from_db()
    return reliance.accept_result(
        actor=data["people"][who],
        pin=changes.pop("pin", PIN),
        acceptance=acceptance,
        expected_revision=changes.pop("expected_revision", acceptance.revision),
        reason="Checked against the supplier's certificate",
    )


def take_back(data, acceptance, who="analyst", **changes):
    """Withdraw a proposal with a reason, or a signed acceptance with a signature."""
    acceptance.refresh_from_db()
    common = {
        "actor": data["people"][who],
        "acceptance": acceptance,
        "expected_revision": changes.pop("expected_revision", acceptance.revision),
        "reason": changes.pop("reason", "Tested in the laboratory instead"),
    }
    if acceptance.state == STATE.ACCEPTED:
        return reliance.withdraw_accepted(pin=changes.pop("pin", PIN), **common)
    return reliance.withdraw_proposal(**common)


def accepted_lot(data, codes=RELIED):
    """The world's lot with a certificate recorded and the stated results accepted."""
    qualify(data)
    certificate = certify(data, fully_stated(), lot=data["lot"])
    return certificate, {code: accept(data, propose(data, certificate, code)) for code in codes}


def person(django_user_model, name, *roles):
    user = django_user_model.objects.create_user(username=name, password=PASSWORD)
    user.groups.add(*[Group.objects.get_or_create(name=role)[0] for role in roles])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def refused_events():
    return AuditEvent.objects.filter(action="supplier_result.refused")


# The rule set decides -----------------------------------------------------------------------------


def test_rule_policy_takes_an_optional_list_of_the_laboratorys_own_tests():
    base = POLICY | {"required_tests": ["identity", "assay"]}
    validate_policy(base)  # Policies approved before this key existed stay valid.
    validate_policy(base | {"supplier_results": {"own_tests": ["identity"]}})
    validate_policy(base | {"supplier_results": {"own_tests": []}})
    for wrong in (
        True,
        [],
        {},
        {"own_tests": "identity"},
        {"own_tests": ["identity", "identity"]},
        {"own_tests": [""]},
        {"own_tests": [" identity"]},
        {"own_tests": [1]},
        {"own_tests": ["identity"], "all": True},
    ):
        with pytest.raises(ValidationError, match="supplier_results must hold exactly own_tests"):
            validate_policy(base | {"supplier_results": wrong})
    with pytest.raises(ValidationError, match="Unsupported or missing rule policy keys"):
        validate_policy(base | {"supplier_result": {"own_tests": []}})
    # A mistyped code would leave the test it meant open to reliance: it is refused.
    for slip in (["identiy"], ["Identity"], ["identity", "water"]):
        with pytest.raises(ValidationError, match="own_tests must be among required_tests"):
            validate_policy(base | {"supplier_results": {"own_tests": slip}})


def test_a_rule_set_that_says_nothing_allows_no_reliance(world):
    """The lot under the earlier rule set: a qualified supplier and a conforming certificate
    change nothing, and the refused proposal is kept in the lot's audit trail."""
    qualify(world)
    lot = world["plain_lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    revision = lot.revision + 1  # The certificate advanced it.
    with pytest.raises(reliance.RelianceRefused, match="does not allow a supplier's result"):
        propose(world, certificate)
    assert not SupplierResultAcceptance.objects.exists()
    refusal = refused_events().get()
    assert (refusal.object_type, refusal.object_id) == ("quality.lot", str(lot.pk))
    assert refusal.actor == world["people"]["analyst"]
    assert refusal.after["test_code"] == "assay" and refusal.after["certificate"] == "COA-SYN-0001"
    assert "does not allow" in refusal.after["reasons"][0]
    lot.refresh_from_db()
    assert lot.revision == revision
    assert reliance.proposal_refusal(lot, line(certificate, "assay")).startswith("Rule set")


def test_a_test_the_rule_set_keeps_with_the_laboratory_is_never_relied_on(world):
    qualify(world, codes=["identity", *RELIED])  # Even a qualification that names it.
    certificate = certify(world, fully_stated(), lot=world["lot"])
    with pytest.raises(reliance.RelianceRefused, match="requires the laboratory to perform"):
        propose(world, certificate, "identity")
    assert not SupplierResultAcceptance.objects.exists()
    assert refused_events().get().after["test_code"] == "identity"
    assert propose(world, certificate, "assay").state == STATE.PROPOSED


# Supplier qualification ---------------------------------------------------------------------------


def test_qualification_is_recorded_by_one_quality_person_and_signed_by_another(world):
    people = world["people"]
    for name in ("analyst2", "reviewer", "auditor", "admin"):
        with pytest.raises(PermissionDenied):
            qualifying.record_qualification(
                actor=people[name],
                supplier=world["supplier"],
                material=world["material"],
                test_codes=["assay"],
                basis="Synthetic basis",
                evidence_ref="SQR-SYN-000",
                valid_from=today(),
                valid_until=today(),
                reason="Not a quality person",
            )
    qualification = qualify(world, codes=["tamc", "assay", "assay"], sign=False)
    assert qualification.test_codes == ["assay", "tamc"]  # Sorted, each once.
    assert (qualification.state, qualification.label) == ("recorded", f"SQ-{qualification.pk}")
    assert qualifying.qualification_status(qualification)[0] == "Awaiting approval"
    event = AuditEvent.objects.get(action="supplier_qualification.recorded")
    assert event.after["test_codes"] == ["assay", "tamc"]
    # Recorded evidence qualifies nothing.
    finding = qualifying.reliance_finding(world["supplier"], world["material"], "assay", today())
    assert not finding.ok and "still awaiting its signature" in finding.reasons[0]
    denial = qualifying.qualification_denial(people["author"], qualification, approve=True)
    assert denial == qualifying.SELF_APPROVAL
    with pytest.raises(PermissionDenied, match="you recorded"):
        sign_qualification(world, qualification, who="author")
    with pytest.raises(PermissionDenied):
        sign_qualification(world, qualification, who="reviewer")
    with pytest.raises(ValidationError, match="Record changed"):
        qualifying.approve_qualification(
            actor=people["approver"],
            pin=PIN,
            qualification=qualification,
            expected_revision=qualification.revision + 1,
            reason="Stale page",
        )
    signed = sign_qualification(world, qualification)
    assert signed.state == "approved" and signed.approved_at and signed.revision == 2
    signature = ElectronicSignature.objects.get(
        object_type="suppliers.supplierqualification", object_id=str(signed.pk)
    )
    assert (signature.meaning, signature.signer, signature.revision) == (
        "approved",
        people["approver"],
        2,
    )
    assert signature.content["test_codes"] == ["assay", "tamc"]
    finding = qualifying.reliance_finding(world["supplier"], world["material"], "assay", today())
    assert finding.ok and finding.evidence["qualification"]["label"] == signed.label
    with pytest.raises(ValidationError, match="Only recorded qualifications"):
        sign_qualification(world, signed)
    # Revoking is protective: the recorder may do it. A revoked qualification is final.
    revoked = revoke(world, signed, who="author")
    assert revoked.state == "revoked" and revoked.revoked_at
    assert qualifying.qualification_status(revoked) == ("Revoked", "danger")
    with pytest.raises(ValidationError, match="Only approved qualifications"):
        revoke(world, revoked)
    finding = qualifying.reliance_finding(world["supplier"], world["material"], "assay", today())
    assert not finding.ok and "was revoked" in finding.reasons[0]


def test_qualification_scope_is_chosen_from_the_materials_specifications(world):
    assert set(qualifying.material_test_codes(world["material"])) == {"identity", *RELIED}
    common = {
        "actor": world["people"]["author"],
        "supplier": world["supplier"],
        "material": world["material"],
        "basis": "Synthetic basis",
        "evidence_ref": "SQR-SYN-002",
        "valid_from": today(),
        "valid_until": today() + timedelta(days=10),
        "reason": "Synthetic",
    }
    with pytest.raises(ValidationError, match="No specification of .* states water"):
        qualifying.record_qualification(test_codes=["assay", "water"], **common)
    for nothing in ([], None, [""], "assay"):
        with pytest.raises(ValidationError):
            qualifying.record_qualification(test_codes=nothing, **common)
    with pytest.raises(ValidationError):
        qualifying.record_qualification(
            test_codes=["assay"], **(common | {"valid_until": today() - timedelta(days=1)})
        )
    with pytest.raises(ValidationError):
        qualifying.record_qualification(test_codes=["assay"], **(common | {"basis": "  "}))
    with pytest.raises(ValidationError):
        qualifying.record_qualification(
            test_codes=["assay"], evidence_url="javascript:alert(1)", **common
        )
    with pytest.raises(ValidationError, match="A reason is required"):
        qualifying.record_qualification(test_codes=["assay"], **(common | {"reason": " "}))
    assert not SupplierQualification.objects.exists()


def test_database_refuses_edited_or_unsigned_qualifications(world):
    qualification = qualify(world)

    def refused(write, message):
        with pytest.raises((DatabaseError, IntegrityError), match=message), transaction.atomic():
            write()

    table = SupplierQualification.objects.filter(pk=qualification.pk)
    refused(lambda: table.update(test_codes=["identity"]), "evidence is immutable")
    refused(lambda: table.update(valid_until=today() + timedelta(days=900)), "immutable")
    refused(lambda: table.update(state="recorded"), "immutable")
    refused(lambda: table.update(approved_at=timezone.now()), "immutable|cannot change")
    refused(lambda: table.delete(), "cannot be deleted")

    def copy(**changes):
        values = {
            "supplier": world["supplier"],
            "material": world["material"],
            "test_codes": ["assay"],
            "basis": "Direct write",
            "evidence_ref": "SQR-DIRECT",
            "valid_from": today(),
            "valid_until": today(),
            "recorded_by": world["people"]["author"],
        } | changes
        return SupplierQualification.objects.create(**values)

    refused(
        lambda: copy(state="approved", approved_at=timezone.now()), "starts as recorded evidence"
    )
    for scope in ([], {}, "assay", [""], [1]):
        refused(lambda scope=scope: copy(test_codes=scope), "names the tests it covers")
    assert SupplierQualification.objects.count() == 1
    qualification.refresh_from_db()
    assert qualification.state == "approved" and qualification.test_codes == RELIED


# Proposing ----------------------------------------------------------------------------------------


def test_a_proposal_freezes_what_it_relies_on_and_answers_nothing(world):
    qualification = qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    lot.refresh_from_db()
    revision = lot.revision
    acceptance = propose(world, certificate)
    assert (acceptance.state, acceptance.label) == (STATE.PROPOSED, f"SRA-{acceptance.pk}")
    assert acceptance.qualification == qualification and acceptance.test_code == "assay"
    assert acceptance.requirement_hash == line(certificate, "assay").requirement_hash
    evidence = acceptance.evidence
    assert evidence["schema"] == reliance.SCHEMA
    assert evidence["stated"] == {
        "result": "99.60",
        "wording": "",
        "method": "Supplier HPLC-07",
        "limits": "98.0 - 102.0 %",
    }
    assert (evidence["name"], evidence["unit"], evidence["acceptance"]) == (
        "Assay",
        "%",
        "98 to 102 %",
    )
    assert evidence["certificate"]["number"] == "COA-SYN-0001"
    assert evidence["certificate"]["author_ids"] == [world["people"]["analyst2"].pk]
    assert evidence["supplier"]["code"] == "sup-syn-001"
    assert evidence["received_on"] == today().isoformat()
    assert evidence["qualification"]["label"] == qualification.label
    assert evidence["qualification"]["evidence_ref"] == "SQR-SYN-001 rev 1"
    assert evidence["rules"]["own_tests"] == ["identity"]
    event = AuditEvent.objects.get(action="supplier_result.proposed")
    assert event.after["evidence"] == evidence and event.actor == world["people"]["analyst"]
    lot.refresh_from_db()
    assert lot.revision == revision + 1
    # A proposal blocks the disposition and answers no requirement.
    relied = reliance.lot_reliance(lot)
    assert relied["accepted"] == {} and relied["standing"] == {"assay": acceptance.label}
    assert f"{acceptance.label}: the supplier's result for assay awaits acceptance" in " ".join(
        gates.lot_blockers(lot)
    )
    with pytest.raises(ValidationError) as again:
        propose(world, certificate)
    assert again.value.messages == [reliance.ALREADY]
    assert SupplierResultAcceptance.objects.count() == 1 and not refused_events().exists()


@pytest.mark.parametrize("role", ["reviewer", "quality", "auditor", "admin"])
def test_only_an_analyst_proposes(world, role):
    qualify(world)
    certificate = certify(world, fully_stated(), lot=world["lot"])
    with pytest.raises(PermissionDenied):
        propose(world, certificate, who=role)
    assert not SupplierResultAcceptance.objects.exists()


def test_a_proposal_needs_a_signed_qualification_that_covers_it(world):
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)

    def refused(message, code="assay"):
        with pytest.raises(reliance.RelianceRefused, match=message):
            propose(world, certificate, code)

    refused("is not qualified for")
    waiting = qualify(world, codes=["assay"], sign=False)
    refused("still awaiting its signature")
    signed = sign_qualification(world, waiting)
    refused("does not cover impurity", "impurity")
    assert refused_events().count() == 3 and not SupplierResultAcceptance.objects.exists()
    assert refused_events().last().after["refused_by"] == "sup-syn-001 · synthetic-rt-material"
    proposal = propose(world, certificate)
    take_back(world, proposal, reason="Proposed too early")
    revoke(world, signed)
    refused("was revoked")
    # Another supplier's qualification is not this supplier's.
    from suppliers.services import create_supplier

    other = create_supplier(
        actor=world["people"]["author"],
        code="sup-syn-002",
        name="Another Synthetic Supply",
        location="Elsewhere, Exampleland",
        reason="Synthetic master data",
    )
    qualify(world, supplier=other)
    refused("was revoked")
    assert SupplierResultAcceptance.objects.filter(state__in=reliance.STANDING).count() == 0


def test_the_qualification_must_cover_the_day_the_lot_was_received(world):
    qualify(world, valid_from=today() - timedelta(days=5), valid_until=today() - timedelta(days=1))
    certificate = certify(world, fully_stated(), lot=world["lot"])
    with pytest.raises(reliance.RelianceRefused, match="covers a lot received on"):
        propose(world, certificate)
    # A lot received within the dates is covered, even though the qualification has run out.
    earlier = receive(world, world["rules"], "SYN-REL-002", received_on=today() - timedelta(days=1))
    certificate = certify(world, fully_stated(), lot=earlier, number="COA-SYN-0002")
    acceptance = propose(world, certificate)
    assert acceptance.evidence["received_on"] == (today() - timedelta(days=1)).isoformat()
    assert accept(world, acceptance).state == STATE.ACCEPTED


def test_a_stated_result_is_relied_on_only_as_the_certificate_record_stands(world):
    qualify(world)
    lot = world["lot"]
    certificate = certify(
        world,
        fully_stated(
            assay=stated("assay", "97.50", method="Supplier HPLC-07", limits="98.0 - 102.0 %"),
            impurity=stated("impurity", "4.20", method="Supplier HPLC-09"),
            tamc=stated("tamc", "10", less=True, limits="NMT 200 CFU/g"),
        ),
        lot=lot,
    )

    def refused(code, message):
        with pytest.raises(ValidationError) as refusal:
            propose(world, certificate, code)
        assert not isinstance(refusal.value, reliance.RelianceRefused)
        assert refusal.value.messages == [message]

    refused("assay", reliance.DOES_NOT_MEET)
    refused("impurity", reliance.NOT_STATED)  # No limits stated.
    refused("tamc", reliance.NOT_STATED)  # No method stated.
    corrected = correct(world, certificate, fully_stated())
    refused("assay", reliance.NOT_CURRENT)  # The replaced record is relied on no further.
    assert propose(world, corrected, "assay").state == STATE.PROPOSED
    withdraw(world, corrected)
    refused("impurity", reliance.NOT_CURRENT)
    with pytest.raises(ValidationError) as refusal:
        reliance.propose_acceptance(
            actor=world["people"]["analyst"],
            result=line(corrected, "impurity"),
            basis="",
            reason="A withdrawn record",
        )
    assert refusal.value.messages == [reliance.NOT_CURRENT]
    # These refusals are about the records, not about authority: none is audited.
    assert not refused_events().exists()
    with pytest.raises(ValidationError, match="A reason is required"):
        reliance.propose_acceptance(
            actor=world["people"]["analyst"],
            result=line(corrected, "salmonella"),
            basis="",
            reason=" ",
        )


def test_a_requirement_the_laboratory_started_testing_is_not_relied_on(world):
    """No testing into compliance: once the laboratory holds work on a requirement, the
    supplier's result cannot answer it."""
    qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    sample = sampling.record_sampling(
        actor=world["people"]["analyst"],
        lot=lot,
        reference="SYN-REL-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=10,
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    tests, _ = analytical.assign_tests(
        actor=world["people"]["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assay = next(t for t in tests if t.test_code == "assay")
    # An assigned test that nobody has touched does not stop a proposal.
    assert gates.tested_here(lot, "assay") == ""
    record(world, assay, "97.10")  # A failing laboratory result.
    with pytest.raises(ValidationError, match="already holds laboratory work"):
        propose(world, certificate, "assay")
    assert reliance.proposal_refusal(lot, line(certificate, "assay")).startswith(assay.label)
    submit(world, assay)
    with pytest.raises(ValidationError, match="already holds laboratory work"):
        propose(world, certificate, "assay")
    assert not SupplierResultAcceptance.objects.exists()
    # The other requirements, untouched, can still be proposed.
    assert propose(world, certificate, "impurity").state == STATE.PROPOSED


def test_a_lot_made_on_site_relies_on_nothing(world):
    qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    quality.correct_receipt(
        actor=world["people"]["analyst2"],
        receipt=quality.current_receipt(lot),
        reason="The lot was made on site",
        **on_site_receipt(),
    )
    with pytest.raises(ValidationError) as refusal:
        propose(world, certificate)
    assert refusal.value.messages == [reliance.NOT_SUPPLIED]


# Accepting ----------------------------------------------------------------------------------------


def test_acceptance_is_signed_by_a_reviewer_who_authored_nothing_of_it(world, django_user_model):
    qualify(world)
    lot = world["lot"]
    both = person(django_user_model, "rel_transcriber", "analyst", "reviewer")
    world["people"]["both"] = both
    certificate = certify(world, fully_stated(), lot=lot, actor="both")
    acceptance = propose(world, certificate)  # Proposed by the analyst who is also a reviewer.
    people = world["people"]
    assert reliance.acceptance_denial(people["analyst"], acceptance) == reliance.SELF_ACCEPTANCE
    assert reliance.acceptance_denial(both, acceptance) == reliance.CERTIFICATE_AUTHOR
    assert reliance.acceptance_denial(people["reviewer"], acceptance) == ""
    with pytest.raises(PermissionDenied, match="you proposed"):
        accept(world, acceptance, who="analyst")
    with pytest.raises(PermissionDenied, match="recorded or corrected the supplier certificate"):
        accept(world, acceptance, who="both")
    for role in ("analyst2", "quality", "auditor", "admin"):
        with pytest.raises(PermissionDenied):
            accept(world, acceptance, who=role)
    with pytest.raises(ValidationError, match="Record changed"):
        accept(world, acceptance, expected_revision=acceptance.revision + 1)
    # A wrong PIN signs nothing and is kept in the audit trail.
    denied = AuditEvent.objects.filter(action="signature.denied").count()
    with pytest.raises(ValidationError, match="PIN was not accepted"):
        accept(world, acceptance, pin="00000000")
    assert AuditEvent.objects.filter(action="signature.denied").count() == denied + 1
    acceptance.refresh_from_db()
    assert acceptance.state == STATE.PROPOSED and acceptance.accepted_at is None
    lot.refresh_from_db()
    revision = lot.revision

    accepted = accept(world, acceptance)
    assert accepted.state == STATE.ACCEPTED and accepted.accepted_at and accepted.revision == 2
    signature = reliance.acceptance_signature(accepted)
    assert (signature.meaning, signature.signer, signature.revision) == (
        "accepted",
        people["reviewer"],
        2,
    )
    # The signature binds what was relied on.
    assert signature.content["evidence"] == acceptance.evidence
    lot.refresh_from_db()
    assert lot.revision == revision + 1
    with pytest.raises(ValidationError, match="already accepted"):
        accept(world, accepted)
    relied = reliance.lot_reliance(lot)
    entry = relied["accepted"]["assay"]
    assert entry["signature"]["signer"] == signature.signer_name
    assert entry["stated"]["result"] == "99.60" and entry["criterion"] == "98 to 102 %"
    assert set(relied["author_ids"]) == {people["analyst"].pk, both.pk}


def test_acceptance_is_refused_when_what_was_proposed_has_changed(world):
    qualification = qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    acceptance = propose(world, certificate)
    revoke(world, qualification)
    with pytest.raises(ValidationError, match="no longer covers this result"):
        accept(world, acceptance)
    # A newer qualification does not rescue a proposal made under the revoked one.
    qualify(world)
    with pytest.raises(ValidationError, match="no longer covers this result"):
        accept(world, acceptance)
    take_back(world, acceptance, reason="Qualification revoked")
    acceptance = propose(world, certificate)
    # The receipt is corrected to another supplier lot: the basis is the same, it is accepted.
    receipt = quality.current_receipt(lot)
    values = {name: getattr(receipt, name) for name in quality.RECEIPT_FIELDS}
    quality.correct_receipt(
        actor=world["people"]["analyst2"],
        receipt=receipt,
        reason="Supplier lot number misread",
        **(values | {"supplier_lot": "SUP-LOT-SYN-009"}),
    )
    accepted = accept(world, acceptance)
    assert accepted.state == STATE.ACCEPTED
    # The certificate is corrected under a proposal for another test: that one is refused.
    other = propose(world, certificate, "impurity")
    correct(world, certificate, fully_stated(), notes="Notes added")
    with pytest.raises(ValidationError) as refusal:
        accept(world, other)
    assert refusal.value.messages == [reliance.NOT_CURRENT]
    other.refresh_from_db()
    assert other.state == STATE.PROPOSED


# The gate, the disposition and the certificate ----------------------------------------------------


def test_accepted_supplier_results_answer_their_requirements_to_the_issued_certificate(world):
    people, lot = world["people"], world["lot"]
    certificate, accepted = accepted_lot(world)
    # Only the test the rule set keeps with the laboratory is assigned and performed.
    released = sample_and_test(world)
    tests = list(AnalyticalTest.objects.filter(lot=lot))
    assert [t.test_code for t in tests] == ["identity"]
    assert gates.lot_blockers(lot) == []
    evidence = gates.lot_evidence(lot)
    assert [r["test_code"] for r in evidence["results"]] == ["identity"]
    assert [s["test_code"] for s in evidence["supplier_results"]] == RELIED
    # The people behind a supplier result are authors of the lot's evidence.
    assert {people["analyst"].pk, people["analyst2"].pk} <= set(evidence["author_ids"])
    for author in ("analyst", "analyst2"):
        assert quality.disposition_denial(people[author], lot) == quality.SELF_DISPOSITION
    notices = quality.disposition_notices(lot)
    assert len(notices) == 4
    assert any(
        "Assay: the supplier's stated result 99.60 % on certificate COA-SYN-0001 was accepted "
        "in place of a laboratory test" in notice
        for notice in notices
    )
    released = dispose(world, people["approver"])
    assert released.state == "released"
    frozen = released.disposition_evidence["analytical"]
    assay = next(s for s in frozen["supplier_results"] if s["test_code"] == "assay")
    assert assay["certificate"]["number"] == "COA-SYN-0001"
    assert assay["supplier"]["name"] == "Synthetic Ingredients Supply"
    assert assay["qualification"]["evidence_ref"] == "SQR-SYN-001 rev 1"
    assert assay["signature"]["meaning"] == "accepted"
    assert assay["label"] == accepted["assay"].label

    evidence, evidence_hash, blockers = reporting.preview(released)
    assert blockers == [], blockers
    issued = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=released,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    version = issued.versions.get(number=1)
    printed = render_to_string("reporting/_certificate.html", {"snapshot": version.snapshot})
    assert "Results accepted from the supplier's certificate of analysis." in printed
    assert "This laboratory did not perform these tests." in printed
    assert "COA-SYN-0001 dated 2026-11-02, issued by Synthetic Ingredients Supply" in printed
    assert "Supplier HPLC-07" in printed and "Limits stated: 98.0 - 102.0 %" in printed
    assert "Supplier result assay accepted in place of a test" in printed
    assert "Stated as: Negative in 25 g" in printed
    assert reporting.read_pdf(actor=people["reviewer"], version=version).startswith(b"%PDF-")
    # A released lot is frozen: nothing about its acceptances changes any more.
    with pytest.raises(ValidationError) as refusal:
        take_back(world, accepted["assay"], who="quality")
    assert refusal.value.messages == [reliance.QUARANTINE_ONLY]
    with pytest.raises(ValidationError) as refusal:
        propose(world, certificate, "identity")
    assert refusal.value.messages == [reliance.QUARANTINE_ONLY]


def test_a_lot_tested_in_full_keeps_the_evidence_shape_it_always_had(world):
    qualify(world)
    certify(world, fully_stated(), lot=world["lot"])
    sample_and_test(world)
    evidence = gates.lot_evidence(world["lot"])
    assert "supplier_results" not in evidence and len(evidence["results"]) == 5
    assert gates.lot_blockers(world["lot"]) == []


def test_laboratory_work_and_an_acceptance_exclude_each_other(world):
    people, lot = world["people"], world["lot"]
    qualify(world)
    certificate = certify(world, fully_stated(), lot=lot)
    sample = sampling.record_sampling(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-REL-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=10,
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    # Tests assigned before the supplier's result was proposed stay, untouched.
    tests, _ = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assay = next(t for t in tests if t.test_code == "assay")
    proposal = propose(world, certificate)
    with pytest.raises(ValidationError, match=f"in place of this test \\({proposal.label}\\)"):
        record(world, assay, "99.90")
    with pytest.raises(ValidationError, match="in place of this test"):
        analytical.record_contract_result(
            actor=people["analyst"],
            test=assay,
            expected_revision=assay.revision,
            laboratory_id=1,
            report_number="CLR-SYN-1",
            report_date=today(),
            raw_reference="DMS-SYN-CLR-1",
            readings=[{"value": 99, "qualifier": "", "outcome": "", "observed_text": ""}],
        )
    assert not Observation.objects.filter(test=assay).exists()
    accepted = accept(world, proposal)
    # The untouched open test is not work left undone; the other requirements still are.
    blockers = gates.lot_blockers(lot)
    assert not any("assay" in blocker for blocker in blockers), blockers
    assert any("impurity is incomplete" in blocker for blocker in blockers)
    assert analytical.supplier_refusal(assay) is not None
    # Withdrawn: the requirement goes back to the laboratory and the test takes its result.
    withdrawn = take_back(world, accepted, who="reviewer")
    assert (withdrawn.state, withdrawn.withdrawn_by) == (STATE.WITHDRAWN, people["reviewer"])
    assert withdrawn.withdrawal_reason == "Tested in the laboratory instead"
    # It reverses a signed decision, so it is signed too.
    signature = ElectronicSignature.objects.get(
        object_type=reliance.SIGNED_TYPE, object_id=str(withdrawn.pk), meaning="withdrawn"
    )
    assert signature.signer == people["reviewer"] and signature.revision == withdrawn.revision
    assert any("assay is incomplete" in blocker for blocker in gates.lot_blockers(lot))
    assay.refresh_from_db()
    record(world, assay, "99.90")
    assert Observation.objects.filter(test=assay).count() == 1
    with pytest.raises(ValidationError, match="already withdrawn"):
        take_back(world, withdrawn)
    with pytest.raises(ValidationError, match="already holds laboratory work"):
        propose(world, certificate)


def test_no_test_is_assigned_for_a_requirement_a_supplier_result_stands_for(world):
    people, lot = world["people"], world["lot"]
    certificate, accepted = accepted_lot(world, codes=["assay", "impurity"])
    sample = sampling.record_sampling(
        actor=people["analyst"],
        lot=lot,
        reference="SYN-REL-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=10,
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    tests, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assert holds == [] and sorted(t.test_code for t in tests) == ["identity", "salmonella", "tamc"]
    take_back(world, accepted["impurity"])
    blockers = gates.lot_blockers(lot)
    assert f"Sample {sample.reference} has no impurity test assigned." in blockers
    assert not any("assay" in blocker for blocker in blockers)
    tests, _ = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign the withdrawn requirement"
    )
    assert [t.test_code for t in tests] == ["impurity"]


def test_a_proposal_is_withdrawn_with_a_reason(world):
    qualify(world)
    certificate = certify(world, fully_stated(), lot=world["lot"])
    proposal = propose(world, certificate)
    for role in ("auditor", "admin"):
        with pytest.raises(PermissionDenied):
            take_back(world, proposal, who=role)
    with pytest.raises(ValidationError) as stale:
        take_back(world, proposal, who="analyst2", expected_revision=proposal.revision - 1)
    assert stale.value.messages == [reliance.STALE]
    with pytest.raises(ValidationError, match="A reason is required"):
        take_back(world, proposal, who="analyst2", reason="  ")
    proposal.refresh_from_db()
    assert proposal.state == STATE.PROPOSED
    withdrawn = take_back(world, proposal, who="analyst2", reason="Proposed on the wrong test")
    assert withdrawn.state == STATE.WITHDRAWN
    assert withdrawn.withdrawn_by == world["people"]["analyst2"]
    event = AuditEvent.objects.get(action="supplier_result.withdrawn")
    assert event.reason == "Proposed on the wrong test" and event.before == {"state": "proposed"}
    # Nothing was signed, so nothing is signed away.
    assert not ElectronicSignature.objects.filter(object_type=reliance.SIGNED_TYPE).exists()
    # The requirement is free again.
    assert propose(world, certificate).state == STATE.PROPOSED


def test_a_signed_acceptance_is_withdrawn_only_with_a_signature(world):
    people = world["people"]
    certificate, accepted = accepted_lot(world, codes=["assay"])
    acceptance = accepted["assay"]
    assert reliance.withdrawal_roles(acceptance) == reliance.SIGNED_WITHDRAW_ROLES
    # The reason-only path refuses a signed acceptance, whoever asks.
    with pytest.raises(ValidationError) as unsigned:
        reliance.withdraw_proposal(
            actor=people["reviewer"],
            acceptance=acceptance,
            expected_revision=acceptance.revision,
            reason="Without a signature",
        )
    assert unsigned.value.messages == [reliance.SIGNATURE_NEEDED]
    for role in ("analyst2", "auditor", "admin"):
        with pytest.raises(PermissionDenied):
            take_back(world, acceptance, who=role)
    with pytest.raises(ValidationError, match="Record changed"):
        take_back(world, acceptance, who="quality", expected_revision=acceptance.revision - 1)
    denied = AuditEvent.objects.filter(action="signature.denied").count()
    with pytest.raises(ValidationError, match="PIN was not accepted"):
        take_back(world, acceptance, who="quality", pin="00000000")
    assert AuditEvent.objects.filter(action="signature.denied").count() == denied + 1
    acceptance.refresh_from_db()
    assert acceptance.state == STATE.ACCEPTED
    lot = world["lot"]
    lot.refresh_from_db()
    revision = lot.revision
    withdrawn = take_back(world, acceptance, who="quality", reason="Supplier under review")
    assert (withdrawn.state, withdrawn.withdrawn_by) == (STATE.WITHDRAWN, people["quality"])
    assert withdrawn.accepted_at == acceptance.accepted_at  # The acceptance stays on record.
    meanings = list(
        ElectronicSignature.objects.filter(
            object_type=reliance.SIGNED_TYPE, object_id=str(withdrawn.pk)
        )
        .order_by("signed_at")
        .values_list("meaning", flat=True)
    )
    assert meanings == ["accepted", "withdrawn"]
    lot.refresh_from_db()
    assert lot.revision == revision + 1
    assert reliance.lot_reliance(lot)["accepted"] == {}


def test_an_acceptance_stops_standing_when_what_it_relied_on_changes(world):
    people, lot = world["people"], world["lot"]
    certificate, accepted = accepted_lot(world)
    sample_and_test(world)
    assert gates.lot_blockers(lot) == []
    # The certificate record is corrected: every acceptance taken from it stops standing.
    correct(world, certificate, fully_stated(), notes="Notes added")
    blockers = gates.lot_blockers(lot)
    assert len(blockers) == 4 * 2  # Each: the acceptance, and the requirement left unanswered.
    assert all(
        any(
            f"{accepted[code].label}: the accepted supplier result for {code} no longer stands: "
            "supplier certificate COA-SYN-0001 was corrected or withdrawn" in blocker
            for blocker in blockers
        )
        for code in RELIED
    )
    assert "has no assay test assigned." in " ".join(blockers)
    assert "supplier_results" not in gates.lot_evidence(lot)
    with pytest.raises(ValidationError):
        dispose(world, people["approver"])
    # Nothing was rewritten: the acceptance still says what it relied on, and is withdrawn.
    acceptance = accepted["assay"]
    acceptance.refresh_from_db()
    assert acceptance.state == STATE.ACCEPTED
    assert reliance.standing_problems(acceptance) == [
        "supplier certificate COA-SYN-0001 was corrected or withdrawn after the result was "
        "taken from it"
    ]
    for item in accepted.values():
        take_back(world, item, reason="Certificate record corrected")
    current = certificates.lot_chains(lot)[0][-1]
    for code in RELIED:
        accept(world, propose(world, current, code))
    assert gates.lot_blockers(lot) == []
    assert dispose(world, people["approver"]).state == "released"


@pytest.mark.parametrize("days", [1, 4])
def test_a_corrected_date_of_receipt_takes_the_ground_from_an_acceptance(world, days):
    """Inside the qualification's dates or outside them: the acceptance froze another day."""
    people, lot = world["people"], world["lot"]
    qualify(world, valid_from=today() - timedelta(days=3))
    certificate = certify(world, fully_stated(), lot=lot)
    acceptance = accept(world, propose(world, certificate))
    assert reliance.standing_problems(acceptance) == []
    receipt = quality.current_receipt(lot)
    values = {name: getattr(receipt, name) for name in quality.RECEIPT_FIELDS}
    corrected = today() - timedelta(days=days)
    quality.correct_receipt(
        actor=people["analyst2"],
        receipt=receipt,
        reason="Date received misread",
        **(values | {"received_on": corrected}),
    )
    assert reliance.standing_problems(acceptance) == [
        f"the date received was corrected from {today().isoformat()} to {corrected.isoformat()}"
    ]
    assert any("no longer stands" in blocker for blocker in gates.lot_blockers(lot))
    assert reliance.lot_reliance(lot)["accepted"] == {}
    # It still stands for the requirement until withdrawn: no laboratory work beside it.
    assert reliance.standing_codes(lot) == {"assay": acceptance.label}
    take_back(world, acceptance, reason="Date of receipt corrected")
    if days == 1:  # Still within the qualification: proposed again on the corrected date.
        again = accept(world, propose(world, certificate))
        assert again.evidence["received_on"] == corrected.isoformat()
    else:
        with pytest.raises(reliance.RelianceRefused, match="covers a lot received on"):
            propose(world, certificate)


def test_another_supplier_named_on_the_receipt_takes_the_ground_too(world):
    from suppliers.services import create_supplier

    people, lot = world["people"], world["lot"]
    certificate, accepted = accepted_lot(world, codes=["assay"])
    other = create_supplier(
        actor=people["author"],
        code="sup-syn-002",
        name="Another Synthetic Supply",
        location="Elsewhere, Exampleland",
        reason="Synthetic master data",
    )
    receipt = quality.current_receipt(lot)
    values = {name: getattr(receipt, name) for name in quality.RECEIPT_FIELDS}
    quality.correct_receipt(
        actor=people["analyst2"],
        receipt=receipt,
        reason="Supplier misread",
        **(values | {"supplier": other}),
    )
    assert reliance.standing_problems(accepted["assay"]) == [
        "the receipt details now name another supplier"
    ]
    assert reliance.lot_reliance(lot)["accepted"] == {}


def test_a_revocation_ends_further_reliance_and_keeps_what_was_accepted(world):
    lot = world["lot"]
    qualification = qualify(world)
    certificate = certify(world, fully_stated(), lot=lot)
    accepted = accept(world, propose(world, certificate))
    pending = propose(world, certificate, "impurity")
    assert quality.disposition_notices(lot)[0].endswith(f"{qualification.label}).")
    revoke(world, qualification)
    # Signed before the revocation: it stands, and says so where the disposition is signed.
    assert reliance.standing_problems(accepted) == []
    assert "assay" in reliance.lot_reliance(lot)["accepted"]
    (notice,) = quality.disposition_notices(lot)
    assert f"({qualification.label}) was revoked" in notice and "does not block" in notice
    # Not yet signed: it is relied on no further, and says so before anyone enters a PIN.
    assert reliance.standing_problems(pending) == [
        f"{qualification.label} was revoked before the proposal was accepted"
    ]
    assert any(
        f"{pending.label}: the proposal for impurity no longer stands" in blocker
        for blocker in gates.lot_blockers(lot)
    )
    with pytest.raises(ValidationError, match="no longer covers this result"):
        accept(world, pending)
    with pytest.raises(reliance.RelianceRefused, match="was revoked"):
        propose(world, certificate, "tamc")
    # The qualification lists what relied on it.
    assert list(qualification.acceptances.order_by("pk")) == [accepted, pending]


def test_database_refuses_edited_or_unfounded_acceptances(world):
    qualification = qualify(world)
    lot = world["lot"]
    certificate = certify(
        world,
        fully_stated(
            impurity=stated("impurity", "5", method="Supplier HPLC-09", limits="NMT 5 mg/g")
        ),
        lot=lot,
    )
    acceptance = propose(world, certificate)
    table = SupplierResultAcceptance.objects.filter(pk=acceptance.pk)

    def refused(write, message):
        with pytest.raises((DatabaseError, IntegrityError), match=message), transaction.atomic():
            write()

    refused(lambda: table.update(evidence={}), "never edited")
    refused(lambda: table.update(test_code="impurity"), "never edited")
    refused(lambda: table.update(state="accepted"), "supplier_acceptance_steps")
    refused(lambda: table.delete(), "cannot be deleted")

    def copy(code, **changes):
        result = line(certificate, code)
        values = {
            "lot": lot,
            "test_code": code,
            "result": result,
            "qualification": qualification,
            "requirement_hash": result.requirement_hash,
            "evidence": acceptance.evidence,
            "reason": "Direct write",
            "proposed_by": world["people"]["analyst"],
        } | changes
        return SupplierResultAcceptance.objects.create(**values)

    for unreadable in ({}, [], {"schema": reliance.SCHEMA}, acceptance.evidence | {"stated": 1}):
        refused(
            lambda unreadable=unreadable: copy("tamc", evidence=unreadable),
            "keeps the evidence it relies on",
        )

    refused(lambda: copy("assay"), "supplier_acceptance_one_standing")
    refused(
        lambda: copy("tamc", state="accepted", accepted_at=timezone.now()), "starts as a proposal"
    )
    refused(lambda: copy("impurity"), "does not meet the specification")
    refused(lambda: copy("tamc", test_code="assay2"), "another requirement")
    refused(lambda: copy("tamc", lot=world["plain_lot"]), "another lot")
    refused(lambda: copy("identity"), "does not cover this test")
    waiting = qualify(world, codes=["tamc"], sign=False)
    refused(lambda: copy("tamc", qualification=waiting), "Only an approved supplier qualification")
    accepted = accept(world, acceptance)
    refused(lambda: table.update(state="proposed"), "never edited")
    refused(lambda: table.update(accepted_at=timezone.now()), "never edited|cannot change")
    assert SupplierResultAcceptance.objects.count() == 1
    accepted.refresh_from_db()
    assert accepted.state == STATE.ACCEPTED and accepted.evidence == acceptance.evidence


def test_database_refuses_an_acceptance_changed_after_release(world):
    people = world["people"]
    certificate, accepted = accepted_lot(world)
    sample_and_test(world)
    dispose(world, people["approver"])
    table = SupplierResultAcceptance.objects.filter(pk=accepted["assay"].pk)
    with pytest.raises(DatabaseError, match="only while the lot is in quarantine"):
        with transaction.atomic():
            table.update(
                state="withdrawn",
                withdrawn_by=people["analyst"],
                withdrawn_at=timezone.now(),
                withdrawal_reason="Direct write",
            )
    accepted["assay"].refresh_from_db()
    assert accepted["assay"].state == STATE.ACCEPTED


@pytest.mark.parametrize("first", ["acceptance", "revocation"])
def test_an_acceptance_and_a_revocation_at_once(world, monkeypatch, first):
    """Both lock the qualification row. An acceptance that holds it first is signed and listed
    for assessment; after a revocation that committed first the acceptance is refused."""
    from core import services as core_services
    from laboratory.tests.helpers import run_interleaved

    qualification = qualify(world)
    certificate = certify(world, fully_stated(), lot=world["lot"])
    acceptance = propose(world, certificate)

    def sign():
        return accept(world, acceptance)

    def end():
        return revoke(world, qualification)

    if first == "acceptance":
        # Reached once the signer holds the acceptance, the lot and the qualification.
        outcome = run_interleaved(monkeypatch, qualifying, "covers", sign, end)
    else:
        outcome = run_interleaved(monkeypatch, core_services, "snapshot", end, sign)
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    qualification.refresh_from_db()
    acceptance.refresh_from_db()
    assert qualification.state == "revoked"
    if first == "acceptance":
        assert not isinstance(outcome["second"], Exception), outcome["second"]
        assert acceptance.state == STATE.ACCEPTED
        assert qualification.revoked_at > acceptance.accepted_at
    else:
        assert isinstance(outcome["second"], ValidationError), outcome["second"]
        assert "no longer covers this result" in outcome["second"].messages[0]
        assert acceptance.state == STATE.PROPOSED


def test_an_acceptance_and_a_disposition_cannot_both_slip_through(world, monkeypatch):
    """A disposition that holds the lot sees the proposal as it is committed: unanswered."""
    import core.services as signing
    from laboratory.tests.helpers import run_interleaved

    people, lot = world["people"], world["lot"]
    qualify(world)
    certificate = certify(world, fully_stated(), lot=lot)
    for code in ("impurity", "salmonella", "tamc"):
        accept(world, propose(world, certificate, code))
    acceptance = propose(world, certificate, "assay")
    sample_and_test(world)  # Identity only; assay stays a proposal.

    def release():
        return dispose(world, people["approver"])

    def sign():
        return accept(world, acceptance)

    # Reached once the disposition holds the lot at the revision it was opened with.
    outcome = run_interleaved(monkeypatch, signing, "snapshot", release, sign)
    assert isinstance(outcome["first"], ValidationError), outcome["first"]
    assert "awaits acceptance" in " ".join(outcome["first"].messages)
    assert not isinstance(outcome["second"], Exception), outcome["second"]
    lot.refresh_from_db()
    assert lot.state == "quarantine"
    assert dispose(world, people["approver"]).state == "released"


def test_received_date_must_be_a_calendar_day():
    finding = qualifying.reliance_finding(
        type("S", (), {"code": "s"})(),
        type("M", (), {"code": "m"})(),
        "assay",
        datetime.datetime(2026, 11, 1, 12, 0),
        [],
    )
    assert not finding.ok and finding.reasons == ("The date the lot was received is not known.",)


# Findings of the independent review ---------------------------------------------------------------


def sampled_tests(data, lot=None):
    """Sample the lot and assign its tests; {code: test}."""
    analyst = data["people"]["analyst"]
    sample = sampling.record_sampling(
        actor=analyst,
        lot=lot or data["lot"],
        reference="SYN-REL-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=10,
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    tests, _ = analytical.assign_tests(
        actor=analyst, sample=sample, reason="Assign frozen required tests"
    )
    return {test.test_code: test for test in tests}


def raw_file(data, test, content=b"synthetic chromatogram", name="assay-run.csv"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from analytical.rawdata import attach_raw_file

    return attach_raw_file(
        actor=data["people"]["analyst"],
        test=test,
        upload=SimpleUploadedFile(name, content, content_type="text/csv"),
        description="Synthetic raw data",
    )


def test_a_raw_data_file_is_laboratory_work(world):
    """A file attached to the test shows the laboratory tested the requirement: the supplier's
    result cannot then stand in, and no file is added beside one that stands."""
    qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    tests = sampled_tests(world)
    raw_file(world, tests["assay"])
    assert "raw-data file" in gates.tested_here(lot, "assay")
    with pytest.raises(ValidationError, match="already holds laboratory work"):
        propose(world, certificate, "assay")
    assert not SupplierResultAcceptance.objects.exists()
    # The other direction: while a proposal or an acceptance stands, no raw data is attached.
    proposal = propose(world, certificate, "impurity")
    with pytest.raises(ValidationError, match="in place of this test"):
        raw_file(world, tests["impurity"])
    accepted = accept(world, proposal)
    with pytest.raises(ValidationError, match="in place of this test"):
        raw_file(world, tests["impurity"])
    assert not tests["impurity"].raw_files.exists()
    assert reliance.standing_problems(accepted) == []


def test_another_certificate_that_contradicts_the_result_stops_reliance(world):
    qualify(world)
    lot = world["lot"]
    failing = certify(
        world,
        [stated("assay", "97.50", method="Supplier HPLC-07", limits="98.0 - 102.0 %")],
        lot=lot,
        number="COA-SYN-FAIL",
    )
    passing = certify(world, fully_stated(), lot=lot)
    with pytest.raises(ValidationError) as refusal:
        propose(world, passing, "assay")
    assert not isinstance(refusal.value, reliance.RelianceRefused)
    assert refusal.value.messages[0].startswith(
        "Supplier certificate COA-SYN-FAIL states a result for assay that does not meet"
    )
    # A requirement the other certificate does not contradict is unaffected.
    impurity = accept(world, propose(world, passing, "impurity"))
    # Once the contradicting record is withdrawn as wrong, the result can be relied on.
    withdraw(world, failing)
    assay = accept(world, propose(world, passing, "assay"))
    assert reliance.standing_problems(assay) == []
    # A contradicting certificate recorded afterwards takes the ground from the acceptance.
    certify(
        world,
        [stated("impurity", "6", method="Supplier HPLC-09", limits="NMT 5 mg/g")],
        lot=lot,
        number="COA-SYN-LATER",
    )
    assert reliance.standing_problems(impurity) == [
        "supplier certificate COA-SYN-LATER states a result for impurity that does not meet "
        "the specification"
    ]
    assert reliance.standing_problems(assay) == []
    assert "impurity" not in reliance.lot_reliance(lot)["accepted"]


def test_whoever_recorded_the_receipt_does_not_accept(world, django_user_model):
    """The acceptance freezes the supplier and the day of receipt, which are their data."""
    qualify(world)
    lot = world["lot"]
    receiver = person(django_user_model, "rel_receiver", "analyst", "reviewer")
    world["people"]["receiver"] = receiver
    receipt = quality.current_receipt(lot)
    values = {name: getattr(receipt, name) for name in quality.RECEIPT_FIELDS}
    quality.correct_receipt(
        actor=receiver,
        receipt=receipt,
        reason="Supplier lot number misread",
        **(values | {"supplier_lot": "SUP-LOT-SYN-002"}),
    )
    certificate = certify(world, fully_stated(), lot=lot)
    acceptance = propose(world, certificate)
    assert reliance.acceptance_denial(receiver, acceptance) == reliance.RECEIPT_AUTHOR
    with pytest.raises(PermissionDenied, match="receipt details of this lot"):
        accept(world, acceptance, who="receiver")
    # The original receipt was recorded by an analyst without the reviewer role.
    assert world["people"]["analyst2"].pk in quality.receipt_author_ids(lot)
    assert accept(world, acceptance).state == STATE.ACCEPTED


def test_qualification_signers_and_the_acceptor_are_not_authors_of_the_result(world):
    """Recording or signing a qualification is not authorship of what is later accepted under
    it, and the reviewer who accepts is treated as a reviewer of a test is: both may hold the
    quality role and sign the disposition. The proposer and the certificate recorders may not."""
    people, lot = world["people"], world["lot"]
    certificate, accepted = accepted_lot(world)
    sample_and_test(world)
    assert gates.lot_blockers(lot) == []
    for name in ("author", "approver", "reviewer", "quality"):
        assert quality.disposition_denial(people[name], lot) == "", name
    for name in ("analyst", "analyst2"):
        assert quality.disposition_denial(people[name], lot) == quality.SELF_DISPOSITION
    assert "a supplier result you proposed" in quality.SELF_DISPOSITION


def test_a_proposal_never_freezes_what_its_author_did_not_see(world):
    """The page showed one qualification; a newer one was signed before the submission."""
    qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    result = line(certificate, "assay")
    shown = shown_basis(result)
    newer = qualify(world)  # The newest covering qualification is the one relied on.
    with pytest.raises(ValidationError) as stale:
        propose(world, certificate, basis=shown)
    assert stale.value.messages == [reliance.BASIS_STALE]
    assert not SupplierResultAcceptance.objects.exists() and not refused_events().exists()
    for nothing in ("", "not-a-token"):
        with pytest.raises(ValidationError):
            reliance.propose_acceptance(
                actor=world["people"]["analyst"], result=result, basis=nothing, reason="Unseen"
            )
    acceptance = propose(world, certificate)
    assert acceptance.qualification == newer


def test_database_guards_repeat_the_checks_at_acceptance(world):
    people, lot = world["people"], world["lot"]
    qualification = qualify(world)
    certificate = certify(world, fully_stated(), lot=lot)
    acceptance = propose(world, certificate)
    other = propose(world, certificate, "impurity")
    table = SupplierResultAcceptance.objects

    def refused(write, message):
        with pytest.raises((DatabaseError, IntegrityError), match=message), transaction.atomic():
            write()

    def signed(row):
        return table.filter(pk=row.pk).update(state="accepted", accepted_at=timezone.now())

    def copy(code, source):
        result = line(source, code)
        return table.create(
            lot=lot,
            test_code=code,
            result=result,
            qualification=qualification,
            requirement_hash=result.requirement_hash,
            evidence=acceptance.evidence,
            reason="Direct write",
            proposed_by=people["analyst"],
        )

    corrected = correct(world, certificate, fully_stated(), notes="Notes added")
    refused(lambda: signed(acceptance), "Only the current record of a supplier certificate")
    refused(lambda: copy("tamc", certificate), "Only the current record of a supplier certificate")
    for row in (acceptance, other):
        take_back(world, row, reason="Certificate record corrected")
    again = propose(world, corrected)
    revoke(world, qualification)
    refused(lambda: signed(again), "Only an approved supplier qualification")
    refused(lambda: copy("tamc", corrected), "Only an approved supplier qualification")
    again.refresh_from_db()
    assert again.state == STATE.PROPOSED and table.filter(state="accepted").count() == 0


def test_database_refuses_a_proposal_for_a_released_lot(world):
    people = world["people"]
    qualification = qualify(world)
    certificate = certify(world, fully_stated(), lot=world["lot"])
    acceptance = accept(world, propose(world, certificate, "impurity"))
    for code in ("salmonella", "tamc"):
        accept(world, propose(world, certificate, code))
    tests = sampled_tests(world)
    for code, reading in (("identity", "conforms"), ("assay", "100.25")):
        record(world, tests[code], reading)
        submit(world, tests[code])
        from tests.test_result_types_journey import review

        review(world, tests[code])
    lot = dispose(world, people["approver"])
    result = line(certificate, "assay")
    with pytest.raises(DatabaseError, match="only while the lot is in quarantine"):
        with transaction.atomic():
            SupplierResultAcceptance.objects.create(
                lot=lot,
                test_code="assay",
                result=result,
                qualification=qualification,
                requirement_hash=result.requirement_hash,
                evidence=acceptance.evidence,
                reason="Direct write",
                proposed_by=people["analyst"],
            )
    # A lot answered partly by tests and partly by supplier results froze both kinds apart.
    frozen = lot.disposition_evidence["analytical"]
    assert sorted(r["test_code"] for r in frozen["results"]) == ["assay", "identity"]
    relied = [s["test_code"] for s in frozen["supplier_results"]]
    assert relied == ["impurity", "salmonella", "tamc"]


def test_a_lot_answered_entirely_by_supplier_results(world):
    """A rule set that keeps no test with the laboratory: the lot is still sampled, and the
    certificate says that this laboratory performed no test."""
    people = world["people"]
    rules = reliance_rules(world, code="synthetic-reliance-all", own=())
    lot = receive(world, rules, "SYN-REL-ALL")
    world["lot"] = lot
    qualify(world, codes=["identity", *RELIED])
    certificate = certify(world, fully_stated(), lot=lot)
    for code in ("identity", *RELIED):
        accept(world, propose(world, certificate, code))
    with pytest.raises(ValidationError, match="requires a sampled and tested record"):
        dispose(world, people["approver"])
    assert sampled_tests(world, lot) == {}  # Nothing left to test.
    assert gates.lot_blockers(lot) == []
    released = dispose(world, people["approver"])
    frozen = released.disposition_evidence["analytical"]
    assert frozen["results"] == [] and len(frozen["supplier_results"]) == 5
    evidence, evidence_hash, blockers = reporting.preview(released)
    assert blockers == [], blockers
    issued = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=released,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    snapshot = issued.versions.get(number=1).snapshot
    printed = render_to_string("reporting/_certificate.html", {"snapshot": snapshot})
    assert "No requirement of this lot was tested by this laboratory." in printed
    assert 'aria-label="Reportable results"' not in printed
    assert printed.count("Requirement source") == 1
    assert "Supplier result identity accepted in place of a test" in printed


@pytest.mark.parametrize("first", ["proposal", "observation"])
def test_a_proposal_and_an_observation_at_once(world, monkeypatch, first):
    """Both lock the lot: exactly one of the two stands, whichever came first."""
    from analytical import services as testing
    from laboratory.tests.helpers import run_interleaved

    qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    assay = sampled_tests(world)["assay"]
    shown = shown_basis(line(certificate, "assay"))  # The page was opened before either.

    def suggest():
        return propose(world, certificate, basis=shown)

    def observe():
        return record(world, assay, "99.90")

    if first == "proposal":
        # Reached once the proposal holds the lot and has passed its checks.
        outcome = run_interleaved(monkeypatch, reliance, "_evidence", suggest, observe)
    else:
        outcome = run_interleaved(monkeypatch, testing, "_touch", observe, suggest)
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    proposals = SupplierResultAcceptance.objects.count()
    observations = Observation.objects.filter(test=assay).count()
    assert (proposals, observations) == ((1, 0) if first == "proposal" else (0, 1))
