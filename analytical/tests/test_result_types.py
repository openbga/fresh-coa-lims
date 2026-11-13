"""Counts, less-than readings, exclusive limits and qualitative results end to end (PostgreSQL)."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.urls import reverse

from analytical import gates, services
from analytical.fixtures import FixtureProvider, requirement_payload
from analytical.models import AnalyticalTest, Investigation, Observation
from core.models import AuditEvent, ElectronicSignature

from .conftest import PIN, fresh, login, pass_qc, review, submit

pytestmark = pytest.mark.django_db(transaction=True)

CODES = ("tamc", "pathogen", "impurity", "appearance")
OBSERVED = "No characteristic colonies after enrichment of 25 g"


@pytest.fixture
def v2(people, make_lot):
    lot, sample = make_lot("SYN-V2", tests=CODES)
    created, holds = services.assign_tests(
        actor=people["analyst"], sample=sample, reason="Required tests"
    )
    assert holds == []
    return lot, sample, {t.test_code: t for t in created}


def read(people, test, *readings, who="analyst"):
    """Record readings: "<10" (less than), "12" (numeric/count) or an outcome code."""
    for reading in readings:
        services.record_observation(
            actor=people[who], test=test, raw_reference="NB-2 p4", **kwargs(reading)
        )
    return fresh(test)


def kwargs(reading):
    if reading in {"absent", "present", "conforms", "does_not_conform"}:
        return {"outcome": reading, "observed_text": OBSERVED}
    if reading.startswith("<"):
        return {"value": Decimal(reading[1:]), "qualifier": "<"}
    return {"value": Decimal(reading)}


def test_less_than_count_is_stored_as_recorded_and_reported(people, v2):
    lot, _, tests = v2
    test = read(people, tests["tamc"], "<10", "<10")
    observation = test.current_observations().first()
    assert (observation.value, observation.qualifier, observation.value_text) == (
        Decimal("10"),
        "<",
        "<10",
    )
    event = AuditEvent.objects.filter(action="observation.recorded").latest("occurred_at")
    assert (event.after["value"], event.after["qualifier"]) == ("<10", "<")
    submitted, investigation = submit(people, test)
    assert investigation is None
    assert (submitted.mean_value, submitted.reportable_value) == (None, None)
    assert (submitted.reportable_text, submitted.reportable_display, submitted.conforms) == (
        "<10",
        "<10",
        True,
    )
    event = AuditEvent.objects.get(action="test.submitted", object_id=str(test.pk))
    assert (event.after["mean"], event.after["reportable"], event.after["values"]) == (
        None,
        "<10",
        ["<10", "<10"],
    )
    reviewed = review(people, test)
    assert reviewed.state == "reviewed"


def test_count_and_less_than_refusals(people, v2):
    _, _, tests = v2
    for reading, message in [
        ("1.5", "whole number"),
        ("-1", "whole number"),
        ("<0", "greater than zero"),
        ("<2.5", "whole number"),
    ]:
        with pytest.raises(ValidationError, match=message):
            read(people, tests["tamc"], reading)
    with pytest.raises(ValidationError, match="Enter the observed value"):
        services.record_observation(
            actor=people["analyst"], test=tests["tamc"], raw_reference="x", outcome="absent"
        )
    with pytest.raises(ValidationError, match="greater than zero"):
        read(people, tests["impurity"], "<-0.01")
    assert not Observation.objects.exists()


def test_qualitative_reading_needs_outcome_and_observation(people, v2):
    _, _, tests = v2
    pathogen = tests["pathogen"]
    for extra, message in [
        ({"outcome": "absent"}, "Describe what was observed"),
        ({"outcome": "absent", "observed_text": "   "}, "Describe what was observed"),
        ({"outcome": "conforms", "observed_text": OBSERVED}, "Absent or Present"),
        ({"value": Decimal("0"), "observed_text": OBSERVED}, "Absent or Present"),
        (
            {"value": Decimal("1"), "qualifier": "<", "observed_text": OBSERVED},
            "cannot be reported as less than",
        ),
    ]:
        with pytest.raises(ValidationError, match=message):
            services.record_observation(
                actor=people["analyst"], test=pathogen, raw_reference="x", **extra
            )
    test = read(people, pathogen, "absent")
    observation = test.current_observations().get()
    assert (observation.value, observation.outcome, observation.value_text) == (
        None,
        "absent",
        "Absent",
    )
    assert observation.observed_text == OBSERVED
    event = AuditEvent.objects.filter(action="observation.recorded").latest("occurred_at")
    assert (event.after["value"], event.after["outcome"], event.after["observed"]) == (
        "Absent",
        "absent",
        OBSERVED,
    )


def test_conforming_qualitative_result_publishes_evidence(people, v2):
    lot, _, tests = v2
    for code, readings in [
        ("pathogen", ("absent", "absent")),
        ("appearance", ("conforms",)),
        ("tamc", ("<10", "50")),
        ("impurity", ("0.09",)),
    ]:
        test = read(people, tests[code], *readings)
        submitted, investigation = submit(people, test)
        assert investigation is None and submitted.conforms, code
        review(people, test)
    assert gates.lot_blockers(fresh(lot)) == []
    results = {r["test_code"]: r for r in gates.lot_evidence(fresh(lot))["results"]}
    pathogen = dict(results["pathogen"])
    replicates = pathogen.pop("replicates")
    assert pathogen.pop("review")["signer"] and pathogen.pop("test") == tests["pathogen"].pk
    assert pathogen.pop("method") == {"code": "SYN-MICRO", "revision": 1}
    assert pathogen == {
        "test_code": "pathogen",
        "for_sample": "SYN-V2-S1",
        "name": "Synthetic pathogen screen",
        "kind": "original",
        "sample": "SYN-V2-S1",
        "requirement_source": "fixture:SYN-SPEC-PATHOGEN@1",
        "requirement_hash": tests["pathogen"].requirement_hash,
        "result_type": "qualitative",
        "unit": "",
        "lower_limit": None,
        "upper_limit": None,
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": "absent",
        "criterion": "Absent in 25 g",
        "acceptance": "Absent in 25 g (expected: Absent)",
        "mean": None,
        "reportable": "Absent",
        "reporting_decimals": None,
        "batch": None,
    }
    assert [(r["value"], r["observed"]) for r in replicates] == [
        ("Absent", OBSERVED),
        ("Absent", OBSERVED),
    ]
    tamc = results["tamc"]
    assert (tamc["mean"], tamc["reportable"], tamc["expected_result"], tamc["criterion"]) == (
        None,
        "<10; 50",
        None,
        "",
    )
    assert [r["value"] for r in tamc["replicates"]] == ["<10", "50"]
    assert [r["observed"] for r in tamc["replicates"]] == ["", ""]
    impurity = results["impurity"]
    assert (impurity["mean"], impurity["reportable"], impurity["upper_inclusive"]) == (
        "0.09000000",
        "0.09",
        False,
    )
    assert impurity["acceptance"] == "less than 0.10 %"


def test_deviating_qualitative_result_opens_investigation_and_holds_lot(people, v2):
    lot, _, tests = v2
    test = read(people, tests["pathogen"], "absent", "present")
    submitted, investigation = submit(people, test)
    assert (submitted.conforms, submitted.reportable_text) == (False, "Present")
    assert (
        investigation.trigger == "Out-of-specification pathogen: observed Present, expected Absent"
    )
    assert any(investigation.label in b for b in gates.lot_blockers(fresh(lot)))
    with pytest.raises(ValidationError, match="cannot be returned"):
        services.return_test(
            actor=people["reviewer"], test=test, expected_revision=fresh(test).revision, reason="x"
        )
    review(people, test)  # a deviating result is still independently reviewed
    assert fresh(test).state == "reviewed"
    assert any("open" in b for b in gates.lot_blockers(fresh(lot)))


def test_less_than_that_cannot_be_shown_to_conform_is_investigated(people, v2):
    _, _, tests = v2
    test = read(people, tests["tamc"], "<2000", "<2000")
    submitted, investigation = submit(people, test)
    assert (submitted.conforms, submitted.reportable_text) == (False, "<2000")
    assert investigation.trigger == (
        "Out-of-specification tamc: <2000 CFU/g cannot be shown to meet at most 1000 CFU/g"
    )
    exclusive = read(people, tests["impurity"], "0.10")
    _, investigation = submit(people, exclusive)
    assert investigation.trigger == "Out-of-specification impurity: reportable 0.10 %"


def test_correction_may_change_qualifier_and_outcome(people, v2):
    _, _, tests = v2
    tamc = read(people, tests["tamc"], "10", "20")
    first = tamc.current_observations().first()
    corrected = services.correct_observation(
        actor=people["analyst"],
        observation=first,
        value=Decimal("10"),
        qualifier="<",
        raw_reference="NB-2 p5",
        reason="Transcription: reported below the reporting limit",
    )
    assert (corrected.value_text, corrected.qualifier, corrected.supersedes_id) == (
        "<10",
        "<",
        first.pk,
    )
    event = AuditEvent.objects.get(action="observation.corrected", object_id=str(tamc.pk))
    assert (event.before["value"], event.after["value"], event.after["qualifier"]) == (
        "10",
        "<10",
        "<",
    )
    pathogen = read(people, tests["pathogen"], "present", "absent")
    first = pathogen.current_observations().first()
    with pytest.raises(ValidationError, match="Describe what was observed"):
        services.correct_observation(
            actor=people["analyst"],
            observation=first,
            outcome="absent",
            raw_reference="NB-2 p6",
            reason="Wrong plate read",
        )
    corrected = services.correct_observation(
        actor=people["analyst"],
        observation=first,
        outcome="absent",
        observed_text="No growth on re-read plate",
        raw_reference="NB-2 p6",
        reason="Wrong plate read",
    )
    assert (corrected.value_text, corrected.observed_text) == (
        "Absent",
        "No growth on re-read plate",
    )
    event = AuditEvent.objects.get(action="observation.corrected", object_id=str(pathogen.pk))
    assert (event.before["outcome"], event.after["outcome"], event.after["observed"]) == (
        "present",
        "absent",
        "No growth on re-read plate",
    )
    assert submit(people, pathogen)[0].reportable_text == "Absent"


def test_review_refuses_when_stored_text_no_longer_matches(people, v2):
    _, _, tests = v2
    test = read(people, tests["tamc"], "<10", "<10")
    submit(people, test)
    # Submitted (not reviewed) tests accept evaluation fields; simulate a stale stored calculation.
    AnalyticalTest.objects.filter(pk=test.pk).update(reportable_text="<5")
    with pytest.raises(ValidationError, match="Calculated result changed"):
        review(people, test)
    assert not ElectronicSignature.objects.filter(object_id=str(test.pk)).exists()


def test_return_clears_reportable_text(people, v2):
    _, _, tests = v2
    test = read(people, tests["tamc"], "<10", "<10")
    submit(people, test)
    returned = services.return_test(
        actor=people["reviewer"],
        test=fresh(test),
        expected_revision=fresh(test).revision,
        reason="Check plate count",
    )
    assert (returned.reportable_text, returned.conforms, returned.mean_value) == ("", None, None)
    assert AuditEvent.objects.get(action="test.returned").before == {
        "mean": None,
        "reportable": "<10",
    }


def test_reviewed_reportable_text_is_immutable(people, v2):
    _, _, tests = v2
    test = read(people, tests["pathogen"], "absent", "absent")
    submit(people, test)
    review(people, test)
    for change in [{"reportable_text": "Present"}, {"reportable_text": ""}]:
        with pytest.raises(DatabaseError), transaction.atomic():
            AnalyticalTest.objects.filter(pk=test.pk).update(**change)
    observation = test.current_observations().first()
    for action in [
        lambda: Observation.objects.filter(pk=observation.pk).update(outcome="present"),
        lambda: Observation.objects.filter(pk=observation.pk).update(observed_text="x"),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic():
            action()


def test_open_test_identity_stays_immutable_while_text_is_settable(people, v2):
    _, _, tests = v2
    test = tests["tamc"]
    AnalyticalTest.objects.filter(pk=test.pk).update(reportable_text="")  # evaluation field
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalTest.objects.filter(pk=test.pk).update(requirement={})


@pytest.mark.parametrize(
    "shape",
    [
        {"value": Decimal("1"), "outcome": "absent", "observed_text": OBSERVED},  # both
        {"value": None, "outcome": ""},  # neither
        {"value": None, "outcome": "absent", "observed_text": ""},  # no observation
        {"value": None, "outcome": "absent", "observed_text": "  "},
        {"value": None, "outcome": "absent", "qualifier": "<", "observed_text": OBSERVED},
        {"value": Decimal("1"), "qualifier": ">"},
    ],
)
def test_malformed_observation_shapes_are_rejected_by_the_database(people, v2, shape):
    _, _, tests = v2
    with pytest.raises(IntegrityError), transaction.atomic():
        Observation.objects.create(
            test=tests["pathogen"],
            replicate=1,
            value_text="x",
            unit="",
            raw_reference="x",
            recorded_by=people["analyst"],
            **shape,
        )


def test_roles_and_self_review_hold_for_new_types(people, v2):
    _, _, tests = v2
    with pytest.raises(PermissionDenied):
        read(people, tests["pathogen"], "absent", who="reviewer")
    test = read(people, tests["pathogen"], "absent", "absent", who="multi")
    with pytest.raises(PermissionDenied):
        submit(people, test, who="reviewer")
    submit(people, test, who="multi")
    with pytest.raises(ValidationError, match="own test"):
        review(people, test, who="multi")
    with pytest.raises(PermissionDenied):
        review(people, test, who="analyst2")
    assert review(people, test, who="reviewer").state == "reviewed"


class BatchCountProvider(FixtureProvider):
    """A count requirement on the batch method, to exercise batch rejection."""

    def requirements(self, lot):
        payload = requirement_payload("tamc")
        payload["test_code"] = "lowcount"
        payload["method"] = requirement_payload("assay")["method"]
        return {"lowcount": payload}


def test_batch_rejection_uses_reading_aware_conformance(people, make_lot, settings):
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = f"{__name__}.BatchCountProvider"
    lot, sample = make_lot("SYN-V2B", tests=("lowcount",))
    (test,), _ = services.assign_tests(actor=people["analyst"], sample=sample, reason="x")
    batch = services.create_batch(
        actor=people["analyst2"], number="SYN-B2", method_code="SYN-HPLC", reason="Run"
    )
    services.assign_to_batch(actor=people["analyst"], test=test, batch=batch, reason="Run")
    pass_qc(people, batch, control="90.0")  # control out of limits: QC fails
    read(people, test, "<10", "<5000")
    services.reject_batch(
        actor=people["reviewer"],
        pin=PIN,
        batch=fresh(batch),
        expected_revision=fresh(batch).revision,
        reason="Control failed",
    )
    event = AuditEvent.objects.get(action="test.invalidated")
    assert event.after["out_of_limit_values"] == ["<5000"]
    investigation = Investigation.objects.get(test=test)
    assert "<5000" in investigation.trigger and "<10" not in investigation.trigger


# Pages ----------------------------------------------------------------------------------------


@pytest.fixture
def pages(plain_static):
    return None


def test_qualitative_observation_form_and_detail(client, people, v2, pages):
    lot, _, tests = v2
    test = tests["pathogen"]
    login(client, people["analyst"])
    url = reverse("analytical:observation_new", args=[test.pk])
    body = client.get(url).content.decode()
    assert 'type="radio"' in body and "Absent" in body and "Present" in body
    assert "What was observed" in body and 'name="value"' not in body
    assert "Absent in 25 g (expected: Absent)" in body
    response = client.post(url, {"outcome": "absent", "raw_reference": "NB-3"})
    assert response.status_code == 422 and not Observation.objects.exists()
    for _ in range(2):
        response = client.post(
            url, {"outcome": "absent", "observed_text": OBSERVED, "raw_reference": "NB-3"}
        )
        assert response.status_code == 302
    submit(people, test)
    for page in [
        reverse("analytical:test_detail", args=[test.pk]),
        reverse("analytical:lot_testing", args=[lot.pk]),
        reverse("analytical:test_list"),
    ]:
        body = client.get(page).content.decode()
        assert "None" not in body and "()" not in body, page
        assert "Absent" in body, page
    body = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert OBSERVED in body and "Mean" not in body and "As expected" in body
    login(client, people["reviewer"])
    body = client.get(reverse("analytical:test_review", args=[test.pk])).content.decode()
    assert f"Absent ({OBSERVED}); Absent ({OBSERVED})" in body
    assert "Absent · conforms" in body


def test_numeric_observation_form_offers_less_than(client, people, v2, pages):
    _, _, tests = v2
    test = tests["tamc"]
    login(client, people["analyst"])
    url = reverse("analytical:observation_new", args=[test.pk])
    body = client.get(url).content.decode()
    assert "Reported as less than this value" in body
    assert "Never enter a nondetect as zero" in body and 'type="radio"' not in body
    response = client.post(url, {"value": "1.5", "raw_reference": "NB-3"})
    assert response.status_code == 422 and "whole number" in response.content.decode()
    assert (
        client.post(url, {"value": "10", "less_than": "on", "raw_reference": "NB-3"}).status_code
        == 302
    )
    assert client.post(url, {"value": "40", "raw_reference": "NB-3"}).status_code == 302
    assert [o.value_text for o in test.current_observations()] == ["<10", "40"]
    first = test.current_observations().first()
    body = client.get(reverse("analytical:observation_correct", args=[first.pk])).content.decode()
    assert "Reported as less than this value" in body and "&lt;10 CFU/g" in body
    response = client.post(
        reverse("analytical:observation_correct", args=[first.pk]),
        {"value": "12", "raw_reference": "NB-3", "reason": "Re-read plate"},
    )
    assert response.status_code == 302
    assert [o.value_text for o in test.current_observations()] == ["12", "40"]
    submit(people, test)
    body = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "26 CFU/g" in body and "at most 1000 CFU/g" in body


def test_less_than_detail_shows_no_mean(client, people, v2, pages):
    _, _, tests = v2
    test = read(people, tests["tamc"], "<10", "<10")
    submit(people, test)
    login(client, people["auditor"])
    body = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert "None: a replicate is reported as less than a value" in body
    assert "&lt;10 CFU/g" in body and "None CFU" not in body


def test_qualitative_correction_form(client, people, v2, pages):
    _, _, tests = v2
    test = read(people, tests["appearance"], "does_not_conform")
    observation = test.current_observations().get()
    login(client, people["analyst"])
    url = reverse("analytical:observation_correct", args=[observation.pk])
    body = client.get(url).content.decode()
    assert "Does not conform" in body and "What was observed" in body and OBSERVED in body
    response = client.post(
        url,
        {
            "outcome": "conforms",
            "observed_text": "White crystalline powder",
            "raw_reference": "NB-4",
            "reason": "Wrong sample viewed",
        },
    )
    assert response.status_code == 302
    assert fresh(test).current_observations().get().value_text == "Conforms"


def test_existing_rows_migrate_without_loss_and_legacy_tests_still_review(people, assigned):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    _, _, tests = assigned
    test = fresh(tests["identity"])
    services.record_observation(
        actor=people["analyst"], test=test, value=Decimal("1.010"), raw_reference="NB-9"
    )
    submit(people, test)
    executor = MigrationExecutor(connection)
    executor.migrate([("analytical", "0003_observation_eligibility")])
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes("analytical"))  # forward to the latest
    observation = Observation.objects.get(test=test)
    assert (observation.value, observation.value_text, observation.unit) == (
        Decimal("1.01000000"),
        "1.010",
        "ratio",
    )
    assert (observation.qualifier, observation.outcome, observation.observed_text) == ("", "", "")
    legacy = fresh(test)  # submitted before the reportable text existed
    assert (legacy.reportable_text, legacy.reportable_display) == ("", "1.01")
    assert review(people, legacy).state == "reviewed"
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalTest.objects.filter(pk=test.pk).update(reportable_text="1.01")


class EscapingProvider(FixtureProvider):
    def requirements(self, lot):
        return {"pathogen": {**requirement_payload("pathogen"), "criterion": "<b>bold</b>"}}


def test_criterion_is_escaped_in_the_observation_form(client, people, make_lot, settings, pages):
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = f"{__name__}.EscapingProvider"
    _, sample = make_lot("SYN-ESC", tests=("pathogen",))
    (test,), _ = services.assign_tests(actor=people["analyst"], sample=sample, reason="x")
    login(client, people["analyst"])
    body = client.get(reverse("analytical:observation_new", args=[test.pk])).content.decode()
    assert "<b>bold</b>" not in body and "&lt;b&gt;bold&lt;/b&gt;" in body
