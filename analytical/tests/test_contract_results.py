"""Results reported by a contract laboratory: recorded as the test's observations behind the
laboratory's approval, then submitted, reviewed and reported like any other result."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from analytical import fixtures, gates, services
from analytical.contracts import CONTRACT, WorkRefused, contract_source
from analytical.models import AnalyticalTest, Observation
from core.models import AuditEvent
from laboratory.tests.helpers import run_interleaved
from quality.models import Lot

from .conftest import fresh, login, pass_qc, record, review, submit

pytestmark = pytest.mark.django_db(transaction=True)

REPORT = "CLR-SYN-001"
KEPT = "DMS-SYN-CLR-001"


def today():
    return timezone.localdate()


def number(value, less_than=False):
    return {
        "value": Decimal(value),
        "qualifier": "<" if less_than else "",
        "outcome": "",
        "observed_text": "",
    }


def stated(outcome, wording):
    return {"value": None, "qualifier": "", "outcome": outcome, "observed_text": wording}


def report(people, test, *values, who="analyst", readings=None, **changes):
    test = fresh(test)
    arguments = {
        "expected_revision": test.revision,
        "laboratory_id": 1,
        "report_number": REPORT,
        "report_date": today(),
        "raw_reference": KEPT,
        "readings": readings if readings is not None else [number(v) for v in values],
        **changes,
    }
    return services.record_contract_result(actor=people[who], test=test, **arguments)


def bench_calls(name):
    return [details for call, details in fixtures.BENCH_LOG if call == name]


def state():
    return (
        Observation.objects.count(),
        AuditEvent.objects.count(),
        sorted(AnalyticalTest.objects.values_list("pk", "state", "revision")),
        sorted(Lot.objects.values_list("pk", "revision")),
    )


@pytest.fixture
def typed(people, make_lot):
    """One test of each result shape, on a lot of its own."""
    lot, sample = make_lot("SYN-CL-TYPES", tests=("tamc", "pathogen", "uv_assay"))
    created, holds = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    assert holds == []
    return lot, {t.test_code: t for t in created}


# Recording --------------------------------------------------------------------------------------


def test_a_reported_result_is_the_tests_result_from_entry_to_evidence(people, assigned):
    lot, sample, tests = assigned
    assay = tests["assay"]  # SYN-HPLC runs in a QC batch here; the contract laboratory runs its own
    revisions = (assay.revision, fresh(lot).revision)
    fixtures.BENCH_LOG.clear()
    observations = report(people, assay, "99.8", "100.2")

    assert [o.replicate for o in observations] == [1, 2]
    assert [o.value_text for o in observations] == ["99.8", "100.2"]
    for observation in observations:
        source = observation.contract
        assert source == contract_source(observation.eligibility)
        assert source["laboratory"]["code"] == "SYN-CL-01"
        assert source["report"] == {"number": REPORT, "date": today().isoformat()}
        assert (observation.raw_reference, observation.recorded_by) == (KEPT, people["analyst"])
        assert (observation.inputs, observation.calculation) == ([], {})
        assert (observation.equipment_used, observation.reagents_used) == ([], [])
    assert (fresh(assay).revision, fresh(lot).revision) == (revisions[0] + 1, revisions[1] + 1)
    assert fresh(assay).contract_source()["laboratory"]["name"] == "Synthetic Contract Analytics"
    # The laboratory's approval was checked, not the analyst or any instrument.
    assert [call for call, _ in fixtures.BENCH_LOG] == ["lock_actor", "authorize_contract"]
    assert bench_calls("authorize_contract")[0] == {
        "laboratory_id": 1,
        "method_code": "SYN-HPLC",
        "test_code": "assay",
        "context_type": "analytical.analyticaltest",
        "context_id": assay.pk,
        "report_number": REPORT,
        "report_date": today().isoformat(),
    }
    event = AuditEvent.objects.get(action="contract_result.recorded")
    assert (event.actor, event.object_id) == (people["analyst"], str(assay.pk))
    assert event.reason == "Contract laboratory result recorded."
    assert event.before == {}
    assert event.after["laboratory"] == "SYN-CL-01"
    assert event.after["report"] == {"number": REPORT, "date": today().isoformat()}
    assert [r["value"] for r in event.after["replicates"]] == ["99.8", "100.2"]
    assert event.after["contract"] == observations[0].eligibility[CONTRACT]

    # Submitted without a QC batch of this laboratory, then reviewed by someone else.
    submitted, investigation = submit(people, assay)
    assert investigation is None
    assert (submitted.state, submitted.reportable_text, submitted.conforms) == (
        "submitted",
        "100.0",
        True,
    )
    assert services.review_refusal(people["reviewer"], submitted) is None
    reviewed = review(people, assay)
    assert reviewed.state == "reviewed"

    # The lot's evidence names the contract laboratory; a result made here has no such key.
    done = record(people, tests["identity"], "1.00")
    submit(people, done)
    review(people, done)
    evidence = gates.lot_evidence(fresh(lot))
    assert evidence["complete"] and evidence["blockers"] == []
    by_code = {r["test_code"]: r for r in evidence["results"]}
    assert by_code["assay"]["contract_laboratory"] == {
        "code": "SYN-CL-01",
        "name": "Synthetic Contract Analytics",
        "location": "Synthetic City",
        "report_number": REPORT,
        "report_date": today().isoformat(),
        "approval": 1,
        "approval_evidence": "QAG-SYN-001 rev 1",
    }
    assert by_code["assay"]["replicates"][0]["eligibility"][CONTRACT]["report"]["number"] == REPORT
    assert "contract_laboratory" not in by_code["identity"]
    assert by_code["assay"]["batch"] is None


def test_whoever_records_the_report_authored_the_result(people, assigned):
    lot, _, tests = assigned
    report(people, tests["identity"], "1.00", who="multi")
    submit(people, tests["identity"], who="multi")
    test = fresh(tests["identity"])
    assert services.review_refusal(people["multi"], test) == "You cannot review your own test."
    with pytest.raises(ValidationError, match="your own test"):
        review(people, test, who="multi")
    assert people["multi"].pk in gates.lot_author_ids(lot)
    assert review(people, test).state == "reviewed"


def test_an_out_of_specification_report_opens_an_investigation(people, assigned):
    lot, _, tests = assigned
    report(people, tests["assay"], "90.0", "90.4")
    submitted, investigation = submit(people, tests["assay"])
    assert submitted.conforms is False and investigation is not None
    assert "Out-of-specification assay" in investigation.trigger
    assert any("is open" in blocker for blocker in gates.lot_blockers(fresh(lot)))


@pytest.mark.parametrize(
    ("code", "readings", "texts", "reportable"),
    [
        ("tamc", [number("10", True), number("10", True)], ["<10", "<10"], "<10"),
        (
            "pathogen",
            [stated("absent", "Not detected in 25 g"), stated("absent", "Not detected")],
            ["Absent", "Absent"],
            "Absent",
        ),
        # The method has an approved calculation: the value is entered as reported, and the
        # specification's own reporting precision still rounds the mean.
        ("uv_assay", [number("100.13"), number("100.13")], ["100.13", "100.13"], "100.1"),
    ],
)
def test_every_result_shape_is_recorded_as_the_report_states_it(
    people, typed, code, readings, texts, reportable
):
    _, tests = typed
    observations = report(people, tests[code], readings=readings)
    assert [o.value_text for o in observations] == texts
    assert not any(o.is_calculated for o in observations)
    if code == "pathogen":
        assert observations[0].observed_text == "Not detected in 25 g"
    submitted, investigation = submit(people, tests[code])
    assert investigation is None and submitted.reportable_text == reportable
    # Review recalculates nothing for a reported value and requires no instrument of this bench.
    assert review(people, tests[code]).state == "reviewed"
    assert bench_calls("authorize") == []


# Refusals ---------------------------------------------------------------------------------------


def test_a_laboratory_without_a_covering_approval_is_refused_and_audited(people, assigned):
    _, _, tests = assigned
    before = state()
    fixtures.BENCH_LOG.clear()
    with pytest.raises(WorkRefused) as revoked:
        report(people, tests["identity"], "1.00", laboratory_id=2)
    assert revoked.value.refusals[0]["subject"] == "SYN-CL-02"
    with pytest.raises(WorkRefused, match="covers a report dated"):
        report(
            people,
            tests["identity"],
            "1.00",
            report_date=today() - timedelta(days=fixtures.CONTRACT_WINDOW + 1),
        )
    assert state() == before
    refusals = bench_calls("record_contract_refusal")
    assert len(refusals) == 2 and bench_calls("record_refusal") == []
    first = refusals[0]
    # Audited after the entry rolled back, naming the test, the laboratory and the report.
    assert first["in_transaction"] is False
    assert (first["laboratory_id"], first["report_number"], first["report_date"]) == (
        2,
        REPORT,
        today().isoformat(),
    )
    assert (first["actor"], first["method_code"], first["test_code"]) == (
        people["analyst"].pk,
        "SYN-IR",
        "identity",
    )
    assert first["context_id"] == tests["identity"].pk
    assert first["refusals"] == revoked.value.refusals


def test_incomplete_or_impossible_reports_store_nothing(people, assigned, typed):
    _, _, tests = assigned
    _, shaped = typed
    identity = tests["identity"]
    before = state()
    fixtures.BENCH_LOG.clear()
    cases = [
        ({"report_number": "  "}, "number of the laboratory's report"),
        ({"raw_reference": ""}, "where the laboratory's report is kept"),
        ({"report_date": None}, "Enter the date of the report"),
        ({"report_date": today() + timedelta(days=1)}, "cannot be dated in the future"),
        ({"readings": []}, "Enter the 1 replicate result the report states"),
        ({"readings": [number("1.00"), number("1.00")]}, "Enter the 1 replicate result"),
        ({"readings": [{"value": Decimal("1.00")}]}, "result is incomplete"),
        (
            {"readings": [{**number("1"), "value": 1.0}]},
            "Replicate 1: Enter the result as an exact",
        ),
        ({"readings": [{**number("1"), "value": None}]}, "Replicate 1: Enter the value the report"),
        ({"laboratory_id": 99}, "does not exist"),
        ({"expected_revision": identity.revision + 7}, "Record changed"),
        # A caller that states no revision cannot be shown to have seen the current record.
        ({"expected_revision": None}, "Record changed"),
        ({"expected_revision": True}, "Record changed"),
        ({"report_number": "X" * 121}, "at most 120 characters"),
    ]
    for changes, message in cases:
        with pytest.raises(ValidationError) as refusal:
            report(people, identity, "1.00", **changes)
        assert message in " ".join(refusal.value.messages), changes
    with pytest.raises(ValidationError, match="Enter the 2 replicate results the report states"):
        report(people, tests["assay"], "99.8")
    with pytest.raises(ValidationError, match="Replicate 2: Enter the wording of the result"):
        report(
            people,
            shaped["pathogen"],
            readings=[stated("absent", "Not detected"), stated("absent", " ")],
        )
    with pytest.raises(ValidationError, match="Replicate 1: A count must be a whole number"):
        report(people, shaped["tamc"], readings=[number("1.5"), number("2")])
    for name in ("reviewer", "quality", "auditor"):
        with pytest.raises(PermissionDenied):
            report(people, identity, "1.00", who=name)
    assert state() == before
    # Nothing reached the laboratory's approval except the unknown laboratory, and no refusal
    # of an approval was audited for a report that was never checked against one.
    assert [c["laboratory_id"] for c in bench_calls("authorize_contract")] == [99]
    assert bench_calls("record_contract_refusal") == []


def test_a_test_is_tested_here_or_reported_never_both(people, assigned, batch):
    lot, _, tests = assigned
    assay, identity = tests["assay"], tests["identity"]
    # In a QC batch of this laboratory: tested here.
    services.assign_to_batch(actor=people["analyst"], test=assay, batch=batch, reason="Run")
    assert services.contract_refusal(fresh(assay)) == services.IN_BATCH
    with pytest.raises(ValidationError) as refusal:
        report(people, assay, "99.8", "100.2")
    assert refusal.value.messages == [services.IN_BATCH]
    # Holding an observation made here: tested here.
    record(people, identity, "1.00")
    with pytest.raises(ValidationError) as refusal:
        report(people, identity, "1.00", reason="Replace")
    assert refusal.value.messages == [services.OWN_OBSERVATIONS]
    assert Observation.objects.filter(test=identity).count() == 1
    assert AnalyticalTest.objects.filter(lot=lot).count() == 2


def test_a_reported_test_accepts_no_bench_work(people, make_lot, batch):
    lot, sample = make_lot("SYN-CL-MIX")
    created, _ = services.assign_tests(actor=people["analyst"], sample=sample, reason="Go")
    tests = {t.test_code: t for t in created}
    first, second = report(people, tests["assay"], "99.8", "100.2")
    before = state()
    with pytest.raises(ValidationError) as refusal:
        services.record_observation(
            actor=people["analyst"],
            test=fresh(tests["assay"]),
            value=Decimal("100.0"),
            raw_reference="NB-1",
        )
    assert refusal.value.messages == [services.REPORTED]
    with pytest.raises(ValidationError) as refusal:
        services.correct_observation(
            actor=people["analyst"],
            observation=first,
            value=Decimal("100.0"),
            raw_reference="NB-1",
            reason="Typo",
        )
    assert refusal.value.messages == [services.CONTRACT_REPLICATE]
    with pytest.raises(ValidationError, match="already has a batch or recorded observations"):
        services.assign_to_batch(
            actor=people["analyst"], test=fresh(tests["assay"]), batch=batch, reason="Run"
        )
    assert state() == before and second.contract is not None


def test_only_an_open_test_of_a_quarantined_lot_takes_a_report(people, assigned):
    lot, _, tests = assigned
    report(people, tests["identity"], "1.00")
    submit(people, tests["identity"])
    with pytest.raises(ValidationError) as refusal:
        report(people, tests["identity"], "1.01", reason="Late change")
    assert refusal.value.messages == [services.NOT_ACCEPTING]
    Lot.objects.filter(pk=lot.pk).update(
        state="rejected",
        # The lot guard requires a rejected lot to carry the evidence of its decision.
        disposition_evidence={"schema": "oq.lot-rejection/1", "decision": "rejected"},
    )
    with pytest.raises(ValidationError, match="no longer in quarantine"):
        report(people, tests["assay"], "99.8", "100.2")
    assert Observation.objects.filter(test=tests["assay"]).count() == 0


def test_reports_are_held_without_a_configured_bench(people, assigned, settings):
    _, _, tests = assigned
    settings.ANALYTICAL_BENCH = ""
    with pytest.raises(ValidationError, match="No bench check is configured"):
        report(people, tests["identity"], "1.00")
    assert not Observation.objects.exists()


# Corrections ------------------------------------------------------------------------------------


def test_a_correction_replaces_the_whole_result_and_keeps_the_original(people, assigned):
    lot, _, tests = assigned
    assay = tests["assay"]
    originals = report(people, assay, "99.8", "100.2")
    before = state()
    with pytest.raises(ValidationError, match="A reason is required"):
        report(people, assay, "99.8", "101.2")
    with pytest.raises(ValidationError, match="The correction changes nothing"):
        report(people, assay, "99.8", "100.2", reason="Checked again")
    stale = fresh(assay).revision - 1
    with pytest.raises(ValidationError, match="Record changed"):
        report(people, assay, "99.8", "101.2", reason="Typo", expected_revision=stale)
    assert state() == before

    lot_revision = fresh(lot).revision
    corrected = report(
        people,
        assay,
        "99.8",
        "101.2",
        who="analyst2",
        reason="Second replicate misread",
        report_number="CLR-SYN-001A",
    )
    assert [c.supersedes for c in corrected] == originals
    assert [c.reason for c in corrected] == ["Second replicate misread"] * 2
    assert [o.value_text for o in fresh(assay).current_observations()] == ["99.8", "101.2"]
    assert Observation.objects.filter(test=assay).count() == 4  # the originals stay
    assert [o.value_text for o in Observation.objects.filter(pk__in=[o.pk for o in originals])] == [
        "99.8",
        "100.2",
    ]
    assert fresh(lot).revision == lot_revision + 1
    assert fresh(assay).contract_source()["report"]["number"] == "CLR-SYN-001A"
    event = AuditEvent.objects.get(action="contract_result.corrected")
    assert event.actor == people["analyst2"] and event.reason == "Second replicate misread"
    assert event.before["observations"] == [o.pk for o in originals]
    assert [r["value"] for r in event.before["replicates"]] == ["99.8", "100.2"]
    assert event.before["report"]["number"] == REPORT
    assert [r["value"] for r in event.after["replicates"]] == ["99.8", "101.2"]
    # A change of the report alone, or of where it is kept, is a correction too.
    calls = len(bench_calls("authorize_contract"))
    again = report(
        people,
        assay,
        "99.8",
        "101.2",
        reason="Filed elsewhere",
        raw_reference="DMS-2",
        report_number="CLR-SYN-001A",
    )
    assert [o.raw_reference for o in again] == ["DMS-2", "DMS-2"]
    # The same report again: nothing new was accepted, the evidence relied on is kept.
    assert len(bench_calls("authorize_contract")) == calls
    assert again[0].eligibility == corrected[0].eligibility
    # Both people who recorded the result authored it.
    submit(people, assay)
    assert {people["analyst"].pk, people["analyst2"].pk} <= gates.data_author_ids(fresh(assay))


def test_only_a_new_acceptance_is_checked_against_the_approval_again(people, assigned, monkeypatch):
    _, _, tests = assigned
    identity = tests["identity"]
    (original,) = report(people, identity, "1.00")
    fixtures.BENCH_LOG.clear()
    # The approval is revoked afterwards. The same report of the same laboratory was already
    # accepted: a transcription error is still corrected, on the evidence relied on then.
    monkeypatch.setitem(
        fixtures.CONTRACT_LABORATORIES,
        1,
        ("SYN-CL-01", "Synthetic Contract Analytics", "Synthetic City", "revoked"),
    )
    (corrected,) = report(people, identity, "1.01", reason="Misread")
    assert corrected.supersedes == original
    assert corrected.eligibility == original.eligibility
    assert bench_calls("authorize_contract") == []
    # Another report, or another laboratory, is a new acceptance and is refused.
    before = state()
    for change in ({"report_number": "CLR-SYN-002"}, {"laboratory_id": 2}):
        with pytest.raises(WorkRefused):
            report(people, identity, "1.02", reason="Other report", **change)
    with pytest.raises(WorkRefused):
        report(
            people,
            identity,
            "1.02",
            reason="Other date",
            report_date=today() - timedelta(days=1),
        )
    assert state() == before
    assert len(bench_calls("authorize_contract")) == 3
    assert len(bench_calls("record_contract_refusal")) == 3


# Pages ------------------------------------------------------------------------------------------


def page_post(client, test, **changes):
    data = {
        "laboratory_id": "1",
        "report_number": REPORT,
        "report_date": today().isoformat(),
        "raw_reference": KEPT,
        "expected_revision": fresh(test).revision,
        **changes,
    }
    return client.post(reverse("analytical:contract_result", args=[test.pk]), data)


@pytest.mark.usefixtures("plain_static")
def test_recording_and_correcting_through_the_pages(client, people, assigned):
    _, _, tests = assigned
    assay = tests["assay"]
    url = reverse("analytical:contract_result", args=[assay.pk])
    detail = reverse("analytical:test_detail", args=[assay.pk])
    login(client, people["analyst"])
    page = client.get(detail).content.decode()
    assert f'href="{url}"' in page and "Record contract laboratory result" in page
    assert "or record the result a contract laboratory reported" in page

    form = client.get(url).content.decode()
    assert "Record contract laboratory result · " in form
    assert "SYN-CL-01 · Synthetic Contract Analytics" in form
    assert "Replicate 1 reported value (% label claim)" in form
    assert "Replicate 2 reported as less than this value" in form
    assert "SYN-HPLC revision 1" in form and "Reason for correction" not in form

    empty = page_post(client, assay, laboratory_id="", report_number="", value_1="99.8")
    body = empty.content.decode()
    assert empty.status_code == 422
    assert "Select the contract laboratory that issued the report." in body
    refused = page_post(client, assay, laboratory_id="2", value_1="99.8", value_2="100.2")
    assert refused.status_code == 422
    assert "Refused: SYN-CL-02: The approval for “SYN-HPLC” is revoked." in (
        refused.content.decode()
    )
    assert not Observation.objects.filter(test=assay).exists()

    done = page_post(client, assay, value_1="99.8", value_2="100.2")
    assert done.status_code == 302 and done.url == detail
    page = client.get(detail).content.decode()
    assert "Contract laboratory result recorded." in page
    assert "It was not tested in this laboratory." in page
    assert "Reported by:" in page and "Approval relied on:" in page and REPORT in page
    assert "Run by the contract laboratory; see its report" in page
    assert "Correct contract laboratory result" in page
    assert "Record contract laboratory result" not in page
    first = Observation.objects.filter(test=assay).first()
    replicate_link = reverse("analytical:observation_correct", args=[first.pk])
    assert replicate_link not in page  # corrected as a whole, never one replicate at a time
    assert "Submit for review" in page  # no QC batch of this laboratory is needed
    refused = client.get(replicate_link, follow=True)
    assert services.CONTRACT_REPLICATE in refused.content.decode()
    entry = client.get(reverse("analytical:observation_new", args=[assay.pk]), follow=True)
    assert "It takes no observation made in this laboratory" in entry.content.decode()

    form = client.get(url).content.decode()
    assert "Correct contract laboratory result · " in form and "Reason for correction" in form
    assert 'value="99.8"' in form and 'value="100.2"' in form and f'value="{REPORT}"' in form
    assert "Result being corrected" in form
    same = page_post(client, assay, value_1="99.8", value_2="100.2", reason="Checked")
    assert same.status_code == 422
    assert "The correction changes nothing." in same.content.decode()
    changed = page_post(client, assay, value_1="99.8", value_2="100.4", reason="Misread")
    assert changed.status_code == 302
    page = client.get(detail).content.decode()
    assert "Contract laboratory result corrected; the result recorded before is kept." in page
    assert "superseded" in page and "100.4" in page

    # The reviewer sees who reported the result where the review is signed.
    client.post(detail, {"expected_revision": fresh(assay).revision, "reason": "Complete"})
    assert fresh(assay).state == "submitted"
    login(client, people["reviewer"])
    sign = client.get(reverse("analytical:test_review", args=[assay.pk])).content.decode()
    assert "Reported by contract laboratory" in sign and "SYN-CL-01" in sign
    late = client.get(url)
    assert late.status_code == 403  # a reviewer records no results


@pytest.mark.usefixtures("plain_static")
def test_the_page_is_refused_where_a_report_cannot_be_recorded(
    client, people, assigned, batch, monkeypatch
):
    _, _, tests = assigned
    assay, identity = tests["assay"], tests["identity"]
    url = reverse("analytical:contract_result", args=[identity.pk])
    for name in ("reviewer", "quality", "auditor"):
        login(client, people[name])
        assert client.get(url).status_code == 403, name
        assert page_post(client, identity, value_1="1.00").status_code == 403
        detail = client.get(reverse("analytical:test_detail", args=[identity.pk]))
        assert url not in detail.content.decode()
    login(client, people["analyst"])
    services.assign_to_batch(actor=people["analyst"], test=assay, batch=batch, reason="Run")
    batched = client.get(reverse("analytical:contract_result", args=[assay.pk]), follow=True)
    assert "This test is in a QC batch of this laboratory. It is tested here" in (
        batched.content.decode()
    )
    assert "Record contract laboratory result" not in batched.content.decode()
    record(people, identity, "1.00")
    own = client.get(url, follow=True)
    assert "This test holds observations made in this laboratory." in own.content.decode()
    assert page_post(client, identity, value_1="1.00").status_code == 302
    assert Observation.objects.filter(test=identity).count() == 1


@pytest.mark.usefixtures("plain_static")
def test_the_page_says_when_no_laboratory_is_approved_or_no_bench_is_set(
    client, people, assigned, monkeypatch, settings
):
    _, _, tests = assigned
    url = reverse("analytical:contract_result", args=[tests["identity"].pk])
    login(client, people["analyst"])
    monkeypatch.setattr(fixtures.SyntheticBench, "contract_choices", lambda self, code: [])
    none = client.get(url, follow=True).content.decode()
    assert "No contract laboratory is approved for method SYN-IR." in none
    settings.ANALYTICAL_BENCH = ""
    held = client.get(url, follow=True).content.decode()
    assert "No bench check is configured; results are held." in held
    assert not Observation.objects.exists()


@pytest.mark.usefixtures("plain_static")
def test_a_recorded_report_is_corrected_through_the_page_after_its_approval_ended(
    client, people, assigned, monkeypatch
):
    _, _, tests = assigned
    identity = tests["identity"]
    report(people, identity, "1.00")
    # No laboratory is approved for the method any more.
    monkeypatch.setattr(fixtures.SyntheticBench, "contract_choices", lambda self, code: [])
    monkeypatch.setitem(
        fixtures.CONTRACT_LABORATORIES,
        1,
        ("SYN-CL-01", "Synthetic Contract Analytics", "Synthetic City", "revoked"),
    )
    login(client, people["analyst"])
    url = reverse("analytical:contract_result", args=[identity.pk])
    form = client.get(url).content.decode()
    assert "SYN-CL-01 · Synthetic Contract Analytics · as recorded" in form
    assert "keeps the approval already relied on" in form
    other = page_post(client, identity, value_1="1.01", report_number="CLR-SYN-9", reason="New")
    assert other.status_code == 422
    assert "Refused: SYN-CL-01" in other.content.decode()
    fixed = page_post(client, identity, value_1="1.01", reason="Misread")
    assert fixed.status_code == 302
    assert [o.value_text for o in fresh(identity).current_observations()] == ["1.01"]


# Concurrency and hardening ---------------------------------------------------------------------


def test_a_stale_caller_without_a_revision_cannot_replace_a_result(people, assigned):
    _, _, tests = assigned
    identity = tests["identity"]
    stale = fresh(identity)
    report(people, identity, "1.00")
    with pytest.raises(ValidationError, match="Record changed"):
        services.record_contract_result(
            actor=people["analyst2"],
            test=stale,
            expected_revision=None,
            laboratory_id=1,
            report_number=REPORT,
            report_date=today(),
            raw_reference=KEPT,
            readings=[number("1.05")],
            reason="Entered from an old page",
        )
    assert [o.value_text for o in fresh(identity).current_observations()] == ["1.00"]


@pytest.mark.parametrize("first", ["bench", "report"])
def test_a_bench_entry_and_a_report_at_once_leave_one_origin(people, assigned, monkeypatch, first):
    """Both lock the test: whichever commits first, the other is refused."""
    _, _, tests = assigned
    identity = fresh(tests["identity"])

    def bench_entry():
        return services.record_observation(
            actor=people["analyst"], test=identity, value=Decimal("1.00"), raw_reference="NB-1"
        )

    def reported():
        return report(people, identity, "1.00", who="analyst2")

    if first == "bench":
        outcome = run_interleaved(monkeypatch, services, "_entry", bench_entry, reported)
    else:
        outcome = run_interleaved(
            monkeypatch, services, "_contract_readings", reported, bench_entry
        )
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    rows = list(Observation.objects.filter(test=identity))
    assert len(rows) == 1 and (rows[0].contract is None) is (first == "bench")


def test_two_reports_at_once_record_one_result(people, assigned, monkeypatch):
    _, _, tests = assigned
    identity = fresh(tests["identity"])
    outcome = run_interleaved(
        monkeypatch,
        services,
        "_contract_readings",
        lambda: report(people, identity, "1.00"),
        lambda: report(people, identity, "1.01", who="analyst2"),
    )
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    assert "Record changed" in outcome["second"].messages[0]
    assert [o.value_text for o in Observation.objects.filter(test=identity)] == ["1.00"]


def test_a_report_and_a_batch_assignment_at_once_do_not_both_apply(
    people, assigned, batch, monkeypatch
):
    _, _, tests = assigned
    assay = fresh(tests["assay"])
    outcome = run_interleaved(
        monkeypatch,
        services,
        "_contract_readings",
        lambda: report(people, assay, "99.8", "100.2"),
        lambda: services.assign_to_batch(
            actor=people["analyst2"], test=assay, batch=batch, reason="Run"
        ),
    )
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    assert fresh(assay).batch_id is None
    assert Observation.objects.filter(test=assay).count() == 2


def test_only_a_reported_result_is_excused_this_laboratorys_batch_qc(
    people, assigned, batch, monkeypatch
):
    _, _, tests = assigned
    assay = tests["assay"]
    # A bench result of a batch method still needs its batch and passing QC.
    services.assign_to_batch(actor=people["analyst"], test=assay, batch=batch, reason="Run")
    record(people, assay, "99.8", "100.2")
    with pytest.raises(ValidationError, match="Batch QC is incomplete"):
        submit(people, assay)
    pass_qc(people, batch)
    assert submit(people, assay)[0].state == "submitted"

    # A bench that returned evidence shaped like a contract laboratory's is refused: only a
    # recorded report carries that mark, and it is what excuses batch QC and recalculation.
    real = fixtures.SyntheticBench.authorize

    def forged(self, **kwargs):
        return {
            **real(self, **kwargs),
            "contract": {"laboratory": {}, "approval": {}, "report": {}},
        }

    monkeypatch.setattr(fixtures.SyntheticBench, "authorize", forged)
    with pytest.raises(ValidationError, match="cannot name a contract laboratory"):
        record(people, tests["identity"], "1.00")
    assert not Observation.objects.filter(test=tests["identity"]).exists()
