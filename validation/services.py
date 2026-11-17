"""Validation records: the laboratory's acceptance of the system for its intended use, and its
rehearsals of recovery, downtime and upgrades.

One person records, a different quality person accepts with a signature; the recorder or any
quality person withdraws a record that will not be accepted. Recorded content is never edited.
The software holds no work because of these records: what changed since an acceptance is
shown for the laboratory to assess under its own change control.

Lock order: the actor's account first, then the validation rows. Accepting a use locks every
use-acceptance row in id order (there are few), so two acceptances serialize and the one
accepted before is superseded by exactly one.
"""

import hashlib
import json
import os

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.audit import record_event, snapshot
from core.services import require_role, sign_transition

from .models import Rehearsal, RehearsalFile, UseAcceptance

KEEPER = "quality"
REHEARSAL_RECORDERS = ("quality", "admin")
READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
OWNER_ROLES = ("analyst", "reviewer", "quality", "admin")
MAX_METHODS = 200
MAX_FILES = 20
USE = UseAcceptance.State
REHEARSAL = Rehearsal.State

# The approved configuration kinds frozen by an acceptance, in the order they are shown.
KINDS = (
    ("rule_sets", "Rule set"),
    ("specifications", "Specification"),
    ("methods", "Method"),
    ("sampling_plans", "Sampling plan"),
    ("stability_protocols", "Stability protocol"),
)


def _require_reason(reason):
    if not (reason or "").strip():
        raise ValidationError("A reason is required.")


def lock_account(actor):
    """The same first lock as signing and every other unsigned write (FOR NO KEY UPDATE)."""
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


def has_role(user, *roles):
    return user.groups.filter(name__in=roles).exists()


def running_release():
    """The source revision of the running release, as the deployment states it, or ""."""
    value = os.environ.get("SOURCE_REVISION") or os.environ.get("RENDER_GIT_COMMIT") or ""
    return value.strip()[:80]


def owner_candidates():
    """Active accounts holding a working role: a process or system owner is one of them."""
    return (
        get_user_model()
        .objects.filter(is_active=True, groups__name__in=OWNER_ROLES)
        .distinct()
        .order_by("username")
    )


# --- The approved configuration in force ---------------------------------------------------


def _in_force(queryset, at):
    return queryset.filter(
        Q(superseded_from__isnull=True) | Q(superseded_from__gt=at),
        status="approved",
        effective_from__lte=at,
    )


def configuration_in_force(at=None):
    """Every approved version in force at ``at``, by kind, each sorted by code.

    A version is identified by its record, code and version number, and by the hash of its
    approved content where it has one, so a frozen copy shows exactly what applied.
    """
    from catalog.models import MethodRevision, SpecificationRevision
    from core.models import RuleSet
    from sampling.models import SamplingPlanRevision
    from stability.models import Protocol

    at = at or timezone.now()

    def controlled(model, parent):
        rows = _in_force(model.objects.filter(effective_until__gt=at), at).select_related(parent)
        return [
            {
                "id": row.pk,
                "code": getattr(row, parent).code,
                "version": row.version,
                "hash": row.approved_hash,
            }
            for row in rows
        ]

    rule_sets = _in_force(
        RuleSet.objects.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=at)), at
    )
    protocols = Protocol.objects.filter(state=Protocol.State.APPROVED)
    found = {
        "rule_sets": [
            {"id": r.pk, "code": r.code, "version": r.version, "segment": r.segment}
            for r in rule_sets
        ],
        "specifications": controlled(SpecificationRevision, "specification"),
        "methods": controlled(MethodRevision, "method"),
        "sampling_plans": controlled(SamplingPlanRevision, "plan"),
        "stability_protocols": [
            {"id": p.pk, "code": p.code, "version": p.version, "hash": p.content_digest}
            for p in protocols
        ],
    }
    return {
        key: sorted(rows, key=lambda e: (e["code"], e["version"])) for key, rows in found.items()
    }


def method_choices(at=None):
    """{code: title} of the methods with an approved version in force: the supported assays
    an acceptance can name."""
    from catalog.models import Method

    codes = {entry["code"] for entry in configuration_in_force(at)["methods"]}
    return dict(Method.objects.filter(code__in=codes).order_by("code").values_list("code", "title"))


def supported_versions(method_codes, configuration):
    """The version in force of each supported method, and the codes that have none."""
    in_force = {entry["code"]: entry for entry in configuration["methods"]}
    found = [in_force[code] for code in method_codes if code in in_force]
    missing = [code for code in method_codes if code not in in_force]
    return found, missing


def outside_assays(method_codes, configuration):
    """Codes of methods in force that are not among the supported assays."""
    return [e["code"] for e in configuration["methods"] if e["code"] not in method_codes]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def current_acceptance():
    return UseAcceptance.objects.filter(state=USE.ACCEPTED).first()


def acceptance_token(acceptance, configuration, release, current):
    """What the signer reviews before accepting: the configuration that will be frozen, the
    running release, the supported assays and the acceptance that would be superseded."""
    return hashlib.sha256(
        _canonical(
            {
                "configuration": configuration,
                "release": release,
                "methods": list(acceptance.method_codes),
                "supersedes": current.pk if current else None,
            }
        ).encode()
    ).hexdigest()


def configuration_changes(frozen, current):
    """Rows for each code whose version in force differs from the frozen configuration."""
    rows = []
    for key, label in KINDS:
        then = {entry["code"]: entry for entry in frozen.get(key, [])}
        now = {entry["code"]: entry for entry in current.get(key, [])}
        for code in sorted(set(then) | set(now)):
            before, after = then.get(code), now.get(code)
            if before and after and before["id"] == after["id"]:
                continue
            if before and after:
                change = "Another version in force"
            elif before:
                change = "No longer in force"
            else:
                change = "Newly in force"
            rows.append(
                {
                    "kind": label,
                    "code": code,
                    "accepted": f"v{before['version']}" if before else "",
                    "now": f"v{after['version']}" if after else "",
                    "change": change,
                }
            )
    return rows


# --- Acceptance for intended use -----------------------------------------------------------


def _owner(user, field):
    if user is None or not owner_candidates().filter(pk=user.pk).exists():
        raise ValidationError({field: "Choose an active account that holds a working role."})
    return user


def _supported(method_codes):
    if not isinstance(method_codes, (list, tuple)) or not method_codes:
        raise ValidationError({"method_codes": "Select at least one supported assay."})
    codes = []
    for code in method_codes:
        if not isinstance(code, str) or not code.strip():
            raise ValidationError({"method_codes": "Select at least one supported assay."})
        if code.strip() not in codes:
            codes.append(code.strip())
    if len(codes) > MAX_METHODS:
        raise ValidationError(
            {"method_codes": f"An acceptance names at most {MAX_METHODS} supported assays."}
        )
    unknown = [code for code in codes if code not in method_choices()]
    if unknown:
        raise ValidationError(
            {
                "method_codes": f"{', '.join(unknown)} has no approved version in force. "
                "Choose methods that are in force."
            }
        )
    return sorted(codes)


@transaction.atomic
def record_use_acceptance(
    *,
    actor,
    title,
    intended_use,
    method_codes,
    process_owner,
    system_owner,
    validation_ref,
    reason,
    exclusions="",
    other_responsibilities="",
    validation_url="",
    open_issues="",
):
    """Record the intended use for acceptance. It accepts nothing until a different quality
    person signs it."""
    require_role(actor, KEEPER)
    _require_reason(reason)
    lock_account(actor)
    acceptance = UseAcceptance(
        title=(title or "").strip(),
        intended_use=(intended_use or "").strip(),
        exclusions=(exclusions or "").strip(),
        method_codes=_supported(method_codes),
        process_owner=_owner(process_owner, "process_owner"),
        system_owner=_owner(system_owner, "system_owner"),
        other_responsibilities=(other_responsibilities or "").strip(),
        validation_ref=(validation_ref or "").strip(),
        validation_url=validation_url or "",
        open_issues=(open_issues or "").strip(),
        recorded_by=actor,
    )
    acceptance.full_clean()
    acceptance.save()
    record_event(
        actor=actor,
        action="use_acceptance.recorded",
        obj=acceptance,
        after=snapshot(acceptance),
        reason=reason,
    )
    return acceptance


SELF_ACCEPTANCE = "You cannot accept a validation record you recorded."


def use_denial(actor, acceptance, *, accept):
    """Why this person cannot accept or withdraw this record now, or "". Repeated under lock."""
    return use_state_refusal(acceptance) or use_person_refusal(actor, acceptance, accept=accept)


def use_state_refusal(acceptance):
    if acceptance.state != USE.RECORDED:
        return (
            f"This record is {acceptance.get_state_display().lower()}; only a record awaiting "
            "acceptance can be accepted or withdrawn."
        )
    return ""


def use_person_refusal(actor, acceptance, *, accept):
    if accept:
        if not has_role(actor, KEEPER):
            return "Only a quality person accepts the intended use."
        if acceptance.recorded_by_id == actor.pk:
            return SELF_ACCEPTANCE
        return ""
    if not has_role(actor, KEEPER):
        return "Only a quality person withdraws a record of the intended use."
    return ""


def accept_use(*, actor, pin, acceptance, expected_revision, reason, token):
    """Sign the acceptance: freeze the approved configuration in force and the running release,
    and supersede the acceptance accepted before, if any."""
    locked_rows = {}

    def prepare():
        # Every row, in id order: a second acceptance waits here until this one commits.
        locked_rows["all"] = list(UseAcceptance.objects.select_for_update().order_by("pk"))

    def apply(locked):
        if locked.state != USE.RECORDED:
            raise ValidationError("Only a record awaiting acceptance can be accepted.")
        if locked.recorded_by_id == actor.pk:
            raise PermissionDenied(SELF_ACCEPTANCE)
        moment = locked._signing_timestamp
        configuration = configuration_in_force(moment)
        supported, missing = supported_versions(locked.method_codes, configuration)
        if missing:
            raise ValidationError(
                f"{', '.join(missing)} no longer has an approved version in force. Withdraw "
                "this record and record the intended use again."
            )
        release = running_release()
        previous = [
            row for row in locked_rows["all"] if row.state == USE.ACCEPTED and row.pk != locked.pk
        ]
        current = previous[0] if previous else None
        if acceptance_token(locked, configuration, release, current) != token:
            raise ValidationError(
                "The approved configuration, the running release or the current acceptance "
                "changed since this page was opened. Review them again before signing."
            )
        frozen = {"schema": "oq.use-configuration/1", "at": moment.isoformat(), **configuration}
        frozen["supported_assays"] = supported
        for row in previous:
            before = snapshot(row)
            row.state = USE.SUPERSEDED
            row.superseded_at = moment
            row.superseded_by = locked
            row.revision += 1
            row.full_clean()
            row.save()
            record_event(
                actor=actor,
                action="use_acceptance.superseded",
                obj=row,
                before=before,
                after=snapshot(row),
                reason=f"Superseded by {locked.label}. {reason}",
            )
        locked.configuration = frozen
        locked.configuration_hash = hashlib.sha256(_canonical(frozen).encode()).hexdigest()
        locked.accepted_release = release
        locked.accepted_at = moment
        locked.state = USE.ACCEPTED

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=acceptance,
        expected_revision=expected_revision,
        meaning="accepted",
        reason=reason,
        permission=KEEPER,
        apply=apply,
        prepare=prepare,
    )


@transaction.atomic
def withdraw_use(*, actor, acceptance, expected_revision, reason):
    """Withdraw a record that will not be accepted; any quality person, its recorder included."""
    require_role(actor, KEEPER)
    _require_reason(reason)
    lock_account(actor)
    locked = UseAcceptance.objects.select_for_update().get(pk=acceptance.pk)
    if refusal := use_state_refusal(locked):
        raise ValidationError(refusal)
    if refusal := use_person_refusal(actor, locked, accept=False):
        raise PermissionDenied(refusal)
    if locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before withdrawing.")
    before = snapshot(locked)
    locked.state = USE.WITHDRAWN
    locked.withdrawn_at = timezone.now()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="use_acceptance.withdrawn",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


# --- Rehearsals ------------------------------------------------------------------------------


@transaction.atomic
def record_rehearsal(
    *,
    actor,
    kind,
    title,
    performed_on,
    release,
    environment,
    procedure_ref,
    acceptance_criteria,
    outcome,
    observations,
    reason,
    previous_release="",
    issues_and_actions="",
):
    """Record a rehearsal that took place. Its recorder attaches the evidence; a different
    quality person accepts it."""
    require_role(actor, *REHEARSAL_RECORDERS)
    _require_reason(reason)
    if performed_on and performed_on > timezone.localdate():
        raise ValidationError({"performed_on": "A rehearsal is recorded after it took place."})
    lock_account(actor)
    rehearsal = Rehearsal(
        kind=kind,
        title=(title or "").strip(),
        performed_on=performed_on,
        release=(release or "").strip(),
        previous_release=(previous_release or "").strip(),
        environment=(environment or "").strip(),
        procedure_ref=(procedure_ref or "").strip(),
        acceptance_criteria=(acceptance_criteria or "").strip(),
        outcome=outcome,
        observations=(observations or "").strip(),
        issues_and_actions=(issues_and_actions or "").strip(),
        recorded_by=actor,
    )
    if rehearsal.kind == Rehearsal.Kind.UPGRADE and not rehearsal.previous_release:
        raise ValidationError({"previous_release": "An upgrade names the release before it."})
    if rehearsal.outcome == Rehearsal.Outcome.NOT_MET and not rehearsal.issues_and_actions:
        raise ValidationError(
            {"issues_and_actions": "State what was not met and the actions taken or planned."}
        )
    rehearsal.full_clean()
    rehearsal.save()
    record_event(
        actor=actor,
        action="rehearsal.recorded",
        obj=rehearsal,
        after=snapshot(rehearsal),
        reason=reason,
    )
    return rehearsal


def file_denial(actor, rehearsal):
    if rehearsal.state != REHEARSAL.RECORDED:
        return "Evidence is attached only while the rehearsal awaits acceptance."
    if rehearsal.recorded_by_id != actor.pk:
        return "Only the person who recorded the rehearsal attaches its evidence."
    return ""


def attach_rehearsal_file(*, actor, rehearsal, upload, description):
    """Store an uploaded file of evidence unchanged, with its checksum. The rehearsal's revision
    advances, so a signing page opened before shows the record as changed."""
    from django.conf import settings

    from analytical.models import RawDataFile
    from analytical.rawdata import clean_filename, max_bytes
    from core.uploads import size_text

    require_role(actor, *REHEARSAL_RECORDERS)
    description = (description or "").strip()
    if not description:
        raise ValidationError("Describe what the file is.")
    limit_description = RehearsalFile._meta.get_field("description").max_length
    if len(description) > limit_description:
        raise ValidationError(f"The description is longer than {limit_description} characters.")
    filename = clean_filename(getattr(upload, "name", ""))
    limit = max_bytes()
    if upload.size > limit:
        raise ValidationError(f"The file is larger than the limit of {size_text(limit)}.")
    upload.seek(0)
    content = upload.read(limit + 1)
    if len(content) > limit:
        raise ValidationError(f"The file is larger than the limit of {size_text(limit)}.")
    if not content:
        raise ValidationError("The file is empty.")
    digest = hashlib.sha256(content).hexdigest()
    with transaction.atomic():
        lock_account(actor)
        locked = Rehearsal.objects.select_for_update().get(pk=rehearsal.pk)
        if refusal := file_denial(actor, locked):
            raise ValidationError(refusal)
        existing = RehearsalFile.objects.filter(rehearsal=locked)
        if existing.count() >= MAX_FILES:
            raise ValidationError(f"A rehearsal holds at most {MAX_FILES} files.")
        if existing.filter(sha256=digest).exists():
            raise ValidationError("This file content is already attached to this rehearsal.")
        ceiling = getattr(settings, "RAW_DATA_TOTAL_MAX_BYTES", 0)
        if ceiling:
            used = (RawDataFile.objects.aggregate(total=Sum("size"))["total"] or 0) + (
                RehearsalFile.objects.aggregate(total=Sum("size"))["total"] or 0
            )
            if used + len(content) > ceiling:
                raise ValidationError(
                    "This deployment has reached its storage limit for files. The file was "
                    "not stored."
                )
        stored = RehearsalFile.objects.create(
            rehearsal=locked,
            filename=filename,
            content_type=(getattr(upload, "content_type", "") or "")[:100],
            size=len(content),
            sha256=digest,
            content=content,
            description=description,
            uploaded_by=actor,
        )
        locked.revision += 1
        locked.save(update_fields=["revision"])
        record_event(
            actor=actor,
            action="rehearsal.file_attached",
            obj=locked,
            after={
                "file": stored.pk,
                "filename": filename,
                "size": stored.size,
                "sha256": digest,
                "description": description,
            },
            reason=description,
        )
        return stored


def rehearsal_denial(actor, rehearsal, *, accept):
    """Why this person cannot accept or withdraw this rehearsal now, or "". Repeated under lock."""
    return rehearsal_state_refusal(rehearsal, accept=accept) or rehearsal_person_refusal(
        actor, rehearsal, accept=accept
    )


def rehearsal_state_refusal(rehearsal, *, accept):
    if rehearsal.state != REHEARSAL.RECORDED:
        return (
            f"This rehearsal is {rehearsal.get_state_display().lower()}; only a rehearsal "
            "awaiting acceptance can be accepted or withdrawn."
        )
    if accept and not rehearsal.files.exists():
        return "Attach the evidence of the rehearsal before it is accepted."
    return ""


def rehearsal_person_refusal(actor, rehearsal, *, accept):
    if accept:
        if not has_role(actor, KEEPER):
            return "Only a quality person accepts a rehearsal."
        if rehearsal.recorded_by_id == actor.pk:
            return SELF_ACCEPTANCE
        return ""
    if rehearsal.recorded_by_id != actor.pk and not has_role(actor, KEEPER):
        return "Only the person who recorded the rehearsal or a quality person withdraws it."
    return ""


def accept_rehearsal(*, actor, pin, rehearsal, expected_revision, reason):
    """Sign the rehearsal record as a true account, with the outcome it states."""

    def apply(locked):
        if refusal := rehearsal_state_refusal(locked, accept=True):
            raise ValidationError(refusal)
        if refusal := rehearsal_person_refusal(actor, locked, accept=True):
            raise PermissionDenied(refusal)
        locked.state = REHEARSAL.ACCEPTED
        locked.accepted_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=rehearsal,
        expected_revision=expected_revision,
        meaning="accepted",
        reason=reason,
        permission=KEEPER,
        apply=apply,
    )


@transaction.atomic
def withdraw_rehearsal(*, actor, rehearsal, expected_revision, reason):
    require_role(actor, *REHEARSAL_RECORDERS)
    _require_reason(reason)
    lock_account(actor)
    locked = Rehearsal.objects.select_for_update().get(pk=rehearsal.pk)
    if refusal := rehearsal_state_refusal(locked, accept=False):
        raise ValidationError(refusal)
    if refusal := rehearsal_person_refusal(actor, locked, accept=False):
        raise PermissionDenied(refusal)
    if locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before withdrawing.")
    before = snapshot(locked)
    locked.state = REHEARSAL.WITHDRAWN
    locked.withdrawn_at = timezone.now()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="rehearsal.withdrawn",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


def rehearsal_status(rehearsal):
    """Display status: (label, tone)."""
    if rehearsal.state == REHEARSAL.WITHDRAWN:
        return "Withdrawn", "neutral"
    if rehearsal.state == REHEARSAL.RECORDED:
        return "Awaiting acceptance", "progress"
    if rehearsal.outcome == Rehearsal.Outcome.MET:
        return "Accepted: criteria met", "success"
    return "Accepted: criteria not met", "danger"


def use_status(acceptance):
    tones = {
        USE.RECORDED: "progress",
        USE.ACCEPTED: "success",
        USE.SUPERSEDED: "neutral",
        USE.WITHDRAWN: "neutral",
    }
    return acceptance.get_state_display(), tones[acceptance.state]
