"""The decisions a rule set reserves for qualified people, through their pages: the lot record
says who may release and what a release relied on, the disposition, certificate and
reassessment signing pages refuse before any PIN is asked for and name the qualification a
signature relies on, the certificate version and the reassessment show it, and the
qualification's page lists the decisions relying on it (synthetic data only)."""

import html
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from core.models import PINCredential
from laboratory.models import Qualification
from quality.models import Lot, Reassessment
from reporting import services as reporting
from tests.test_decision_authorization import (
    COA_ACTIVITY,
    RELEASE_ACTIVITY,
    WRONG_PIN,
    issue,
    qualify,
    release,
)
from tests.test_decision_authorization import reassessed as reassessed  # noqa: F401
from tests.test_decision_authorization import world as world  # noqa: F401
from tests.test_reassessment import conclude as conclude_reassessment

pytestmark = pytest.mark.django_db(transaction=True)


def text(response):
    """The page as text, tags and whitespace runs removed."""
    return " ".join(html.unescape(strip_tags(response.content.decode())).split())


def requirement(lot, decision):
    return (
        f"Rule set {lot.rules.code} v{lot.rules.version} reserves {decision} for people "
        f"qualified for “{RELEASE_ACTIVITY if decision == 'release decisions' else COA_ACTIVITY}”."
    )


def test_the_lot_record_says_who_may_release_it(client, world):  # noqa: F811
    lot, approver = world["lot"], world["people"]["approver"]
    client.force_login(approver)
    body = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "Who may release" in body
    assert requirement(lot, "release decisions") in body
    # Not offered as the next step: the refusal is the note beside the actions.
    assert "Review disposition" not in body
    assert "You hold no approved, current qualification for it." in body
    # Rejection is not reserved: the same person is still offered it.
    assert "Reject lot" in body


def test_the_disposition_page_refuses_before_any_pin(client, world):  # noqa: F811
    lot, approver = world["lot"], world["people"]["approver"]
    client.force_login(approver)
    url = reverse("quality:disposition", args=[lot.pk])
    page = client.get(url)
    assert page.status_code == 403
    assert b'name="pin"' not in page.content
    assert requirement(lot, "release decisions") in text(page)
    posted = client.post(
        url,
        {
            "expected_revision": lot.revision,
            "signature_username": approver.username,
            "pin": WRONG_PIN,
            "reason": "Synthetic",
        },
    )
    assert posted.status_code == 403
    assert PINCredential.objects.get(user=approver).failures == 0
    assert Lot.objects.get(pk=lot.pk).state == "quarantine"


def test_the_disposition_page_names_the_qualification_relied_on(client, world):  # noqa: F811
    lot, approver = world["lot"], world["people"]["approver"]
    held = qualify(world, "approver", RELEASE_ACTIVITY, "release")
    client.force_login(approver)
    page = client.get(reverse("quality:disposition", args=[lot.pk]))
    assert page.status_code == 200
    body = text(page)
    assert (
        f"This signature relies on your qualification QUAL-{held.pk}, for release decisions in "
        f"“{RELEASE_ACTIVITY}” (Rule set {lot.rules.code} v1), and records it." in body
    )


def test_a_released_lot_shows_the_qualification_and_who_may_issue(client, world):  # noqa: F811
    held = qualify(world, "approver", RELEASE_ACTIVITY, "release")
    lot = release(world)
    client.force_login(world["people"]["reviewer"])
    page = client.get(reverse("quality:lot_detail", args=[lot.pk]))
    body = text(page)
    assert "Released under" in body and f"QUAL-{held.pk}" in body
    assert reverse("laboratory:qualification_detail", args=[held.pk]) in page.content.decode()
    assert "Who may issue" in body and requirement(lot, "issuing certificates") in body
    # The qualification's own page lists the release.
    detail = client.get(reverse("laboratory:qualification_detail", args=[held.pk]))
    body = text(detail)
    assert "Decisions relying on it" in body and "Release" in body and lot.number in body
    assert "Release decisions" in body  # Qualified for


def test_a_qualification_to_perform_lists_no_decisions(client, world):  # noqa: F811
    held = qualify(world, "approver", "synthetic-rt-method", "perform")
    client.force_login(world["people"]["reviewer"])
    body = text(client.get(reverse("laboratory:qualification_detail", args=[held.pk])))
    assert "Decisions relying on it" not in body


def test_the_certificate_preview_refuses_without_the_qualification(client, world):  # noqa: F811
    qualify(world, "approver", RELEASE_ACTIVITY, "release")
    lot = release(world)
    approver = world["people"]["approver"]
    client.force_login(approver)
    preview = client.get(reverse("reporting:issue_preview", args=[lot.pk]))
    body = text(preview)
    assert "Not permitted" in body and requirement(lot, "issuing certificates") in body
    assert "Continue to signing" not in body
    _, digest, _ = reporting.preview(lot)
    sign_url = reverse("reporting:issue_sign", args=[lot.pk])
    refused = client.get(f"{sign_url}?evidence={digest}")
    assert refused.status_code == 302
    assert refused["Location"].startswith(reverse("reporting:issue_preview", args=[lot.pk]))
    posted = client.post(
        sign_url,
        {
            "evidence_hash": digest,
            "recipient": "Synthetic recipient",
            "signature_username": approver.username,
            "pin": WRONG_PIN,
            "reason": "Synthetic",
        },
    )
    assert posted.status_code == 403
    assert requirement(lot, "issuing certificates") in text(posted)
    assert PINCredential.objects.get(user=approver).failures == 0


def test_the_certificate_pages_name_the_qualification_relied_on(client, world):  # noqa: F811
    qualify(world, "approver", RELEASE_ACTIVITY, "release")
    world["lot"] = release(world)
    held = qualify(world, "approver", COA_ACTIVITY, "certify")
    client.force_login(world["people"]["approver"])
    lot = world["lot"]
    _, digest, _ = reporting.preview(lot)
    sign = client.get(reverse("reporting:issue_sign", args=[lot.pk]) + f"?evidence={digest}")
    assert f"This signature relies on your qualification QUAL-{held.pk}" in text(sign)
    report = issue(world)
    version = client.get(reverse("reporting:version", args=[report.pk, 1]))
    body = text(version)
    assert "Signed under" in body and f"QUAL-{held.pk}" in body
    assert f"issuing certificates in “{COA_ACTIVITY}”" in body
    detail = text(client.get(reverse("laboratory:qualification_detail", args=[held.pk])))
    assert "Certificate issued" in detail and f"{report.number} version 1" in detail


def test_the_qualification_form_offers_the_new_kinds_and_refuses_a_non_quality_person(
    client,
    world,  # noqa: F811
):
    people = world["people"]
    client.force_login(people["author"])
    url = reverse("laboratory:qualification_new")
    page = client.get(url).content.decode()
    assert 'value="release"' in page and 'value="certify"' in page
    response = client.post(
        url,
        {
            "user": people["reviewer"].pk,
            "activity": RELEASE_ACTIVITY,
            "work": "release",
            "evidence_ref": "AUTH-SYN-VIEW",
            "valid_from": timezone.localdate().isoformat(),
            "valid_until": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "reason": "Synthetic",
        },
    )
    assert response.status_code == 422
    assert "Release decisions are signed with the quality role" in text(response)
    assert not Qualification.objects.filter(work="release").exists()
    response = client.post(
        url,
        {
            "user": people["approver"].pk,
            "activity": RELEASE_ACTIVITY,
            "work": "release",
            "evidence_ref": "AUTH-SYN-VIEW",
            "valid_from": timezone.localdate().isoformat(),
            "valid_until": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "reason": "Synthetic",
        },
    )
    assert response.status_code == 302
    recorded = Qualification.objects.get(work="release")
    listing = text(client.get(reverse("laboratory:qualification_list") + "?work=release"))
    assert recorded.activity in listing and "Release decisions" in listing and "Person" in listing


def test_the_conclusion_page_says_why_suitable_cannot_be_signed(client, reassessed):  # noqa: F811
    item, author = reassessed["item"], reassessed["people"]["author"]
    client.force_login(author)
    url = reverse("quality:reassessment_conclude", args=[item.pk])
    body = text(client.get(url))
    assert "You cannot conclude that the material is suitable:" in body
    assert "reserves release decisions" in body
    held = qualify(reassessed, "author", RELEASE_ACTIVITY, "release", recorder="approver")
    body = text(client.get(url))
    assert "You cannot conclude that the material is suitable" not in body
    assert f"This signature relies on your qualification QUAL-{held.pk}" in body
    done = conclude_reassessment(
        reassessed,
        item,
        Reassessment.Outcome.SUITABLE,
        timezone.localdate() + timedelta(days=200),
    )
    detail = text(client.get(reverse("quality:reassessment_detail", args=[done.pk])))
    assert "Concluded under" in detail and f"QUAL-{held.pk}" in detail


def test_the_rule_sets_page_states_what_a_rule_set_reserves(client, world):  # noqa: F811
    client.force_login(world["people"]["reviewer"])
    body = text(client.get(reverse("core:rules")))
    assert f"Release decisions reserved for people qualified for “{RELEASE_ACTIVITY}”" in body
    assert f"Issuing certificates reserved for people qualified for “{COA_ACTIVITY}”" in body


def test_the_amendment_pages_refuse_without_the_qualification(client, world):  # noqa: F811
    qualify(world, "approver", RELEASE_ACTIVITY, "release")
    world["lot"] = release(world)
    qualify(world, "approver", COA_ACTIVITY, "certify")
    report = issue(world)
    # Another quality person who issued nothing and holds no such qualification.
    author = world["people"]["author"]
    client.force_login(author)
    preview = text(client.get(reverse("reporting:amend_preview", args=[report.pk])))
    assert "Not permitted" in preview
    assert requirement(world["lot"], "issuing certificates") in preview
    assert "Continue to signing" not in preview
    _, digest, _ = reporting.preview(world["lot"])
    sign_url = reverse("reporting:amend_sign", args=[report.pk])
    refused = client.get(f"{sign_url}?evidence={digest}")
    assert refused.status_code == 302
    assert refused["Location"] == reverse("reporting:amend_preview", args=[report.pk])
    posted = client.post(
        sign_url,
        {
            "evidence_hash": digest,
            "expected_version": 1,
            "remarks": "Synthetic",
            "signature_username": author.username,
            "pin": WRONG_PIN,
            "reason": "Synthetic",
        },
    )
    assert posted.status_code == 403
    assert PINCredential.objects.get(user=author).failures == 0
