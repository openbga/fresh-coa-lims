"""Approval preflight avoids unusable signing forms without weakening POST checks."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import save_rule
from tests.test_core import PIN, approve
from tests.test_core import people as people  # noqa: F401
from tests.test_core import rule as rule  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def overlapping_draft(rule, people, days=30):
    return save_rule(
        actor=people[0],
        code=rule.code,
        segment=rule.segment,
        policy=rule.policy,
        effective_from=timezone.now() + timedelta(days=days),
        effective_until=rule.effective_until + timedelta(days=365),
        reason="Synthetic overlapping draft",
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("author", "Rule authors cannot approve their own revision."),
        ("approved", "Only draft rules can be approved."),
        ("missing_end", "An effective end date is required for approval."),
        ("later", "Version 3 is already approved for these dates"),
    ],
)
def test_ineligible_rule_get_explains_without_pin_or_mutation(client, people, rule, case, message):
    actor = people[0] if case == "author" else people[1]
    if case in {"approved", "later"}:
        rule = approve(rule, people[1])
    if case == "missing_end":
        rule.effective_until = None
        rule.save(update_fields=["effective_until"])
    if case == "later":
        # A draft left behind while a later version of the rule set was approved.
        stale = overlapping_draft(rule, people)
        approve(overlapping_draft(rule, people), people[1])
        rule = stale
    client.force_login(actor)
    before = (rule.revision, ElectronicSignature.objects.count(), AuditEvent.objects.count())
    credential = PINCredential.objects.get(user=actor)
    credential.failures = 2
    credential.save(update_fields=["failures"])

    response = client.get(reverse("core:rule_approve", args=[rule.pk]), follow=True)

    assert response.redirect_chain == [(reverse("core:rules"), 302)]
    assert message in response.content.decode()
    assert 'name="pin"' not in response.content.decode()
    rule.refresh_from_db()
    credential.refresh_from_db()
    assert credential.failures == 2
    assert (
        rule.revision,
        ElectronicSignature.objects.count(),
        AuditEvent.objects.count(),
    ) == before


def test_valid_get_does_not_authorize_a_later_stale_post(client, people, rule):
    actor = people[1]
    client.force_login(actor)
    url = reverse("core:rule_approve", args=[rule.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'name="pin"' in response.content.decode()
    revision = rule.revision
    approve(rule, actor)  # Another completed signing makes the open page stale.
    signatures = ElectronicSignature.objects.count()

    response = client.post(
        url,
        {
            "revision": revision,
            "signature_username": actor.username,
            "pin": PIN,
            "reason": "Review",
        },
    )

    assert "Record changed. Reload and review before signing." in response.content.decode()
    assert ElectronicSignature.objects.count() == signatures


def test_author_cannot_bypass_preflight_with_direct_post(client, people, rule):
    actor = people[0]
    client.force_login(actor)
    response = client.post(
        reverse("core:rule_approve", args=[rule.pk]),
        {
            "revision": rule.revision,
            "signature_username": actor.username,
            "pin": PIN,
            "reason": "Review",
        },
    )
    assert response.status_code == 403
    assert not ElectronicSignature.objects.exists()
    rule.refresh_from_db()
    assert rule.status == "draft" and rule.revision == 1


def test_approval_page_names_the_version_it_retires_and_the_lots_received_under_it(
    client, people, rule
):
    from quality.models import Lot

    first = approve(rule, people[1])
    Lot.objects.create(
        number="SYN-RULE-001", material="Synthetic", rules=first, created_by=people[0]
    )
    draft = overlapping_draft(first, people)
    client.force_login(people[1])
    url = reverse("core:rule_approve", args=[draft.pk])
    page = " ".join(client.get(url).content.decode().split())
    assert "Your signature also retires it" in page
    assert f"<strong>{first}</strong> stops applying on" in page
    assert "1 lot in quarantine is on it" in page
    assert "assigned again (before testing has started) or replaced with a signature" in page
    assert "the moment of your signature" not in page  # the new version starts later
    response = client.post(
        url,
        {
            "revision": draft.revision,
            "signature_username": people[1].username,
            "pin": PIN,
            "reason": "Independent review of the revised policy",
        },
    )
    assert response.status_code == 302
    first.refresh_from_db()
    draft.refresh_from_db()
    assert draft.status == "approved"
    assert first.superseded_by == draft and first.superseded_from == draft.effective_from
    listing = " ".join(client.get(reverse("core:rules")).content.decode().split())
    assert "Superseded by version 2 from" in listing
