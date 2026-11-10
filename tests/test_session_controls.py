from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.test import override_settings
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature, RuleSet
from core.services import save_rule, set_pin

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def signer(django_user_model):
    user = django_user_model.objects.create_user("signer", password="Synthetic-session-test-2026!")
    user.groups.add(Group.objects.get_or_create(name="quality")[0])
    set_pin(actor=user, pin="82519374", password="Synthetic-session-test-2026!")
    return user


@override_settings(SESSION_IDLE_SECONDS=60, SESSION_ABSOLUTE_SECONDS=120)
@pytest.mark.parametrize("clock", ["last_activity_at", "authenticated_at"])
def test_expired_session_cannot_post(client, signer, clock):
    client.force_login(signer)
    session = client.session
    session[clock] = timezone.now().timestamp() - 121
    session.save()
    response = client.post("/rules/", {"code": "must-not-write"})
    assert response.status_code == 302
    assert "/accounts/login/" in response.url
    assert not RuleSet.objects.exists()
    assert "_auth_user_id" not in client.session
    assert AuditEvent.objects.filter(action="session.expired", actor=signer).exists()


def test_http_signing_requires_both_components_each_time(client, signer, django_user_model):
    author = django_user_model.objects.create_user("author")
    author.groups.add(Group.objects.get(name="quality"))
    rule = save_rule(
        actor=author,
        code="session-rule",
        segment="chemical",
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=1),
        reason="Synthetic rule",
    )
    client.force_login(signer)
    payload = {"revision": 1, "pin": "82519374", "reason": "Independent review"}
    assert client.post(f"/rules/{rule.pk}/approve/", payload).status_code == 200
    assert not ElectronicSignature.objects.exists()
    payload["signature_username"] = "someone-else"
    response = client.post(f"/rules/{rule.pk}/approve/", payload)
    assert "Enter your own signing username" in response.content.decode()
    assert not ElectronicSignature.objects.exists()
    payload["signature_username"] = signer.username
    assert client.post(f"/rules/{rule.pk}/approve/", payload).status_code == 302
    evidence = ElectronicSignature.objects.get().authentication_context
    assert evidence["channel"] == "web"
    assert evidence["components"] == ["username", "pin"]
    assert evidence["authenticated_at"]
    assert client.get("/rules/")["Cache-Control"] == "no-store, private"


def test_legacy_session_without_clocks_is_invalidated(client, signer):
    client.force_login(signer)
    session = client.session
    del session["authenticated_at"]
    session.save()
    assert client.get("/rules/").status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("change", ["password", "deactivate"])
def test_pin_replacement_rechecks_locked_current_account(signer, django_user_model, change):
    """A previously loaded User must not authorize PIN replacement after revocation."""
    from django.core.exceptions import PermissionDenied

    from core.models import PINCredential

    before = PINCredential.objects.get(user=signer).encoded
    current = django_user_model.objects.get(pk=signer.pk)
    if change == "password":
        current.set_password("Replacement-synthetic-password-2026!")
        current.save(update_fields=["password"])
    else:
        current.is_active = False
        current.save(update_fields=["is_active"])
    with pytest.raises(PermissionDenied, match="Password confirmation failed"):
        set_pin(actor=signer, pin="73918462", password="Synthetic-session-test-2026!")
    assert PINCredential.objects.get(user=signer).encoded == before
    assert AuditEvent.objects.filter(actor=signer, action="pin.changed").count() == 1


@override_settings(SESSION_IDLE_SECONDS=60, SESSION_ABSOLUTE_SECONDS=120)
@pytest.mark.parametrize("clock", ["last_activity_at", "authenticated_at"])
def test_session_expiry_during_transition_rolls_back_all_evidence(signer, monkeypatch, clock):
    """Time spent waiting for locks or applying checks cannot extend signing authority."""
    from django.core.exceptions import ValidationError
    from django.test import RequestFactory

    from core.audit import record_event
    from core.services import sign_transition
    from core.session_control import current_request

    rule = save_rule(
        actor=signer,
        code="expiry-during-transition",
        segment="chemical",
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=1),
        reason="Synthetic clock-boundary fixture",
    )
    now = timezone.now()
    request = RequestFactory().post("/synthetic-signing/", {"signature_username": signer.username})
    request.user = signer
    request.session = {
        "authenticated_at": now.timestamp(),
        "last_activity_at": now.timestamp(),
    }
    request.session[clock] -= 119 if clock == "authenticated_at" else 59
    monkeypatch.setattr("core.session_control.timezone.now", lambda: now)

    def apply(locked):
        locked.status = "approved"
        record_event(
            actor=signer,
            action="synthetic.callback",
            obj=locked,
            reason="This callback evidence must roll back together with the transition",
        )
        monkeypatch.setattr("core.session_control.timezone.now", lambda: now + timedelta(seconds=2))

    token = current_request.set(request)
    try:
        with pytest.raises(ValidationError, match="Session expired"):
            sign_transition(
                actor=signer,
                pin="82519374",
                obj=rule,
                expected_revision=rule.revision,
                meaning="approved",
                reason="Synthetic expiry boundary",
                permission="quality",
                apply=apply,
            )
    finally:
        current_request.reset(token)
    rule.refresh_from_db()
    assert rule.status == "draft"
    assert rule.revision == 1
    assert not ElectronicSignature.objects.exists()
    assert not AuditEvent.objects.filter(
        action__in=["synthetic.callback", "signed.approved"]
    ).exists()
