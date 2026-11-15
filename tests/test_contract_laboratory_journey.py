"""A contract laboratory's result through the production adapters: refused without a signed
approval, then recorded, reviewed, dispositioned and named on the issued certificate."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from analytical import gates
from analytical import services as analytical
from analytical.contracts import WorkRefused
from analytical.models import Observation
from core.models import AuditEvent
from core.services import set_pin
from laboratory import contract
from laboratory.models import ContractUse, ResourceUse
from quality import services as quality
from reporting import services as reporting
from tests.test_integrated_journey import (
    PASSWORD,
    PIN,
    assign_and_sample,
    dispose,
    integrated,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.django_db(transaction=True)

REPORT = "CLR-SYN-2026-0042"


def today():
    return timezone.localdate()


def assigned_test(data):
    sample = assign_and_sample(data)
    tests, holds = analytical.assign_tests(
        actor=data["people"]["analyst"], sample=sample, reason="Assign frozen required tests"
    )
    assert holds == [] and len(tests) == 1
    return tests[0]


def report(data, test, value="100.25", *, who="receiver", **changes):
    test.refresh_from_db()
    arguments = {
        "expected_revision": test.revision,
        "report_number": REPORT,
        "report_date": today(),
        "raw_reference": "DMS-SYN-CLR-0042",
        "readings": [
            {"value": Decimal(value), "qualifier": "", "outcome": "", "observed_text": ""}
        ],
        **changes,
    }
    return analytical.record_contract_result(actor=data["people"][who], test=test, **arguments)


def approved_laboratory(data, *, sign=True, **dates):
    people = data["people"]
    laboratory = contract.register_contract_laboratory(
        actor=people["author"],
        code="cl-syn-001",
        name="Synthetic Contract Analytics",
        location="Synthetic City, Nowhere",
        reason="Synthetic contract laboratory",
    )
    approval = contract.record_contract_approval(
        actor=people["author"],
        laboratory=laboratory,
        method_code=data["method"].method.code,
        evidence_ref="QAG-SYN-001 rev 1",
        scope_note="Synthetic powders only",
        valid_from=dates.get("valid_from", today() - timedelta(days=30)),
        valid_until=dates.get("valid_until", today() + timedelta(days=300)),
        reason="Synthetic quality agreement",
    )
    if sign:
        approval = contract.approve_contract_approval(
            actor=people["approver"],
            pin=PIN,
            approval=approval,
            expected_revision=approval.revision,
            reason="Independent approval of the laboratory",
        )
    return laboratory, approval


def test_contract_result_from_approval_to_issued_certificate(integrated, client):  # noqa: F811
    data, people = integrated, integrated["people"]
    test = assigned_test(data)
    laboratory, approval = approved_laboratory(data, sign=False)

    # Recorded evidence is not an approval: the report is refused and the refusal is audited.
    with pytest.raises(WorkRefused, match="still awaiting its signature"):
        report(data, test, laboratory_id=laboratory.pk)
    assert not Observation.objects.exists() and not ContractUse.objects.exists()
    refusal = AuditEvent.objects.get(action="contract.report_refused")
    assert refusal.actor == people["receiver"]
    assert refusal.after["context"] == f"analytical.analyticaltest:{test.pk}"
    assert refusal.after["refusals"][0]["subject"] == "cl-syn-001"

    approval = contract.approve_contract_approval(
        actor=people["approver"],
        pin=PIN,
        approval=approval,
        expected_revision=approval.revision,
        reason="Independent approval of the laboratory",
    )
    # The receiver holds no qualification for the method: recording a report needs none, while
    # an observation of their own is still refused.
    with pytest.raises(WorkRefused, match="No approved, current qualification"):
        analytical.record_observation(
            actor=people["receiver"],
            test=test,
            value=Decimal("100.25"),
            raw_reference="RAW-SYN-001",
        )
    (observation,) = report(data, test, laboratory_id=laboratory.pk)
    source = observation.contract
    assert source["laboratory"]["id"] == laboratory.pk
    assert source["approval"]["id"] == approval.pk
    assert source["approval"]["evidence_ref"] == "QAG-SYN-001 rev 1"
    assert source["approval"]["scope"] == "Synthetic powders only"
    use = ContractUse.objects.get()
    assert (use.approval, use.context_id, use.report_number) == (approval, str(test.pk), REPORT)
    assert source["use"] == use.pk and not ResourceUse.objects.exists()

    test.refresh_from_db()
    test, investigation = analytical.submit_test(
        actor=people["receiver"],
        test=test,
        expected_revision=test.revision,
        reason="Report transcribed",
    )
    assert investigation is None and test.conforms
    # Recording the report is authorship: the analyst role signs no review.
    with pytest.raises(PermissionDenied):
        analytical.review_test(
            actor=people["receiver"],
            pin=PIN,
            test=test,
            expected_revision=test.revision,
            reason="Review by the person who recorded the report",
        )
    test = analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Checked against the laboratory's report",
    )
    assert gates.lot_blockers(data["lot"]) == []
    assert people["receiver"].pk in gates.lot_author_ids(data["lot"])

    lot = dispose(data, people["approver"])
    assert lot.state == "released"
    (frozen,) = lot.disposition_evidence["analytical"]["results"]
    assert frozen["contract_laboratory"]["name"] == "Synthetic Contract Analytics"
    assert frozen["contract_laboratory"]["report_number"] == REPORT

    evidence, evidence_hash, blockers = reporting.preview(lot)
    assert blockers == [], blockers
    issued = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic quality recipient",
        evidence_hash=evidence_hash,
        reason="Independent synthetic certificate issue",
    )
    version = issued.versions.get(number=1)
    printed = render_to_string("reporting/_certificate.html", {"snapshot": version.snapshot})
    assert (
        "Tested by contract laboratory Synthetic Contract Analytics, Synthetic City, Nowhere. "
        f"Report {REPORT} dated {today().isoformat()}."
    ) in printed
    assert reporting.read_pdf(actor=people["reviewer"], version=version).startswith(b"%PDF-")

    # The laboratory's record lists the result that relied on its approval, for any reader.
    client.force_login(people["reviewer"])
    page = client.get(
        reverse("laboratory:contract_laboratory_detail", args=[laboratory.pk])
    ).content.decode()
    assert reverse("analytical:test_detail", args=[test.pk]) in page
    assert REPORT in page and lot.number in page and "Reviewed" in page


def test_report_dated_outside_the_approval_and_revocation(integrated, client):  # noqa: F811
    data, people = integrated, integrated["people"]
    test = assigned_test(data)
    laboratory, approval = approved_laboratory(data, valid_from=today() - timedelta(days=5))
    with pytest.raises(WorkRefused, match="covers a report dated"):
        report(data, test, laboratory_id=laboratory.pk, report_date=today() - timedelta(days=6))
    assert not Observation.objects.exists()
    report(data, test, laboratory_id=laboratory.pk, report_date=today() - timedelta(days=5))

    contract.revoke_contract_approval(
        actor=people["author"],
        pin=PIN,
        approval=approval,
        expected_revision=approval.revision,
        reason="Synthetic audit finding",
    )
    # The recorded result stays and says what happened to the approval it relied on.
    assert test.current_observations().count() == 1
    client.force_login(people["reviewer"])
    page = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert f"({approval.label}) was revoked" in page
    # A transcription error in the report already accepted is still corrected, on the
    # evidence relied on then; another report is a new acceptance and is refused.
    accepted = {"laboratory_id": laboratory.pk, "report_date": today() - timedelta(days=5)}
    (corrected,) = report(data, test, "100.30", reason="Transcription error", **accepted)
    assert corrected.contract["approval"]["id"] == approval.pk
    assert corrected.supersedes is not None and ContractUse.objects.count() == 1
    with pytest.raises(WorkRefused, match="was revoked"):
        report(data, test, "100.30", reason="Other report", report_number="CLR-SYN-2", **accepted)
    assert ContractUse.objects.count() == 1
    assert AuditEvent.objects.filter(action="contract.report_refused").count() == 2
    # The reviewer is told about the revocation where the review is signed.
    test.refresh_from_db()
    analytical.submit_test(
        actor=people["receiver"],
        test=test,
        expected_revision=test.revision,
        reason="Report transcribed",
    )
    sign = client.get(reverse("analytical:test_review", args=[test.pk])).content.decode()
    assert "Approval revoked" in sign and f"({approval.label}) was revoked" in sign


def test_recording_the_report_bars_the_disposition_signature(integrated, django_user_model):  # noqa: F811
    """Someone who holds the quality role and did nothing else on the lot: recording the
    contract laboratory's report alone makes them an author who cannot sign the disposition."""
    data, people = integrated, integrated["people"]
    transcriber = django_user_model.objects.create_user(
        username="synthetic_transcriber", password=PASSWORD
    )
    transcriber.groups.add(
        *[Group.objects.get_or_create(name=r)[0] for r in ("analyst", "quality")]
    )
    set_pin(actor=transcriber, pin=PIN, password=PASSWORD)
    people["transcriber"] = transcriber
    test = assigned_test(data)
    laboratory, _ = approved_laboratory(data)
    assert quality.disposition_denial(transcriber, data["lot"]) == ""
    report(data, test, who="transcriber", laboratory_id=laboratory.pk)
    test.refresh_from_db()
    test, _ = analytical.submit_test(
        actor=transcriber, test=test, expected_revision=test.revision, reason="Report transcribed"
    )
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Checked against the laboratory's report",
    )
    assert gates.lot_blockers(data["lot"]) == []
    assert quality.disposition_denial(transcriber, data["lot"]) == quality.SELF_DISPOSITION
    with pytest.raises(ValidationError) as refusal:
        dispose(data, transcriber)
    assert refusal.value.messages == [quality.SELF_DISPOSITION]
    data["lot"].refresh_from_db()
    assert data["lot"].state == "quarantine"


@pytest.mark.parametrize("first", ["report", "revocation"])
def test_a_report_and_a_revocation_at_once(integrated, monkeypatch, first):  # noqa: F811
    """Both lock the approval row. The report that holds it first is recorded and listed for
    assessment; after a revocation that committed first the report is refused and audited."""
    from core import services as core_services
    from laboratory.tests.helpers import run_interleaved

    data, people = integrated, integrated["people"]
    test = assigned_test(data)
    laboratory, approval = approved_laboratory(data)

    def record():
        return report(data, test, laboratory_id=laboratory.pk)

    def revoke():
        return contract.revoke_contract_approval(
            actor=people["author"],
            pin=PIN,
            approval=approval,
            expected_revision=approval.revision,
            reason="Synthetic audit finding",
        )

    if first == "report":
        # Reached once the recorder holds the laboratory's approval rows.
        outcome = run_interleaved(monkeypatch, contract, "contract_eligibility", record, revoke)
    else:
        outcome = run_interleaved(monkeypatch, core_services, "snapshot", revoke, record)
    assert not isinstance(outcome["first"], Exception), outcome["first"]
    approval.refresh_from_db()
    assert approval.state == "revoked"
    if first == "report":
        assert not isinstance(outcome["second"], Exception), outcome["second"]
        assert Observation.objects.count() == 1 and ContractUse.objects.get().approval == approval
    else:
        assert isinstance(outcome["second"], WorkRefused), outcome["second"]
        assert not Observation.objects.exists() and not ContractUse.objects.exists()
        refused = AuditEvent.objects.get(action="contract.report_refused")
        assert refused.after["laboratory"] == laboratory.pk
        assert refused.after["report"] == {"number": REPORT, "date": today().isoformat()}


def test_disposition_page_says_when_a_relied_on_approval_was_revoked(integrated, client):  # noqa: F811
    data, people = integrated, integrated["people"]
    test = assigned_test(data)
    laboratory, approval = approved_laboratory(data)
    report(data, test, laboratory_id=laboratory.pk)
    test.refresh_from_db()
    test, _ = analytical.submit_test(
        actor=people["receiver"],
        test=test,
        expected_revision=test.revision,
        reason="Report transcribed",
    )
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Checked against the laboratory's report",
    )
    assert quality.disposition_notices(data["lot"]) == []
    contract.revoke_contract_approval(
        actor=people["author"],
        pin=PIN,
        approval=approval,
        expected_revision=approval.revision,
        reason="Synthetic audit finding",
    )
    (notice,) = quality.disposition_notices(data["lot"])
    assert f"{test.label} assay was reported by a contract laboratory." in notice
    assert f"({approval.label}) was revoked" in notice and "does not block" in notice
    client.force_login(people["approver"])
    page = client.get(reverse("quality:disposition", args=[data["lot"].pk])).content.decode()
    assert "was reported by a contract laboratory" in page and 'name="pin"' in page
    # Information only: the lot is still dispositioned by an independent quality signer.
    assert dispose(data, people["approver"]).state == "released"
