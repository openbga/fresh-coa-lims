"""Method evidence pages: role boundaries, the draft's pages, signing through the web form,
and the suitability of a draft method version. Synthetic data."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalog import evidence
from catalog.models import MethodEvidence, MethodRevision
from core.models import ElectronicSignature

from .factories import PIN, method_revision
from .test_method_evidence import approved, characteristic, record

pytestmark = pytest.mark.django_db(transaction=True)


def login(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def method(people):
    return method_revision(people["author"]).method


def form_data(method=None, **overrides):
    data = {
        "kind": "validation",
        "title": "Validation of the synthetic assay",
        "procedure_ref": "SOP-SYN-ASSAY rev 2",
        "intended_use": "Assay of the synthetic API in tablets.",
        "source": "",
        "transfer_approach": "",
        "protocol_ref": "",
        "report_ref": "VR-SYN-002 rev 1",
        "report_url": "",
        "completed_on": (timezone.localdate() - timedelta(days=1)).isoformat(),
        "conclusion": "suitable",
        "statement": "Suitable for the assay.",
        "deviations": "",
        "reason": "Report issued",
    }
    if method is not None:
        data["method"] = method.pk
    data.update(overrides)
    return data


def signing(revision, **overrides):
    data = {"reason": "Report checked", "pin": PIN, "expected_revision": revision}
    data.update(overrides)
    return data


@pytest.mark.parametrize("role", ["analyst", "reviewer", "author", "admin", "auditor"])
def test_list_is_readable_by_laboratory_roles(client, people, method, role):
    record(people["analyst"], method)
    response = login(client, people[role]).get(reverse("catalog:evidence_list"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "MEV-" in body and "Method evidence" in body
    assert (reverse("catalog:evidence_new") in body) is (role in ("analyst", "reviewer", "author"))


def test_list_and_record_are_refused_without_a_role(client, people, method):
    item = record(people["analyst"], method)
    outsider = get_user_model().objects.create_user("outsider", password="x-synthetic-91")
    client = login(client, outsider)
    assert client.get(reverse("catalog:evidence_list")).status_code == 403
    assert client.get(reverse("catalog:evidence_detail", args=[item.pk])).status_code == 403
    assert client.get(reverse("catalog:evidence_new")).status_code == 403


def test_list_filters(client, people, method):
    record(people["analyst"], method, title="Validation A")
    record(people["analyst"], method, title="Failed study", conclusion="not_suitable")
    client = login(client, people["auditor"])
    url = reverse("catalog:evidence_list")
    body = client.get(url, {"conclusion": "not_suitable"}).content.decode()
    assert "Failed study" in body and "Validation A" not in body
    body = client.get(url, {"q": "nothing-matches"}).content.decode()
    assert "Clear filters" in body


def test_record_a_draft_through_the_pages(client, people, method):
    client = login(client, people["analyst"])
    page = client.get(reverse("catalog:evidence_new"), {"method": method.pk})
    assert page.status_code == 200 and method.code in page.content.decode()
    refused = client.post(
        reverse("catalog:evidence_new"), form_data(method, kind="transfer", source="")
    )
    assert refused.status_code == 422
    assert "Choose how the transfer was performed" in refused.content.decode()
    done = client.post(reverse("catalog:evidence_new"), form_data(method))
    item = MethodEvidence.objects.get()
    assert done.status_code == 302 and done["Location"].endswith(f"/method-evidence/{item.pk}/")
    detail = client.get(done["Location"]).content.decode()
    assert "Add the characteristics" in detail and "Add characteristic" in detail
    added = client.post(
        reverse("catalog:evidence_characteristic_new", args=[item.pk]),
        {
            "expected_revision": 1,
            "characteristic": "accuracy",
            "detail": "",
            "criterion": "98.0-102.0 %",
            "result": "99.8 %",
            "outcome": "met",
            "reason": "Report table 2",
        },
    )
    assert added.status_code == 302
    item.refresh_from_db()
    changed = client.post(
        reverse("catalog:evidence_edit", args=[item.pk]),
        form_data(title="Validation of the assay, film-coated tablets", expected_revision=1),
    )
    assert changed.status_code == 422 and "Record changed" in changed.content.decode()
    changed = client.post(
        reverse("catalog:evidence_edit", args=[item.pk]),
        form_data(
            title="Validation of the assay, film-coated tablets", expected_revision=item.revision
        ),
    )
    assert changed.status_code == 302
    line = item.characteristics.get()
    remove = reverse("catalog:evidence_characteristic_remove", args=[item.pk, line.pk])
    assert client.get(remove).status_code == 200


def test_approve_page_explains_what_is_missing_before_any_pin(client, people, method):
    item = record(people["analyst"], method)
    response = login(client, people["approver"]).get(
        reverse("catalog:evidence_approve", args=[item.pk])
    )
    body = response.content.decode()
    assert response.status_code == 403 and "Add the characteristics" in body
    assert "Sign and approve" not in body and 'type="password"' not in body


def test_approve_through_the_signing_page(client, people, method):
    item = record(people["analyst"], method)
    characteristic(people["analyst"], item)
    item.refresh_from_db()
    url = reverse("catalog:evidence_approve", args=[item.pk])
    # The recorder sees the reason on the record and the signing page refuses them.
    recorder = login(client, people["analyst"])
    assert recorder.get(url).status_code == 403
    client.logout()
    dual = login(client, people["dual"])
    evidence.change_evidence(
        actor=people["dual"],
        evidence=item,
        expected_revision=item.revision,
        reason="Clarified",
        **{name: getattr(item, name) for name in evidence.FIELDS if name != "statement"},
        statement="Suitable; system suitability in every run.",
    )
    detail = dual.get(reverse("catalog:evidence_detail", args=[item.pk])).content.decode()
    assert evidence.INDEPENDENT in detail and url not in detail
    assert dual.get(url).status_code == 403
    client.logout()
    approver = login(client, people["approver"])
    detail = approver.get(reverse("catalog:evidence_detail", args=[item.pk])).content.decode()
    assert url in detail
    page = approver.get(url)
    assert page.status_code == 200 and "Sign and approve" in page.content.decode()
    item.refresh_from_db()
    stale = approver.post(
        url,
        signing(item.revision - 1, signature_username=people["approver"].username),
    )
    assert stale.status_code == 422 and "Record changed" in stale.content.decode()
    done = approver.post(url, signing(item.revision, signature_username="qa-approver"))
    assert done.status_code == 302
    item.refresh_from_db()
    assert item.state == "approved"
    assert ElectronicSignature.objects.get(object_id=str(item.pk)).meaning == "approved"
    detail = approver.get(reverse("catalog:evidence_detail", args=[item.pk])).content.decode()
    assert "Withdraw" in detail and reverse("catalog:evidence_edit", args=[item.pk]) not in detail


def test_withdraw_pages(client, people, method):
    draft = record(people["analyst"], method)
    url = reverse("catalog:evidence_withdraw", args=[draft.pk])
    reviewer = login(client, people["reviewer"])
    refused = reviewer.post(url, {"expected_revision": 1, "reason": "Not needed"}, follow=True)
    assert "recorded this draft" in refused.content.decode()
    assert MethodEvidence.objects.get(pk=draft.pk).state == "draft"
    client.logout()
    analyst = login(client, people["analyst"])
    assert analyst.post(url, {"expected_revision": 1, "reason": "Not needed"}).status_code == 302
    assert MethodEvidence.objects.get(pk=draft.pk).state == "withdrawn"

    item = approved(people, method)
    url = reverse("catalog:evidence_withdraw", args=[item.pk])
    assert analyst.get(url).status_code == 403
    client.logout()
    quality = login(client, people["author"])
    page = quality.get(url)
    assert page.status_code == 200 and "Sign and withdraw" in page.content.decode()
    done = quality.post(url, signing(item.revision, signature_username="qa-author"))
    assert done.status_code == 302
    item.refresh_from_db()
    assert item.state == "withdrawn"
    detail = quality.get(reverse("catalog:evidence_detail", args=[item.pk])).content.decode()
    assert "Quality withdrew this record after approving it" in detail


def test_suitability_of_a_draft_version_through_the_pages(client, people, method):
    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    url = reverse("catalog:suitability_set", args=[draft.pk])
    analyst = login(client, people["analyst"])
    assert analyst.get(url).status_code == 403
    client.logout()
    quality = login(client, people["author"])
    detail = quality.get(reverse("catalog:evidence_detail", args=[item.pk])).content.decode()
    assert f"{url}?evidence={item.pk}" in detail.replace("&amp;", "&")
    page = quality.get(url, {"evidence": item.pk})
    assert page.status_code == 200 and item.identifier in page.content.decode()
    refused = quality.post(
        url,
        {"evidence": "", "suitability_kind": "", "reason": "x", "expected_revision": 1},
    )
    assert refused.status_code == 422
    done = quality.post(
        url,
        {
            "evidence": item.pk,
            "reason": "Validation report approved",
            "expected_revision": draft.revision,
        },
    )
    assert done.status_code == 302
    draft.refresh_from_db()
    assert draft.evidence == item
    method_page = quality.get(reverse("catalog:method", args=[method.pk])).content.decode()
    assert reverse("catalog:evidence_detail", args=[item.pk]) in method_page
    assert "Evidence records" in method_page
    client.logout()
    approver = login(client, people["approver"])
    approve_page = approver.get(reverse("catalog:method_approve", args=[draft.pk]))
    assert item.identifier in approve_page.content.decode()
    record_page = approver.get(reverse("catalog:evidence_detail", args=[item.pk]))
    assert f"{method.code} v{draft.version}" in record_page.content.decode()


def test_suitability_page_redirects_for_an_approved_version(client, people, method):
    from .factories import approve

    version = approve(MethodRevision.objects.get(method=method), people["approver"])
    response = login(client, people["author"]).get(
        reverse("catalog:suitability_set", args=[version.pk])
    )
    assert response.status_code == 302


def test_a_version_relying_on_an_unusable_record_is_refused_before_any_pin(client, people, method):
    draft = MethodRevision.objects.get(method=method)
    item = approved(people, method)
    evidence.set_suitability(
        actor=people["author"], revision=draft, reason="Validation approved", evidence=item
    )
    item.refresh_from_db()
    evidence.withdraw_evidence(
        actor=people["author"],
        pin=PIN,
        evidence=item,
        expected_revision=item.revision,
        reason="Data integrity finding",
    )
    approver = login(client, people["approver"])
    method_page = approver.get(reverse("catalog:method", args=[method.pk])).content.decode()
    url = reverse("catalog:method_approve", args=[draft.pk])
    assert f"{item.identifier} was withdrawn" in method_page and url not in method_page
    page = approver.get(url)
    body = page.content.decode()
    assert "Cannot be approved" in body and f"{item.identifier} was withdrawn" in body
    assert 'type="password"' not in body
    assert MethodRevision.objects.get(pk=draft.pk).status == "draft"


def test_suitability_page_refuses_a_stale_save(client, people, method):
    draft = MethodRevision.objects.get(method=method)
    quality = login(client, people["author"])
    response = quality.post(
        reverse("catalog:suitability_set", args=[draft.pk]),
        {
            "expected_revision": draft.revision + 1,
            "evidence": "",
            "suitability_kind": "validation",
            "suitability_ref": "VAL-OTHER rev 2",
            "reason": "Other report",
        },
    )
    assert response.status_code == 422 and "Record changed" in response.content.decode()
