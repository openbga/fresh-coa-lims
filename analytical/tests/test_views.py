from decimal import Decimal

import pytest
from django.urls import reverse

from analytical import services
from analytical.models import AnalyticalTest, Investigation, Observation
from core.models import AuditEvent, ElectronicSignature, PINCredential

from .conftest import PIN, complete, fresh, login, pass_qc, record, review, submit

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("plain_static")]


def test_pages_render_for_readers_and_deny_others(
    client, people, assigned, batch, django_user_model
):
    lot, sample, tests = assigned
    test = record(people, tests["identity"], "1.30")
    _, investigation = submit(people, test)
    urls = [
        reverse("analytical:test_list"),
        reverse("analytical:test_list") + "?state=oos&q=SYN",
        reverse("analytical:batch_list"),
        reverse("analytical:investigation_list") + "?state=all",
        reverse("analytical:lot_testing", args=[lot.pk]),
        reverse("analytical:test_detail", args=[test.pk]),
        reverse("analytical:batch_detail", args=[batch.pk]),
        reverse("analytical:investigation_detail", args=[investigation.pk]),
    ]
    login(client, people["auditor"])
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
    body = client.get(urls[5]).content.decode()
    assert "Out of specification" in body and "Record observation" not in body
    assert "Sign review" not in body  # auditors see no scientific actions
    for url in [
        reverse("analytical:observation_new", args=[tests["assay"].pk]),
        reverse("analytical:test_review", args=[test.pk]),
        reverse("analytical:conclude", args=[investigation.pk]),
    ]:
        assert client.get(url).status_code == 403
    nobody = django_user_model.objects.create_user("norole", password="x-synthetic-2026")
    login(client, nobody)
    assert client.get(urls[0]).status_code == 403
    client.logout()
    assert client.get(urls[0]).status_code == 302


def test_empty_and_filtered_states(client, people):
    login(client, people["analyst"])
    body = client.get(reverse("analytical:test_list")).content.decode()
    assert "No tests assigned yet" in body
    body = client.get(reverse("analytical:test_list") + "?q=nothing").content.decode()
    assert "No tests match these filters" in body and "Clear filters" in body
    body = client.get(reverse("analytical:batch_list")).content.decode()
    assert "No QC batches yet" in body and "New QC batch" in body


def test_http_journey_record_correct_submit_and_sign(client, people, lot_sample):
    lot, sample = lot_sample
    login(client, people["analyst"])
    response = client.post(
        reverse("analytical:lot_testing", args=[lot.pk]), {"sample": sample.pk, "reason": "Assign"}
    )
    assert response.status_code == 302
    test = AnalyticalTest.objects.get(test_code="identity")
    url = reverse("analytical:observation_new", args=[test.pk])
    response = client.post(url, {"value": "abc", "raw_reference": ""})
    assert response.status_code == 422 and "Original record" in response.content.decode()
    client.post(url, {"value": "1.20", "raw_reference": "NB-7 p3"})
    observation = Observation.objects.get(test=test)
    client.post(
        reverse("analytical:observation_correct", args=[observation.pk]),
        {"value": "1.02", "raw_reference": "NB-7 p3", "reason": "Misread"},
    )
    test = fresh(test)
    body = client.get(reverse("analytical:test_detail", args=[test.pk])).content.decode()
    assert '<del class="vr-prior">1.20</del>' in body and "Misread" in body
    client.post(
        reverse("analytical:test_detail", args=[test.pk]),
        {"expected_revision": test.revision, "reason": "Done"},
    )
    test = fresh(test)
    assert test.state == "submitted"

    login(client, people["reviewer"])
    sign_url = reverse("analytical:test_review", args=[test.pk])
    page = client.get(sign_url).content.decode()
    assert "Signature PIN" in page and "data-signature-dialog" in page and "revision" in page
    bad = client.post(
        sign_url,
        {
            "expected_revision": test.revision,
            "pin": "11111111",
            "signature_username": "reviewer",
            "reason": "Checked",
        },
    )
    assert bad.status_code == 422
    assert "not accepted" in bad.content.decode() and "11111111" not in bad.content.decode()
    stale = client.post(
        sign_url,
        {
            "expected_revision": test.revision - 1,
            "pin": PIN,
            "signature_username": "reviewer",
            "reason": "Checked",
        },
    )
    assert stale.status_code == 422 and "Record changed" in stale.content.decode()
    wrong_id = client.post(
        sign_url,
        {
            "expected_revision": test.revision,
            "pin": PIN,
            "signature_username": "analyst",
            "reason": "Checked",
        },
    )
    assert wrong_id.status_code == 422
    assert not ElectronicSignature.objects.exists()
    ok = client.post(
        sign_url,
        {
            "expected_revision": test.revision,
            "pin": PIN,
            "signature_username": "reviewer",
            "reason": "Checked",
        },
    )
    assert ok.status_code == 302 and fresh(test).state == "reviewed"
    signature = ElectronicSignature.objects.get()
    assert signature.authentication_context["channel"] != "trusted-service"


def test_oos_submission_redirects_to_investigation_and_quality_actions(client, people, assigned):
    _, _, tests = assigned
    test = record(people, tests["identity"], "0.50")
    login(client, people["analyst"])
    response = client.post(
        reverse("analytical:test_detail", args=[test.pk]),
        {"expected_revision": fresh(test).revision, "reason": "Done"},
    )
    investigation = Investigation.objects.get()
    assert response.url == reverse("analytical:investigation_detail", args=[investigation.pk])
    client.post(
        reverse("analytical:entry_new", args=[investigation.pk]),
        {"kind": "assessment", "text": "Balance check failed", "external_reference": ""},
    )
    login(client, people["quality"])
    page = client.get(reverse("analytical:investigation_detail", args=[investigation.pk]))
    assert "Balance check failed" in page.content.decode()
    response = client.post(
        reverse("analytical:conclude", args=[investigation.pk]),
        {
            "outcome": "invalidated",
            "assignable_cause": "",
            "reason": "Done",
            "pin": PIN,
            "signature_username": "quality",
            "expected_revision": fresh(investigation).revision,
        },
    )
    # Preflight refuses before any PIN check: original not yet reviewed; nothing signed.
    assert response.status_code == 302
    assert "needs independent data review" in client.get(response.url).content.decode()
    assert fresh(investigation).is_open


def test_batch_pages_record_qc_and_reject(client, people, assigned):
    _, _, tests = assigned
    login(client, people["analyst2"])
    response = client.post(
        reverse("analytical:batch_new"),
        {"number": "SYN-B9", "method_code": "SYN-HPLC", "reason": "Run"},
    )
    batch = services.QCBatch.objects.get(number="SYN-B9")
    assert response.url == reverse("analytical:batch_detail", args=[batch.pk])
    client.post(
        reverse("analytical:qc_record", args=[batch.pk, "blank"]),
        {"value": "0.30", "raw_reference": "RUN-9"},
    )
    assert client.get(reverse("analytical:qc_record", args=[batch.pk, "nope"])).status_code == 404
    services.record_qc(
        actor=people["analyst2"],
        batch=batch,
        check_code="control",
        value=Decimal("100"),
        raw_reference="RUN-9",
    )
    login(client, people["reviewer"])
    page = client.get(reverse("analytical:batch_detail", args=[batch.pk])).content.decode()
    assert "QC failed" in page and "Reject batch" in page
    response = client.post(
        reverse("analytical:batch_reject", args=[batch.pk]),
        {
            "expected_revision": fresh(batch).revision,
            "pin": PIN,
            "signature_username": "reviewer",
            "reason": "Blank failed",
        },
    )
    assert response.status_code == 302 and fresh(batch).state == "rejected"


def test_action_pages_refuse_records_in_wrong_state(client, people, assigned, batch):
    _, _, tests = assigned
    login(client, people["reviewer"])
    response = client.get(reverse("analytical:test_review", args=[tests["identity"].pk]))
    assert response.status_code == 302
    page = client.get(response.url).content.decode()
    assert "This test is not awaiting review." in page
    login(client, people["analyst"])
    response = client.get(reverse("analytical:observation_new", args=[tests["assay"].pk]))
    assert response.status_code == 302  # batch method without a batch
    response = client.get(reverse("analytical:batch_reject", args=[batch.pk]))
    assert response.status_code == 403  # analysts cannot reject at all


def test_assign_rejects_sample_from_another_lot(client, people, make_lot):
    lot, _ = make_lot("SYN-LOT-X")
    _, foreign = make_lot("SYN-LOT-Y")
    login(client, people["analyst"])
    response = client.post(
        reverse("analytical:lot_testing", args=[lot.pk]), {"sample": foreign.pk, "reason": "Assign"}
    )
    assert response.status_code == 404
    for hostile in ("not-a-number", "1.5", "99999999999999999999999", "9" * 5000):
        response = client.post(
            reverse("analytical:lot_testing", args=[lot.pk]), {"sample": hostile, "reason": "x"}
        )
        assert response.status_code == 404, hostile
    assert not AnalyticalTest.objects.exists()


def _refused(client, url, reason):
    """GET shows the reason on the record page; no PIN form is ever rendered."""
    response = client.get(url)
    assert response.status_code == 302, url
    page = client.get(response.url).content.decode()
    assert reason in page, (reason, url)
    assert 'name="pin"' not in page


def _no_credential_effects():
    assert not AuditEvent.objects.filter(
        action__in=["signature.denied", "signature.identity_denied"]
    ).exists()
    assert set(PINCredential.objects.values_list("failures", flat=True)) == {0}


def test_review_and_return_preflight_authorship_and_state(client, people, assigned, batch):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.0", who="multi")
    submit(people, test, who="multi")
    review_url = reverse("analytical:test_review", args=[test.pk])
    return_url = reverse("analytical:test_return", args=[test.pk])
    login(client, people["multi"])
    _refused(client, review_url, "You cannot review your own test.")
    _refused(client, return_url, "You cannot review your own test.")
    # A forged POST with the right PIN is refused before the credential is checked.
    response = client.post(
        review_url,
        {
            "expected_revision": fresh(test).revision,
            "pin": PIN,
            "signature_username": "multi",
            "reason": "Self",
        },
    )
    assert response.status_code == 302 and fresh(test).state == "submitted"
    assert not ElectronicSignature.objects.exists()
    _no_credential_effects()
    login(client, people["reviewer"])
    page = client.get(review_url)
    assert page.status_code == 200 and 'name="pin"' in page.content.decode()
    assert client.get(return_url).status_code == 200
    stale = client.post(
        review_url,
        {
            "expected_revision": fresh(test).revision - 1,
            "pin": PIN,
            "signature_username": "reviewer",
            "reason": "Checked",
        },
    )
    assert stale.status_code == 422 and "Record changed" in stale.content.decode()
    review(people, test)
    _refused(client, review_url, "This test is not awaiting review.")
    _refused(client, return_url, "Only submitted tests can be returned.")
    _no_credential_effects()


def test_review_preflight_blocks_failed_batch_qc_and_oos_return(client, people, assigned, batch):
    _, _, tests = assigned
    pass_qc(people, batch)
    services.assign_to_batch(
        actor=people["analyst"], test=tests["assay"], batch=batch, reason="Run"
    )
    record(people, tests["assay"], "90.0", "91.0")
    submit(people, tests["assay"])  # out of specification
    login(client, people["reviewer"])
    _refused(
        client,
        reverse("analytical:test_return", args=[tests["assay"].pk]),
        "Out-of-specification results cannot be returned",
    )
    assert (
        client.get(reverse("analytical:test_review", args=[tests["assay"].pk])).status_code == 200
    )


def test_batch_page_preflight(client, people, assigned, make_lot):
    _, _, tests = assigned
    login(client, people["analyst"])
    url = reverse("analytical:test_batch", args=[tests["assay"].pk])
    _refused(client, url, "No open QC batch accepting tests uses SYN-HPLC revision 1.")
    full = services.create_batch(
        actor=people["analyst2"], number="SYN-B5", method_code="SYN-HPLC", reason="Run"
    )
    assert "SYN-B5" in client.get(url).content.decode()
    # A batch with submitted results is no longer offered, matching the locked add.
    _, other = make_lot("SYN-LOT-Z", tests=("assay",))
    (other_test,), _ = services.assign_tests(actor=people["analyst"], sample=other, reason="Go")
    pass_qc(people, full)
    complete(people, other_test, "100.0", "100.1", batch=full)
    _refused(client, url, "No open QC batch accepting tests uses SYN-HPLC revision 1.")
    services.create_batch(
        actor=people["analyst2"], number="SYN-B6", method_code="SYN-HPLC", reason="Run"
    )
    page = client.get(url).content.decode()
    assert "SYN-B6" in page and "SYN-B5" not in page
    forged = client.post(url, {"batch": full.pk, "reason": "Forged"})
    assert forged.status_code == 422 and fresh(tests["assay"]).batch_id is None
    _refused(
        client,
        reverse("analytical:test_batch", args=[tests["identity"].pk]),
        "This test cannot be added to a QC batch.",
    )


def test_authorize_and_conclude_preflight(client, people, assigned):
    _, _, tests = assigned
    test = record(people, tests["identity"], "1.30")
    _, investigation = submit(people, test)
    authorize_url = reverse("analytical:authorize", args=[investigation.pk])
    conclude_url = reverse("analytical:conclude", args=[investigation.pk])
    login(client, people["quality"])
    _refused(client, authorize_url, "Record the laboratory assessment first.")
    _refused(client, conclude_url, "Record the laboratory assessment first.")
    services.add_entry(
        actor=people["quality2"],
        investigation=investigation,
        kind="assessment",
        text="Dilution checked",
    )
    _refused(client, conclude_url, "The original result needs independent data review first.")
    assert client.get(authorize_url).status_code == 200
    review(people, test)
    assert "Sign conclusion" in client.get(conclude_url).content.decode()
    login(client, people["quality2"])  # authored the assessment entry
    _refused(client, conclude_url, "You cannot conclude an investigation of your own work.")
    forged = client.post(
        conclude_url,
        {
            "outcome": "confirmed",
            "assignable_cause": "",
            "reason": "Self",
            "pin": PIN,
            "signature_username": "quality2",
            "expected_revision": fresh(investigation).revision,
        },
    )
    assert forged.status_code == 302 and fresh(investigation).is_open
    people["analyst"].groups.add(people["quality"].groups.get())
    login(client, people["analyst"])  # generated the original data
    _refused(client, authorize_url, "You cannot authorize retesting of your own result.")
    login(client, people["quality"])
    services.authorize_retest(
        actor=people["quality"],
        pin=PIN,
        investigation=fresh(investigation),
        expected_revision=fresh(investigation).revision,
        kind="retest",
        reason="One retest",
    )
    _refused(
        client, authorize_url, "The approved specification allows no further retests or resamples."
    )
    _refused(client, conclude_url, "Authorized retests or resamples are still incomplete.")
    child = AnalyticalTest.objects.get(investigation=investigation)
    complete(people, child, "1.01")
    services.conclude(
        actor=people["quality"],
        pin=PIN,
        investigation=fresh(investigation),
        expected_revision=fresh(investigation).revision,
        outcome="invalidated",
        assignable_cause="Dilution error",
        reason="Closed",
    )
    _refused(client, conclude_url, "This investigation is already closed.")
    _refused(client, authorize_url, "This investigation is closed.")
    assert not ElectronicSignature.objects.filter(signer=people["quality2"]).exists()
    _no_credential_effects()
