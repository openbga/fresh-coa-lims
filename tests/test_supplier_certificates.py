"""Supplier certificates: stated results against the lot's requirements, apart from own tests.

Uses the production requirement adapter and service-created approvals only (synthetic data).
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.contracts import canonical_hash
from analytical.models import AnalyticalTest
from core.models import AuditEvent
from core.services import set_pin
from quality import certificates
from quality import services as quality
from quality.models import (
    Lot,
    SupplierCertificate,
    SupplierCertificateResult,
    SupplierCertificateWithdrawal,
)
from sampling import services as sampling
from suppliers.services import create_supplier
from tests.receipts import on_site_receipt, supplier_receipt
from tests.test_integrated_journey import PASSWORD, PIN, dispose
from tests.test_result_types_journey import DEFAULT, build_world, record, review, submit

pytestmark = pytest.mark.django_db(transaction=True)

HEADER = {
    "number": "COA-SYN-0001",
    "issued_by": "Synthetic Ingredients Supply",
    "issued_on": datetime.date(2026, 11, 2),
    "stated_lot": "SUP-LOT-SYN-001",
    "document_ref": "DMS-SYN-COA-0001",
    "notes": "",
}
REASON = "Synthetic certificate transcribed"
EXTRA_ROLES = {
    "analyst2": ["analyst"],
    "certifier": ["analyst", "quality"],
    "quality": ["quality"],
    "auditor": ["auditor"],
    "admin": ["admin"],
}


def stated(code, value=None, *, less=False, outcome="", wording="", method="", limits=""):
    """One result as a certificate states it, with every key the service requires."""
    return {
        "test_code": code,
        "value": None if value is None else Decimal(value),
        "qualifier": "<" if less else "",
        "outcome": outcome,
        "stated_text": wording,
        "method": method,
        "limits": limits,
    }


def conforming():
    return [
        stated("identity", outcome="conforms", wording="Complies", method="Supplier IR-01"),
        stated("salmonella", outcome="absent", wording="Negative in 25 g"),
        stated("tamc", "10", less=True, limits="NMT 100 CFU/g"),
        stated("impurity", "4.20"),
        stated("assay", "99.60", method="Supplier HPLC-07", limits="98.0 - 102.0 %"),
    ]


def assign(data, lot=None):
    assignment = sampling.assign_requirements(
        actor=data["people"]["analyst"],
        lot=lot or data["lot"],
        material=data["material"],
        stage="incoming",
        reason="Assign approved synthetic policy",
    )
    assert assignment.status == "ready"
    return assignment


def build_supplied_world(django_user_model):
    """The mixed result-type world with a lot received from a supplier and its requirements."""
    data = build_world(django_user_model, with_assay=True)
    people = data["people"]
    for name, roles in EXTRA_ROLES.items():
        person = django_user_model.objects.create_user(username=f"sc_{name}", password=PASSWORD)
        person.groups.add(*[Group.objects.get_or_create(name=role)[0] for role in roles])
        set_pin(actor=person, pin=PIN, password=PASSWORD)
        people[name] = person
    data["rules"] = data["lot"].rules
    data["supplier"] = create_supplier(
        actor=people["author"],
        code="sup-syn-001",
        name="Synthetic Ingredients Supply",
        location="Sampletown, Exampleland",
        reason="Synthetic master data",
    )
    data["lot"] = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-SC-001",
        material=data["material"].name,
        rules=data["rules"],
        reason="Synthetic receipt",
        receipt=supplier_receipt(
            data["supplier"], manufacturer="Synthetic Maker", manufacturer_lot="MFG-SYN-0009"
        ),
    )
    assign(data)
    data["lot"].refresh_from_db()
    return data


@pytest.fixture
def world(django_user_model):
    return build_supplied_world(django_user_model)


def basis(lot):
    return certificates.requirements_basis(certificates.lot_requirements(lot)[0])


def certify(data, results=None, *, actor="analyst2", lot=None, reason=REASON, **changes):
    lot = lot or data["lot"]
    return certificates.record_certificate(
        actor=data["people"][actor],
        lot=lot,
        reason=reason,
        basis=changes.pop("basis", None) or basis(lot),
        results=conforming() if results is None else results,
        **(HEADER | changes),
    )


def correct(data, certificate, results=None, *, actor="analyst2", reason="Misread", **changes):
    return certificates.correct_certificate(
        actor=data["people"][actor],
        certificate=certificate,
        reason=reason,
        basis=changes.pop("basis", None) or basis(certificate.lot),
        results=conforming() if results is None else results,
        **(HEADER | changes),
    )


def withdraw(data, certificate, *, actor="analyst2", reason="Recorded on the wrong lot"):
    return certificates.withdraw_certificate(
        actor=data["people"][actor], certificate=certificate, reason=reason
    )


def sample_and_test(data, **readings):
    """Sample the lot and test every requirement without reassigning its requirements."""
    analyst = data["people"]["analyst"]
    sample = sampling.record_sampling(
        actor=analyst,
        lot=data["lot"],
        reference="SYN-SC-S001",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample
    tests, holds = analytical.assign_tests(
        actor=analyst, sample=sample, reason="Assign frozen required tests"
    )
    assert holds == [], holds
    readings = {**DEFAULT, "assay": "100.25", **readings}
    for test in tests:
        record(data, test, readings[test.test_code])
        submit(data, test)
        review(data, test)
    data["lot"].refresh_from_db()
    return data["lot"]


def counts():
    return (
        SupplierCertificate.objects.count(),
        SupplierCertificateResult.objects.count(),
        SupplierCertificateWithdrawal.objects.count(),
        AuditEvent.objects.filter(action__startswith="supplier_certificate.").count(),
    )


# Recording -------------------------------------------------------------------------------------


def test_stated_results_are_compared_with_the_frozen_requirements(world):
    lot, revision = world["lot"], world["lot"].revision
    required, holds = certificates.lot_requirements(lot)
    # The order of the approved specification content: by test code.
    assert holds == [] and list(required) == ["assay", "identity", "impurity", "salmonella", "tamc"]
    certificate = certify(
        world,
        [
            stated("assay", "99.60", method="Supplier HPLC-07", limits="98.0 - 102.0 %"),
            stated("impurity", "5"),  # The approved limit is "less than 5": 5 does not meet it.
            stated("tamc", "10", less=True),
            stated("identity", outcome="conforms", wording=" Complies "),
            stated("salmonella", outcome="present", wording="Detected in 25 g"),
        ],
    )
    lines = {line.test_code: line for line in certificate.results.all()}
    # Stored in specification order whatever the order of entry.
    assert [line.test_code for line in certificate.results.all()] == list(required)
    assert [line.position for line in certificate.results.all()] == [1, 2, 3, 4, 5]
    assert certificate.result_count == 5 and certificate.recorded_by == world["people"]["analyst2"]
    assay = lines["assay"]
    assert (assay.value, assay.value_text, assay.qualifier, assay.conforms) == (
        Decimal("99.6"),
        "99.60",  # As stated: the trailing zero is kept.
        "",
        True,
    )
    assert (assay.method, assay.limits) == ("Supplier HPLC-07", "98.0 - 102.0 %")
    assert (lines["impurity"].value_text, lines["impurity"].conforms) == ("5", False)
    # A less-than result is kept as stated and never becomes zero or the number.
    tamc = lines["tamc"]
    assert (tamc.value, tamc.qualifier, tamc.value_text, tamc.conforms) == (
        Decimal("10"),
        "<",
        "<10",
        True,
    )
    identity = lines["identity"]
    assert (identity.outcome, identity.value, identity.value_text, identity.stated_text) == (
        "conforms",
        None,
        "Conforms",
        "Complies",
    )
    assert identity.conforms and not lines["salmonella"].conforms
    assert lines["salmonella"].value_text == "Present"
    # Each result keeps the exact requirement it was compared with.
    for code, (payload, _) in required.items():
        assert lines[code].requirement == payload
        assert lines[code].requirement_hash == canonical_hash(payload)
    lot.refresh_from_db()
    assert lot.revision == revision + 1
    event = AuditEvent.objects.get(action="supplier_certificate.recorded")
    assert (event.actor, event.reason, event.before) == (world["people"]["analyst2"], REASON, {})
    assert event.object_type == "quality.suppliercertificate"
    assert event.object_id == str(certificate.pk)
    assert event.after == certificates.certificate_content(certificate)
    assert event.after["results"][0] == {
        "test_code": "assay",
        "result": "99.60",
        "qualifier": "",
        "outcome": "",
        "stated": "",
        "method": "Supplier HPLC-07",
        "limits": "98.0 - 102.0 %",
        "conforms": True,
        "requirement_hash": assay.requirement_hash,
    }


def test_supplier_results_never_answer_a_requirement(world):
    """A certificate on which every result meets the specification replaces no laboratory test."""
    lot, people = world["lot"], world["people"]
    before = gates.lot_blockers(lot)
    certify(world)
    assert gates.lot_blockers(lot) == before
    assert not AnalyticalTest.objects.filter(lot=lot).exists()
    assert gates.lot_evidence(lot)["results"] == []
    with pytest.raises(ValidationError, match="sampled and tested record"):
        dispose(world, people["approver"])
    # Once the laboratory's own tests are reviewed the evidence holds those tests only.
    lot = sample_and_test(world)
    assert gates.lot_blockers(lot) == []
    evidence = gates.lot_evidence(lot)
    assert {result["test_code"] for result in evidence["results"]} == set(DEFAULT) | {"assay"}
    assert all(result["replicates"] for result in evidence["results"])
    released = dispose(world, people["approver"])
    assert released.state == "released"
    assert "supplier" not in str(released.disposition_evidence).lower()


def test_a_certificate_states_some_of_the_requirements(world):
    certificate = certify(world, [stated("tamc", "20")])
    assert [line.test_code for line in certificate.results.all()] == ["tamc"]
    assert certificate.results.get().position == 5  # Its place in the specification.


def test_a_lot_may_hold_several_certificates(world):
    first = certify(world, [stated("assay", "99.6")])
    second = certify(world, [stated("tamc", "20")], number="COA-SYN-0002", actor="analyst")
    chains = certificates.lot_chains(world["lot"])
    assert [chain[-1] for chain in chains] == [first, second]
    assert [item["certificate"] for item in certificates.lot_summary(world["lot"])] == [
        first,
        second,
    ]


def test_a_certificate_number_is_current_once_on_a_lot(world):
    """A second record of the same certificate is a duplicate entry, however it is typed."""
    first = certify(world)
    before = counts()
    for number in ("COA-SYN-0001", " coa-syn-0001 "):
        with pytest.raises(ValidationError) as refusal:
            certify(world, [stated("assay", "99")], number=number)
        assert refusal.value.message_dict == {"number": [certificates.DUPLICATE]}
    second = certify(world, [stated("assay", "99")], number="COA-SYN-0002")
    with pytest.raises(ValidationError) as refusal:
        correct(world, second, [stated("assay", "99")], number="COA-SYN-0001")
    assert refusal.value.message_dict == {"number": [certificates.DUPLICATE]}
    assert counts() == (before[0] + 1, before[1] + 1, 0, before[3] + 1)
    # A record keeps its own number through a correction, and a withdrawn record frees it.
    assert correct(world, first, [stated("assay", "98.5")]).number == "COA-SYN-0001"
    withdraw(world, second)
    assert certify(world, [stated("assay", "99")], number="COA-SYN-0002").corrects is None
    # Another lot may hold the same certificate number.
    other = quality.receive_lot(
        actor=world["people"]["analyst"],
        number="SYN-SC-002",
        material=world["material"].name,
        rules=world["rules"],
        reason="Synthetic receipt",
        receipt=supplier_receipt(world["supplier"]),
    )
    assign(world, other)
    assert certify(world, [stated("assay", "99")], lot=other).number == "COA-SYN-0001"


@pytest.mark.parametrize("actor", ["reviewer", "quality", "auditor", "admin", "approver"])
def test_only_analysts_record_correct_and_withdraw(world, actor):
    certificate = certify(world)
    before = counts()
    with pytest.raises(PermissionDenied):
        certify(world, actor=actor)
    with pytest.raises(PermissionDenied):
        correct(world, certificate, [stated("assay", "99")], actor=actor)
    with pytest.raises(PermissionDenied):
        withdraw(world, certificate, actor=actor)
    assert counts() == before


REFUSED_RESULTS = {
    "none": ([], "at least one result"),
    "not a list": ("assay", "at least one result"),
    "unknown test": ([stated("water", "1")], "not an approved requirement"),
    "twice": ([stated("assay", "99"), stated("assay", "100")], "more than once"),
    "missing key": ([{"test_code": "assay", "value": Decimal("99")}], "results are incomplete"),
    "extra key": ([stated("assay", "99") | {"conforms": True}], "results are incomplete"),
    "float": ([stated("assay") | {"value": 99.6}], "exact decimal number"),
    "no value": ([stated("assay")], "Enter the observed value"),
    "infinite": ([stated("assay", "Infinity")], "must be finite"),
    "fraction of a count": ([stated("tamc", "1.5")], "whole number"),
    "negative count": ([stated("tamc", "-1")], "whole number"),
    "less than zero": ([stated("tamc", "0", less=True)], "greater than zero"),
    "qualifier": ([stated("assay", "99") | {"qualifier": ">"}], "Unsupported result qualifier"),
    "nine decimals": ([stated("assay", "99.123456789")], "8 decimal places"),
    "exponent": ([stated("assay", "1E+2")], "plain digits"),
    "signed zero": ([stated("tamc", "-0")], "plain digits"),
    "signed zero with decimals": ([stated("impurity", "-0.00")], "plain digits"),
    "too large": ([stated("assay", "1234567890123.5")], "no more than 12 digits"),
    "wording on a number": ([stated("assay", "99", wording="OK")], "Only a qualitative result"),
    "outcome on a number": ([stated("assay", "99", outcome="conforms")], "observed value"),
    "number on an outcome": (
        [stated("identity", "1", outcome="conforms", wording="Complies")],
        "Choose the observed result",
    ),
    "other pair": (
        [stated("salmonella", outcome="conforms", wording="OK")],
        "Choose the observed result: Absent or Present",
    ),
    "no wording": ([stated("identity", outcome="conforms", wording="  ")], "wording of the result"),
    "long method": ([stated("assay", "99", method="m" * 201)], "at most 200 characters"),
    "long limits": ([stated("assay", "99", limits="l" * 201)], "at most 200 characters"),
}


@pytest.mark.parametrize("case", REFUSED_RESULTS)
def test_refused_results_record_nothing(world, case):
    results, message = REFUSED_RESULTS[case]
    revision = world["lot"].revision
    with pytest.raises(ValidationError) as refusal:
        certify(world, results)
    assert message in " ".join(refusal.value.messages)
    world["lot"].refresh_from_db()
    assert counts() == (0, 0, 0, 0) and world["lot"].revision == revision


def test_a_refused_result_names_its_test(world):
    with pytest.raises(ValidationError) as refusal:
        certify(world, [stated("assay", "99"), stated("tamc", "1.5")])
    assert refusal.value.messages == [
        "Total aerobic count: A count must be a whole number of zero or more."
    ]


REFUSED_HEADERS = {
    "number": ({"number": "  "}, "Enter the certificate number."),
    "issuer": ({"issued_by": ""}, "Enter who issued the certificate."),
    "lot": ({"stated_lot": ""}, "Enter the lot number printed on the certificate."),
    "document": ({"document_ref": " "}, "Enter where the certificate is kept."),
    "no date": ({"issued_on": None}, "Enter the date of the certificate."),
    "text date": ({"issued_on": "2026-11-02"}, "Enter the date of the certificate."),
    "moment": ({"issued_on": timezone.now()}, "Enter the date of the certificate."),
    "long number": ({"number": "n" * 81}, "at most 80 characters"),
}


@pytest.mark.parametrize("case", REFUSED_HEADERS)
def test_refused_certificate_details_record_nothing(world, case):
    changes, message = REFUSED_HEADERS[case]
    with pytest.raises(ValidationError) as refusal:
        certify(world, **changes)
    assert message in " ".join(refusal.value.messages)
    assert counts() == (0, 0, 0, 0)


def test_certificate_date_is_not_in_the_future_of_the_laboratory(world):
    today = timezone.localdate()
    with pytest.raises(ValidationError, match="cannot be in the future"):
        certify(world, issued_on=today + datetime.timedelta(days=1))
    assert certify(world, issued_on=today).issued_on == today


def test_certificate_details_are_complete_or_refused(world):
    lot = world["lot"]
    header = {key: value for key, value in HEADER.items() if key != "notes"}
    with pytest.raises(ValidationError, match="Certificate details are incomplete"):
        certificates.record_certificate(
            actor=world["people"]["analyst2"],
            lot=lot,
            reason=REASON,
            basis=basis(lot),
            results=conforming(),
            **header,
        )
    with pytest.raises(ValidationError, match="A reason is required"):
        certify(world, reason="  ")
    assert counts() == (0, 0, 0, 0)


def test_text_is_stored_without_surrounding_spaces(world):
    certificate = certify(
        world,
        [stated("assay", "99", method="  HPLC  ", limits=" 98-102 ")],
        number=" COA-SYN-0009 ",
        notes="  Retest date 2027-06  ",
    )
    line = certificate.results.get()
    assert (certificate.number, certificate.notes) == ("COA-SYN-0009", "Retest date 2027-06")
    assert (line.method, line.limits) == ("HPLC", "98-102")


# What the lot must be ---------------------------------------------------------------------------


def test_only_a_quarantined_lot_received_from_a_supplier_with_requirements(world):
    people, rules, material = world["people"], world["rules"], world["material"]
    on_site = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-SC-ONSITE",
        material=material.name,
        rules=rules,
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    assign(world, on_site)
    earlier = Lot.objects.create(
        number="SYN-SC-EARLIER", material=material.name, rules=rules, created_by=people["analyst"]
    )
    assign(world, earlier)
    unassigned = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-SC-UNASSIGNED",
        material=material.name,
        rules=rules,
        reason="Synthetic receipt",
        receipt=supplier_receipt(world["supplier"]),
    )
    for lot, message in [
        (on_site, certificates.NOT_SUPPLIED),
        (earlier, certificates.NO_RECEIPT),
        (unassigned, certificates.NO_REQUIREMENTS),
    ]:
        with pytest.raises(ValidationError) as refusal:
            certify(world, lot=lot, basis="unknown")
        assert refusal.value.messages[0] == message
    assert certificates.recording_blocker(on_site) == certificates.NOT_SUPPLIED
    assert certificates.recording_blocker(earlier) == certificates.NO_RECEIPT
    assert certificates.recording_blocker(unassigned) is None  # The page explains requirements.
    assert certificates.recording_blocker(world["lot"]) is None
    assert counts() == (0, 0, 0, 0)


def test_a_released_lot_keeps_its_certificates_unchanged(world):
    certificate = certify(world)
    sample_and_test(world)
    released = dispose(world, world["people"]["approver"])
    before = counts()
    assert certificates.recording_blocker(released) == certificates.QUARANTINE_ONLY
    for change in (
        lambda: certify(world, number="COA-SYN-LATE"),
        lambda: correct(world, certificate, [stated("assay", "99")]),
        lambda: withdraw(world, certificate),
    ):
        with pytest.raises(ValidationError) as refusal:
            change()
        assert refusal.value.messages == [certificates.QUARANTINE_ONLY]
    released.refresh_from_db()
    assert counts() == before and released.revision == world["lot"].revision + 1


def test_requirements_that_changed_after_the_page_opened_are_refused(world):
    lot = world["lot"]
    opened = basis(lot)
    assign(world)  # A new assignment: every requirement now names the new assignment.
    assert basis(lot) != opened
    with pytest.raises(ValidationError) as refusal:
        certify(world, basis=opened)
    assert refusal.value.messages == [certificates.REQUIREMENTS_STALE]
    assert counts() == (0, 0, 0, 0)
    assert certify(world).result_count == 5


def test_a_result_compared_with_replaced_requirements_is_marked(world):
    lot = world["lot"]
    certificate = certify(world, [stated("assay", "99.6")])
    hashes = certificates.current_hashes(lot)
    assert [row["replaced"] for row in certificates.result_rows(certificate, hashes)] == [False]
    assign(world)
    row = certificates.result_rows(certificate, certificates.current_hashes(lot))[0]
    assert row["replaced"] and row["line"].conforms  # The comparison stands as recorded.
    summary = certificates.lot_summary(lot)[0]
    assert [r["line"].test_code for r in summary["replaced"]] == ["assay"]
    # The same stated values are a change: the result is compared with the current requirement.
    corrected = correct(world, certificate, [stated("assay", "99.6")], reason="Compare again")
    new = certificates.result_rows(corrected, certificates.current_hashes(lot))[0]
    assert not new["replaced"]
    assert new["line"].requirement_hash != row["line"].requirement_hash


# Corrections ------------------------------------------------------------------------------------


def test_correction_adds_a_linked_record_and_keeps_the_original(world):
    lot = world["lot"]
    original = certify(world)
    lot.refresh_from_db()
    revision = lot.revision
    results = conforming()
    results[4] = stated("assay", "97.90", method="Supplier HPLC-07", limits="98.0 - 102.0 %")
    corrected = correct(world, original, results, actor="analyst", notes="Second page read")
    assert corrected.corrects == original and corrected.recorded_by == world["people"]["analyst"]
    original.refresh_from_db()
    assert original.corrected_by == corrected
    assert original.results.get(test_code="assay").value_text == "99.60"  # Kept as recorded.
    assert not corrected.results.get(test_code="assay").conforms
    assert [chain[-1] for chain in certificates.lot_chains(lot)] == [corrected]
    assert certificates.lot_chains(lot)[0] == [original, corrected]
    lot.refresh_from_db()
    assert lot.revision == revision + 1
    event = AuditEvent.objects.get(action="supplier_certificate.corrected")
    assert event.before == certificates.certificate_content(original)
    assert event.after == certificates.certificate_content(corrected)
    assert (event.before["results"][0]["result"], event.after["results"][0]["result"]) == (
        "99.60",
        "97.90",
    )
    assert event.after["corrects"] == original.pk and event.reason == "Misread"


def test_refused_corrections_change_nothing(world):
    original = certify(world)
    before = counts()
    with pytest.raises(ValidationError, match="The correction changes nothing"):
        correct(world, original)
    with pytest.raises(ValidationError, match="A reason is required"):
        correct(world, original, [stated("assay", "99")], reason="")
    with pytest.raises(ValidationError, match="at least one result"):
        correct(world, original, [])
    assert counts() == before
    # A correction prepared before the lot's requirements changed is refused like a new record.
    opened = basis(original.lot)
    assign(world)
    with pytest.raises(ValidationError) as refusal:
        correct(world, original, [stated("assay", "99")], basis=opened)
    assert refusal.value.messages == [certificates.REQUIREMENTS_STALE]
    assert counts() == before
    # The value as stated is part of the record: another precision is a change.
    results = conforming()
    results[4] = stated("assay", "99.6", method="Supplier HPLC-07", limits="98.0 - 102.0 %")
    corrected = correct(world, original, results)
    assert corrected.results.get(test_code="assay").value_text == "99.6"
    # Only the current record of a certificate is corrected.
    with pytest.raises(ValidationError) as refusal:
        correct(world, original, [stated("assay", "98")])
    assert refusal.value.messages == [certificates.CERTIFICATE_STALE]
    assert certificates.change_blocker(original) == certificates.CERTIFICATE_STALE
    assert certificates.change_blocker(corrected) is None


def test_simultaneous_corrections_of_one_record_cannot_both_apply(world, monkeypatch):
    from laboratory.tests.helpers import run_interleaved

    lot = world["lot"]
    original = certify(world)

    def change(actor, value):
        return lambda: correct(world, original, [stated("assay", value)], actor=actor)

    outcome = run_interleaved(
        monkeypatch, certificates, "record_event", change("analyst", "99"), change("analyst2", "98")
    )
    assert isinstance(outcome["first"], SupplierCertificate)
    assert isinstance(outcome["second"], ValidationError)
    assert outcome["second"].messages == [certificates.CERTIFICATE_STALE]
    lot.refresh_from_db()
    assert SupplierCertificate.objects.filter(lot=lot).count() == 2
    assert certificates.lot_chains(lot)[0][-1].results.get().value_text == "99"


def before_commit():
    """Where a direct write pauses, holding its locks, while another transaction starts."""


@pytest.mark.parametrize("first", ["correction", "withdrawal"])
def test_database_makes_a_correction_and_a_withdrawal_wait_for_each_other(
    world, monkeypatch, first
):
    """Written directly, without the lot lock the services take: the row lock in the insert
    guards decides, so whichever commits first the other is refused."""
    import sys

    from laboratory.tests.helpers import run_interleaved

    certificate = certify(world, [stated("assay", "99.6")])
    line = certificate.results.get()
    analyst = world["people"]["analyst"]

    def correction():
        with transaction.atomic():
            record = copy_of(certificate, corrects=certificate, result_count=1)
            record.save()
            line_of(record, line).save()
            before_commit()
        return record

    def withdrawal():
        with transaction.atomic():
            made = SupplierCertificateWithdrawal.objects.create(
                certificate=certificate, reason="Direct write", withdrawn_by=analyst
            )
            before_commit()
        return made

    writes = [correction, withdrawal] if first == "correction" else [withdrawal, correction]
    outcome = run_interleaved(monkeypatch, sys.modules[__name__], "before_commit", *writes)
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], DatabaseError)
    refusal = (
        "Only the current record of a supplier certificate can be withdrawn"
        if first == "correction"
        else "A withdrawn supplier certificate cannot be corrected"
    )
    assert refusal in str(outcome["second"])
    assert (
        SupplierCertificate.objects.filter(corrects=certificate).count()
        + SupplierCertificateWithdrawal.objects.filter(certificate=certificate).count()
    ) == 1


def test_sampling_and_a_certificate_by_one_analyst_do_not_deadlock(world, monkeypatch):
    """Both lock the account and then the lot, so one waits for the other and both apply."""
    from laboratory.tests.helpers import run_interleaved
    from sampling.models import SamplingRecord

    lot, analyst = world["lot"], world["people"]["analyst2"]
    revision = lot.revision

    def sample():
        return sampling.record_sampling(
            actor=analyst,
            lot=lot,
            reference="SYN-SC-S900",
            sampled_at=timezone.now(),
            containers_total=1,
            containers_sampled=1,
            container_ids="SYN-C001",
            quantity=Decimal("10"),
            quantity_unit="g",
            location="Synthetic sampling booth",
            reason="Synthetic controlled sampling",
        )

    # The sampling transaction holds the lot when it checks whether sampling may be recorded.
    outcome = run_interleaved(
        monkeypatch, sampling, "sampling_blocker", sample, lambda: certify(world)
    )
    assert isinstance(outcome["first"], SamplingRecord), outcome["first"]
    assert isinstance(outcome["second"], SupplierCertificate), outcome["second"]
    lot.refresh_from_db()
    assert lot.revision == revision + 2


# Withdrawal -------------------------------------------------------------------------------------


def test_withdrawal_keeps_the_record_and_ends_its_changes(world):
    lot = world["lot"]
    certificate = certify(world)
    lot.refresh_from_db()
    revision = lot.revision
    withdrawal = withdraw(world, certificate, actor="analyst")
    assert withdrawal.certificate == certificate
    assert withdrawal.withdrawn_by == world["people"]["analyst"]
    certificate.refresh_from_db()
    assert certificates.is_withdrawn(certificate) and certificate.results.count() == 5
    lot.refresh_from_db()
    assert lot.revision == revision + 1
    event = AuditEvent.objects.get(action="supplier_certificate.withdrawn")
    assert event.before == certificates.certificate_content(certificate)
    assert (event.after, event.reason) == ({"withdrawn": True}, "Recorded on the wrong lot")
    summary = certificates.lot_summary(lot)
    assert [(item["certificate"], item["withdrawn"]) for item in summary] == [(certificate, True)]
    before = counts()
    for change in (
        lambda: correct(world, certificate, [stated("assay", "99")]),
        lambda: withdraw(world, certificate),
    ):
        with pytest.raises(ValidationError) as refusal:
            change()
        assert refusal.value.messages == [certificates.WITHDRAWN]
    assert counts() == before
    assert certificates.change_blocker(certificate) == certificates.WITHDRAWN
    # The lot can hold the right certificate afterwards.
    assert certify(world, number="COA-SYN-0002").corrects is None


def test_withdrawal_needs_a_reason_and_the_current_record(world):
    original = certify(world)
    corrected = correct(world, original, [stated("assay", "99")])
    before = counts()
    with pytest.raises(ValidationError, match="A reason is required"):
        withdraw(world, corrected, reason="  ")
    with pytest.raises(ValidationError) as refusal:
        withdraw(world, original)
    assert refusal.value.messages == [certificates.CERTIFICATE_STALE]
    assert counts() == before


# Independence -----------------------------------------------------------------------------------


@pytest.mark.parametrize("authored", ["recorded", "corrected", "withdrew"])
def test_certificate_author_cannot_sign_the_disposition(world, client, authored):
    """Recording, correcting or withdrawing a supplier certificate is authorship of lot data."""
    from django.urls import reverse

    people, lot = world["people"], world["lot"]
    certifier = people["certifier"]  # Analyst and quality: nothing else on this lot is theirs.
    if authored == "recorded":
        certificate = certify(world, actor="certifier")
        correct(world, certificate, [stated("assay", "99")], actor="analyst2")
    else:
        certificate = certify(world, actor="analyst2")
        if authored == "corrected":
            correct(world, certificate, [stated("assay", "99")], actor="certifier")
        else:
            withdraw(world, certificate, actor="certifier")
    lot = sample_and_test(world)
    assert certifier.pk in certificates.certificate_author_ids(lot)
    assert certifier.pk not in quality.receipt_author_ids(lot)
    assert certifier.pk not in gates.lot_author_ids(lot)
    assert certifier.pk not in sampling.lot_author_ids(lot)
    assert quality.disposition_denial(certifier, lot) == quality.SELF_DISPOSITION
    client.force_login(certifier)
    page = client.get(reverse("quality:disposition", args=[lot.pk]))
    assert page.status_code == 403
    assert b"own receipt, supplier certificate, sampling" in page.content
    assert b'name="pin"' not in page.content
    with pytest.raises(ValidationError, match="own receipt, supplier certificate, sampling"):
        dispose(world, certifier)
    lot.refresh_from_db()
    assert lot.state == "quarantine"
    assert dispose(world, people["approver"]).state == "released"


def test_a_change_makes_an_open_disposition_page_stale(world):
    certificate = certify(world)
    lot = sample_and_test(world)
    opened = lot.revision
    correct(world, certificate, [stated("assay", "97")])
    with pytest.raises(ValidationError, match="changed"):
        quality.dispose_lot(
            actor=world["people"]["approver"],
            pin=PIN,
            lot=lot,
            expected_revision=opened,
            reason="Signed from a page opened before the correction",
        )
    lot.refresh_from_db()
    assert lot.state == "quarantine"


def test_disposition_notice_names_a_supplier_result_outside_the_specification(world):
    lot = world["lot"]
    assert certificates.disposition_notices(lot) == []
    certify(world)
    assert certificates.disposition_notices(lot) == []
    failing = certify(
        world, [stated("assay", "97.5"), stated("tamc", "500")], number="COA-SYN-0002"
    )
    notices = certificates.disposition_notices(lot)
    assert len(notices) == 1
    assert "Supplier certificate COA-SYN-0002" in notices[0]
    assert "Assay, Total aerobic count" in notices[0] and "do not block" in notices[0]
    withdraw(world, failing)
    assert certificates.disposition_notices(lot) == []


def test_lot_number_on_the_certificate_is_checked_against_the_receipt(world):
    lot = world["lot"]
    receipt = quality.current_receipt(lot)
    assert (receipt.supplier_lot, receipt.manufacturer_lot) == ("SUP-LOT-SYN-001", "MFG-SYN-0009")
    for printed, outcome in [
        ("SUP-LOT-SYN-001", "match"),
        (" sup-lot-syn-001 ", "match"),
        ("MFG-SYN-0009", "match"),
        ("SUP-LOT-SYN-002", "differs"),
    ]:
        certificate = SupplierCertificate(stated_lot=printed)
        assert certificates.lot_number_check(certificate, receipt) == outcome
    receipt.supplier_lot = receipt.manufacturer_lot = ""
    assert certificates.lot_number_check(SupplierCertificate(stated_lot="X"), receipt) == ""
    assert certificates.lot_number_check(SupplierCertificate(stated_lot="X"), None) == ""


# Database guards --------------------------------------------------------------------------------


def copy_of(certificate, **changes):
    values = {name: getattr(certificate, name) for name in certificates.HEADER_FIELDS}
    values |= {
        "lot": certificate.lot,
        "result_count": certificate.result_count,
        "reason": "Direct write",
        "recorded_by": certificate.recorded_by,
    }
    return SupplierCertificate(**(values | changes))


def line_of(certificate, source, **changes):
    values = {
        name: getattr(source, name)
        for name in (
            "position",
            "test_code",
            "value",
            "qualifier",
            "outcome",
            "value_text",
            "stated_text",
            "method",
            "limits",
            "requirement",
            "requirement_hash",
            "conforms",
        )
    }
    return SupplierCertificateResult(certificate=certificate, **(values | changes))


def delete_row(table, pk):
    """A delete as the database sees it, without the ORM's own protection of related rows."""
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [pk])


def refused(write, message, error=DatabaseError):
    with pytest.raises(error) as refusal, transaction.atomic():
        write()
    assert message in str(refusal.value)


def test_database_keeps_certificate_records_as_recorded(world):
    certificate = certify(world)
    withdrawn = certify(world, [stated("assay", "99")], number="COA-SYN-0002")
    withdrawal = withdraw(world, withdrawn)
    line = certificate.results.get(test_code="assay")
    unchanged = "Historical evidence cannot be updated or deleted"
    refused(
        lambda: SupplierCertificate.objects.filter(pk=certificate.pk).update(notes="x"), unchanged
    )
    refused(lambda: delete_row("quality_suppliercertificate", withdrawn.pk), unchanged)
    refused(
        lambda: SupplierCertificateResult.objects.filter(pk=line.pk).update(conforms=False),
        unchanged,
    )
    refused(lambda: SupplierCertificateResult.objects.filter(pk=line.pk).delete(), unchanged)
    refused(
        lambda: SupplierCertificateWithdrawal.objects.filter(pk=withdrawal.pk).update(reason="x"),
        unchanged,
    )
    refused(
        lambda: SupplierCertificateWithdrawal.objects.filter(pk=withdrawal.pk).delete(), unchanged
    )
    certificate.refresh_from_db()
    assert certificate.notes == "" and certificate.results.count() == 5


def test_database_seals_the_results_of_a_record(world):
    certificate = certify(world, [stated("assay", "99.6")])
    line = certificate.results.get()
    payload, _ = certificates.lot_requirements(world["lot"])[0]["tamc"]
    extra = line_of(
        certificate,
        line,
        position=3,
        test_code="tamc",
        requirement=payload,
        requirement_hash=canonical_hash(payload),
    )
    refused(extra.save, "holds only the results it was recorded with")
    # A record states how many results it holds and is refused with fewer when it commits.
    refused(
        lambda: copy_of(certificate, number="COA-SYN-SHORT", result_count=2).save(),
        "recorded together with all of its results",
    )
    refused(
        lambda: copy_of(certificate, number="COA-SYN-EMPTY", result_count=0).save(),
        "supplier_certificate_has_results",
        IntegrityError,
    )
    assert counts()[:2] == (1, 1)


def test_database_refuses_rows_that_are_not_a_stated_result(world):
    certificate = certify(world, [stated("assay", "99.6")])
    line = certificate.results.get()

    def write(**changes):
        def save():
            record = copy_of(certificate, number="COA-SYN-SHAPE", result_count=1)
            record.save()
            line_of(record, line, **changes).save()

        return save

    shape = "supplier_result_shape"
    refused(write(outcome="conforms"), shape, IntegrityError)  # A number and an outcome.
    refused(write(value=None), shape, IntegrityError)
    refused(write(qualifier=">"), shape, IntegrityError)
    refused(write(stated_text="Complies"), shape, IntegrityError)  # Wording on a number.
    refused(
        write(value=None, outcome="conforms", value_text="Conforms", stated_text=" "),
        shape,
        IntegrityError,
    )
    refused(write(value_text=""), "supplier_result_stated", IntegrityError)
    refused(
        lambda: copy_of(certificate, number="", result_count=1).save(),
        "supplier_certificate_stated",
        IntegrityError,
    )

    def twice():
        record = copy_of(certificate, number="COA-SYN-TWICE", result_count=2)
        record.save()
        line_of(record, line).save()
        line_of(record, line, position=2).save()

    refused(twice, "supplier_result_one_per_test", IntegrityError)
    assert counts()[:2] == (1, 1)


def test_database_refuses_changes_to_other_lots_and_closed_records(world):
    people, lot = world["people"], world["lot"]
    certificate = certify(world, [stated("assay", "99.6")])
    line = certificate.results.get()
    other = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-SC-002",
        material=world["material"].name,
        rules=world["rules"],
        reason="Synthetic receipt",
        receipt=supplier_receipt(world["supplier"]),
    )

    def linked(**changes):
        def save():
            record = copy_of(certificate, result_count=1, **changes)
            record.save()
            line_of(record, line).save()

        return save

    refused(
        linked(lot=other, corrects=certificate),
        "belongs to the lot of the record it corrects",
    )
    withdrawn = certify(world, [stated("assay", "99")], number="COA-SYN-0002")
    withdraw(world, withdrawn)
    refused(linked(corrects=withdrawn), "A withdrawn supplier certificate cannot be corrected")
    corrected = correct(world, certificate, [stated("assay", "98.5")])
    refused(
        lambda: SupplierCertificateWithdrawal.objects.create(
            certificate=certificate, reason="Direct write", withdrawn_by=people["analyst"]
        ),
        "Only the current record of a supplier certificate can be withdrawn",
    )
    refused(
        linked(corrects=certificate), "quality_suppliercertificate_corrects_id_key", IntegrityError
    )
    refused(
        lambda: SupplierCertificateWithdrawal.objects.create(
            certificate=corrected, reason="", withdrawn_by=people["analyst"]
        ),
        "supplier_certificate_withdrawal_reason",
        IntegrityError,
    )
    assert SupplierCertificate.objects.filter(lot=lot).count() == 3
    assert not SupplierCertificate.objects.filter(lot=other).exists()


def test_database_refuses_certificate_rows_for_a_released_lot(world):
    people = world["people"]
    certificate = certify(world, [stated("assay", "99.6")])
    line = certificate.results.get()
    sample_and_test(world)
    dispose(world, people["approver"])
    quarantine = "only while the lot is in quarantine"

    def late():
        record = copy_of(certificate, number="COA-SYN-LATE", result_count=1)
        record.save()
        line_of(record, line).save()

    refused(late, "recorded " + quarantine)
    refused(
        lambda: SupplierCertificateWithdrawal.objects.create(
            certificate=certificate, reason="Direct write", withdrawn_by=people["analyst"]
        ),
        "withdrawn " + quarantine,
    )
    assert counts()[:3] == (1, 1, 0)


def test_database_guard_waits_for_a_release_in_progress(world, monkeypatch):
    """A certificate written beside a disposition that has not committed yet is still refused."""
    import core.services as signing
    from laboratory.tests.helpers import run_interleaved

    certificate = certify(world, [stated("assay", "99.6")])
    line = certificate.results.get()
    lot = sample_and_test(world)

    def release():
        return quality.dispose_lot(
            actor=world["people"]["approver"],
            pin=PIN,
            lot=lot,
            expected_revision=lot.revision,
            reason="Synthetic disposition",
        )

    def direct_write():
        with transaction.atomic():
            record = copy_of(certificate, number="COA-SYN-BESIDE", result_count=1)
            record.save()
            line_of(record, line).save()

    outcome = run_interleaved(monkeypatch, signing, "record_event", release, direct_write)
    assert outcome["first"].state == "released"
    assert isinstance(outcome["second"], DatabaseError)
    assert "only while the lot is in quarantine" in str(outcome["second"])
    assert counts()[:2] == (1, 1)


def test_correction_and_disposition_cannot_both_apply(world, monkeypatch):
    """Whichever commits first, the other is refused: a release never signs unseen results."""
    import core.services as signing
    from laboratory.tests.helpers import run_interleaved

    certificate = certify(world, [stated("assay", "99.6")])
    lot = sample_and_test(world)

    def release():
        return quality.dispose_lot(
            actor=world["people"]["approver"],
            pin=PIN,
            lot=lot,
            expected_revision=lot.revision,
            reason="Synthetic disposition",
        )

    def change():
        return correct(world, certificate, [stated("assay", "97")])

    outcome = run_interleaved(monkeypatch, signing, "record_event", release, change)
    assert outcome["first"].state == "released"
    assert isinstance(outcome["second"], ValidationError)
    assert outcome["second"].messages == [certificates.QUARANTINE_ONLY]
    assert counts()[:2] == (1, 1)
