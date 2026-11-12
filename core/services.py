import hashlib
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .audit import record_event, snapshot
from .models import AuditEvent, AuditReview, ElectronicSignature, PINCredential, RuleSet

AUDIT_READ_ROLES = frozenset({"admin", "quality", "auditor"})


def require_role(actor, *roles):
    if not actor.pk or not get_user_model().objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied("Active account required.")
    if not actor.groups.filter(name__in=roles).exists():
        raise PermissionDenied("Your role does not permit this action.")


@sensitive_variables()
def set_pin(*, actor, pin, password):
    """Self-service enrollment/replacement requires login password reauthentication."""
    from accounts.authentication import confirm_password

    if not pin.isascii() or not pin.isdigit() or len(pin) < 8 or len(pin) > 32:
        raise ValidationError("Use 8–32 digits for your signature PIN.")
    # Shares the sign-in failure counter; the count or reset commits whatever happens to the PIN.
    verified = confirm_password(actor, password)
    if verified is None:
        raise PermissionDenied("Password confirmation failed.")
    with transaction.atomic():
        actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not actor.is_active or actor.password != verified:  # Changed since the confirmation.
            raise PermissionDenied("Password confirmation failed.")
        if actor.credentials_locked:
            from accounts.administration import CREDENTIALS_LOCKED

            raise PermissionDenied(CREDENTIALS_LOCKED)
        PINCredential.objects.update_or_create(
            user=actor,
            defaults={"encoded": make_password(pin), "failures": 0, "locked_until": None},
        )
        record_event(
            actor=actor,
            action="pin.changed",
            obj=actor,
            reason="Owner confirmed login password; PIN enrolled or replaced.",
        )


@sensitive_variables()
def verify_pin(actor, pin):
    # A caller's transaction must never roll back failed-attempt counters or security events.
    if connection.in_atomic_block:
        raise RuntimeError("Call signing outside an enclosing transaction.")
    error = None
    with transaction.atomic():
        actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
        credential = PINCredential.objects.select_for_update().filter(user=actor).first()
        if credential is None:
            error = "Enroll a signature PIN first."
        elif credential.locked_until and credential.locked_until > timezone.now():
            error = "Signature PIN is temporarily locked."
        elif not check_password(pin, credential.encoded):
            credential.failures += 1
            if credential.failures >= 5:
                credential.locked_until = timezone.now() + timedelta(minutes=15)
                credential.failures = 0
            # Counters only: the stored hash stays out of the statement and its parameters.
            credential.save(update_fields=["failures", "locked_until"])
            error = "Signature PIN was not accepted."
        elif credential.failures or credential.locked_until is not None:
            credential.failures = 0
            credential.locked_until = None
            credential.save(update_fields=["failures", "locked_until"])
        if error:
            record_event(actor=actor, action="signature.denied", obj=actor, reason=error)
    if error:
        raise ValidationError(error)
    return credential.encoded


@sensitive_variables()
def lock_signer(actor, permission, encoded):
    """Lock the signer, then the credential (the order PIN changes and role changes use), and
    recheck the role and the credential verify_pin accepted. Every local here holds or reaches
    the stored hash, so all of them, and those of the queries below, stay out of error reports."""
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    credential = PINCredential.objects.select_for_update().filter(user=actor).first()
    require_role(actor, permission)
    if (
        credential is None  # Re-enrollment was required after verification.
        or credential.encoded != encoded
        or (credential.locked_until and credential.locked_until > timezone.now())
    ):
        raise ValidationError("Signing credential changed. Try again.")
    return actor


@sensitive_variables("pin", "encoded")
def sign_transition(*, actor, pin, obj, expected_revision, meaning, reason, permission, apply):
    require_role(actor, permission)
    if not reason.strip() or not meaning.strip():
        raise ValidationError("Meaning and reason are required.")
    from .session_control import signing_context

    authentication_context = signing_context(actor)
    encoded = verify_pin(actor, pin)
    with transaction.atomic():
        actor = lock_signer(actor, permission, encoded)
        locked = type(obj).objects.select_for_update().get(pk=obj.pk)
        if locked.revision != expected_revision:
            raise ValidationError("Record changed. Reload and review before signing.")
        before = snapshot(locked)
        signing_timestamp = timezone.now()
        locked._signing_timestamp = signing_timestamp
        apply(locked)
        authentication_context = signing_context(actor)
        locked.revision += 1
        locked.full_clean()
        locked.save()
        content = snapshot(locked)
        event = record_event(
            actor=actor,
            action=f"signed.{meaning}",
            obj=locked,
            before=before,
            after=content,
            reason=reason,
        )
        ElectronicSignature.objects.create(
            signer=actor,
            signed_at=signing_timestamp,
            authentication_context=authentication_context,
            signer_name=actor.get_full_name() or actor.get_username(),
            meaning=meaning,
            object_type=locked._meta.label_lower,
            object_id=str(locked.pk),
            revision=locked.revision,
            content=content,
            content_hash=hashlib.sha256(
                json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            audit_event=event,
        )
        return locked


def validate_rules(rule, at=None):
    at = at or timezone.now()
    if (
        rule.status != "approved"
        or rule.effective_from > at
        or (rule.effective_until and rule.effective_until <= at)
    ):
        raise ValidationError("An approved, effective rule revision is required.")
    validate_policy(rule.policy)


def validate_policy(policy):
    allowed = {"required_tests", "review_meaning", "disposition_meaning"}
    if not isinstance(policy, dict) or set(policy) != allowed:
        raise ValidationError("Unsupported or missing rule policy keys.")
    tests = policy["required_tests"]
    if (
        not isinstance(tests, list)
        or not tests
        or any(not isinstance(t, str) or not t for t in tests)
    ):
        raise ValidationError("At least one required test code is needed.")
    if policy["review_meaning"] != "reviewed" or policy["disposition_meaning"] != "approved":
        raise ValidationError("This foundation supports reviewed and approved signature meanings.")


def save_rule(*, actor, code, segment, policy, effective_from, reason, effective_until=None):
    require_role(actor, "quality")
    validate_policy(policy)
    if not reason.strip() or (effective_until and effective_until <= effective_from):
        raise ValidationError("Provide a reason and a valid effective interval.")
    with transaction.atomic():
        # One global configuration lock avoids races when creating a first revision.
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(681240)")
        latest = RuleSet.objects.filter(code=code).order_by("-version").first()
        rule = RuleSet.objects.create(
            code=code,
            segment=segment,
            policy=policy,
            version=latest.version + 1 if latest else 1,
            author=actor,
            effective_from=effective_from,
            effective_until=effective_until,
        )
        record_event(
            actor=actor, action="rule.created", obj=rule, after=snapshot(rule), reason=reason
        )
        return rule


def check_rule_approval(*, actor, rule):
    """Read-only preflight; signing repeats it under the record/configuration locks."""
    from django.db import models

    require_role(actor, "quality")
    if rule.author_id == actor.pk:
        raise PermissionDenied("Rule authors cannot approve their own revision.")
    if rule.status != "draft":
        raise ValidationError("Only draft rules can be approved.")
    validate_policy(rule.policy)
    if rule.effective_until is None:
        raise ValidationError("An effective end date is required for approval.")
    overlaps = RuleSet.objects.filter(
        code=rule.code, status="approved", effective_from__lt=rule.effective_until
    ).filter(
        models.Q(effective_until__isnull=True) | models.Q(effective_until__gt=rule.effective_from)
    )
    if overlaps.exists():
        raise ValidationError("Effective dates overlap an approved revision.")


@sensitive_variables("pin")
def approve_rule(*, actor, pin, rule, expected_revision, reason):
    # Credential serialization is not sufficient for approvals by different people.
    # Callback acquires global configuration lock before overlap check.
    def serialized(locked):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(681240)")
        check_rule_approval(actor=actor, rule=locked)
        locked.status = "approved"

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=rule,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=serialized,
    )


def review_audit(*, actor, event_ids, conclusion):
    require_role(actor, "quality", "auditor")
    if not conclusion.strip() or not event_ids:
        raise ValidationError("Select events and record a review conclusion.")
    with transaction.atomic():
        events = list(AuditEvent.objects.filter(pk__in=event_ids))
        if len(events) != len(set(event_ids)) or any(e.actor_id == actor.pk for e in events):
            raise PermissionDenied("Review requires existing events from other actors.")
        review = AuditReview.objects.create(reviewer=actor, conclusion=conclusion)
        review.events.set(events)
        record_event(
            actor=actor,
            action="audit.reviewed",
            obj=review,
            after={"events": [str(e.pk) for e in events]},
            reason=conclusion,
        )
        return review
