from decimal import Decimal

import pytest
from django.urls import reverse

from analytical import services
from analytical.models import AnalyticalTest, Investigation, Observation
from core.models import ElectronicSignature

from .conftest import PIN, fresh, record, submit

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def plain_static(settings):
    # Template tests must not depend on a collected manifest in the shared static directory.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def login(client, user):
    client.force_login(user)
    session = client.session
    import time

    session["authenticated_at"] = session["last_activity_at"] = time.time()
    session.save()
    return client


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
    assert response.status_code == 422  # original not yet reviewed; nothing signed
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
