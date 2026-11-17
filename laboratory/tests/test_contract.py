"""Contract laboratories: the register, the signed approval per method and the gate that lets a
reported result be relied on. Refusals, independence, immutability and concurrency."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.urls import reverse
from django.utils import timezone

from catalog.models import Method
from core import services as core_services
from core.models import AuditEvent, ElectronicSignature, PINCredential
from laboratory import contract
from laboratory.models import ContractApproval, ContractLaboratory, ContractUse

from .access import make_user
from .helpers import (
    PIN,
    approve_contract_laboratory,
    make_contract_laboratory,
    run_interleaved,
)

pytestmark = pytest.mark.django_db(transaction=True)

METHOD = "HPLC-ASSAY"
CONTEXT = "analytical.analyticaltest"


def today():
    return timezone.localdate()


def accept(people, laboratory, *, method=METHOD, report_date=None, number="CLR-SYN-001"):
    with transaction.atomic():
        return contract.use_contract_report(
            actor=people["analyst"],
            laboratory_id=laboratory.pk,
            method_code=method,
            context_type=CONTEXT,
            context_id=1,
            report_number=number,
            report_date=report_date or today(),
            test_code="assay",
        )


def sign(people, approval, *, approve, who="quality2", pin=PIN):
    approval.refresh_from_db()
    service = contract.approve_contract_approval if approve else contract.revoke_contract_approval
    return service(
        actor=people[who],
        pin=pin,
        approval=approval,
        expected_revision=approval.revision,
        reason="Evidence checked",
    )


def counts():
    return (
        ContractLaboratory.objects.count(),
        ContractApproval.objects.count(),
        ContractUse.objects.count(),
        ElectronicSignature.objects.count(),
    )


# Register ---------------------------------------------------------------------------------------


def test_quality_registers_a_laboratory_and_nobody_else(people):
    laboratory = make_contract_laboratory(people)
    assert (laboratory.code, laboratory.created_by) == ("cl-syn-001", people["quality"])
    event = AuditEvent.objects.get(action="contract_laboratory.registered")
    assert event.after["name"] == "Synthetic Contract Analytics"
    assert event.reason == "Synthetic contract laboratory"
    for name in ("analyst", "reviewer", "auditor", "admin"):
        with pytest.raises(PermissionDenied):
            contract.register_contract_laboratory(
                actor=people[name], code="cl-syn-002", name="Other", location="Town", reason="Add"
            )
    with pytest.raises(ValidationError, match="A reason is required"):
        contract.register_contract_laboratory(
            actor=people["quality"], code="cl-syn-002", name="Other", location="Town", reason=" "
        )
    with pytest.raises(ValidationError) as taken:
        make_contract_laboratory(people)
    assert taken.value.messages == [contract.CODE_TAKEN]
    assert ContractLaboratory.objects.count() == 1


def test_two_people_adding_one_code_at_once_get_one_laboratory(people, monkeypatch):
    def add(who):
        return lambda: contract.register_contract_laboratory(
            actor=people[who],
            code="cl-syn-009",
            name="Synthetic Contract Analytics",
            location="Synthetic City, Nowhere",
            reason="Synthetic contract laboratory",
        )

    # The first has checked that the code is free and has not yet committed.
    outcome = run_interleaved(
        monkeypatch, contract, "record_event", add("quality"), add("quality2")
    )
    assert isinstance(outcome["first"], ContractLaboratory), outcome["first"]
    assert isinstance(outcome["second"], ValidationError), outcome["second"]
    assert outcome["second"].messages == [contract.CODE_TAKEN]
    assert ContractLaboratory.objects.filter(code="cl-syn-009").count() == 1


def test_laboratory_identity_cannot_be_changed_or_deleted(people):
    laboratory = make_contract_laboratory(people)
    with pytest.raises(DatabaseError), transaction.atomic():
        ContractLaboratory.objects.filter(pk=laboratory.pk).update(name="Renamed")
    with pytest.raises(DatabaseError), transaction.atomic():
        ContractLaboratory.objects.filter(pk=laboratory.pk).delete()
    laboratory.refresh_from_db()
    assert laboratory.name == "Synthetic Contract Analytics"


# Approval ---------------------------------------------------------------------------------------


def test_recorded_evidence_approves_nothing_until_a_second_person_signs(people):
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory, sign=False)
    assert (approval.state, approval.approved_at) == ("recorded", None)
    finding = contract.contract_eligibility(laboratory, METHOD, today())
    assert not finding.ok and "still awaiting its signature" in finding.reasons[0]
    assert contract.contract_choices(METHOD) == []
    with pytest.raises(contract.ContractBlocked):
        accept(people, laboratory)

    # The recorder cannot approve, whatever other roles the account holds.
    assert contract.approval_denial(people["quality"], approval, approve=True) == (
        contract.SELF_APPROVAL
    )
    with pytest.raises(PermissionDenied, match="you recorded"):
        sign(people, approval, approve=True, who="quality")
    for name in ("analyst", "reviewer"):
        with pytest.raises(PermissionDenied):
            sign(people, approval, approve=True, who=name)
    approval.refresh_from_db()
    assert approval.state == "recorded" and not ElectronicSignature.objects.exists()

    approved = sign(people, approval, approve=True)
    assert approved.state == "approved" and approved.approved_at is not None
    signature = ElectronicSignature.objects.get()
    assert (signature.signer, signature.meaning) == (people["quality2"], "approved")
    assert (signature.object_type, signature.object_id) == (
        "laboratory.contractapproval",
        str(approval.pk),
    )
    assert signature.revision == approved.revision == 2
    assert contract.contract_eligibility(laboratory, METHOD, today()).ok
    (choice,) = contract.contract_choices(METHOD)
    assert choice[0] == laboratory.pk and "cl-syn-001 · Synthetic Contract Analytics" in choice[1]


def test_only_quality_records_an_approval_and_it_states_its_evidence(people):
    laboratory = make_contract_laboratory(people)
    values = {
        "laboratory": laboratory,
        "method_code": METHOD,
        "evidence_ref": "QAG-SYN-001 rev 1",
        "valid_from": today(),
        "valid_until": today() + timedelta(days=30),
        "reason": "Synthetic quality agreement",
    }
    for name in ("analyst", "reviewer", "auditor", "admin"):
        with pytest.raises(PermissionDenied):
            contract.record_contract_approval(actor=people[name], **values)
    for change in (
        {"reason": " "},
        {"method_code": "  "},
        {"evidence_ref": ""},
        {"valid_until": today() - timedelta(days=1)},
        {"evidence_url": "javascript:alert(1)"},
    ):
        with pytest.raises(ValidationError):
            contract.record_contract_approval(actor=people["quality"], **{**values, **change})
    assert not ContractApproval.objects.exists()
    approval = contract.record_contract_approval(
        actor=people["quality"], **{**values, "method_code": "  HPLC-ASSAY "}
    )
    assert approval.method_code == METHOD  # surrounding spaces are not part of the code
    assert AuditEvent.objects.get(action="contract_approval.recorded").after["evidence_ref"] == (
        "QAG-SYN-001 rev 1"
    )


def test_stale_page_and_wrong_pin_do_not_approve_and_past_dates_can_be_signed(people):
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory, sign=False)
    with pytest.raises(ValidationError, match="Record changed"):
        contract.approve_contract_approval(
            actor=people["quality2"],
            pin=PIN,
            approval=approval,
            expected_revision=approval.revision + 1,
            reason="Evidence checked",
        )
    with pytest.raises(ValidationError, match="PIN was not accepted"):
        sign(people, approval, approve=True, pin="00000000")
    # The failed attempt is counted although nothing was approved.
    assert PINCredential.objects.get(user=people["quality2"]).failures == 1
    approval.refresh_from_db()
    assert approval.state == "recorded" and not ElectronicSignature.objects.exists()

    past = approve_contract_laboratory(
        people, laboratory, "KF-WATER", sign=False, days_before=60, days_after=-1
    )
    assert "not signed yet" in contract.approval_denial(people["quality2"], past, approve=False)
    # Evidence whose dates lie in the past can still be signed: it covers the reports dated
    # within it, whenever they are recorded.
    assert contract.approval_denial(people["quality2"], past, approve=True) == ""
    assert sign(people, past, approve=True).state == "approved"
    inside = today() - timedelta(days=10)
    assert accept(people, laboratory, method="KF-WATER", report_date=inside)["approval"]["id"] == (
        past.pk
    )
    with pytest.raises(contract.ContractBlocked):
        accept(people, laboratory, method="KF-WATER", report_date=today())


def test_revocation_is_signed_and_ends_reliance(people):
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory)
    evidence = accept(people, laboratory)
    assert contract.reliance_notice(evidence) == ""
    with pytest.raises(PermissionDenied):
        sign(people, approval, approve=False, who="reviewer")
    # Revoking is protective: the person who recorded the evidence may do it.
    revoked = sign(people, approval, approve=False, who="quality")
    assert revoked.state == "revoked" and revoked.revoked_at is not None
    assert ElectronicSignature.objects.filter(meaning="revoked").count() == 1
    finding = contract.contract_eligibility(laboratory, METHOD, today())
    assert not finding.ok and "was revoked" in finding.reasons[0]
    assert contract.contract_choices(METHOD) == []
    before = counts()
    with pytest.raises(contract.ContractBlocked):
        accept(people, laboratory, number="CLR-SYN-002")
    assert counts() == before
    # The result recorded before stays, and its reader is told.
    assert ContractUse.objects.get().approval == approval
    assert f"({approval.label}) was revoked" in contract.reliance_notice(evidence)
    for change in (True, False):  # a revoked approval is final
        assert "A revoked approval is final" in contract.approval_denial(
            people["quality2"], revoked, approve=change
        )
        with pytest.raises(ValidationError):
            sign(people, approval, approve=change)


# Gate -------------------------------------------------------------------------------------------


def test_the_approval_must_cover_the_date_of_the_report(people):
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory, days_before=10, days_after=20)
    start, end = approval.valid_from, approval.valid_until

    def ok(day, method=METHOD, *, now=None):
        return contract.contract_eligibility(laboratory, method, day, today=now).ok

    assert ok(start) and ok(today())
    assert not ok(start - timedelta(days=1))
    # Both days of the interval count; a report cannot be dated after the day it is recorded.
    assert ok(end, now=end) and not ok(end + timedelta(days=1), now=end + timedelta(days=5))
    future = contract.contract_eligibility(laboratory, METHOD, today() + timedelta(days=1))
    assert future.reasons == ("The report cannot be dated in the future.",)
    # An approval that has since run out still covers a report dated within it.
    assert ok(end, now=end + timedelta(days=90))
    assert ok(today(), "hplc-assay")  # the method code is matched whatever its case
    other = contract.contract_eligibility(laboratory, "KF-WATER", today())
    assert other.reasons == ("The laboratory is not approved for method “KF-WATER”.",)
    outside = contract.contract_eligibility(laboratory, METHOD, start - timedelta(days=1))
    assert "covers a report dated" in outside.reasons[0]
    assert contract.contract_eligibility(laboratory, METHOD, None).reasons == (
        "Enter the date of the report.",
    )
    # Another laboratory's approval is not this laboratory's.
    second = make_contract_laboratory(people, "cl-syn-002")
    assert not contract.contract_eligibility(second, METHOD, today()).ok


def test_a_renewed_approval_and_the_one_before_each_cover_their_own_dates(people):
    laboratory = make_contract_laboratory(people)
    earlier = approve_contract_laboratory(people, laboratory, days_before=40, days_after=5)
    later = approve_contract_laboratory(people, laboratory, days_before=10, days_after=300)
    old = accept(people, laboratory, report_date=today() - timedelta(days=20))
    # Where the two overlap, the approval recorded last is the one relied on.
    new = accept(people, laboratory, report_date=today(), number="CLR-SYN-002")
    assert (old["approval"]["id"], new["approval"]["id"]) == (earlier.pk, later.pk)
    choice = contract.contract_choices(METHOD)[0][1]
    assert choice.count(" to ") == 2  # both periods are shown to the person choosing


def test_accepting_a_report_records_the_use_and_returns_the_evidence(people):
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory)
    with pytest.raises(RuntimeError):  # only inside the caller's transaction
        contract.use_contract_report(
            actor=people["analyst"],
            laboratory_id=laboratory.pk,
            method_code=METHOD,
            context_type=CONTEXT,
            context_id=1,
            report_number="CLR-SYN-001",
            report_date=today(),
        )
    evidence = accept(people, laboratory, number="  CLR-SYN-001 ")
    use = ContractUse.objects.get()
    assert evidence == {
        "laboratory": {
            "id": laboratory.pk,
            "code": "cl-syn-001",
            "name": "Synthetic Contract Analytics",
            "location": "Synthetic City, Nowhere",
        },
        "approval": {
            "id": approval.pk,
            "method_code": METHOD,
            "valid_from": approval.valid_from.isoformat(),
            "valid_until": approval.valid_until.isoformat(),
            "evidence_ref": "QAG-SYN-001 rev 1",
            "scope": "",
            "approved_at": approval.approved_at.isoformat(),
        },
        "report": {"number": "CLR-SYN-001", "date": today().isoformat()},
        "use": use.pk,
    }
    assert (use.approval, use.context_type, use.context_id) == (approval, CONTEXT, "1")
    assert (use.method_code, use.test_code, use.used_by) == (METHOD, "assay", people["analyst"])
    before = counts()
    for change in ({"number": "  "}, {"method": "KF-WATER"}, {"number": "X" * 121}):
        with pytest.raises(ValidationError):
            accept(people, laboratory, **change)
    with pytest.raises(ValidationError, match="does not exist"), transaction.atomic():
        contract.use_contract_report(
            actor=people["analyst"],
            laboratory_id=999_999,
            method_code=METHOD,
            context_type=CONTEXT,
            context_id=1,
            report_number="CLR-SYN-001",
            report_date=today(),
        )
    assert counts() == before


def test_a_refusal_is_audited_outside_the_rolled_back_entry(people):
    laboratory = make_contract_laboratory(people)
    with pytest.raises(contract.ContractBlocked) as refusal:
        accept(people, laboratory)
    finding = refusal.value.finding
    assert (finding.subject, finding.ok) == ("cl-syn-001", False)
    contract.record_blocked_contract(
        actor=people["analyst"],
        laboratory_id=laboratory.pk,
        method_code=METHOD,
        context_type=CONTEXT,
        context_id=1,
        report_number="CLR-SYN-001",
        report_date=today(),
        refusals=[{"subject": finding.subject, "reasons": list(finding.reasons)}],
        reason="Contract laboratory result for T-1 assay",
    )
    event = AuditEvent.objects.get(action="contract.report_refused")
    assert event.actor == people["analyst"]
    assert event.after == {
        "context": f"{CONTEXT}:1",
        "method": METHOD,
        "laboratory": laboratory.pk,
        "report": {"number": "CLR-SYN-001", "date": today().isoformat()},
        "refusals": [
            {
                "subject": "cl-syn-001",
                "reasons": ["The laboratory is not approved for method “HPLC-ASSAY”."],
            }
        ],
    }
    assert not ContractUse.objects.exists()


def test_a_report_waits_for_a_revocation_being_signed_and_is_then_refused(people, monkeypatch):
    """Both lock the approval row: the revocation that commits first decides."""
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory)
    outcome = run_interleaved(
        monkeypatch,
        core_services,
        "snapshot",  # taken once the signer holds the approval row
        lambda: sign(people, approval, approve=False),
        lambda: accept(people, laboratory),
    )
    assert isinstance(outcome["first"], ContractApproval), outcome["first"]
    assert isinstance(outcome["second"], contract.ContractBlocked), outcome["second"]
    assert not ContractUse.objects.exists()


# Database guards --------------------------------------------------------------------------------


def test_database_keeps_approval_evidence_and_its_lifecycle(people):
    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory, sign=False)
    rows = ContractApproval.objects.filter(pk=approval.pk)
    for change in (
        {"evidence_ref": "Another document"},
        {"valid_until": approval.valid_until + timedelta(days=365)},
        {"method_code": "KF-WATER"},
        {"state": "revoked", "approved_at": timezone.now(), "revoked_at": timezone.now()},
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            rows.update(**change)
    with pytest.raises(DatabaseError), transaction.atomic():
        rows.delete()
    # A row cannot be written already approved, around the signature.
    with pytest.raises(DatabaseError), transaction.atomic():
        ContractApproval.objects.create(
            laboratory=laboratory,
            method_code=METHOD,
            evidence_ref="QAG-SYN-002",
            valid_from=today(),
            valid_until=today(),
            recorded_by=people["quality"],
            state="approved",
            approved_at=timezone.now(),
        )
    # Nor approved by a plain write that leaves out the time, or adds a revocation time.
    for change in (
        {"state": "approved"},
        {"state": "approved", "approved_at": timezone.now(), "revoked_at": timezone.now()},
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            rows.update(**change)
    approved = sign(people, approval, approve=True)
    signed_at = approved.approved_at
    for change in (
        {"state": "recorded", "approved_at": None},
        # A revocation states its time and never rewrites the time of the approval.
        {"state": "revoked"},
        {"state": "revoked", "revoked_at": timezone.now(), "approved_at": timezone.now()},
        {"state": "revoked", "revoked_at": timezone.now(), "approved_at": None},
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            rows.update(**change)
    approved.refresh_from_db()
    assert (approved.state, approved.evidence_ref) == ("approved", "QAG-SYN-001 rev 1")
    assert (approved.approved_at, approved.revoked_at) == (signed_at, None)
    revoked = sign(people, approved, approve=False)
    assert revoked.approved_at == signed_at and revoked.revoked_at is not None


def test_database_accepts_a_use_only_under_a_covering_approved_approval(people):
    laboratory = make_contract_laboratory(people)
    waiting = approve_contract_laboratory(people, laboratory, sign=False)
    approved = approve_contract_laboratory(people, laboratory, days_before=5, days_after=5)

    def write(approval, **changes):
        values = {
            "approval": approval,
            "context_type": CONTEXT,
            "context_id": "1",
            "method_code": METHOD,
            "report_number": "CLR-SYN-001",
            "report_date": today(),
            "used_by": people["analyst"],
            **changes,
        }
        with transaction.atomic():
            return ContractUse.objects.create(**values)

    for approval, changes in (
        (waiting, {}),
        (approved, {"report_date": today() - timedelta(days=6)}),
        (approved, {"report_date": today() + timedelta(days=6)}),
        (approved, {"method_code": "KF-WATER"}),
        (approved, {"report_number": "  "}),
    ):
        with pytest.raises(DatabaseError):
            write(approval, **changes)
    use = write(approved)
    with pytest.raises(DatabaseError), transaction.atomic():
        ContractUse.objects.filter(pk=use.pk).update(report_number="Changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        ContractUse.objects.filter(pk=use.pk).delete()
    sign(people, approved, approve=False)
    with pytest.raises(DatabaseError):
        write(approved, report_number="CLR-SYN-002")
    assert ContractUse.objects.count() == 1


# Pages ------------------------------------------------------------------------------------------


def sign_post(client, url, user, revision, *, pin=PIN):
    return client.post(
        url,
        {
            "signature_username": user.username,
            "expected_revision": revision,
            "pin": pin,
            "reason": "Evidence checked",
        },
    )


def test_register_and_approval_through_the_pages(client, people):
    listing = reverse("laboratory:contract_laboratory_list")
    client.force_login(people["quality"])
    page = client.get(listing).content.decode()
    assert "No records yet" in page and reverse("laboratory:contract_laboratory_new") in page
    new = reverse("laboratory:contract_laboratory_new")
    refused = client.post(new, {"code": "cl syn", "name": "", "location": "", "reason": ""})
    assert refused.status_code == 422 and not ContractLaboratory.objects.exists()
    created = client.post(
        new,
        {
            "code": "cl-syn-001",
            "name": "Synthetic Contract Analytics",
            "location": "Synthetic City, Nowhere",
            "reason": "Synthetic contract laboratory",
        },
        follow=True,
    )
    laboratory = ContractLaboratory.objects.get()
    detail = reverse("laboratory:contract_laboratory_detail", args=[laboratory.pk])
    assert created.redirect_chain[-1][0] == detail
    body = created.content.decode()
    assert "Contract laboratory cl-syn-001 added." in body
    assert "Results from this laboratory are refused until an approval" in body
    duplicate = client.post(
        new, {"code": "cl-syn-001", "name": "Again", "location": "Town", "reason": "Again"}
    )
    assert duplicate.status_code == 422
    assert "This contract laboratory code already exists." in duplicate.content.decode()

    record = reverse("laboratory:contract_approval_new", args=[laboratory.pk])
    assert record in body
    Method.objects.create(code="hplc-assay", title="Synthetic assay", created_by=people["quality"])
    values = {
        "method_code": METHOD,
        "scope_note": "Synthetic powders",
        "evidence_ref": "QAG-SYN-001 rev 1",
        "evidence_url": "",
        "valid_from": (today() - timedelta(days=30)).isoformat(),
        "valid_until": (today() + timedelta(days=300)).isoformat(),
        "reason": "Synthetic quality agreement",
    }
    backwards = client.post(record, {**values, "valid_until": "2020-01-01"})
    assert backwards.status_code == 422
    assert "Valid until cannot precede valid from." in backwards.content.decode()
    # A code the method catalog does not hold would approve nothing: the typo is refused.
    typo = client.post(record, {**values, "method_code": "HPLC-ASSSAY"})
    assert typo.status_code == 422
    assert "The method catalog holds no method with this code." in typo.content.decode()
    assert not ContractApproval.objects.exists()
    recorded = client.post(record, values, follow=True)
    approval = ContractApproval.objects.get()
    assert approval.method_code == "hplc-assay"  # stored as the catalog writes it
    approval_url = reverse("laboratory:contract_approval_detail", args=[approval.pk])
    assert recorded.redirect_chain[-1][0] == approval_url
    body = recorded.content.decode()
    assert "Awaiting approval" in body and approval.label in body
    approve = reverse("laboratory:contract_approval_approve", args=[approval.pk])
    revoke = reverse("laboratory:contract_approval_revoke", args=[approval.pk])
    # The recorder is shown no way to approve, and the page refuses without a PIN control.
    assert approve not in body and revoke not in body
    denied = client.get(approve)
    assert denied.status_code == 403
    assert contract.SELF_APPROVAL in denied.content.decode()
    assert 'name="pin"' not in denied.content.decode()
    assert sign_post(client, approve, people["quality"], approval.revision).status_code == 403

    client.force_login(people["quality2"])
    assert approve in client.get(approval_url).content.decode()
    signing = client.get(approve).content.decode()
    # The signer sees everything the signature binds, the scope included.
    assert "Synthetic powders" in signing and "QAG-SYN-001 rev 1" in signing
    wrong = sign_post(client, approve, people["quality2"], approval.revision, pin="00000000")
    assert wrong.status_code == 422 and "PIN was not accepted" in wrong.content.decode()
    approval.refresh_from_db()
    assert approval.state == "recorded"
    signed = sign_post(client, approve, people["quality2"], approval.revision)
    assert signed.status_code == 302 and signed.url == approval_url
    approval.refresh_from_db()
    assert approval.state == "approved"
    body = client.get(approval_url).content.decode()
    assert revoke in body and approve not in body and "No result has relied on it." in body
    listed = client.get(listing).content.decode()
    assert "cl-syn-001" in listed and "Synthetic City, Nowhere" in listed
    for status, shown in (("current", True), ("waiting", False), ("none", False)):
        filtered = client.get(listing, {"status": status}).content.decode()
        assert ("cl-syn-001" in filtered) is shown, status
    assert "cl-syn-001" in client.get(listing, {"q": "hplc"}).content.decode()
    assert "cl-syn-001" not in client.get(listing, {"q": "nothing-like-it"}).content.decode()

    assert "Accepted reports that relied on it" in client.get(revoke).content.decode()
    revoked = sign_post(client, revoke, people["quality2"], approval.revision)
    assert revoked.status_code == 302
    approval.refresh_from_db()
    assert approval.state == "revoked"
    final = client.get(revoke)
    assert final.status_code == 403 and "A revoked approval is final" in final.content.decode()


def test_roles_around_the_contract_pages(client, people, django_user_model):
    laboratory = make_contract_laboratory(people)
    waiting = approve_contract_laboratory(people, laboratory, sign=False)
    reads = [
        reverse("laboratory:contract_laboratory_list"),
        reverse("laboratory:contract_laboratory_detail", args=[laboratory.pk]),
        reverse("laboratory:contract_approval_detail", args=[waiting.pk]),
    ]
    writes = [
        reverse("laboratory:contract_laboratory_new"),
        reverse("laboratory:contract_approval_new", args=[laboratory.pk]),
        reverse("laboratory:contract_approval_approve", args=[waiting.pk]),
        reverse("laboratory:contract_approval_revoke", args=[waiting.pk]),
    ]
    assert client.get(reads[0]).status_code == 302  # sign-in first
    outsider = django_user_model.objects.create_user("outsider", password="password-for-tests")
    client.force_login(outsider)
    assert [client.get(url).status_code for url in reads] == [403, 403, 403]
    for name in ("analyst", "reviewer", "auditor", "admin"):
        client.force_login(people[name])
        for url in reads:
            response = client.get(url)
            assert response.status_code == 200, (name, url)
            for write in writes:
                assert f'href="{write}' not in response.content.decode(), (name, url, write)
        for url in writes:
            assert client.get(url).status_code == 403, (name, url)
            assert client.post(url, {"reason": "Attempt", "pin": PIN}).status_code == 403
    # An administrator who is also quality has the quality role's authority and its limits.
    both = make_user(django_user_model, "admin_quality", ["admin", "quality"])
    client.force_login(both)
    assert client.get(writes[0]).status_code == 200
    assert client.get(writes[2]).status_code == 200  # did not record this evidence
    assert ContractApproval.objects.get().state == "recorded"


def test_laboratory_and_approval_pages_list_the_results_that_relied_on_them(client, people):
    from .test_bench import make_test

    laboratory = make_contract_laboratory(people)
    approval = approve_contract_laboratory(people, laboratory)
    test = make_test(people)
    with transaction.atomic():
        contract.use_contract_report(
            actor=people["analyst"],
            laboratory_id=laboratory.pk,
            method_code=METHOD,
            context_type=CONTEXT,
            context_id=test.pk,
            report_number="CLR-SYN-001",
            report_date=today(),
            test_code="assay",
        )
    client.force_login(people["auditor"])
    link = reverse("analytical:test_detail", args=[test.pk])
    for url in (
        reverse("laboratory:contract_laboratory_detail", args=[laboratory.pk]),
        reverse("laboratory:contract_approval_detail", args=[approval.pk]),
    ):
        body = client.get(url).content.decode()
        assert f'href="{link}"' in body and "CLR-SYN-001" in body and "SYN-LOT-1" in body
    sign(people, approval, approve=False)
    body = client.get(
        reverse("laboratory:contract_approval_detail", args=[approval.pk])
    ).content.decode()
    assert "1 accepted report relied on this approval before it was revoked." in body
    assert "the software records no assessment and holds no lot by itself" in body
    assert "Revoked" in body


def test_overview_counts_laboratories_and_the_list_counts_methods(client, people):
    laboratory = make_contract_laboratory(people)
    approve_contract_laboratory(people, laboratory, sign=False)
    approve_contract_laboratory(people, laboratory, sign=False, days_after=200)
    approve_contract_laboratory(people, laboratory, "KF-WATER", days_after=10)
    approve_contract_laboratory(people, laboratory, "kf-water", days_after=20)
    client.force_login(people["quality"])
    response = client.get(reverse("laboratory:overview"))
    body = response.content.decode()
    listing = reverse("laboratory:contract_laboratory_list")
    assert f'href="{listing}?status=waiting"' in body
    assert f'href="{listing}?status=expiring"' in body
    # One laboratory behind each queue, however many approvals it holds: the count is the
    # number of rows the queue opens.
    counts = {q["label"]: q["count"] for q in response.context["queues"]}
    assert counts["Contract laboratories with an approval awaiting signature"] == 1
    assert counts["Contract laboratories with an approval expiring within 30 days"] == 1
    row = client.get(listing).context["rows"][0]
    # Two approvals of one method in force are one method; two wait for a signature.
    assert row[2]["text"] == "Expiring soon"  # the approval that most needs attention
    assert [cell["text"] for cell in row[3:5]] == ["1", "2"]
    for status in ("waiting", "expiring", "current"):
        assert "cl-syn-001" in client.get(listing, {"status": status}).content.decode(), status
    assert "Contract laboratories" in body  # the section tab


def test_approving_a_laboratory_is_not_authorship_of_its_results(people, django_user_model):
    """Decided: whoever recorded or signed an approval may, with the analyst role, record a
    report under it. Recording the report is what makes someone an author of the result, and
    review and disposition independence are enforced there."""
    both = make_user(django_user_model, "quality_analyst", ["quality", "analyst"])
    laboratory = make_contract_laboratory(people)
    approval = contract.record_contract_approval(
        actor=people["quality"],
        laboratory=laboratory,
        method_code=METHOD,
        evidence_ref="QAG-SYN-001 rev 1",
        valid_from=today() - timedelta(days=30),
        valid_until=today() + timedelta(days=300),
        reason="Synthetic quality agreement",
    )
    approval = contract.approve_contract_approval(
        actor=both,
        pin=PIN,
        approval=approval,
        expected_revision=approval.revision,
        reason="Independent approval",
    )
    with transaction.atomic():
        evidence = contract.use_contract_report(
            actor=both,
            laboratory_id=laboratory.pk,
            method_code=METHOD,
            context_type=CONTEXT,
            context_id=1,
            report_number="CLR-SYN-001",
            report_date=today(),
        )
    assert evidence["approval"]["id"] == approval.pk
    assert ContractUse.objects.get().used_by == both
