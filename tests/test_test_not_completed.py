"""Signed record that a test cannot be completed: what it keeps, what follows, who may sign it,
and the exits it gives a lot that would otherwise be stuck (a lost sample, an authorized retest
that cannot be run, an unfinished test holding a reading outside its limits).

Uses the production adapters and service-created approvals only (synthetic data).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.models import AnalyticalTest, Investigation
from catalog import services as catalog
from core.models import AuditEvent, ElectronicSignature
from core.services import approve_rule, save_rule, set_pin
from laboratory import services as laboratory
from laboratory.tests.conftest import people  # noqa: F401  (shared synthetic role users)
from quality import rejection
from quality import services as quality
from quality.models import Lot
from sampling import services as sampling
from stability import services as stability
from stability.tests import helpers as stb
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import PASSWORD, PIN, approve

pytestmark = pytest.mark.django_db(transaction=True)

STATE = AnalyticalTest.State
REASON = "Synthetic: the sample container broke in the balance room (DEV-SYN-007)"


@pytest.fixture
def world(django_user_model):
    """A lot whose assay needs two replicates and allows one retest. The analyst holds every
    laboratory role and quality too; the approver and quality2 authored nothing on the lot."""
    staff = {}
    for name, roles in {
        "author": ["quality"],
        "approver": ["quality"],
        "quality2": ["quality"],
        "analyst": ["analyst", "quality", "reviewer"],
        "reviewer": ["reviewer"],
        "receiver": ["analyst"],
    }.items():
        person = django_user_model.objects.create_user(
            username=f"nc_{name}", password=PASSWORD, first_name="Synthetic", last_name=name
        )
        person.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        set_pin(actor=person, pin=PIN, password=PASSWORD)
        staff[name] = person
    author, approver = staff["author"], staff["approver"]
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=365)
    rules = save_rule(
        actor=author,
        code="synthetic-not-completed",
        segment="chemical",
        policy={
            "required_tests": ["assay"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        effective_from=start,
        effective_until=end,
        reason="Synthetic policy",
    )
    rules = approve_rule(
        actor=approver, pin=PIN, rule=rules, expected_revision=rules.revision, reason="Review"
    )
    material = catalog.create_material(
        actor=author,
        code="synthetic-nc-powder",
        name="Synthetic not-completed powder",
        kind="raw_material",
        reason="Synthetic master data",
    )
    method, method_revision = catalog.create_method(
        actor=author,
        code="synthetic-nc-assay",
        title="Synthetic assay",
        technique="Gravimetry",
        document_ref="SOP-SYN-NC rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-NC rev 1",
        requires_batch=False,
        effective_from=start,
        effective_until=end,
        reason="Explicit no-batch synthetic method",
    )
    approve(method_revision, approver)
    _, spec = catalog.create_specification(
        actor=author,
        code="synthetic-nc-spec",
        title="Synthetic specification",
        material=material,
        stage="incoming",
        scope="general",
        basis="Synthetic limits",
        effective_from=start,
        effective_until=end,
        reason="Synthetic specification",
    )
    catalog.add_test_line(
        actor=author,
        revision=spec,
        reason="Synthetic assay",
        code="assay",
        name="Assay",
        method=method,
        result_type="numeric",
        unit="%",
        lower_limit=Decimal("98"),
        upper_limit=Decimal("102"),
        lower_inclusive=True,
        upper_inclusive=True,
        reporting_decimals=2,
        replicates=2,
        replicate_limits=True,
        max_retests=1,
        required=True,
    )
    approve(spec, approver)
    _, plan = sampling.create_plan(
        actor=author,
        code="synthetic-nc-plan",
        title="Synthetic sampling plan",
        material=material,
        stage="incoming",
        basis="all",
        minimum_quantity=Decimal("10"),
        quantity_unit="g",
        instructions="Take one identified sample from each container.",
        rationale="Synthetic single-container lot only",
        effective_from=start,
        effective_until=end,
        reason="Synthetic sampling plan",
    )
    approve(plan, approver)
    qualification = laboratory.record_qualification(
        actor=author,
        user=staff["analyst"],
        activity=method.code,
        evidence_ref="QUAL-SYN-NC rev 1",
        valid_from=start.date(),
        valid_until=end.date(),
        reason="Synthetic training evidence",
    )
    laboratory.approve_qualification(
        actor=approver,
        pin=PIN,
        qualification=qualification,
        expected_revision=qualification.revision,
        reason="Independent training evidence review",
    )
    lot = quality.receive_lot(
        actor=staff["receiver"],
        number="SYN-NC-001",
        material=material.name,
        rules=rules,
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    sampling.assign_requirements(
        actor=staff["analyst"],
        lot=lot,
        material=material,
        stage="incoming",
        reason="Assign approved synthetic policy",
    )
    data = {"people": staff, "lot": lot}
    data["sample"] = new_sample(data, "SYN-NC-S001")
    (data["assay"],), holds = analytical.assign_tests(
        actor=staff["analyst"], sample=data["sample"], reason="Assign frozen required tests"
    )
    assert holds == []
    return data


def new_sample(data, reference):
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


def fresh(test):
    return AnalyticalTest.objects.get(pk=test.pk)


def lot_of(data):
    return Lot.objects.get(pk=data["lot"].pk)


def observe(data, test, *values):
    for value in values:
        analytical.record_observation(
            actor=data["people"]["analyst"],
            test=fresh(test),
            value=Decimal(value),
            raw_reference="RAW-SYN-NC rev 1",
            reason="Synthetic observation",
        )


def submit(data, test):
    test = fresh(test)
    return analytical.submit_test(
        actor=data["people"]["analyst"],
        test=test,
        expected_revision=test.revision,
        reason="Results complete",
    )


def review(data, test):
    test = fresh(test)
    return analytical.review_test(
        actor=data["people"]["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent review",
    )


def passing(data, test):
    observe(data, test, "99.90", "100.10")
    submit(data, test)
    return review(data, test)


def not_completed(data, test, who="approver", **changes):
    test = fresh(test)
    kwargs = {
        "actor": data["people"][who],
        "pin": PIN,
        "test": test,
        "expected_revision": test.revision,
        "cause": "sample",
        "reason": REASON,
    }
    kwargs.update(changes)
    return analytical.record_not_completed(**kwargs)


def assess(data, investigation):
    analytical.add_entry(
        actor=data["people"]["reviewer"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic laboratory assessment",
    )


def authorize(data, investigation, kind="retest", sample=None):
    investigation.refresh_from_db()
    analytical.authorize_retest(
        actor=data["people"]["approver"],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        kind=kind,
        reason="Synthetic retest plan",
        sample=sample,
    )
    return investigation.tests.order_by("-pk").first()


def conclude(data, investigation, outcome, cause="", who="quality2"):
    investigation.refresh_from_db()
    return analytical.conclude(
        actor=data["people"][who],
        pin=PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome=outcome,
        assignable_cause=cause,
        reason="Synthetic conclusion",
    )


def release(data, who="approver"):
    lot = lot_of(data)
    return quality.dispose_lot(
        actor=data["people"][who],
        pin=PIN,
        lot=lot,
        expected_revision=lot.revision,
        reason="Synthetic disposition",
    )


def test_an_untouched_test_is_closed_by_signature_and_repeated_on_the_same_sample(world):
    assay, lot = world["assay"], lot_of(world)
    closed = not_completed(world, assay, repeat="same", cause="equipment")

    assert closed.state == STATE.NOT_COMPLETED and closed.revision == assay.revision + 1
    record = closed.not_completed_record
    repeat = AnalyticalTest.objects.get(parent=closed)
    assert record == {
        "schema": "oq.test-not-completed/1",
        "cause": "equipment",
        "recorded": [],
        "outside_limits": [],
        "corrections": [],
        "raw_data_files": 0,
        "batch": None,
        "held_work": False,
        "follow_up": "repeat",
        "repeat": {"test": repeat.pk, "sample": "SYN-NC-S001"},
        "investigation": None,
    }
    assert repeat.kind == "repeat" and repeat.state == STATE.OPEN
    assert repeat.sample_id == world["sample"].pk and repeat.investigation_id is None
    assert repeat.requirement_hash == assay.requirement_hash
    signature = ElectronicSignature.objects.get(
        object_type="analytical.analyticaltest", object_id=str(assay.pk), meaning="not_completed"
    )
    assert signature.signer == world["people"]["approver"]
    assert signature.revision == closed.revision
    assert signature.content["not_completed_record"] == record
    assert signature.audit_event.reason == REASON
    assert AuditEvent.objects.filter(action="test.assigned", object_id=str(repeat.pk)).exists()
    assert lot_of(world).revision > lot.revision
    # The closed test blocks nothing; the repeat is what the lot waits for.
    blockers = gates.lot_blockers(lot_of(world))
    assert f"{repeat.label} assay is incomplete." in blockers
    assert not any(assay.label in item for item in blockers)

    passing(world, repeat)
    assert gates.lot_blockers(lot_of(world)) == []
    released = release(world)
    assert released.state == "released"
    evidence = gates.lot_evidence(lot_of(world))
    assert [row["test"] for row in evidence["results"]] == [repeat.pk]
    (excluded,) = evidence["excluded_tests"]
    assert excluded["test"] == assay.pk and excluded["state"] == "not_completed"
    assert excluded["not_completed"]["cause"] == "equipment"
    assert excluded["not_completed"]["signature"]["id"] == signature.pk


def test_a_lost_sample_is_repeated_on_a_new_sample_that_stands_in_for_it(world):
    assay = world["assay"]
    observe(world, assay, "99.50")  # one replicate, within the limits, then the sample is lost
    replacement = new_sample(world, "SYN-NC-S002")
    assert list(analytical.repeat_samples(fresh(assay))) == [replacement]

    closed = not_completed(world, assay, repeat="sample", sample=replacement)

    record = closed.not_completed_record
    assert record["recorded"] == ["99.50"] and record["outside_limits"] == []
    assert record["held_work"] is True and record["follow_up"] == "repeat"
    repeat = AnalyticalTest.objects.get(parent=closed)
    assert repeat.sample_id == replacement.pk and record["repeat"]["sample"] == "SYN-NC-S002"
    # The new sample stands in for the lost one: it is not a sample needing its own tests.
    assert not any("SYN-NC-S002" in item for item in gates.lot_blockers(lot_of(world)))
    assert list(analytical.repeat_samples(repeat)) == []  # S001 holds original tests
    passing(world, repeat)
    assert gates.lot_blockers(lot_of(world)) == []
    evidence = gates.lot_evidence(lot_of(world))
    (result,) = evidence["results"]
    assert (result["for_sample"], result["sample"], result["kind"]) == (
        "SYN-NC-S001",
        "SYN-NC-S002",
        "repeat",
    )


def test_a_new_sample_stands_in_for_one_sample_only(world):
    first, second = world["assay"], None
    other = new_sample(world, "SYN-NC-S003")
    (second,), _ = analytical.assign_tests(
        actor=world["people"]["analyst"], sample=other, reason="Second sample"
    )
    spare = new_sample(world, "SYN-NC-S004")
    not_completed(world, first, repeat="sample", sample=spare)
    # S004 now answers for S001; S003's test cannot be repeated on it, nor on S001.
    assert list(analytical.repeat_samples(fresh(second))) == []
    with pytest.raises(ValidationError, match="holds no tests of its own"):
        not_completed(world, second, repeat="sample", sample=spare)
    with pytest.raises(ValidationError, match="holds no tests of its own"):
        not_completed(world, second, repeat="sample", sample=world["sample"])
    assert fresh(second).state == STATE.OPEN


def test_a_reading_outside_the_limits_opens_an_investigation_and_is_not_repeated(world):
    assay = world["assay"]
    observe(world, assay, "97.10")
    with pytest.raises(ValidationError, match="investigation decides"):
        not_completed(world, assay, repeat="same")
    # Lot rejection is refused while the reading was not evaluated, and names this exit.
    preview = rejection.rejection_preview(lot_of(world))
    assert any("record that on the test" in reason for reason in preview.reasons)

    closed = not_completed(world, assay)

    record = closed.not_completed_record
    assert record["outside_limits"] == ["97.10"] and record["follow_up"] == "opens"
    investigation = Investigation.objects.get(test=closed)
    assert record["investigation"] == {"id": investigation.pk, "label": investigation.label}
    assert "97.10" in investigation.trigger
    assert investigation.opened_by == world["people"]["approver"]
    assert not AnalyticalTest.objects.filter(parent=closed).exists()
    assert f"{investigation.label} is open" in " ".join(gates.lot_blockers(lot_of(world)))
    assert rejection.rejection_preview(lot_of(world)).reasons == [
        f"{investigation.label} is open. Conclude it before the lot is rejected: the "
        "investigation is completed whatever is decided about the lot."
    ]
    # The investigation is concluded on the readings that were recorded.
    assess(world, investigation)
    retest = authorize(world, investigation)
    passing(world, retest)
    conclude(world, investigation, "invalidated", cause="Synthetic weighing error found")
    assert gates.lot_blockers(lot_of(world)) == []
    assert fresh(assay).state == STATE.NOT_COMPLETED  # never reviewed, never invalidated


def test_a_confirmed_failure_on_an_unfinished_test_leads_to_rejection(world):
    assay = world["assay"]
    observe(world, assay, "97.10")
    not_completed(world, assay)
    investigation = Investigation.objects.get(test=assay)
    assess(world, investigation)
    conclude(world, investigation, "confirmed")
    assert f"{investigation.label} confirmed" in " ".join(gates.lot_blockers(lot_of(world)))
    lot = lot_of(world)
    preview = rejection.rejection_preview(lot)
    assert preview.possible
    rejected = rejection.reject_lot(
        actor=world["people"]["quality2"],
        pin=PIN,
        lot=lot,
        expected_revision=lot.revision,
        grounds="results",
        reason="Synthetic: assay confirmed out of specification",
        reference="",
        basis=preview.basis,
    )
    rows = {row["test"]: row for row in rejected.disposition_evidence["tests"]}
    assert rows[assay.pk]["state"] == "not_completed"


def test_an_authorized_retest_that_cannot_be_run_leaves_the_investigation_to_decide(world):
    assay = world["assay"]
    observe(world, assay, "97.10", "97.30")
    _, investigation = submit(world, assay)
    review(world, assay)
    assess(world, investigation)
    retest = authorize(world, investigation)
    assert analytical.retests_used(investigation) == 1
    with pytest.raises(ValidationError, match="still incomplete"):
        conclude(world, investigation, "confirmed")
    revision = Investigation.objects.get(pk=investigation.pk).revision
    with pytest.raises(ValidationError, match="investigation decides"):
        not_completed(world, retest, repeat="same")

    closed = not_completed(world, retest)

    assert closed.not_completed_record["follow_up"] == "investigation"
    assert closed.not_completed_record["investigation"]["id"] == investigation.pk
    assert not AnalyticalTest.objects.filter(parent=closed).exists()
    # A conclusion page opened before the record is stale.
    assert Investigation.objects.get(pk=investigation.pk).revision == revision + 1
    # It gave no result, so the allowed retest can still be used.
    assert analytical.retests_used(investigation) == 0
    second = authorize(world, investigation)
    passing(world, second)
    conclude(world, investigation, "invalidated", cause="Synthetic dilution error found")
    assert gates.lot_blockers(lot_of(world)) == []


def test_a_retest_holding_readings_counts_and_a_reading_outside_the_limits_stands(world):
    assay = world["assay"]
    observe(world, assay, "97.10", "97.30")
    _, investigation = submit(world, assay)
    review(world, assay)
    assess(world, investigation)
    retest = authorize(world, investigation)
    observe(world, retest, "96.90")
    closed = not_completed(world, retest)
    assert closed.not_completed_record["outside_limits"] == ["96.90"]
    # It is part of the investigation: no second investigation is opened on it.
    assert not Investigation.objects.filter(test=closed).exists()
    assert analytical.retests_used(investigation) == 1
    with pytest.raises(ValidationError, match="allows no further retests"):
        authorize(world, investigation)
    with pytest.raises(ValidationError, match="held readings outside the limits"):
        conclude(world, investigation, "invalidated", cause="Synthetic cause")
    assert conclude(world, investigation, "confirmed").outcome == "confirmed"


@pytest.mark.parametrize(
    "who, error, message",
    [
        ("analyst", ValidationError, "Another quality person"),  # recorded its data
        ("reviewer", PermissionDenied, "role"),
        ("receiver", PermissionDenied, "role"),
    ],
)
def test_only_an_independent_quality_person_signs(world, who, error, message):
    assay = world["assay"]
    observe(world, assay, "99.50")
    with pytest.raises(error, match=message):
        not_completed(world, assay, who=who, repeat="same")
    assert fresh(assay).state == STATE.OPEN
    assert not ElectronicSignature.objects.filter(meaning="not_completed").exists()


def test_refusals_leave_the_test_open(world):
    assay = world["assay"]
    with pytest.raises(ValidationError, match="Choose the cause"):
        not_completed(world, assay, cause="lost", repeat="same")
    with pytest.raises(ValidationError, match="Choose where the test is repeated"):
        not_completed(world, assay)
    with pytest.raises(ValidationError, match="Record changed"):
        not_completed(world, assay, repeat="same", expected_revision=assay.revision - 1)
    with pytest.raises(ValidationError, match="holds no tests of its own"):
        not_completed(world, assay, repeat="sample", sample=None)
    observe(world, assay, "99.90", "100.10")
    submit(world, assay)
    with pytest.raises(ValidationError, match="awaits review"):
        not_completed(world, assay, repeat="same")
    review(world, assay)
    with pytest.raises(ValidationError, match="Only an open test"):
        not_completed(world, assay, repeat="same")
    assert not AnalyticalTest.objects.filter(kind="repeat").exists()


def test_a_page_opened_before_a_new_reading_is_stale(world):
    assay = world["assay"]
    shown = fresh(assay).revision
    observe(world, assay, "97.10")  # recorded after the signer opened the page
    with pytest.raises(ValidationError, match="Record changed"):
        not_completed(world, assay, repeat="same", expected_revision=shown)
    assert fresh(assay).state == STATE.OPEN


def test_a_lot_out_of_quarantine_takes_no_record(world):
    assay = world["assay"]
    lot = lot_of(world)
    preview = rejection.rejection_preview(lot)
    rejection.reject_lot(
        actor=world["people"]["approver"],
        pin=PIN,
        lot=lot,
        expected_revision=lot.revision,
        grounds="other",
        reason="Synthetic rejection",
        reference="",
        basis=preview.basis,
    )
    with pytest.raises(ValidationError, match="no longer in quarantine"):
        not_completed(world, assay, who="quality2", repeat="same")


def test_the_database_keeps_the_record_and_the_test_unchanged(world):
    assay = world["assay"]
    with pytest.raises(DatabaseError, match="record of why"), transaction.atomic():
        AnalyticalTest.objects.filter(pk=assay.pk).update(state="not_completed")
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        AnalyticalTest.objects.filter(pk=assay.pk).update(not_completed_record={"cause": "x"})
    # A new test carries a record exactly when it is not completed.
    copy = {
        "lot_id": assay.lot_id,
        "sample_id": assay.sample_id,
        "test_code": assay.test_code,
        "requirement": assay.requirement,
        "requirement_hash": assay.requirement_hash,
        "kind": "repeat",
        "parent_id": assay.pk,
        "created_by": world["people"]["analyst"],
    }
    for shape in ({"not_completed_record": {"cause": "x"}}, {"state": "not_completed"}):
        with pytest.raises(IntegrityError), transaction.atomic():
            AnalyticalTest.objects.create(**copy, **shape)
    observe(world, assay, "99.90", "100.10")
    submit(world, assay)
    with pytest.raises(DatabaseError, match="Only an open test"), transaction.atomic():
        AnalyticalTest.objects.filter(pk=assay.pk).update(
            state="not_completed",
            not_completed_record={"schema": "oq.test-not-completed/1", "cause": "other"},
        )
    other = new_sample(world, "SYN-NC-S005")
    (test,), _ = analytical.assign_tests(
        actor=world["people"]["analyst"], sample=other, reason="Second sample"
    )
    with pytest.raises(DatabaseError, match="record of why"), transaction.atomic():
        AnalyticalTest.objects.filter(pk=test.pk).update(
            state="not_completed", not_completed_record={"cause": "other"}
        )
    closed = not_completed(world, test, repeat="same")
    for change in (
        {"state": "open", "not_completed_record": {}},
        {"not_completed_record": {**closed.not_completed_record, "cause": "handling"}},
        {"revision": closed.revision + 1},
    ):
        with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
            AnalyticalTest.objects.filter(pk=test.pk).update(**change)
    with connection.cursor() as cursor, pytest.raises(DatabaseError), transaction.atomic():
        cursor.execute("DELETE FROM analytical_analyticaltest WHERE id = %s", [test.pk])
    assert fresh(test).not_completed_record == closed.not_completed_record


def test_the_pages_offer_the_record_to_quality_and_show_what_follows(world, client):
    assay = world["assay"]
    detail = reverse("analytical:test_detail", args=[assay.pk])
    page = reverse("analytical:test_not_completed", args=[assay.pk])
    client.force_login(world["people"]["reviewer"])
    assert page not in client.get(detail).content.decode()
    assert client.get(page).status_code == 403
    client.force_login(world["people"]["approver"])
    assert page in client.get(detail).content.decode()
    shown = client.get(page)
    text = shown.content.decode()
    assert shown.status_code == 200
    assert "is repeated by a linked test" in text and 'name="repeat"' in text
    # No other sample yet: only the same sample is offered.
    assert "record a new sample of the lot first" in text
    response = client.post(
        page,
        {
            "cause": "sample",
            "repeat": "same",
            "reason": REASON,
            "signature_username": world["people"]["approver"].username,
            "pin": PIN,
            "expected_revision": assay.revision,
        },
    )
    assert response.status_code == 302 and response["Location"] == detail
    assert fresh(assay).state == STATE.NOT_COMPLETED
    text = client.get(detail).content.decode()
    assert "signed that this test cannot be completed" in text
    assert "the sample was lost, damaged or used up" in text
    repeat = AnalyticalTest.objects.get(parent=assay)
    assert reverse("analytical:test_detail", args=[repeat.pk]) in text
    assert page not in text
    listing = client.get(reverse("analytical:test_list"), {"state": "not_completed"})
    assert assay.label in listing.content.decode()
    assert repeat.label not in listing.content.decode()


def test_the_page_refuses_the_author_and_explains_an_investigation(world, client):
    assay = world["assay"]
    observe(world, assay, "97.10")
    page = reverse("analytical:test_not_completed", args=[assay.pk])
    client.force_login(world["people"]["analyst"])  # holds quality, recorded the reading
    response = client.get(page)
    assert response.status_code == 302
    client.force_login(world["people"]["approver"])
    text = client.get(page).content.decode()
    assert "open an investigation on this test" in text and "97.10" in text
    assert 'name="repeat"' not in text


# Stability pulls: a pull's test is repeated on the material pulled ------------------------------


def pull_not_completed(team, test, who="quality", **changes):
    test = fresh(test)
    kwargs = {
        "actor": team[who],
        "pin": stb.PIN,
        "test": test,
        "expected_revision": test.revision,
        "cause": "handling",
        "reason": "Synthetic: the vial was dropped during preparation",
    }
    kwargs.update(changes)
    return analytical.record_not_completed(**kwargs)


def test_a_pull_test_is_repeated_on_the_material_pulled(people):  # noqa: F811
    study, _ = stb.specified_study(people)
    pull = stb.pulled(people, study)
    (test,) = stb.assign(people, pull)
    with pytest.raises(ValidationError, match="no other sample"):
        pull_not_completed(people, test, repeat="sample", sample=None)
    closed = pull_not_completed(people, test, repeat="same")
    repeat = AnalyticalTest.objects.get(parent=closed)
    assert (repeat.pull_id, repeat.lot_id, repeat.sample_id, repeat.kind) == (
        pull.pk,
        None,
        None,
        "repeat",
    )
    assert closed.not_completed_record["repeat"] == {"test": repeat.pk, "sample": None}
    stb.reviewed(people, repeat, "100.3")
    accepted = stb.accept(people, pull)
    assert accepted.outcome == "conforms"
    (result,) = accepted.result_evidence["results"]
    assert [t["test"] for t in result["tests"]] == [repeat.pk]
    (excluded,) = result["excluded_tests"]
    assert (excluded["test"], excluded["state"]) == (test.pk, "not_completed")
    assert excluded["not_completed"]["cause"] == "handling"
    assert excluded["not_completed"]["signature"]["meaning"] == "not_completed"


def test_a_study_closes_once_unfinished_work_is_recorded_not_completed(people):  # noqa: F811
    study, _ = stb.specified_study(people)
    pull = stb.pulled(people, study)
    (test,) = stb.assign(people, pull)
    stb.observe(people, test, "100.1")
    study.refresh_from_db()

    def close():
        study.refresh_from_db()
        return stability.close_study(
            actor=people["quality2"],
            pin=stb.PIN,
            study=study,
            expected_revision=study.revision,
            outcome="terminated",
            reason="Synthetic early termination",
        )

    with pytest.raises(ValidationError, match="holds results or raw data"):
        close()
    pull_not_completed(people, test, repeat="same")
    assert close().state == "terminated"


def test_a_qc_batch_keeps_a_test_not_completed_as_it_is(people):  # noqa: F811
    study, config = stb.specified_study(people, requires_batch=True, codes=("assay", "water"))
    pull = stb.pulled(people, study)
    assay, water = sorted(stb.assign(people, pull), key=lambda t: t.test_code)
    batch = analytical.create_batch(
        actor=people["analyst2"],
        number="SYN-NC-QC-1",
        method_code=config["method"].code,
        reason="Synthetic run",
    )
    for test in (assay, water):
        analytical.assign_to_batch(
            actor=people["analyst2"], test=fresh(test), batch=batch, reason="Synthetic run"
        )
    pull_not_completed(people, water, repeat="same")
    # It was never submitted: the batch's QC is not fixed by it.
    assert not analytical.results_submitted(batch)
    analytical.record_qc(
        actor=people["analyst2"],
        batch=batch,
        check_code="control",
        value=Decimal("90.0"),
        raw_reference="NB-STB-QC p1",
    )
    stb.observe(people, assay, "100.1")
    batch.refresh_from_db()
    analytical.reject_batch(
        actor=people["reviewer2"],
        pin=stb.PIN,
        batch=batch,
        expected_revision=batch.revision,
        reason="Control out of limits",
    )
    assert fresh(assay).state == STATE.INVALIDATED
    assert AnalyticalTest.objects.get(parent=assay).kind == "rerun"
    assert fresh(water).state == STATE.NOT_COMPLETED
    assert list(AnalyticalTest.objects.filter(parent=water).values_list("kind", flat=True)) == [
        "repeat"
    ]


def test_a_pull_failure_found_on_an_unfinished_test_is_accepted_and_shown(people, client):  # noqa: F811
    study, _ = stb.specified_study(people)
    pull = stb.pulled(people, study)
    (test,) = stb.assign(people, pull)
    stb.observe(people, test, "91.0")  # outside 95.0 to 105.0
    closed = pull_not_completed(people, test)
    investigation = Investigation.objects.get(test=closed)
    analytical.add_entry(
        actor=people["analyst2"],
        investigation=investigation,
        kind="assessment",
        text="Synthetic assessment: no laboratory error found",
    )
    investigation.refresh_from_db()
    analytical.conclude(
        actor=people["quality2"],
        pin=stb.PIN,
        investigation=investigation,
        expected_revision=investigation.revision,
        outcome="confirmed",
        assignable_cause="",
        reason="Out-of-specification result confirmed",
    )
    accepted = stb.accept(people, pull)
    assert accepted.outcome == "fails"
    (result,) = accepted.result_evidence["results"]
    assert result["outcome"] == "fails" and result["tests"] == []
    (excluded,) = result["excluded_tests"]
    assert excluded["not_completed"]["outside_limits"] == ["91.0"]
    client.force_login(people["quality"])
    page = client.get(reverse("stability:study_detail", args=[study.pk])).content.decode()
    assert "Fails · test not completed" in page
