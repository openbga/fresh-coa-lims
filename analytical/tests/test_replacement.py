"""Tests of a lot when its requirements are replaced: content matching, supersession, repeats,
QC batches that hold a superseded test, and investigation lineages (PostgreSQL)."""

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction

from analytical import gates, replacement, services
from analytical.contracts import canonical_hash, content_hash
from analytical.fixtures import requirement_payload
from analytical.models import AnalyticalTest, Investigation
from core.models import AuditEvent

from .conftest import PIN, complete, fresh, pass_qc, record, review, submit
from .test_services import _authorize, _conclude, _oos, blockers

pytestmark = pytest.mark.django_db(transaction=True)

# {code: {key: value}} applied on top of the fixture requirements; a code mapped to None is
# no longer required. Reset for every test.
CHANGES = {}


class Revised:
    """The fixture requirements as a later document states them."""

    def requirements(self, lot):
        payloads = {}
        for code in lot.rules.policy["required_tests"]:
            if code in CHANGES and CHANGES[code] is None:
                continue
            payload = requirement_payload(code)
            payload["source"] = f"fixture:SYN-SPEC-{code.upper()}@2"
            payload.update(CHANGES.get(code, {}))
            payloads[code] = payload
        return payloads

    def methods(self):
        return []


@pytest.fixture(autouse=True)
def revised(settings):
    CHANGES.clear()
    yield settings
    CHANGES.clear()


def requirements(lot, settings, **changes):
    """Switch the lot's requirements to the revised document and return them."""
    CHANGES.update(changes)
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.tests.test_replacement.Revised"
    return Revised().requirements(fresh(lot))


def supersede(people, lot, payloads, who="quality"):
    """What the signed replacement does on the testing side: lock the tests, then the lot."""
    from quality.models import Lot

    with transaction.atomic():
        locked = replacement.lock(lot)
        Lot.objects.select_for_update().get(pk=lot.pk)
        return replacement.apply(
            actor=people[who],
            lot=lot,
            requirements=payloads,
            reason="Synthetic replacement",
            locked=locked,
        )


def test_a_test_answers_a_requirement_by_its_content_whatever_document_states_it(
    people, assigned, revised
):
    lot, _, tests = assigned
    complete(people, tests["identity"], "1.00")
    assert not any("identity" in b for b in blockers(lot))
    same = requirements(lot, revised)
    identity = fresh(tests["identity"])
    assert canonical_hash(same["identity"]) != identity.requirement_hash  # another source
    assert content_hash(same["identity"]) == content_hash(identity.requirement)
    assert not any("identity" in b for b in blockers(lot))
    evidence = gates.lot_evidence(fresh(lot))
    assert [r["test_code"] for r in evidence["results"]] == ["identity"]
    assert evidence["results"][0]["requirement_source"] == "fixture:SYN-SPEC-IDENTITY@1"
    rows = replacement.effects(lot, same)
    assert {row["test_code"]: row["effect"] for row in rows} == {
        "assay": "carried",
        "identity": "carried",
    }
    # Any difference in what is asked (here a limit) is another requirement.
    tightened = requirements(lot, revised, identity={"lower_limit": "0.95"})
    assert content_hash(tightened["identity"]) != content_hash(identity.requirement)
    assert any("superseded requirement" in b for b in blockers(lot))
    assert gates.lot_evidence(fresh(lot))["results"] == []


def test_superseded_tests_are_closed_and_repeated_under_the_new_requirement(
    people, assigned, revised
):
    lot, sample, tests = assigned
    complete(people, tests["identity"], "1.00")
    reviewed = fresh(tests["identity"]).revision
    payloads = requirements(lot, revised, identity={"lower_limit": "0.95"})
    rows = supersede(people, lot, payloads)
    assert [(r["test_code"], r["effect"], r["why"], r["state"]) for r in rows] == [
        ("assay", "carried", "", "open"),
        ("identity", "superseded", "changed", "reviewed"),
    ]
    identity, assay = fresh(tests["identity"]), fresh(tests["assay"])
    assert identity.state == "superseded" and identity.revision == reviewed + 1
    assert identity.reportable_display == "1.00" and identity.conforms is True
    assert assay.state == "open" and assay.revision == tests["assay"].revision
    event = AuditEvent.objects.get(action="test.superseded")
    assert event.object_id == str(identity.pk) and event.actor == people["quality"]
    assert event.after["why"] == "changed" and event.after["result"] == "1.00"
    now = blockers(lot)
    assert any("no identity test under the lot's current requirements" in b for b in now)
    assert not any(identity.label in b for b in now)  # a closed test blocks nothing itself
    # The laboratory's own work on the requirement still excludes a supplier's result.
    assert "already holds laboratory work" in gates.tested_here(lot, "identity")
    assert gates.tested_here(lot, "assay") == ""

    created, holds = services.assign_tests(
        actor=people["analyst"], sample=sample, reason="Repeat superseded tests"
    )
    assert holds == [] and len(created) == 1
    repeat = created[0]
    assert (repeat.kind, repeat.parent_id, repeat.sample_id, repeat.investigation_id) == (
        "revised",
        identity.pk,
        sample.pk,
        None,
    )
    assert repeat.requirement == payloads["identity"]
    assigned_event = AuditEvent.objects.filter(action="test.assigned").order_by("-occurred_at")[0]
    assert assigned_event.after["repeats"] == identity.pk
    assert services.assign_tests(actor=people["analyst"], sample=sample, reason="Again")[0] == []
    complete(people, repeat, "1.00")
    assert not any("identity" in b for b in blockers(lot))
    evidence = gates.lot_evidence(fresh(lot))
    result = next(r for r in evidence["results"] if r["test_code"] == "identity")
    assert (result["test"], result["kind"], result["lower_limit"]) == (repeat.pk, "revised", "0.95")
    assert {
        "test": identity.pk,
        "test_code": "identity",
        "kind": "original",
        "state": "superseded",
    } in evidence["excluded_tests"]
    # The authors of the superseded test stay authors of the lot's data.
    assert people["analyst"].pk in evidence["author_ids"]


def test_an_untouched_superseded_test_leaves_room_for_a_supplier_result(people, assigned, revised):
    lot, _, tests = assigned
    payloads = requirements(lot, revised, identity={"lower_limit": "0.95"})
    supersede(people, lot, payloads)
    assert fresh(tests["identity"]).state == "superseded"
    assert gates.tested_here(lot, "identity") == ""


def test_a_requirement_no_longer_asked_for_closes_its_tests(people, assigned, revised):
    lot, sample, tests = assigned
    complete(people, tests["identity"], "1.00")
    payloads = requirements(lot, revised, identity=None)
    rows = supersede(people, lot, payloads)
    assert [(r["test_code"], r["why"]) for r in rows if r["effect"] == "superseded"] == [
        ("identity", "not_required")
    ]
    assert services.assign_tests(actor=people["analyst"], sample=sample, reason="Again")[0] == []
    assert not any("identity" in b for b in blockers(lot))


def test_nothing_recorded_is_set_aside_unevaluated(people, assigned, revised):
    lot, _, tests = assigned
    record(people, tests["identity"], "1.30")  # recorded, outside the limits, not submitted
    payloads = requirements(lot, revised, identity={"upper_limit": "1.50"})
    rows = replacement.effects(lot, payloads)
    reasons = replacement.refusals(lot, rows)
    assert len(reasons) == 1 and "holds results or raw-data files that were not" in reasons[0]
    with pytest.raises(ValidationError, match="holds results or raw-data files that were not"):
        supersede(people, lot, payloads)
    _, investigation = submit(people, tests["identity"])
    reasons = replacement.refusals(lot, replacement.effects(lot, payloads))
    assert len(reasons) == 1 and f"{investigation.label} is open on this lot" in reasons[0]
    with pytest.raises(ValidationError, match="is open on this lot"):
        supersede(people, lot, payloads)
    assert fresh(tests["identity"]).state == "submitted"
    assert not AuditEvent.objects.filter(action="test.superseded").exists()


def test_new_requirements_testing_cannot_execute_are_held(people, assigned, revised):
    lot, _, _ = assigned
    payloads = requirements(lot, revised, identity={"replicates": 0})
    reasons = replacement.held(payloads)
    assert len(reasons) == 1 and reasons[0].startswith("Requirement for identity is held:")
    assert replacement.held({}) == ["No required tests in the new requirements."]
    from config.integrations import TestingUnderReplacement

    adapter = TestingUnderReplacement()
    found = adapter.effects(lot, payloads)
    assert found["refusals"] == reasons and found["supplier_results"] == []
    with transaction.atomic():
        locked = adapter.lock(lot)
        with pytest.raises(ValidationError, match="Requirement for identity is held"):
            adapter.apply(
                actor=people["quality"], lot=lot, requirements=payloads, reason="x", locked=locked
            )


def test_a_superseded_test_does_not_fix_a_batch_it_never_submitted_to(
    people, assigned, make_lot, batch, revised
):
    """Another lot's tests in the same batch are not stranded by a replacement."""
    lot, _, tests = assigned
    other_lot, other_sample = make_lot("SYN-LOT-2", tests=("assay",))
    other = services.assign_tests(actor=people["analyst"], sample=other_sample, reason="x")[0][0]
    for test in (tests["assay"], other):
        services.assign_to_batch(actor=people["analyst"], test=test, batch=batch, reason="Run")
    payloads = requirements(lot, revised, assay={"lower_limit": "96.0"})
    supersede(people, lot, payloads)
    assert fresh(tests["assay"]).state == "superseded"
    assert fresh(tests["assay"]).batch_id == batch.pk  # kept where it was
    assert not services.results_submitted(fresh(batch))
    pass_qc(people, batch)  # QC entry is still open
    record(people, other, "100.0", "100.2")
    submit(people, other)
    assert services.results_submitted(fresh(batch))
    assert review(people, other).state == "reviewed"
    assert other_lot.pk != lot.pk


def test_a_test_superseded_after_submission_keeps_its_batch_fixed(people, assigned, batch, revised):
    lot, _, tests = assigned
    services.assign_to_batch(actor=people["analyst"], test=tests["assay"], batch=batch, reason="x")
    pass_qc(people, batch)
    record(people, tests["assay"], "100.0", "100.2")
    submit(people, tests["assay"])
    supersede(people, lot, requirements(lot, revised, assay={"lower_limit": "96.0"}))
    assert fresh(tests["assay"]).state == "superseded"
    assert services.results_submitted(fresh(batch))
    with pytest.raises(ValidationError, match="QC cannot change"):
        services.correct_qc(
            actor=people["analyst2"],
            qc_result=batch.current_qc().get(check_code="blank"),
            value="0.02",
            raw_reference="x",
            reason="change",
        )


def test_rejecting_a_failed_batch_leaves_a_superseded_test_as_it_is(
    people, assigned, make_lot, batch, revised
):
    lot, _, tests = assigned
    _, other_sample = make_lot("SYN-LOT-2", tests=("assay",))
    other = services.assign_tests(actor=people["analyst"], sample=other_sample, reason="x")[0][0]
    for test in (tests["assay"], other):
        services.assign_to_batch(actor=people["analyst"], test=test, batch=batch, reason="Run")
    supersede(people, lot, requirements(lot, revised, assay={"lower_limit": "96.0"}))
    pass_qc(people, batch, control="90.0")
    services.reject_batch(
        actor=people["reviewer"],
        pin=PIN,
        batch=fresh(batch),
        expected_revision=fresh(batch).revision,
        reason="Control failed",
    )
    assert fresh(batch).state == "rejected"
    assert fresh(tests["assay"]).state == "superseded"
    assert not AnalyticalTest.objects.filter(parent=tests["assay"]).exists()  # no rerun for it
    assert fresh(other).state == "invalidated"
    assert AnalyticalTest.objects.get(parent=other).kind == "rerun"


def test_a_retest_lineage_is_repeated_on_the_sample_that_answers(people, assigned, revised):
    """Original invalidated by an investigation, retest reviewed, then the requirement is
    replaced: the repeat follows the retest, not the invalidated original."""
    lot, sample, test, investigation = _oos(people, assigned)
    review(people, test)
    services.add_entry(
        actor=people["analyst"],
        investigation=investigation,
        kind="assessment",
        text="Dilution flask 3 used wrong volume",
    )
    _authorize(people, investigation)
    retest = AnalyticalTest.objects.get(investigation=investigation)
    record(people, retest, "1.01", who="analyst2")
    submit(people, retest, who="analyst2")
    review(people, retest)
    _conclude(people, investigation, "invalidated", "Dilution error documented")
    assert not any("identity" in b for b in blockers(lot))
    payloads = requirements(lot, revised, identity={"lower_limit": "0.95"})
    rows = supersede(people, lot, payloads, who="quality2")
    # The invalidated original is closed already; only the retest that answered is superseded.
    assert [(r["label"], r["effect"]) for r in rows if r["test_code"] == "identity"] == [
        (retest.label, "superseded")
    ]
    assert fresh(test).state == "invalidated" and fresh(retest).state == "superseded"
    created, _ = services.assign_tests(actor=people["analyst"], sample=sample, reason="Repeat")
    assert [(t.kind, t.parent_id, t.investigation_id) for t in created] == [
        ("revised", retest.pk, None)
    ]
    complete(people, created[0], "1.00")
    assert not any("identity" in b for b in blockers(lot))
    assert Investigation.objects.get(pk=investigation.pk).outcome == "invalidated"
    result = next(
        r for r in gates.lot_evidence(fresh(lot))["results"] if r["test_code"] == "identity"
    )
    assert result["test"] == created[0].pk and result["kind"] == "revised"


def test_whoever_worked_on_a_superseded_test_does_not_reject_its_batch(
    people, assigned, make_lot, batch, revised
):
    """A superseded test is not rerun, but its raw data is still someone's work in the batch."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from analytical.rawdata import attach_raw_file

    lot, _, tests = assigned
    _, other_sample = make_lot("SYN-LOT-2", tests=("assay",))
    other = services.assign_tests(actor=people["analyst"], sample=other_sample, reason="x")[0][0]
    for test in (tests["assay"], other):
        services.assign_to_batch(actor=people["analyst"], test=test, batch=batch, reason="Run")
    attach_raw_file(
        actor=people["multi"],
        test=tests["assay"],
        upload=SimpleUploadedFile("run.csv", b"synthetic run", content_type="text/csv"),
        description="Synthetic raw data",
    )
    # A replacement refuses to set unsubmitted raw data aside, so this state does not arise
    # through the pages; the own-work rule holds all the same if it ever does.
    with pytest.raises(ValidationError, match="raw-data files that were not submitted"):
        supersede(people, lot, requirements(lot, revised, assay={"lower_limit": "96.0"}))
    AnalyticalTest.objects.filter(pk=tests["assay"].pk).update(state="superseded")
    assert fresh(tests["assay"]).state == "superseded"
    pass_qc(people, batch, control="90.0")
    with pytest.raises(ValidationError, match="containing your own work"):
        services.reject_batch(
            actor=people["multi"],
            pin=PIN,
            batch=fresh(batch),
            expected_revision=fresh(batch).revision,
            reason="Control failed",
        )
    assert fresh(batch).state == "open"


def test_a_superseded_contract_result_raises_no_disposition_notice(
    people, assigned, revised, monkeypatch
):
    from analytical import fixtures

    from .test_contract_results import report

    lot, _, tests = assigned
    report(people, tests["identity"], "1.00")
    submit(people, tests["identity"])
    monkeypatch.setattr(
        fixtures.SyntheticBench, "contract_notice", lambda self, evidence: "Approval revoked."
    )
    assert len(gates.lot_notices(lot)) == 1
    # Whatever a superseded test relied on, it is not part of the evidence being signed.
    supersede(people, lot, requirements(lot, revised, identity={"lower_limit": "0.95"}))
    assert fresh(tests["identity"]).state == "superseded"
    assert gates.lot_notices(lot) == []
