"""Certificates for a scope of the lot through the pages: the choice on the review page, the
certificate shown for the scope, the signing page and its refusals, and the record and the list
that name the scope (synthetic data only)."""

import html
import re

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils.html import strip_tags

from reporting import services as reporting
from reporting.models import Report
from tests.test_customer_certificates import MARKET, released
from tests.test_customer_certificates import world as world  # noqa: F401
from tests.test_integrated_journey import PIN
from tests.test_requirement_applicability import TIGHT, WATER

pytestmark = pytest.mark.django_db(transaction=True)


def text(response):
    return " ".join(html.unescape(strip_tags(response.content.decode())).split())


def preview_url(lot, scope=None):
    url = reverse("reporting:issue_preview", args=[lot.pk])
    return f"{url}?scope={scope}" if scope is not None else url


def sign_url(lot):
    return reverse("reporting:issue_sign", args=[lot.pk])


def test_the_review_page_offers_the_scopes_of_a_lot_under_several_specifications(client, world):
    lot = released(world, TIGHT, WATER)
    client.force_login(world["people"]["author"])
    response = client.get(preview_url(lot))
    assert response.status_code == 200
    page = text(response)
    assert "Certificate for" in page and "All of the lot's requirements" in page
    assert "eu-market: synthetic-rt-eu-market version 1" in page
    assert "general: synthetic-rt-spec version 1" in page
    assert "Conformity with each specification" in page
    body = response.content.decode()
    assert 'type="radio" name="scope" value="" ' in body or 'value="" checked' in body
    # The certificate for the market scope: its tests, its limits, and the scope passed on.
    response = client.get(preview_url(lot, MARKET))
    page = text(response)
    assert "This certificate is issued for scope eu-market." in page
    assert "For scope eu-market" in page
    assert "Conformity with each specification" not in page
    assert f"{sign_url(lot)}?evidence=" in response.content.decode()
    assert "&amp;scope=eu-market" in response.content.decode()


def test_a_scope_the_lot_cannot_have_a_certificate_for_is_explained_not_offered(client, world):
    lot = released(world, TIGHT)
    client.force_login(world["people"]["author"])
    response = client.get(preview_url(lot, "us-market"))
    page = text(response)
    assert "Cannot issue" in page
    assert "The lot's requirements name no specification for scope us-market" in page
    assert "Continue to signing" not in page
    # A failing scope sends the signer back to the review page with the reason.
    digest = reporting.preview(lot, "us-market")[1]
    response = client.get(f"{sign_url(lot)}?evidence={digest}&scope=us-market")
    assert response.status_code == 302 and "scope=us-market" in response["Location"]
    notes = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("name no specification for scope us-market" in n for n in notes)


def test_a_lot_under_one_specification_has_no_choice_of_scope(client, world):
    from tests.test_integrated_journey import dispose
    from tests.test_requirement_applicability import assign, complete, sample_and_tests

    assign(world)
    complete(world, sample_and_tests(world))
    lot = dispose(world, world["people"]["approver"])
    client.force_login(world["people"]["author"])
    page = text(client.get(preview_url(lot)))
    assert "Certificate for" not in page and "Continue to signing" in page


def test_quality_signs_a_certificate_for_a_scope_and_the_record_names_it(client, world):
    lot = released(world, TIGHT)
    author = world["people"]["author"]
    client.force_login(author)
    digest = reporting.preview(lot, MARKET)[1]
    response = client.get(f"{sign_url(lot)}?evidence={digest}&scope={MARKET}")
    assert response.status_code == 200
    page = text(response)
    assert "version 1, for scope eu-market" in page
    assert re.search(r'name="scope" value="eu-market"', response.content.decode())
    response = client.post(
        sign_url(lot),
        {
            "recipient": "Synthetic customer EU",
            "remarks": "",
            "reason": "Customer certificate",
            "evidence_hash": digest,
            "scope": MARKET,
            "signature_username": author.username,
            "pin": PIN,
        },
    )
    report = Report.objects.get()
    assert response.status_code == 302 and response["Location"] == reverse(
        "reporting:detail", args=[report.pk]
    )
    assert report.scope == MARKET
    page = text(client.get(reverse("reporting:detail", args=[report.pk])))
    assert "Scope eu-market: the tests its specification states, with its limits" in page
    assert "This certificate is issued for scope eu-market." in page
    listed = text(client.get(reverse("reporting:list")))
    assert "Synthetic customer EUFor scope eu-market" in listed
    found = text(client.get(reverse("reporting:list") + "?q=eu-market"))
    assert report.number in found
    version = text(client.get(reverse("reporting:version", args=[report.pk, 1])))
    assert "This certificate is issued for scope eu-market." in version
    # The amendment pages keep the scope and name it.
    amend = text(client.get(reverse("reporting:amend_preview", args=[report.pk])))
    assert "For scope eu-market" in amend
    assert "This certificate is issued for scope eu-market." in amend
    digest = reporting.preview(lot, MARKET)[1]
    page = text(
        client.get(reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={digest}")
    )
    assert "new version 2, for scope eu-market" in page


def test_a_post_for_a_scope_whose_results_fail_issues_nothing(client, world):
    lot = released(world, TIGHT, choice="general", readings={"assay": "98.50"})
    author = world["people"]["author"]
    client.force_login(author)
    digest = reporting.preview(lot, MARKET)[1]
    response = client.post(
        sign_url(lot),
        {
            "recipient": "Synthetic customer EU",
            "reason": "Customer certificate",
            "evidence_hash": digest,
            "scope": MARKET,
            "signature_username": author.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 422
    assert "does not meet synthetic-rt-eu-market version 1 (eu-market)" in text(response)
    assert not Report.objects.exists()
