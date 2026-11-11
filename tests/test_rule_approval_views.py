"""Approval preflight avoids unusable signing forms without weakening POST checks."""

import pytest
from django.urls import reverse

from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import save_rule
from tests.test_core import PIN, approve
from tests.test_core import people as people  # noqa: F401
from tests.test_core import rule as rule  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("author", "Rule authors cannot approve their own revision."),
        ("approved", "Only draft rules can be approved."),
        ("missing_end", "An effective end date is required for approval."),
        ("overlap", "Effective dates overlap an approved revision."),
    ],
)
def test_ineligible_rule_get_explains_without_pin_or_mutation(client, people, rule, case, message):
    actor = people[0] if case == "author" else people[1]
    if case in {"approved", "overlap"}:
        rule = approve(rule, people[1])
    if case == "missing_end":
        rule.effective_until = None
        rule.save(update_fields=["effective_until"])
    if case == "overlap":
        rule = save_rule(
            actor=people[0],
            code=rule.code,
            segment=rule.segment,
            policy=rule.policy,
            effective_from=rule.effective_from,
            effective_until=rule.effective_until,
            reason="Synthetic overlapping draft",
        )
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
