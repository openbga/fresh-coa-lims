"""Work in progress when a version is retired: nothing a lot has started is left without a way
forward. A test frozen to an earlier revision of a QC-batch method still gets its batch, a lot
keeps the sampling plan its samples were taken under, and the notices say what blocks.

Uses the production adapters and service-created approvals only (synthetic data).
"""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest
from analytical.rawdata import attach_raw_file
from catalog import services as catalog
from catalog.models import Specification
from laboratory import services as laboratory
from quality import services as quality
from quality.models import Lot
from sampling import services as sampling
from sampling.models import SamplingPlan
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import PIN, approve, dispose
from tests.test_requirement_replacement import (
    READINGS,
    complete,
    new_rule_version,
    new_specification_version,
    replace,
)
from tests.test_result_types_journey import (
    assign_sample_tests,
    build_world,
    record,
    review,
    submit,
)

pytestmark = pytest.mark.django_db(transaction=True)


def batch_method(data, code="synthetic-batch"):
    """An approved method that runs in a QC batch, with the analyst qualified for it."""
    people = data["people"]
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=365)
    method, revision = catalog.create_method(
        actor=people["author"],
        code=code,
        title="Synthetic batch method",
        technique="Chromatography",
        document_ref="SOP-SYN-B rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-B rev 1",
        requires_batch=True,
        effective_from=start,
        effective_until=end,
        reason="Synthetic batch method",
    )
    catalog.add_qc_check(
        actor=people["author"],
        revision=revision,
        code="control",
        name="Control",
        unit="%",
        lower_limit=Decimal("98"),
        upper_limit=Decimal("102"),
        reason="Synthetic QC check",
    )
    approve(revision, people["approver"])
    qualification = laboratory.record_qualification(
        actor=people["author"],
        user=people["analyst"],
        activity=method.code,
        evidence_ref="QUAL-SYN-B rev 1",
        valid_from=start.date(),
        valid_until=end.date(),
        reason="Synthetic training evidence",
    )
    laboratory.approve_qualification(
        actor=people["approver"],
        pin=PIN,
        qualification=qualification,
        expected_revision=qualification.revision,
        reason="Independent training evidence review",
    )
    return method


def assay_on(data, method):
    """The next specification version, whose assay line uses ``method`` and allows a retest."""
    people = data["people"]
    revision = catalog.new_specification_revision(
        actor=people["author"],
        specification=Specification.objects.get(code="synthetic-rt-spec"),
        basis="Assay by the batch method",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic revision",
    )
    for line in revision.tests.filter(code="assay"):
        catalog.remove_test_line(actor=people["author"], line=line, reason="Revise the line")
    catalog.add_test_line(
        actor=people["author"],
        revision=revision,
        reason="Revised",
        code="assay",
        name="Assay",
        method=method,
        result_type="numeric",
        unit="%",
        lower_limit=Decimal("98"),
        upper_limit=Decimal("102"),
        reporting_decimals=2,
        required=True,
        replicates=1,
        max_retests=1,
    )
    return approve(revision, people["approver"])


def new_method_version(data, method):
    draft = catalog.new_method_revision(
        actor=data["people"]["author"],
        method=method,
        technique="Chromatography",
        document_ref="SOP-SYN-B rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-B rev 2",
        requires_batch=True,
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic method revision",
    )
    return approve(draft, data["people"]["approver"])


def pass_qc(data, batch):
    analytical.record_qc(
        actor=data["people"]["analyst"],
        batch=batch,
        check_code="control",
        value=Decimal("100.0"),
        raw_reference="RAW-QC rev 1",
        reason="Synthetic QC",
    )


@pytest.fixture
def batched(django_user_model):
    """The mixed result-type world with its assay run by a QC-batch method."""
    data = build_world(django_user_model, with_assay=True)
    data["method"] = batch_method(data)
    assay_on(data, data["method"])
    data["tests"] = assign_sample_tests(data)
    data["lot"].refresh_from_db()
    return data


def test_a_test_with_raw_data_frozen_to_a_retired_batch_method_still_gets_its_batch(batched):
    """It cannot be superseded unevaluated, so it must be able to finish: a QC batch of the
    earlier revision is created for it, and for nothing else."""
    people, method = batched["people"], batched["method"]
    assay = batched["tests"]["assay"]
    assert assay.spec.method.requires_batch and assay.batch_id is None
    assert analytical.earlier_batch_methods() == {}
    with pytest.raises(ValidationError, match="No test in progress is frozen to this method"):
        analytical.create_batch(
            actor=people["analyst"], number="B-0", method_code=method.code, revision=7, reason="x"
        )
    attach_raw_file(
        actor=people["analyst"],
        test=assay,
        upload=SimpleUploadedFile("run.csv", b"a,b\n1,2\n", "text/csv"),
        description="Synthetic instrument export",
    )
    new_method_version(batched, method)  # retires revision 1 now
    current = analytical.create_batch(
        actor=people["analyst"], number="B-NEW", method_code=method.code, reason="New run"
    )
    assert current.method_spec.revision == 2
    with pytest.raises(ValidationError, match="does not match this batch"):
        analytical.assign_to_batch(actor=people["analyst"], test=assay, batch=current, reason="x")
    lot = Lot.objects.get(pk=batched["lot"].pk)
    assert any(
        "raw-data files that were not" in r for r in sampling.replacement_preview(lot).reasons
    )

    assert list(analytical.earlier_batch_methods()) == [(method.code, 1)]
    earlier = analytical.create_batch(
        actor=people["analyst"], number="B-OLD", method_code=method.code, revision=1, reason="Run"
    )
    assert earlier.method_spec.revision == 1 and earlier.method == assay.requirement["method"]
    analytical.assign_to_batch(actor=people["analyst"], test=assay, batch=earlier, reason="Run")
    assert analytical.earlier_batch_methods() == {}  # nothing else waits for that revision
    with pytest.raises(ValidationError, match="No test in progress is frozen to this method"):
        analytical.create_batch(
            actor=people["analyst"],
            number="B-OLD2",
            method_code=method.code,
            revision=1,
            reason="x",
        )
    pass_qc(batched, earlier)
    assay.refresh_from_db()
    record(batched, assay, "99.60")
    submit(batched, assay)
    review(batched, assay)
    assay.refresh_from_db()
    assert assay.state == "reviewed" and assay.conforms
    # Evaluated under its own requirement, it can now be superseded by the replacement.
    replace(batched)
    assay.refresh_from_db()
    assert assay.state == "superseded"


def test_a_retest_frozen_to_a_retired_batch_method_can_finish_its_investigation(batched):
    """The replacement waits for the investigation, so the investigation must not wait for a
    batch that could never be created."""
    people, method = batched["people"], batched["method"]
    assay = batched["tests"]["assay"]
    first = analytical.create_batch(
        actor=people["analyst"], number="B-1", method_code=method.code, reason="Run"
    )
    analytical.assign_to_batch(actor=people["analyst"], test=assay, batch=first, reason="Run")
    pass_qc(batched, first)
    assay.refresh_from_db()
    record(batched, assay, "97.00")
    _, investigation = submit(batched, assay)
    review(batched, assay)
    analytical.add_entry(
        actor=people["reviewer"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic assessment: dilution error suspected",
    )
    investigation.refresh_from_db()
    analytical.authorize_retest(
        actor=people["approver"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind="retest",
        reason="One justified retest",
    )
    retest = AnalyticalTest.objects.get(investigation=investigation)
    new_method_version(batched, method)  # retires revision 1 while the retest waits
    lot = Lot.objects.get(pk=batched["lot"].pk)
    assert any("is open on this lot" in r for r in sampling.replacement_preview(lot).reasons)
    with pytest.raises(ValidationError, match="already has submitted results"):
        analytical.assign_to_batch(actor=people["analyst"], test=retest, batch=first, reason="x")

    second = analytical.create_batch(
        actor=people["analyst"], number="B-2", method_code=method.code, revision=1, reason="Retest"
    )
    analytical.assign_to_batch(actor=people["analyst"], test=retest, batch=second, reason="Retest")
    pass_qc(batched, second)
    retest.refresh_from_db()
    record(batched, retest, "99.80")
    submit(batched, retest)
    review(batched, retest)
    investigation.refresh_from_db()
    concluded = analytical.conclude(
        actor=people["approver"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="invalidated",
        assignable_cause="Dilution error documented",
        reason="Synthetic conclusion",
    )
    assert concluded.phase == "closed"
    preview = sampling.replacement_preview(Lot.objects.get(pk=lot.pk))
    assert preview.possible, (preview.blocker, preview.reasons)


def test_the_new_batch_page_offers_the_earlier_revision_only_while_it_is_needed(client, batched):
    people, method = batched["people"], batched["method"]
    client.force_login(people["analyst"])
    url = reverse("analytical:batch_new")
    option = f'value="{method.code}@1"'
    assert option not in client.get(url).content.decode()
    new_method_version(batched, method)
    page = client.get(url).content.decode()
    assert option in page
    assert f"{method.code} revision 1 · earlier version, for tests in progress" in page
    assert f"{method.code} revision 2" in page
    response = client.post(
        url, {"number": "B-OLD", "method_code": f"{method.code}@1", "reason": "Run in progress"}
    )
    assert response.status_code == 302
    batch = analytical.QCBatch.objects.get(number="B-OLD")
    assert batch.method_spec.revision == 1
    analytical.assign_to_batch(
        actor=people["analyst"], test=batched["tests"]["assay"], batch=batch, reason="Run"
    )
    assert option not in client.get(url).content.decode()
    refused = client.post(
        url, {"number": "B-OLD2", "method_code": f"{method.code}@1", "reason": "Run in progress"}
    )
    assert refused.status_code == 422
    assert not analytical.QCBatch.objects.filter(number="B-OLD2").exists()


def sample_once(data, reference="SYN-RT-S001"):
    return sampling.record_sampling(
        actor=data["people"]["analyst"],
        lot=data["lot"],
        reference=reference,
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    ).sample


def new_plan_version(data):
    plan = SamplingPlan.objects.get(code="synthetic-rt-plan")
    draft = sampling.new_plan_revision(
        actor=data["people"]["author"],
        plan=plan,
        basis="all",
        minimum_quantity=Decimal("10"),
        quantity_unit="g",
        instructions="Take one identified sample from each container, v2.",
        rationale="Synthetic single-container lot only",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic plan revision",
    )
    return approve(draft, data["people"]["approver"])


def test_a_sampled_lot_keeps_the_plan_its_samples_were_taken_under(django_user_model):
    """A rule version and a sampling plan version are both approved after sampling and before
    any test: assigning the requirements again moves the lot to the rule version in force
    and keeps the plan, so the samples already taken do not block the lot for good."""
    data = build_world(django_user_model, with_assay=True)
    people, lot = data["people"], data["lot"]
    assign = {
        "actor": people["analyst"],
        "lot": lot,
        "material": data["material"],
        "stage": "incoming",
        "reason": "Assign approved synthetic policy",
    }
    first = sampling.assign_requirements(**assign)
    sample = sample_once(data)
    second_plan = new_plan_version(data)
    second_rules = new_rule_version(data)
    with pytest.raises(ValidationError, match="approved, effective rule"):
        analytical.assign_tests(actor=people["analyst"], sample=sample, reason="Assign tests")
    lot.refresh_from_db()
    assert sampling.replacement_preview(lot).blocker == sampling.NOT_STARTED
    again = sampling.assign_requirements(**assign)
    lot.refresh_from_db()
    assert again.status == "ready" and lot.rules == second_rules
    assert again.plan_revision == first.plan_revision != second_plan
    assert again.payload["sampling_plan"] == first.payload["sampling_plan"]
    assert sampling.lot_blockers(lot) == []
    created, holds = analytical.assign_tests(
        actor=people["analyst"], sample=sample, reason="Assign tests"
    )
    assert holds == [] and len(created) == 5
    # A lot that has not been sampled takes the plan in force.
    other = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-RT-002",
        material=data["material"].name,
        rules=second_rules,
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    fresh = sampling.assign_requirements(**(assign | {"lot": other}))
    assert fresh.plan_revision == second_plan


def test_the_notice_says_when_a_retired_rule_version_blocks_the_disposition(django_user_model):
    data = build_world(django_user_model, with_assay=True)
    data["tests"] = assign_sample_tests(data)
    people = data["people"]
    complete(data, *READINGS)
    new_specification_version(data)
    lot = Lot.objects.get(pk=data["lot"].pk)
    (notice,) = quality.disposition_notices(lot)
    assert "This does not block the disposition." in notice
    second = new_rule_version(data)
    lot = Lot.objects.get(pk=lot.pk)
    (notice,) = quality.disposition_notices(lot)
    assert notice == (
        f"The lot's rule set version is no longer in force: rule set {second}, specification "
        "synthetic-rt-spec v2, 1 requirement changed in force now. The disposition is refused "
        "until quality replaces the lot's requirements."
    )
    with pytest.raises(ValidationError, match="approved, effective rule"):
        dispose(data, people["approver"])


def test_one_account_signing_while_it_assigns_tests_does_not_deadlock(
    django_user_model, monkeypatch
):
    """Assigning tests takes the account first, like signing and every other lot writer: the
    new tests name it, and that reference used to be the last lock taken."""
    data = build_world(django_user_model, with_assay=True)
    data["tests"] = assign_sample_tests(data)
    people = data["people"]
    multi = people["analyst"]  # also holds the reviewer and quality roles
    assay, impurity = data["tests"]["assay"], data["tests"]["impurity"]
    complete(data, "impurity", reviewed=False)
    AnalyticalTest.objects.filter(pk=impurity.pk).update(submitted_by=people["reviewer"])
    new_specification_version(data)
    replace(data)  # the assay test is superseded: assigning creates a repeat
    impurity.refresh_from_db()
    holding, signing = threading.Event(), threading.Event()
    real_resolve = analytical.resolve

    def paused(lot):
        holding.set()  # the account, the lot's tests and the lot are locked
        signing.wait(10)
        threading.Event().wait(0.5)  # let the signature queue on the account
        return real_resolve(lot)

    monkeypatch.setattr(analytical, "resolve", paused)
    outcomes = {}

    def assign():
        try:
            outcomes["assign"] = analytical.assign_tests(
                actor=multi, sample=assay.sample, reason="Repeat superseded tests"
            )
        except Exception as exc:  # reported to the asserting test
            outcomes["assign"] = exc
        finally:
            connection.close()

    def sign():
        holding.wait(10)
        signing.set()
        try:
            outcomes["sign"] = analytical.review_test(
                actor=multi,
                pin=PIN,
                test=impurity,
                expected_revision=impurity.revision,
                reason="Review while assigning",
            )
        except Exception as exc:  # reported to the asserting test
            outcomes["sign"] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=assign), threading.Thread(target=sign)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(40)
    assert not any("deadlock" in repr(outcome).lower() for outcome in outcomes.values()), outcomes
    created, _ = outcomes["assign"]
    assert [(t.test_code, t.kind) for t in created] == [("assay", "revised")]
