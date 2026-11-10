"""Shared evidence contracts against PostgreSQL, including database bypass guards."""

import hashlib
import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from core.audit import snapshot
from core.models import AuditEvent, AuditReview, ElectronicSignature, PINCredential, RuleSet
from core.services import approve_rule, review_audit, save_rule, set_pin, validate_rules

pytestmark = pytest.mark.django_db(transaction=True)
PIN = "82519374"
PASSWORD = "synthetic-test-password-847"


@pytest.fixture
def people():
    users = []
    for name in ("author", "reviewer"):
        user = get_user_model().objects.create_user(username=name, password=PASSWORD)
        user.groups.add(Group.objects.get_or_create(name="quality")[0])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        users.append(user)
    return users


@pytest.fixture
def rule(people):
    return save_rule(
        actor=people[0],
        code="synthetic-identity",
        segment="chemical",
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        effective_from=timezone.now() - timedelta(hours=1),
        effective_until=timezone.now() + timedelta(days=365),
        reason="Synthetic test rule",
    )


def approve(rule, actor, **overrides):
    kwargs = {
        "actor": actor,
        "pin": PIN,
        "rule": rule,
        "expected_revision": rule.revision,
        "reason": "Independently checked synthetic policy",
    }
    kwargs.update(overrides)
    return approve_rule(**kwargs)


def test_success_binds_exact_revision_snapshot_and_audit(rule, people):
    approved = approve(rule, people[1])
    signature = ElectronicSignature.objects.get()
    event = signature.audit_event
    assert approved.status == "approved"
    assert approved.revision == 2
    assert signature.revision == approved.revision
    assert signature.content == snapshot(approved) == event.after
    assert signature.object_id == str(approved.pk)
    assert signature.object_type == "core.ruleset"
    assert signature.signer == people[1]
    assert signature.signer_name == "reviewer"
    assert signature.meaning == "approved"
    assert signature.signed_at is not None
    assert (
        signature.content_hash
        == hashlib.sha256(
            json.dumps(signature.content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert event.before["status"] == "draft"
    assert event.after["status"] == "approved"
    validate_rules(approved)


def test_bad_pin_does_not_transition_but_failure_persists(rule, people):
    with pytest.raises(ValidationError, match="PIN was not accepted"):
        approve(rule, people[1], pin="00000000")
    rule.refresh_from_db()
    assert rule.status == "draft"
    assert rule.revision == 1
    assert not ElectronicSignature.objects.exists()
    assert not AuditEvent.objects.filter(action="signed.approved").exists()
    assert PINCredential.objects.get(user=people[1]).failures == 1
    assert AuditEvent.objects.filter(actor=people[1], action="signature.denied").count() == 1


def test_lockout_cannot_be_bypassed_by_correct_pin(rule, people):
    for _ in range(5):
        with pytest.raises(ValidationError):
            approve(rule, people[1], pin="00000000")
    credential = PINCredential.objects.get(user=people[1])
    assert credential.locked_until > timezone.now()
    with pytest.raises(ValidationError, match="temporarily locked"):
        approve(rule, people[1])
    assert not ElectronicSignature.objects.exists()
    assert AuditEvent.objects.filter(actor=people[1], action="signature.denied").count() == 6
    credential.locked_until = timezone.now() - timedelta(seconds=1)
    credential.save()
    assert approve(rule, people[1]).status == "approved"


def test_pin_is_hashed_and_secret_not_audited(people):
    credential = PINCredential.objects.get(user=people[0])
    assert credential.encoded != PIN
    assert check_password(PIN, credential.encoded)
    for event in AuditEvent.objects.all():
        assert PIN not in json.dumps([event.before, event.after, event.reason])
        assert credential.encoded not in json.dumps([event.before, event.after, event.reason])


def test_stale_revision_rejected_without_signature(rule, people):
    with pytest.raises(ValidationError, match="Record changed"):
        approve(rule, people[1], expected_revision=0)
    rule.refresh_from_db()
    assert rule.status == "draft"
    assert not ElectronicSignature.objects.exists()


def test_author_cannot_approve_even_with_quality_role(rule, people):
    with pytest.raises(PermissionDenied, match="own revision"):
        approve(rule, people[0])
    rule.refresh_from_db()
    assert rule.status == "draft"
    assert not ElectronicSignature.objects.exists()


def test_superuser_does_not_implicitly_gain_quality_authority(rule, people):
    reviewer = people[1]
    reviewer.groups.clear()
    reviewer.is_superuser = True
    reviewer.save()
    with pytest.raises(PermissionDenied):
        approve(rule, reviewer)
    assert not ElectronicSignature.objects.exists()


def test_signature_insert_failure_rolls_back_transition_and_audit(rule, people, monkeypatch):
    def fail_insert(**kwargs):
        raise RuntimeError("Synthetic persistence failure")

    monkeypatch.setattr(ElectronicSignature.objects, "create", fail_insert)
    with pytest.raises(RuntimeError, match="Synthetic persistence failure"):
        approve(rule, people[1])
    rule.refresh_from_db()
    assert rule.status == "draft"
    assert rule.revision == 1
    assert not AuditEvent.objects.filter(action="signed.approved").exists()


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_approved_rule_database_guard(rule, people, operation):
    approve(rule, people[1])
    with pytest.raises(DatabaseError), transaction.atomic():
        queryset = RuleSet.objects.filter(pk=rule.pk)
        if operation == "update":
            queryset.update(segment="food")
        else:
            queryset.delete()
    rule.refresh_from_db()
    assert rule.segment == "chemical"


@pytest.mark.parametrize("model", [AuditEvent, ElectronicSignature])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_evidence_database_guards(rule, people, model, operation):
    approve(rule, people[1])
    obj = model.objects.first()
    with pytest.raises(DatabaseError), transaction.atomic():
        queryset = model.objects.filter(pk=obj.pk)
        if operation == "update":
            field = "reason" if model is AuditEvent else "meaning"
            queryset.update(**{field: "tampered"})
        else:
            queryset.delete()
    assert model.objects.filter(pk=obj.pk).exists()


def test_audit_review_is_attributed_and_excludes_own_events(rule, people):
    event = AuditEvent.objects.get(action="rule.created", object_id=str(rule.pk))
    with pytest.raises(PermissionDenied):
        review_audit(actor=people[0], event_ids=[event.pk], conclusion="Self review")
    assert not AuditReview.objects.exists()
    review = review_audit(
        actor=people[1], event_ids=[event.pk], conclusion="Checked rule creation evidence"
    )
    assert review.events.get() == event
    assert review.reviewer == people[1]
    reviewed = AuditEvent.objects.get(action="audit.reviewed")
    assert reviewed.after["events"] == [str(event.pk)]


def test_rule_revisions_and_effective_interval(rule, people):
    approve(rule, people[1])
    next_rule = save_rule(
        actor=people[0],
        code=rule.code,
        segment=rule.segment,
        policy=rule.policy,
        effective_from=timezone.now(),
        effective_until=timezone.now() + timedelta(days=730),
        reason="Revised test panel",
    )
    assert next_rule.version == 2
    with pytest.raises(ValidationError, match="overlap"):
        approve(next_rule, people[1])
    with pytest.raises(ValidationError, match="approved, effective"):
        validate_rules(next_rule)


def test_approval_requires_finite_effective_interval(rule, people):
    RuleSet.objects.filter(pk=rule.pk).update(effective_until=None)
    rule.refresh_from_db()
    with pytest.raises(ValidationError, match="effective"):
        approve(rule, people[1])
    rule.refresh_from_db()
    assert rule.status == "draft"
    assert not ElectronicSignature.objects.exists()


def test_completed_audit_review_cannot_gain_members(rule, people):
    event = AuditEvent.objects.get(action="rule.created", object_id=str(rule.pk))
    review = review_audit(
        actor=people[1], event_ids=[event.pk], conclusion="Checked selected creation evidence"
    )
    another_event = AuditEvent.objects.filter(actor=people[0], action="pin.changed").get()
    with pytest.raises(DatabaseError), transaction.atomic():
        review.events.add(another_event)
    assert list(review.events.values_list("pk", flat=True)) == [event.pk]


def test_draft_presets_are_idempotent_and_do_not_auto_approve(people):
    from django.core.management import call_command

    call_command("seed_rules", actor=people[0].username)
    call_command("seed_rules", actor=people[0].username)
    assert set(RuleSet.objects.values_list("segment", flat=True)) == {
        "pharma",
        "supplement",
        "food",
        "chemical",
        "device",
    }
    assert RuleSet.objects.count() == 5
    assert not RuleSet.objects.exclude(status="draft").exists()


def test_audit_export_requires_role_and_sanitizes_cells(client, people):
    user = get_user_model().objects.create_user(username="no-role")
    client.force_login(user)
    assert client.get("/audit/?export=csv").status_code == 403
    client.force_login(people[0])
    with transaction.atomic():
        from core.audit import record_event

        record_event(actor=people[1], action="test", obj=people[1], reason="=1+1")
    response = client.get("/audit/?export=csv")
    assert response.status_code == 200
    assert "'=1+1" in response.content.decode()


def test_non_object_policy_rejected(people):
    from core.services import validate_policy

    with pytest.raises(ValidationError):
        validate_policy(["required_tests", "review_meaning", "disposition_meaning"])
