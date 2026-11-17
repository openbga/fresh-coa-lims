"""Rejection and cancellation of a lot through the pages: the lot record's actions, the signed
pages with their refusals and independence, and how the lot list and record show the decision."""

import re

import pytest
from django.urls import reverse

from core.models import ElectronicSignature
from quality.models import Lot
from tests.test_integrated_journey import PIN
from tests.test_lot_rejection import received, world  # noqa: F401
from tests.test_result_types_journey import record, submit

pytestmark = pytest.mark.django_db(transaction=True)

REASON = "Synthetic: the lot cannot be used (NCR-SYN-010)"


def text(response):
    return " ".join(response.content.decode().split())


def basis_of(page):
    return re.search(r'name="basis" value="([0-9a-f]{64})"', page).group(1)


def signing(user, lot, page, **changes):
    data = {
        "signature_username": user.username,
        "expected_revision": lot.revision,
        "basis": basis_of(page),
        "reason": REASON,
        "reference": "NCR-SYN-010",
        "pin": PIN,
    }
    data.update(changes)
    return data


def test_quality_reviews_and_signs_the_rejection(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    approver = people["approver"]
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    reject_url = reverse("quality:lot_reject", args=[lot.pk])
    client.force_login(approver)
    detail = text(client.get(lot_url))
    assert f'href="{reject_url}"' in detail and ">Reject lot</a>" in detail
    # The lot's material was sampled and tested: cancelling it as received in error would be
    # refused (quality.rejection.cancellation_refusals), so it is not offered.
    assert reverse("quality:lot_cancel", args=[lot.pk]) not in detail

    page = text(client.get(reject_url))
    assert "What stands in the way of release" in page
    assert "T-" in page and "incomplete" in page
    assert "Sign and reject the lot" in page and 'name="pin"' in page
    assert f"lot revision {lot.revision + 1}" in page

    for bad, message in (
        ({"pin": "00000000"}, "Signature PIN was not accepted."),
        ({"basis": "0" * 64}, "changed after this page was opened"),
        ({"grounds": ""}, "This field is required."),
        ({"reason": ""}, "This field is required."),
    ):
        response = client.post(
            reject_url, signing(approver, lot, page, **{"grounds": "results", **bad})
        )
        assert response.status_code == 422, bad
        assert message in text(response), bad
        assert Lot.objects.get(pk=lot.pk).state == "quarantine"
        # The page carries the basis of the lot as it is now, never the one submitted.
        assert basis_of(text(response)) == basis_of(page), bad

    response = client.post(reject_url, signing(approver, lot, page, grounds="receipt"), follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    body = text(response)
    assert "Lot rejected. Its records are kept as they were signed." in body
    assert ">Rejected<" in body and "Condition or documents on receipt" in body
    assert REASON in body and "NCR-SYN-010" in body
    assert "What stood in the way of release" in body
    assert f'href="{reject_url}"' not in body
    signature = ElectronicSignature.objects.get(object_type="quality.lot")
    assert signature.meaning == "rejected" and signature.signer == approver

    # The page is closed now; it sends the reader back to the lot.
    response = client.get(reject_url, follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    assert "was rejected; its decision cannot change" in text(response)

    listing = text(client.get(reverse("quality:lot_list"), {"state": "rejected"}))
    assert lot.number in listing and ">Rejected<" in listing
    assert lot.number not in text(client.get(reverse("quality:lot_list"), {"state": "quarantine"}))


def test_an_author_or_another_role_cannot_sign_the_rejection(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    reject_url = reverse("quality:lot_reject", args=[lot.pk])
    # The analyst holds the quality role and received, sampled and tested the lot.
    client.force_login(people["analyst"])
    page = client.get(reject_url)
    assert page.status_code == 403
    assert "Another quality person must sign" in text(page) and 'name="pin"' not in text(page)
    response = client.post(reject_url, {"pin": PIN, "reason": REASON, "grounds": "results"})
    assert response.status_code == 403
    client.force_login(people["reviewer"])
    assert client.get(reject_url).status_code == 403
    assert reject_url not in text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert Lot.objects.get(pk=lot.pk).state == "quarantine"


def test_the_rejection_page_says_what_must_happen_first(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    assay = world["tests"]["assay"]
    record(world, assay, "96.00")
    client.force_login(people["approver"])
    reject_url = reverse("quality:lot_reject", args=[lot.pk])
    page = text(client.get(reject_url))
    assert "The lot cannot be rejected yet" in page
    assert "holds a result outside its limits that was not submitted (96.00)" in page
    assert "results not submitted: 96.00 (96.00 outside the limits)" in page
    assert 'name="pin"' not in page
    # The lot record does not offer Reject lot while it would be refused: it says why instead.
    detail = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert f'href="{reject_url}"' not in detail
    assert 'data-refused="reject">' in detail and "was not submitted (96.00)" in detail
    submit(world, assay)
    page = text(client.get(reject_url))
    assert "is open. Conclude it before the lot is rejected" in page
    lot.refresh_from_db()
    response = client.post(reject_url, {"pin": PIN, "reason": REASON, "grounds": "results"})
    assert response.status_code == 422
    assert Lot.objects.get(pk=lot.pk).state == "quarantine"


def test_quality_cancels_a_lot_received_in_error(client, received):  # noqa: F811
    people, lot = received["people"], received["lot"]
    approver = people["approver"]
    cancel_url = reverse("quality:lot_cancel", args=[lot.pk])
    lot_url = reverse("quality:lot_detail", args=[lot.pk])
    client.force_login(people["analyst"])  # received the lot
    assert client.get(cancel_url).status_code == 403
    client.force_login(approver)
    assert cancel_url in text(client.get(lot_url))  # nothing refuses it: offered under More
    page = text(client.get(cancel_url))
    assert "Cancel lot received in error" in page and "Sign and cancel the lot" in page
    assert "What was recorded in error" in page
    response = client.post(
        cancel_url,
        signing(approver, lot, page, reason="Synthetic: delivery recorded twice"),
        follow=True,
    )
    assert response.redirect_chain == [(lot_url, 302)]
    body = text(response)
    assert "Lot cancelled as received in error." in body
    assert ">Cancelled<" in body and "Synthetic: delivery recorded twice" in body
    assert "Its number is not used again." in body
    assert ElectronicSignature.objects.get(object_type="quality.lot").meaning == "cancelled"
    listing = text(client.get(reverse("quality:lot_list"), {"state": "cancelled"}))
    assert lot.number in listing and ">Cancelled<" in listing


def test_a_sampled_lot_is_not_cancelled(client, world):  # noqa: F811
    lot = world["lot"]
    client.force_login(world["people"]["approver"])
    cancel_url = reverse("quality:lot_cancel", args=[lot.pk])
    page = text(client.get(cancel_url))
    assert "The lot cannot be cancelled" in page
    assert "Samples were taken from this lot: SYN-RT-S001." in page
    assert 'name="pin"' not in page
    lot.refresh_from_db()
    response = client.post(cancel_url, {"pin": PIN, "reason": "Error"})
    assert response.status_code == 422
    assert Lot.objects.get(pk=lot.pk).state == "quarantine"
