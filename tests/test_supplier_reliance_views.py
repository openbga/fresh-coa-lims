"""Reliance on a supplier's results through the pages: the supplier qualification, the proposal,
the signed acceptance, its withdrawal, and what the lot, testing and disposition pages show."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent
from quality import reliance
from quality.models import SupplierResultAcceptance
from suppliers.models import SupplierQualification
from tests.test_integrated_journey import PIN
from tests.test_supplier_certificates import certify, sample_and_test
from tests.test_supplier_reliance import (
    RELIED,
    accept,
    accepted_lot,
    build_reliance_world,
    fully_stated,
    line,
    propose,
    qualify,
    revoke,
    today,
)

pytestmark = pytest.mark.django_db(transaction=True)
READERS = ["analyst2", "reviewer", "quality", "auditor", "admin"]


@pytest.fixture
def world(django_user_model):
    return build_reliance_world(django_user_model)


def sign_in(client, world, name):
    client.force_login(world["people"][name])
    return world["people"][name]


def signing(user, record, reason="Checked against the evidence", pin=PIN):
    return {
        "signature_username": user.username,
        "expected_revision": record.revision,
        "reason": reason,
        "pin": pin,
    }


def text(response):
    return response.content.decode()


def basis_of(page):
    """The token the proposal page carries of what it showed."""
    return re.search(r'name="basis" value="([0-9a-f]{64})"', page).group(1)


# Supplier qualification pages ---------------------------------------------------------------------


def test_qualification_is_recorded_in_two_steps_and_signed_by_another(client, world):
    supplier, material = world["supplier"], world["material"]
    new = reverse("suppliers:qualification_new", args=[supplier.pk])
    detail = reverse("suppliers:detail", args=[supplier.pk])
    for name in ("analyst2", "reviewer", "auditor", "admin"):
        sign_in(client, world, name)
        assert client.get(new).status_code == 403
        assert "Record qualification" not in text(client.get(detail))
    author = sign_in(client, world, "author")
    page = text(client.get(detail))
    assert f'href="{new}"' in page and "No qualification is recorded." in page
    # First step: the material. Nothing is written.
    first = text(client.get(new))
    assert 'name="material"' in first and 'name="test_codes"' not in first
    form = text(client.get(new, {"material": material.pk}))
    for code in ("identity", *RELIED):
        assert f'value="{code}"' in form
    assert "Assay (assay)" in form and str(material) in form
    posted = {
        "test_codes": ["assay", "impurity"],
        "basis": "Three synthetic lots tested in full and compared with the certificates",
        "evidence_ref": "SQR-SYN-001 rev 1",
        "evidence_url": "",
        "valid_from": (today() - timedelta(days=10)).isoformat(),
        "valid_until": (today() + timedelta(days=200)).isoformat(),
        "reason": "Synthetic supplier qualification",
    }
    url = f"{new}?material={material.pk}"
    refused = client.post(url, posted | {"test_codes": []})
    assert refused.status_code == 422 and not SupplierQualification.objects.exists()
    refused = client.post(url, posted | {"valid_until": (today() - timedelta(days=20)).isoformat()})
    assert refused.status_code == 422
    assert "cannot be before the first" in text(refused)
    refused = client.post(url, posted | {"evidence_url": "ftp://files.example/report"})
    assert refused.status_code == 422 and not SupplierQualification.objects.exists()
    response = client.post(url, posted)
    qualification = SupplierQualification.objects.get()
    record = reverse("suppliers:qualification_detail", args=[qualification.pk])
    assert response.status_code == 302 and response.url == record
    assert qualification.test_codes == ["assay", "impurity"]
    assert qualification.recorded_by == author and qualification.state == "recorded"

    approve = reverse("suppliers:qualification_approve", args=[qualification.pk])
    revoke_url = reverse("suppliers:qualification_revoke", args=[qualification.pk])
    page = text(client.get(record))
    assert "Awaiting approval" in page and "Assay (assay), Impurity (impurity)" in page
    assert f'href="{approve}"' not in page  # The recorder is not offered the signature.
    denied = client.get(approve)
    assert denied.status_code == 403 and "you recorded" in text(denied)
    assert 'name="pin"' not in text(denied)
    for name in READERS:
        sign_in(client, world, name)
        assert client.get(record).status_code == 200
        if name != "quality":
            assert client.get(approve).status_code == 403
    approver = sign_in(client, world, "approver")
    page = text(client.get(record))
    assert f'href="{approve}"' in page and f'href="{revoke_url}"' not in page
    sign = text(client.get(approve))
    assert "You approve this evidence" in sign and "SQR-SYN-001 rev 1" in sign
    wrong = client.post(approve, signing(approver, qualification, pin="00000000"))
    assert wrong.status_code == 422 and "PIN was not accepted" in text(wrong)
    response = client.post(approve, signing(approver, qualification))
    assert response.status_code == 302 and response.url == record
    qualification.refresh_from_db()
    assert qualification.state == "approved"
    page = text(client.get(record))
    assert "Approved" in page and f'href="{revoke_url}"' in page
    assert "No supplier result has relied on it." in page
    assert "signed.approved" in page
    # The supplier's record lists it.
    page = text(client.get(detail))
    assert f'href="{record}"' in page and qualification.label in page
    assert "SQR-SYN-001 rev 1" in page and "No qualification is recorded." not in page
    qualification.refresh_from_db()
    response = client.post(revoke_url, signing(approver, qualification, "Synthetic discrepancy"))
    assert response.status_code == 302
    qualification.refresh_from_db()
    assert qualification.state == "revoked"
    assert "Revoked" in text(client.get(record))


# Proposing, accepting and withdrawing through the pages -------------------------------------------


def test_certificate_page_offers_a_proposal_only_where_it_would_stand(client, world):
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    page_url = reverse("quality:certificate_detail", args=[certificate.pk])
    assay = reverse("quality:acceptance_new", args=[line(certificate, "assay").pk])
    identity = reverse("quality:acceptance_new", args=[line(certificate, "identity").pk])
    sign_in(client, world, "analyst2")
    # No qualification yet: nothing is offered and the page says why.
    page = text(client.get(page_url))
    assert "In place of a test" in page and f'href="{assay}"' not in page
    assert "Not available: sup-syn-001 is not qualified for synthetic-rt-material." in page
    assert "requires the laboratory to perform identity itself" in page
    refused = client.get(assay, follow=True)
    assert refused.redirect_chain[-1][0] == page_url
    assert "is not qualified for" in text(refused)
    qualify(world)
    page = text(client.get(page_url))
    assert f'href="{assay}"' in page and f'href="{identity}"' not in page
    assert page.count("Propose in place of a test") == 4
    # Readers without the analyst role see the state, never the action or the reasons.
    for name in ("reviewer", "quality", "auditor", "admin"):
        sign_in(client, world, name)
        page = text(client.get(page_url))
        assert "Propose in place of a test" not in page and "Not available" not in page
        assert "In place of a test:" not in page
        assert client.get(assay).status_code == 403
    assert not AuditEvent.objects.filter(action="supplier_result.refused").exists()


def test_a_supplier_result_is_proposed_accepted_and_withdrawn_through_the_pages(client, world):
    qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    new = reverse("quality:acceptance_new", args=[line(certificate, "assay").pk])
    sign_in(client, world, "analyst")
    form = text(client.get(new))
    for shown in (
        "Propose supplier result in place of a test",
        "Assay (assay)",
        "98 to 102 %",
        "99.60 %",
        "Supplier HPLC-07",
        "98.0 - 102.0 %",
        "COA-SYN-0001 dated 2026-11-02",
        "SQR-SYN-001 rev 1",
        "the laboratory always performs: identity",
    ):
        assert shown in form, shown
    basis = basis_of(form)
    missing = client.post(new, {"basis": basis, "reason": ""})
    assert missing.status_code == 422 and not SupplierResultAcceptance.objects.exists()
    # A submission that does not carry what the page showed is refused, and shown again.
    unseen = client.post(new, {"reason": "Supplier qualified for this test"})
    assert unseen.status_code == 422 and reliance.BASIS_STALE in text(unseen)
    assert basis_of(text(unseen)) == basis and not SupplierResultAcceptance.objects.exists()
    response = client.post(new, {"basis": basis, "reason": "Supplier qualified for this test"})
    acceptance = SupplierResultAcceptance.objects.get()
    detail = reverse("quality:acceptance_detail", args=[acceptance.pk])
    accept_url = reverse("quality:acceptance_accept", args=[acceptance.pk])
    withdraw_url = reverse("quality:acceptance_withdraw", args=[acceptance.pk])
    assert response.status_code == 302 and response.url == detail
    page = text(client.get(detail))
    assert "Awaiting acceptance" in page and acceptance.label in page
    assert "blocks the lot&#x27;s disposition" in page
    # The proposer holds the reviewer role as well and is not offered the signature.
    assert f'href="{accept_url}"' not in page and f'href="{withdraw_url}"' in page
    denied = client.get(accept_url)
    assert denied.status_code == 403 and "you proposed" in text(denied)
    assert 'name="pin"' not in text(denied)
    # A second proposal for the same requirement is not offered and is refused.
    again = client.get(new, follow=True)
    assert "already proposed or accepted" in text(again)
    lot_page = text(client.get(lot_url))
    assert "Supplier results in place of tests" in lot_page and f'href="{detail}"' in lot_page
    assert "Awaiting acceptance" in lot_page
    certificate_page = text(
        client.get(reverse("quality:certificate_detail", args=[certificate.pk]))
    )
    assert f'href="{detail}"' in certificate_page

    for name in READERS:
        sign_in(client, world, name)
        assert client.get(detail).status_code == 200
        if name != "reviewer":
            assert client.get(accept_url).status_code == 403
    for name in ("auditor", "admin"):
        sign_in(client, world, name)
        assert client.get(withdraw_url).status_code == 403
        assert f'href="{withdraw_url}"' not in text(client.get(detail))

    reviewer = sign_in(client, world, "reviewer")
    page = text(client.get(detail))
    assert f'href="{accept_url}"' in page
    sign = text(client.get(accept_url))
    assert "You accept the supplier&#x27;s stated result in place of" in sign
    assert "99.60 %" in sign and 'name="pin"' in sign
    wrong = client.post(accept_url, signing(reviewer, acceptance, pin="00000000"))
    assert wrong.status_code == 422
    acceptance.refresh_from_db()
    assert acceptance.state == "proposed"
    response = client.post(accept_url, signing(reviewer, acceptance))
    assert response.status_code == 302 and response.url == detail
    acceptance.refresh_from_db()
    assert acceptance.state == "accepted"
    page = text(client.get(detail))
    assert "Accepted" in page and "signed.accepted" in page
    assert reviewer.get_full_name() in page  # The signature names its signer.
    assert f'href="{accept_url}"' not in page

    # Withdrawing a signed acceptance takes a signature, and an analyst alone cannot give it.
    sign_in(client, world, "analyst2")
    assert f'href="{withdraw_url}"' not in text(client.get(detail))
    assert client.get(withdraw_url).status_code == 403
    reviewer = sign_in(client, world, "reviewer")
    sign = text(client.get(withdraw_url))
    assert "You withdraw the acceptance of this supplier&#x27;s result." in sign
    assert 'name="pin"' in sign
    stale = client.post(
        withdraw_url, signing(reviewer, acceptance, "Stale page") | {"expected_revision": 1}
    )
    assert stale.status_code == 422 and "Record changed" in text(stale)
    unsigned = client.post(
        withdraw_url, {"expected_revision": acceptance.revision, "reason": "No signature"}
    )
    assert unsigned.status_code == 422
    acceptance.refresh_from_db()
    assert acceptance.state == "accepted"
    response = client.post(
        withdraw_url, signing(reviewer, acceptance, "Tested in the laboratory instead")
    )
    assert response.status_code == 302 and response.url == detail
    acceptance.refresh_from_db()
    assert acceptance.state == "withdrawn" and acceptance.withdrawn_by == reviewer
    page = text(client.get(detail))
    assert "Withdrawn" in page and "Tested in the laboratory instead" in page
    assert "signed.withdrawn" in page and f'href="{withdraw_url}"' not in page
    again = client.get(withdraw_url, follow=True)
    assert "already withdrawn" in text(again)
    assert "Withdrawn" in text(client.get(lot_url))


def test_a_refused_submission_is_reported_and_audited(client, world):
    """A page opened while the supplier was qualified, submitted after the revocation."""
    qualification = qualify(world)
    certificate = certify(world, fully_stated(), lot=world["lot"])
    new = reverse("quality:acceptance_new", args=[line(certificate, "assay").pk])
    sign_in(client, world, "analyst")
    basis = basis_of(text(client.get(new)))
    revoke(world, qualification)
    response = client.post(new, {"basis": basis, "reason": "Supplier qualified for this test"})
    assert response.status_code == 422 and "was revoked" in text(response)
    assert not SupplierResultAcceptance.objects.exists()
    refusal = AuditEvent.objects.get(action="supplier_result.refused")
    assert refusal.actor == world["people"]["analyst"]
    assert refusal.reason == "Supplier qualified for this test"


# What the other pages show ------------------------------------------------------------------------


def test_testing_pages_show_what_the_supplier_result_stands_for(client, world):
    from analytical import services as analytical
    from analytical.models import AnalyticalTest
    from sampling import services as sampling

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
    analytical.assign_tests(actor=people["analyst"], sample=sample, reason="Assign tests")
    assay = AnalyticalTest.objects.get(lot=lot, test_code="assay")
    acceptance = accept(world, propose(world, certificate))
    sign_in(client, world, "analyst")
    test_url = reverse("analytical:test_detail", args=[assay.pk])
    page = text(client.get(test_url))
    assert "is proposed or accepted in place of this test" in page and acceptance.label in page
    assert "Not tested · supplier result" in page
    for hidden in ("Record observation", "Record contract laboratory result"):
        assert hidden not in page
    blocked = client.get(reverse("analytical:observation_new", args=[assay.pk]), follow=True)
    assert "Withdraw it on the lot record" in text(blocked)
    blocked = client.get(reverse("analytical:contract_result", args=[assay.pk]), follow=True)
    assert "Withdraw it on the lot record" in text(blocked)
    testing = text(client.get(reverse("analytical:lot_testing", args=[lot.pk])))
    assert "Supplier results accepted in place of tests" in testing
    assert reverse("quality:acceptance_detail", args=[acceptance.pk]) in testing
    assert "Not tested · supplier result" in testing and "COA-SYN-0001" in testing
    listed = text(client.get(reverse("analytical:test_list"), {"q": lot.number}))
    assert listed.count("Not tested · supplier result") == 1
    # The other open tests are still work to do.
    assert "impurity is incomplete" in testing


def test_disposition_page_names_the_accepted_supplier_results(client, world):
    people, lot = world["people"], world["lot"]
    certificate, accepted = accepted_lot(world)
    sample_and_test(world)
    url = reverse("quality:disposition", args=[lot.pk])
    sign_in(client, world, "approver")
    page = text(client.get(url))
    assert page.count("was accepted in place of a laboratory test") == 4 and 'name="pin"' in page
    assert f"({accepted['assay'].label}, " in page
    # The proposer, who holds the quality role, is an author of the lot's evidence.
    sign_in(client, world, "analyst")
    denied = client.get(url)
    assert denied.status_code == 403 and 'name="pin"' not in text(denied)
    # A qualification revoked since is shown where the disposition is signed; it does not block.
    revoke(world, SupplierQualification.objects.get())
    sign_in(client, world, "approver")
    page = text(client.get(url))
    assert "was revoked on" in page and "does not block the disposition" in page
    approver = people["approver"]
    lot.refresh_from_db()
    response = client.post(
        url,
        {
            "signature_username": approver.username,
            "expected_revision": lot.revision,
            "reason": "Synthetic independent QC disposition",
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    lot.refresh_from_db()
    assert lot.state == "released"
    # Released: the record is read, and nothing about it is offered any more.
    detail = reverse("quality:acceptance_detail", args=[accepted["assay"].pk])
    sign_in(client, world, "quality")
    page = text(client.get(detail))
    assert "Qualification revoked" in page
    assert reverse("quality:acceptance_withdraw", args=[accepted["assay"].pk]) not in page
    refused = client.get(
        reverse("quality:acceptance_withdraw", args=[accepted["assay"].pk]), follow=True
    )
    assert reliance.QUARANTINE_ONLY in text(refused)
    revoked = text(
        client.get(
            reverse("suppliers:qualification_detail", args=[SupplierQualification.objects.get().pk])
        )
    )
    assert "4 accepted supplier results relied on this qualification" in revoked
    assert lot.number in revoked and "Released" in revoked


def test_an_acceptance_that_no_longer_stands_says_so_on_its_pages(client, world):
    from tests.test_supplier_certificates import correct

    lot = world["lot"]
    certificate, accepted = accepted_lot(world, codes=["assay"])
    correct(world, certificate, fully_stated(), notes="Notes added")
    acceptance = accepted["assay"]
    sign_in(client, world, "reviewer")
    page = text(client.get(reverse("quality:acceptance_detail", args=[acceptance.pk])))
    assert "No longer stands" in page and "was corrected or withdrawn" in page
    assert reverse("quality:acceptance_accept", args=[acceptance.pk]) not in page
    lot_page = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "No longer stands" in lot_page and "Withdraw it." in lot_page
    # The corrected record links the acceptance taken from the one it replaced, and says the
    # same; nothing is offered for that requirement until it is withdrawn.
    from quality import certificates

    current = certificates.lot_chains(lot)[0][-1]
    sign_in(client, world, "analyst2")
    record = text(client.get(reverse("quality:certificate_detail", args=[current.pk])))
    assert reverse("quality:acceptance_detail", args=[acceptance.pk]) in record
    assert "No longer stands" in record and "Taken from another record: COA-SYN-0001." in record
    assert record.count("Propose in place of a test") == 3


def test_a_proposal_under_a_revoked_qualification_says_so_before_any_pin(client, world):
    qualification = qualify(world)
    lot = world["lot"]
    certificate = certify(world, fully_stated(), lot=lot)
    proposal = propose(world, certificate)
    revoke(world, qualification)
    detail = reverse("quality:acceptance_detail", args=[proposal.pk])
    accept_url = reverse("quality:acceptance_accept", args=[proposal.pk])
    sign_in(client, world, "reviewer")
    page = text(client.get(detail))
    assert "No longer stands" in page
    assert f"{qualification.label} was revoked before the proposal was accepted" in page
    assert f'href="{accept_url}"' not in page
    denied = client.get(accept_url)
    assert denied.status_code == 403 and 'name="pin"' not in text(denied)
    assert "was revoked before the proposal was accepted" in text(denied)
    lot_page = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "No longer stands" in lot_page and "Awaiting acceptance" not in lot_page
    # The qualification's record counts signed acceptances only: here there is none to assess.
    record = text(client.get(reverse("suppliers:qualification_detail", args=[qualification.pk])))
    assert "Assess the results" not in record and proposal.label in record
    assert "No longer stands" in record and "Awaiting acceptance" not in record


def test_assigning_tests_says_which_requirements_got_none(client, world):
    from sampling import services as sampling

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
    sign_in(client, world, "analyst")
    testing = reverse("analytical:lot_testing", args=[lot.pk])
    page = text(client.post(testing, {"sample": sample.pk, "reason": "Assign"}, follow=True))
    assert "Assigned 3 test(s) to SYN-REL-S001." in page
    assert (
        "No test was assigned for assay, impurity: a supplier&#x27;s result is proposed or "
        "accepted in place of it." in page
    )


def test_testing_pages_after_release_and_the_raw_data_page(client, world):
    from analytical.models import AnalyticalTest
    from tests.test_supplier_reliance import raw_file, sampled_tests

    people, lot = world["people"], world["lot"]
    qualify(world)
    certificate = certify(world, fully_stated(), lot=lot)
    tests = sampled_tests(world)  # Every requirement has a test before anything is proposed.
    sign_in(client, world, "analyst")
    for code in RELIED:
        accept(world, propose(world, certificate, code))
    assay = tests["assay"]
    # Raw data is not attached beside a supplier's result that stands, by link or by address.
    page = text(client.get(reverse("analytical:test_detail", args=[assay.pk])))
    upload = reverse("analytical:raw_file_new", args=[assay.pk])
    assert f'href="{upload}"' not in page
    blocked = client.get(upload, follow=True)
    assert "Withdraw it on the lot record" in text(blocked)
    with pytest.raises(Exception, match="in place of this test"):
        raw_file(world, assay)
    # Assigning again says why nothing was assigned.
    testing = reverse("analytical:lot_testing", args=[lot.pk])
    again = client.post(
        testing, {"sample": assay.sample_id, "reason": "Assign required tests"}, follow=True
    )
    assert "has a test or a supplier&#x27;s result that stands for it" in text(again)
    identity = tests["identity"]
    from tests.test_result_types_journey import record, review, submit

    record(world, identity, "conforms")
    submit(world, identity)
    review(world, identity)
    from tests.test_integrated_journey import dispose

    assert dispose(world, people["approver"]).state == "released"
    # Released: the untouched test still says what answered its requirement, on every page.
    page = text(client.get(reverse("analytical:test_detail", args=[assay.pk])))
    assert "Not tested · supplier result" in page and "This test was not performed." in page
    assert "Withdraw it there" not in page
    listed = text(client.get(reverse("analytical:test_list"), {"q": lot.number}))
    assert listed.count("Not tested · supplier result") == 4
    assert AnalyticalTest.objects.filter(lot=lot, state="open").count() == 4


def test_supplier_list_shows_each_suppliers_best_qualification_state(client, world):
    sign_in(client, world, "auditor")
    url = reverse("suppliers:list")
    assert "Awaiting approval" not in text(client.get(url))
    qualify(world, sign=False)
    assert "Awaiting approval" in text(client.get(url))
    qualify(world, valid_until=today() + timedelta(days=10))
    page = text(client.get(url))
    assert "Expiring soon" in page and "Awaiting approval" not in page
