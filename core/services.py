import hashlib
import json
import re
from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q
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


def _roles(permission):
    return permission if isinstance(permission, tuple) else (permission,)


@sensitive_variables()
def lock_signer(actor, permission, encoded):
    """Lock the signer, then the credential (the order PIN changes and role changes use), and
    recheck the role and the credential verify_pin accepted. Every local here holds or reaches
    the stored hash, so all of them, and those of the queries below, stay out of error reports."""
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    credential = PINCredential.objects.select_for_update().filter(user=actor).first()
    require_role(actor, *_roles(permission))
    if (
        credential is None  # Re-enrollment was required after verification.
        or credential.encoded != encoded
        or (credential.locked_until and credential.locked_until > timezone.now())
    ):
        raise ValidationError("Signing credential changed. Try again.")
    return actor


@sensitive_variables("pin", "encoded")
def sign_transition(
    *, actor, pin, obj, expected_revision, meaning, reason, permission, apply, prepare=None
):
    """Sign one record: verify the PIN, lock the signer and the record, recheck its revision,
    apply the change and commit it with the signature and the audit event, or nothing.

    ``prepare`` runs inside the transaction after the signer is locked and before the record
    is: a transition that also writes rows which its module locks ahead of this record takes
    those locks there, so that it never locks out of order.

    ``permission`` is the role the signer needs, or a tuple of roles any one of which will do
    (the trainee acknowledging their own training holds whichever laboratory role they have).
    """
    require_role(actor, *_roles(permission))
    if not reason.strip() or not meaning.strip():
        raise ValidationError("Meaning and reason are required.")
    from .session_control import signing_context

    authentication_context = signing_context(actor)
    encoded = verify_pin(actor, pin)
    with transaction.atomic():
        actor = lock_signer(actor, permission, encoded)
        if prepare is not None:
            prepare()
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
        or (rule.superseded_from and rule.superseded_from <= at)
    ):
        raise ValidationError("An approved, effective rule revision is required.")
    validate_policy(rule.policy)


def validate_approved_rules(rule):
    """An approved rule version with a valid policy, whether or not it is still in force.

    For steps that evaluate what was already recorded under it (the review of a result).
    Assigning tests and the disposition need the version in force (``validate_rules``), so a
    version retired meanwhile never strands a result awaiting review or an investigation.
    """
    if rule.status != "approved":
        raise ValidationError("An approved rule revision is required.")
    validate_policy(rule.policy)


def applies_at(at):
    """Filter for approved versions that apply at ``at``: inside their effective period and not
    yet superseded by a later version. Shared by rule sets and controlled catalog revisions,
    which name these columns alike."""
    return (
        Q(status="approved", effective_from__lte=at)
        & (Q(effective_until__isnull=True) | Q(effective_until__gt=at))
        & (Q(superseded_from__isnull=True) | Q(superseded_from__gt=at))
    )


def supersession_plan(siblings, revision, at):
    """[(earlier version, moment it stops applying)] for approving ``revision`` at ``at``.

    ``siblings`` are the other versions of the same document. An approved version whose
    remaining period overlaps the new version's is retired when the new one takes over: at the
    later of the new version's start and ``at``, so never retroactively, or at its own start
    when it had not begun (it then never applies). A version already retired is only ever
    retired earlier. A draft cannot retire a version numbered after it.
    """
    start = max(revision.effective_from, at)
    if revision.effective_until is None or revision.effective_until <= start:
        return []
    overlapping = siblings.filter(
        status="approved", effective_from__lt=revision.effective_until
    ).filter(
        Q(superseded_from__isnull=True)
        & (Q(effective_until__isnull=True) | Q(effective_until__gt=start))
        | Q(superseded_from__gt=start)
    )
    plan = []
    for other in overlapping.order_by("version"):
        moment = max(other.effective_from, start)
        if other.superseded_from is not None and other.superseded_from <= moment:
            continue  # already retired by then (for example a version that never applies)
        if other.version > revision.version:
            raise ValidationError(
                f"Version {other.version} is already approved for these dates, and a version "
                "cannot retire a later one. Withdraw this draft and create a new version."
            )
        plan.append((other, moment))
    return plan


def supersede(*, actor, plan, revision, action, reason):
    """Retire the planned versions inside the approval's transaction, each with its audit event.

    Only the two supersession columns change; the approved content and its signature stay as
    they are. The caller holds the lock that serializes approvals of this kind of document.
    """
    for other, moment in plan:
        before = {
            "superseded_from": other.superseded_from.isoformat() if other.superseded_from else None,
            "superseded_by": other.superseded_by_id,
        }
        other.superseded_from = moment
        other.superseded_by = revision
        other.save(update_fields=["superseded_from", "superseded_by"])
        record_event(
            actor=actor,
            action=action,
            obj=other,
            before=before,
            after={"superseded_from": moment.isoformat(), "superseded_by": revision.pk},
            reason=f"Superseded by the approval of {revision}. {reason}",
        )


POLICY_KEYS = frozenset({"required_tests", "review_meaning", "disposition_meaning"})
# Optional. A rule set that carries it lets a qualified supplier's certificate result stand in
# for a test, except for the tests it lists under ``own_tests``, which the laboratory always
# performs itself. A rule set without it allows no such reliance.
SUPPLIER_RESULTS = "supplier_results"
OWN_TESTS = "own_tests"
# Optional. A rule set that carries it is not chosen when a lot is received: it applies, in
# addition to the lot's own rule set, to every lot whose material, stage and scopes it names.
# A dimension it leaves out matches every lot. The site is the deployment.
APPLIES_TO = "applies_to"
APPLIES_TO_KEYS = ("materials", "stages", "scopes")
# Optional. Which of a lot's dates the rule set requires before it is released: its expiry date,
# its retest date, at least one of them, or both. A rule set without it requires neither; a lot
# may still carry dates, and the release and the certificate respect them either way.
MATERIAL_DATES = "material_dates"
MATERIAL_DATES_RULES = {
    "expiry": "an expiry date",
    "retest": "a retest date",
    "expiry_or_retest": "an expiry date or a retest date",
    "expiry_and_retest": "an expiry date and a retest date",
}
# Optional. Which of a lot's decisions the rule set reserves for people holding an approved,
# current qualification for an activity it names: the release of a lot (and the conclusion that
# reassessed material stays in use), and the certificates issued for it. A rule set without it
# leaves both to the quality role.
AUTHORIZATION = "authorization"
AUTHORIZED_DECISIONS = {
    "release": "release decisions",
    "certificate": "issuing certificates",
}
ACTIVITY_LENGTH = 120
OPTIONAL_POLICY_KEYS = frozenset({SUPPLIER_RESULTS, APPLIES_TO, MATERIAL_DATES, AUTHORIZATION})
SCOPE_NAME = re.compile(r"[-a-zA-Z0-9_]+")


def _codes(value, *, allow_empty=False):
    """True for a list of codes: non-empty text without surrounding space, each listed once."""
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(t, str) and t.strip() and t == t.strip() for t in value)
        and len(set(value)) == len(value)
    )


def validate_policy(policy):
    if not isinstance(policy, dict) or not POLICY_KEYS <= set(policy) <= (
        POLICY_KEYS | OPTIONAL_POLICY_KEYS
    ):
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
    if SUPPLIER_RESULTS in policy:
        reliance = policy[SUPPLIER_RESULTS]
        own = reliance.get(OWN_TESTS) if isinstance(reliance, dict) else None
        if (
            not isinstance(reliance, dict)
            or set(reliance) != {OWN_TESTS}
            or not _codes(own, allow_empty=True)
        ):
            raise ValidationError(
                "supplier_results must hold exactly own_tests: a list of the test codes the "
                "laboratory always performs itself, each listed once (the list may be empty)."
            )
        # A code the rule set does not require could be a slip that leaves the intended test
        # open to reliance; a required code the specification lacks holds the lot instead.
        unknown = [t for t in own if t not in tests]
        if unknown:
            raise ValidationError(
                "own_tests must be among required_tests; not required: " + ", ".join(unknown) + "."
            )
    if MATERIAL_DATES in policy and (
        not isinstance(policy[MATERIAL_DATES], str)
        or policy[MATERIAL_DATES] not in MATERIAL_DATES_RULES
    ):
        raise ValidationError(
            "material_dates must be one of " + ", ".join(MATERIAL_DATES_RULES) + "."
        )
    if AUTHORIZATION in policy:
        reserved = policy[AUTHORIZATION]
        if (
            not isinstance(reserved, dict)
            or not reserved
            or not set(reserved) <= set(AUTHORIZED_DECISIONS)
            or not all(
                isinstance(activity, str)
                and activity.strip()
                and activity == activity.strip()
                and len(activity) <= ACTIVITY_LENGTH
                for activity in reserved.values()
            )
        ):
            raise ValidationError(
                "authorization must name, for release, certificate or both, the activity a "
                f"signer must be qualified for: a code of at most {ACTIVITY_LENGTH} characters "
                "without surrounding spaces."
            )
    if APPLIES_TO in policy:
        where = policy[APPLIES_TO]
        if (
            not isinstance(where, dict)
            or not where
            or not set(where) <= set(APPLIES_TO_KEYS)
            or not all(_codes(value) for value in where.values())
        ):
            raise ValidationError(
                "applies_to must say where the rule set applies with at least one of "
                "materials, stages and scopes, each a list of codes listed once."
            )
        # A scope is matched by its name: one that could never be entered for a lot would
        # leave the rule set silently without effect.
        for scope in where.get("scopes", []):
            if len(scope) > 60 or not SCOPE_NAME.fullmatch(scope):
                raise ValidationError(
                    f"applies_to names “{scope}”, which is not a scope name: use letters, "
                    "digits, - and _, at most 60 characters."
                )


def is_additional(rule):
    """True for a rule set that applies in addition to a lot's own rule set (``applies_to``)."""
    return isinstance(rule.policy, dict) and isinstance(rule.policy.get(APPLIES_TO), dict)


def rule_applies(rule, *, material, stage, scopes):
    """Whether an additional rule set version applies to a lot of this material code, at this
    stage, under these scopes. Every dimension it names must match; one of its scopes is
    enough. A rule set without ``applies_to`` never applies this way."""
    if not is_additional(rule):
        return False
    where = rule.policy[APPLIES_TO]
    return (
        ("materials" not in where or material in where["materials"])
        and ("stages" not in where or stage in where["stages"])
        and ("scopes" not in where or bool(set(where["scopes"]) & set(scopes)))
    )


def additional_rules(*, material, stage, scopes, at, exclude_code=None):
    """The additional rule set versions in force at ``at`` that apply to such a lot, by code.

    One version per rule set: the latest of those that apply at ``at``, as for a lot's own
    rule set. Nothing is selected by a rule set that states no ``applies_to``.
    """
    latest = {}
    for rule in RuleSet.objects.filter(applies_at(at)).order_by("code", "version"):
        latest[rule.code] = rule
    return [
        rule
        for code, rule in latest.items()
        if code != exclude_code
        and rule_applies(rule, material=material, stage=stage, scopes=scopes)
    ]


def applicability_problems(policy):
    """Codes under ``applies_to`` that name nothing: an unknown material or stage never
    matches a lot, so the rule set would silently never apply. Read through the app registry;
    rule sets do not depend on the catalog."""
    where = policy.get(APPLIES_TO) if isinstance(policy, dict) else None
    if not isinstance(where, dict) or not apps.is_installed("catalog"):
        return []
    problems = []
    if "materials" in where:
        material = apps.get_model("catalog", "Material")
        known = set(
            material.objects.filter(code__in=where["materials"]).values_list("code", flat=True)
        )
        if unknown := [code for code in where["materials"] if code not in known]:
            problems.append("applies_to names unknown materials: " + ", ".join(unknown) + ".")
    if "stages" in where:
        field = apps.get_model("catalog", "Specification")._meta.get_field("stage")
        known = {value for value, _ in field.choices}
        if unknown := [code for code in where["stages"] if code not in known]:
            problems.append(
                "applies_to names unknown stages: "
                + ", ".join(unknown)
                + ". Use "
                + ", ".join(sorted(known))
                + "."
            )
    return problems


def check_applicability(policy, earlier=None):
    """Refuse an ``applies_to`` that names nothing known, and a version that changes what kind
    of rule set this is: a lot's own rule set and an additional one are never the same code."""
    if problems := applicability_problems(policy):
        raise ValidationError(problems)
    if earlier is not None and is_additional(earlier) != (APPLIES_TO in policy):
        raise ValidationError(
            f"Rule set {earlier.code} "
            + (
                "applies in addition to a lot's own rule set, so every version states applies_to."
                if is_additional(earlier)
                else "is chosen when a lot is received, so no version states applies_to. "
                "Create an additional rule set under another code."
            )
        )


def supplier_reliance_refusal(rule, test_code):
    """Why this rule revision does not let a supplier's result stand in for the test, or "".

    The rule set decides, never a default: without ``supplier_results`` nothing is relied on,
    and a test it lists under ``own_tests`` is always performed by the laboratory.
    """
    reliance = rule.policy.get(SUPPLIER_RESULTS) if isinstance(rule.policy, dict) else None
    if not isinstance(reliance, dict):
        return (
            f"Rule set {rule} does not allow a supplier's result to stand in for a test. "
            "Every required test is performed by the laboratory."
        )
    if test_code in reliance.get(OWN_TESTS, []):
        return (
            f"Rule set {rule} requires the laboratory to perform {test_code} itself; a "
            "supplier's result cannot stand in for it."
        )
    return ""


def own_tests(rule):
    """The tests the rule revision keeps with the laboratory, or None when it allows no
    reliance on supplier results at all."""
    reliance = rule.policy.get(SUPPLIER_RESULTS) if isinstance(rule.policy, dict) else None
    if not isinstance(reliance, dict):
        return None
    return list(reliance.get(OWN_TESTS, []))


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
        check_applicability(policy, latest)
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


def check_rule_approval(*, actor, rule, at=None):
    """Read-only preflight; signing repeats it under the record/configuration locks.

    Returns the approved versions of the rule set this approval retires, each with the moment
    it stops applying (see ``supersession_plan``).
    """
    require_role(actor, "quality")
    if rule.author_id == actor.pk:
        raise PermissionDenied("Rule authors cannot approve their own revision.")
    if rule.status != "draft":
        raise ValidationError("Only draft rules can be approved.")
    validate_policy(rule.policy)
    if rule.effective_until is None:
        raise ValidationError("An effective end date is required for approval.")
    siblings = RuleSet.objects.filter(code=rule.code).exclude(pk=rule.pk)
    check_applicability(rule.policy, siblings.order_by("version").first())
    return supersession_plan(siblings, rule, at or timezone.now())


@sensitive_variables("pin")
def approve_rule(*, actor, pin, rule, expected_revision, reason):
    # Credential serialization is not sufficient for approvals by different people.
    # The callback takes the global configuration lock before it works out which approved
    # versions this one retires.
    def serialized(locked):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(681240)")
        plan = check_rule_approval(actor=actor, rule=locked, at=locked._signing_timestamp)
        supersede(actor=actor, plan=plan, revision=locked, action="rule.superseded", reason=reason)
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
