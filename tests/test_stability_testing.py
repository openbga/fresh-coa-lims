"""Stability testing with the production adapters: a released lot and its certificate stay as
they were, a QC batch carries a pull's tests, and testing a pull does not deadlock with the
study's own transitions (synthetic data only)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.models import AnalyticalTest, Investigation, Observation
from catalog import services as catalog
from core.models import AuditEvent, ElectronicSignature
from laboratory.tests.conftest import people  # noqa: F401  (shared synthetic role users)
from laboratory.tests.helpers import PIN as LAB_PIN
from laboratory.tests.helpers import run_interleaved
from quality.models import Lot, Sample
from reporting import services as reporting
from sampling import services as sampling
from stability import services as stability
from stability.models import Hold, Pull
from stability.tests.helpers import (
    accept,
    assign,
    observe,
    pulled,
    review,
    reviewed,
    specified_study,
    submit,
)
from tests.test_integrated_journey import (
    PIN,
    approve,
    assign_and_sample,
    dispose,
    integrated,  # noqa: F401
    observed_test,
)

pytestmark = pytest.mark.django_db(transaction=True)


def lot_record(lot):
    """The released lot's record as every reader sees it, as one comparable value."""
    lot = Lot.objects.get(pk=lot.pk)
    evidence, evidence_hash, blockers = reporting.preview(lot)
    return {
        "lot": (lot.state, lot.revision, lot.disposition_evidence),
        "samples": sorted(Sample.objects.filter(lot=lot).values_list("pk", flat=True)),
        "tests": sorted(AnalyticalTest.objects.filter(lot=lot).values_list("pk", flat=True)),
        "investigations": Investigation.objects.filter(lot=lot).count(),
        "holds": Hold.objects.filter(lot=lot).count(),
        "analytical_status": gates.lot_status(lot)[0],
        "analytical_evidence": gates.lot_evidence(lot),
        "sampling": sampling.lot_blockers(lot),
        "certificate": (evidence, evidence_hash, blockers),
        "history": AuditEvent.objects.filter(
            object_type="quality.lot", object_id=str(lot.pk)
        ).count(),
        "signatures": ElectronicSignature.objects.filter(
            object_type="quality.lot", object_id=str(lot.pk)
        ).count(),
    }


def released(data):
    """Release the integrated lot through sampling, testing, review and disposition, and
    issue its certificate. Returns (lot, certificate version)."""
    staff = data["people"]
    sample = assign_and_sample(data)
    test, _ = observed_test(data, sample, "100.25")
    analytical.review_test(
        actor=staff["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    lot = dispose(data, staff["approver"])
    _, evidence_hash, blockers = reporting.preview(lot)
    assert lot.state == "released" and blockers == []
    report = reporting.issue_report(
        actor=staff["approver"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    return lot, report.versions.get(number=1)


def shelf_life_of(data):
    """An approved shelf-life specification for the integrated material, with the integrated
    method (the analyst is already qualified for it)."""
    staff = data["people"]
    method = data["method"].method
    start, end = data["spec"].effective_from, data["spec"].effective_until
    specification, revision = catalog.create_specification(
        actor=staff["author"],
        code="synthetic-shelf-life",
        title="Synthetic shelf-life specification",
        material=data["material"],
        stage="stability",
        scope="general",
        basis="Synthetic shelf-life limits",
        effective_from=start,
        effective_until=end,
        reason="Synthetic shelf-life specification",
    )
    catalog.add_test_line(
        actor=staff["author"],
        revision=revision,
        reason="Synthetic shelf-life assay",
        code="assay",
        name="Assay",
        method=method,
        result_type="numeric",
        unit="%",
        lower_limit=Decimal("95"),
        upper_limit=Decimal("105"),
        lower_inclusive=True,
        upper_inclusive=True,
        reporting_decimals=2,
        replicates=1,
        replicate_limits=True,
        max_retests=1,
        required=True,
    )
    approve(revision, staff["approver"])
    return specification


def study_of(data, lot, specification):
    staff = data["people"]
    author = staff["receiver"]  # analyst only: authors the protocol, starts the study, pulls
    protocol = stability.create_protocol(
        actor=author,
        code="SYN-STB-REL",
        title="Synthetic stability protocol",
        product="Synthetic reference powder",
        document_ref="DOC-SYN-STB r1",
        document_url="",
        test_profile_ref="",
        specification=specification,
        basis="Synthetic basis, not a regulatory default",
        reason="Synthetic draft",
    )
    condition = stability.add_condition(
        actor=author,
        protocol=protocol,
        label="Long-term",
        setpoint="Synthetic setpoint",
        temperature_c=Decimal("25.0"),
        humidity_pct=Decimal("60.0"),
        reason="Synthetic condition",
    )
    for days in (0, 1):
        stability.add_timepoint(
            actor=author,
            protocol=protocol,
            condition=condition,
            label=f"Day {days}",
            interval_days=days,
            window_days=3,
            test_codes=["assay"],
            reason="Synthetic timepoint",
        )
    protocol.refresh_from_db()
    protocol = stability.approve_protocol(
        actor=staff["approver"],
        pin=PIN,
        protocol=protocol,
        expected_revision=protocol.revision,
        reason="Independent approval",
    )
    return stability.start_study(
        actor=author,
        identifier="STB-REL-001",
        protocol=protocol,
        lot=lot,
        container_closure="Synthetic marketed container",
        start_date=timezone.localdate(),
        reason="Synthetic study start",
    )


def pull_of(data, study, day):
    pull = study.pulls.get(timepoint__interval_days=day)
    return stability.record_pull(
        actor=data["people"]["receiver"],
        pull=pull,
        pulled_on=timezone.localdate(),
        quantity=Decimal("5"),
        quantity_unit="g",
        storage_location="Synthetic stability shelf",
        reason="Synthetic pull",
    )


def assayed(data, pull, value):
    """Assign, record, submit and review the pull's assay. Returns (test, investigation)."""
    staff = data["people"]
    (test,) = analytical.assign_pull_tests(
        actor=staff["analyst"], pull=pull, reason="Tests of the time point"
    )
    analytical.record_observation(
        actor=staff["analyst"],
        test=test,
        value=Decimal(value),
        raw_reference="RAW-SYN-STB-001 rev 1",
        reason="Synthetic stability observation",
    )
    test.refresh_from_db()
    test, investigation = analytical.submit_test(
        actor=staff["analyst"],
        test=test,
        expected_revision=test.revision,
        reason="Submit synthetic stability observation",
    )
    test = analytical.review_test(
        actor=staff["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    return test, investigation


def test_stability_testing_leaves_the_released_lot_and_its_certificate_unchanged(integrated):  # noqa: F811
    data, staff = integrated, integrated["people"]
    lot, version = released(data)
    pdf = reporting.read_pdf(actor=staff["reviewer"], version=version)
    before = lot_record(lot)
    study = study_of(data, lot, shelf_life_of(data))
    assert lot_record(lot) == before

    # A conforming time point: recorded, reviewed and signed like a release test.
    first = pull_of(data, study, 0)
    test, investigation = assayed(data, first, "99.80")
    assert investigation is None and test.lot_id is None and test.pull_id == first.pk
    assert test.requirement["source"].startswith("catalog:synthetic-shelf-life@v1#rev")
    first.refresh_from_db()
    accepted = stability.accept_pull(
        actor=staff["reviewer"],
        pin=PIN,
        pull=first,
        expected_revision=first.revision,
        reason="Pull and results reviewed",
    )
    assert accepted.outcome == "conforms"

    # A failing time point: investigated, confirmed and closed with its outcome.
    second = pull_of(data, study, 1)
    failing, investigation = assayed(data, second, "90.10")
    assert investigation.lot_id is None and not failing.conforms
    # Whoever investigates is an author of the pull's evidence and does not accept it; the
    # analyst already is one.
    analytical.add_entry(
        actor=staff["analyst"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic assessment: no laboratory error found",
    )
    investigation.refresh_from_db()
    analytical.conclude(
        actor=staff["approver"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="confirmed",
        assignable_cause="",
        reason="Out-of-specification stability result confirmed",
    )
    second.refresh_from_db()
    closed = stability.accept_pull(
        actor=staff["reviewer"],
        pin=PIN,
        pull=second,
        expected_revision=second.revision,
        reason="Pull and results reviewed",
    )
    assert closed.outcome == "fails"

    # Nothing of the released lot moved: its row, samples, tests, gates, frozen evidence,
    # history, signatures, the evidence a certificate would be issued or amended from, and
    # the certificate already issued.
    assert lot_record(lot) == before
    assert reporting.read_pdf(actor=staff["reviewer"], version=version) == pdf
    # The lot still takes no release testing; the testing of its pulls did not reopen it.
    with pytest.raises(ValidationError, match="no longer in quarantine"):
        analytical.assign_tests(
            actor=staff["analyst"],
            sample=Sample.objects.get(lot=lot),
            reason="Release testing after release",
        )


def test_a_qc_batch_carries_the_tests_of_a_pull(people, settings):  # noqa: F811
    assert settings.ANALYTICAL_REQUIREMENT_PROVIDER.endswith("CatalogRequirementProvider")
    study, config = specified_study(people, requires_batch=True)
    pull = pulled(people, study)
    lot_revision = study.lot.revision
    (test,) = assign(people, pull)
    with pytest.raises(ValidationError, match="QC batch"):
        observe(people, test)
    method = config["method"].code

    def batch_with(number):
        batch = analytical.create_batch(
            actor=people["analyst2"], number=number, method_code=method, reason="Synthetic run"
        )
        current = AnalyticalTest.objects.filter(pull=pull, state="open").get()
        analytical.assign_to_batch(
            actor=people["analyst2"], test=current, batch=batch, reason="Synthetic run"
        )
        return batch, current

    def control(batch, value):
        return analytical.record_qc(
            actor=people["analyst2"],
            batch=batch,
            check_code="control",
            value=Decimal(value),
            raw_reference="NB-STB-QC p1",
        )

    # A run whose control fails is rejected: the pull's test is invalidated and rerun.
    failed, original = batch_with("SYN-STB-QC-1")
    control(failed, "90.0")
    observe(people, original, "100.1")
    pull.refresh_from_db()
    before_rejection = pull.revision
    failed.refresh_from_db()
    analytical.reject_batch(
        actor=people["reviewer2"],
        pin=LAB_PIN,
        batch=failed,
        expected_revision=failed.revision,
        reason="Control out of limits",
    )
    rerun = AnalyticalTest.objects.get(parent=original)
    assert (rerun.pull_id, rerun.lot_id, rerun.sample_id, rerun.kind) == (
        pull.pk,
        None,
        None,
        "rerun",
    )
    pull.refresh_from_db()
    assert pull.revision == before_rejection + 1
    # The rerun passes in a second run and answers for the pull.
    passed, current = batch_with("SYN-STB-QC-2")
    assert current.pk == rerun.pk
    control(passed, "100.0")
    reviewed(people, rerun, "100.3")
    accepted = accept(people, pull)
    assert accepted.outcome == "conforms"
    result = accepted.result_evidence["results"][0]
    assert [t["test"] for t in result["tests"]] == [rerun.pk]
    assert result["excluded_tests"] == [
        {"test": original.pk, "kind": "original", "state": "invalidated"}
    ]
    study.lot.refresh_from_db()
    assert study.lot.revision == lot_revision


def test_an_earlier_method_version_still_gets_a_batch_for_a_pull_in_testing(people):  # noqa: F811
    study, config = specified_study(people, requires_batch=True)
    pull = pulled(people, study)
    (test,) = assign(people, pull)
    method = config["method"]
    later = catalog.new_method_revision(
        actor=people["quality"],
        method=method,
        technique="Liquid chromatography",
        document_ref="SOP-SYN-STB-001 rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-STB-001 rev 2",
        requires_batch=True,
        effective_from=timezone.now(),
        effective_until=config["method_revision"].effective_until,
        reason="Synthetic method revision",
    )
    later.refresh_from_db()
    catalog.approve_revision(
        actor=people["quality2"],
        pin=LAB_PIN,
        revision=later,
        expected_revision=later.revision,
        reason="Independent synthetic configuration review",
    )
    # The pull's test keeps the version frozen on it and can still be run under it.
    assert (method.code, 1) in analytical.earlier_batch_methods()
    batch = analytical.create_batch(
        actor=people["analyst2"],
        number="SYN-STB-QC-EARLIER",
        method_code=method.code,
        revision=1,
        reason="Run of the frozen method version",
    )
    analytical.assign_to_batch(
        actor=people["analyst2"], test=test, batch=batch, reason="Synthetic run"
    )
    # Once the pull is no longer in testing, nothing asks for the earlier version.
    stability.close_study(
        actor=people["quality"],
        pin=LAB_PIN,
        study=study,
        expected_revision=study.revision,
        outcome="terminated",
        reason="Synthetic early termination",
    )
    other, _ = AnalyticalTest.objects.get(pk=test.pk), None
    assert other.batch_id == batch.pk
    assert (method.code, 1) not in analytical.earlier_batch_methods()


def test_testing_a_pull_and_closing_its_study_do_not_deadlock(people, monkeypatch):  # noqa: F811
    study, _ = specified_study(people, codes=("assay", "water"))
    pull = pulled(people, study)
    assay, water = sorted(assign(people, pull), key=lambda t: t.test_code)

    def close():
        study.refresh_from_db()
        return stability.close_study(
            actor=people["quality"],
            pin=LAB_PIN,
            study=study,
            expected_revision=study.revision,
            outcome="terminated",
            reason="Synthetic early termination",
        )

    # The observation holds the test, the pull and the study while the closure queues.
    outcome = run_interleaved(
        monkeypatch, analytical, "_touch", lambda: observe(people, assay, "100.0"), close
    )
    assert isinstance(outcome["first"], Observation), outcome
    assert outcome["second"].state == "terminated", outcome
    # Afterwards the closed study refuses the next observation.
    with pytest.raises(ValidationError, match="is closed"):
        observe(people, water, "99.0")


def test_accepting_a_pull_and_recording_on_it_do_not_deadlock(people, monkeypatch):  # noqa: F811
    study, _ = specified_study(people, codes=("assay", "water"))
    pull = pulled(people, study)
    assay, water = sorted(assign(people, pull), key=lambda t: t.test_code)
    reviewed(people, assay)
    observe(people, water, "99.0")
    submit(people, water)
    review(people, water)
    pull.refresh_from_db()
    shown = pull.revision

    def sign():
        return stability.accept_pull(
            actor=people["reviewer"],
            pin=LAB_PIN,
            pull=pull,
            expected_revision=shown,
            reason="Pull and results reviewed",
        )

    # The acceptance holds the pull while a raw-data file for one of its tests queues on it:
    # the file is refused once the pull is accepted, and neither waits on the other forever.
    from django.core.files.uploadedfile import SimpleUploadedFile

    from analytical import rawdata

    def attach():
        return rawdata.attach_raw_file(
            actor=people["analyst2"],
            test=water,
            upload=SimpleUploadedFile("late.txt", b"synthetic late raw data"),
            description="Late file",
        )

    outcome = run_interleaved(monkeypatch, stability, "frozen_results", sign, attach)
    assert isinstance(outcome["first"], Pull) and outcome["first"].state == "accepted", outcome
    assert isinstance(outcome["second"], ValidationError), outcome
    pull.refresh_from_db()
    assert pull.revision == shown + 1 and pull.outcome == "conforms"
