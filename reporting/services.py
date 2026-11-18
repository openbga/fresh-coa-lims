"""CoA issue, amendment, withdrawal and retrieval.

Signed transitions use the shared `sign_transition` contract: the report head is locked, the lot
is locked and the evidence recollected and compared with what the signer reviewed, the PDF is
rendered inside the same transaction, and signature, audit event, version row and head update
commit together. Any failure, including a render failure, leaves no issued version.

A withdrawal is signed on the head too (meaning ``withdrawn``) and is final: the certificate
stops being valid, every issued version and its PDF bytes stay exactly as issued and can still
be read, and it is never amended again. A later certificate for the same lot and recipient is a
new series with its own number. That each recipient was told is recorded afterwards as
append-only `RecipientNotification` evidence, which leaves the head's signed revision as it is.
"""

import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event, snapshot
from core.models import ElectronicSignature
from core.services import require_role, sign_transition, verify_pin
from core.session_control import signing_context
from quality.models import Lot

from . import evidence as ev
from .models import RecipientNotification, Report, ReportVersion
from .render import RenderError, render_certificate

READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
ISSUE_ROLE = "quality"
HISTORY_ROLES = ("quality", "auditor", "admin")
WITHDRAWN = (
    "This certificate was withdrawn; it is not amended. A new certificate for the lot is issued "
    "as a new numbered certificate."
)
NOT_ISSUED = "Only an issued certificate can be withdrawn."
ALREADY_WITHDRAWN = "This certificate is already withdrawn."
NOT_WITHDRAWN = "A recipient notification is recorded only for a withdrawn certificate."


def require_reader(actor):
    require_role(actor, *READ_ROLES)


def scope_label(scope):
    """How a certificate's scope reads in a sentence."""
    return f"for scope {scope}" if scope else "for all of the lot's requirements"


def display_name(user):
    return user.get_full_name() or user.get_username()


def preview(lot, scope=""):
    """Current evidence, its hash and any blockers (no mutation, no authorization); with a
    scope, also what stops a certificate for that scope of the lot."""
    evidence = ev.collect_evidence(lot)
    return evidence, ev.canonical_hash(evidence), ev.blockers(evidence, scope)


def lock_account(actor):
    """The actor's account row first, FOR NO KEY UPDATE: it serializes with the same person's
    signing (which locks the account FOR UPDATE before any record) without blocking the
    foreign-key checks that rows referencing the account take at commit."""
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


@transaction.atomic
def open_report(*, actor, lot, recipient, scope=""):
    """Create (or fetch) the CoA series head for a released lot and recipient, for all of the
    lot's requirements or for one scope of the lot. The scope is fixed with the head."""
    require_role(actor, ISSUE_ROLE)
    recipient = recipient.strip()
    scope = (scope or "").strip()
    lock_account(actor)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    if locked.state != "released":
        raise ValidationError("A certificate needs a lot with a signed QC disposition.")
    # The current series for this recipient; a withdrawn one is never reused.
    existing = (
        Report.objects.filter(lot=locked, recipient=recipient).exclude(state="withdrawn").first()
    )
    if existing:
        if existing.scope != scope:
            raise ValidationError(
                f"{existing.number} is already open for this recipient, "
                f"{scope_label(existing.scope)}. Amend it, or withdraw it before issuing a "
                f"certificate {scope_label(scope)}."
            )
        return existing
    sequence = (Report.objects.filter(lot=locked).count()) + 1
    report = Report.objects.create(
        lot=locked,
        recipient=recipient,
        scope=scope,
        sequence=sequence,
        number=f"CoA-{locked.number}-{sequence}",
        created_by=actor,
    )
    record_event(
        actor=actor,
        action="report.opened",
        obj=report,
        after=snapshot(report),
        reason="Certificate record opened for signed issuance.",
    )
    return report


@sensitive_variables("pin")
def _transition(*, actor, pin, report, kind, expected_version, evidence_hash, reason, remarks):
    meaning = "issued" if kind == "issue" else "amended"
    reason = reason.strip()
    remarks = remarks.strip()
    if not reason:
        raise ValidationError("A reason is required.")

    def apply(locked):
        if locked.state == "withdrawn":
            raise ValidationError(WITHDRAWN)
        if kind == "issue" and locked.version_count:
            raise ValidationError("This certificate is already issued; amend it instead.")
        if locked.version_count != expected_version:
            raise ValidationError("The certificate changed since you reviewed it. Review again.")
        if kind == "amendment" and not locked.version_count:
            raise ValidationError("Only an issued certificate can be amended.")
        lot = Lot.objects.select_for_update().get(pk=locked.lot_id)
        evidence = ev.collect_evidence(lot)
        current_hash = ev.canonical_hash(evidence)
        if current_hash != evidence_hash:
            raise ValidationError("The evidence changed since you reviewed it. Review again.")
        problems = ev.blockers(evidence, locked.scope)
        if problems:
            raise ValidationError(["Certificate cannot be issued:", *problems])
        if ev.independence_conflict(evidence, actor):
            raise PermissionDenied("You cannot issue a certificate for records you authored.")
        previous = locked.versions.order_by("-number").first()
        # The exact server time that sign_transition persists as the signature's signed_at.
        issued_at = locked._signing_timestamp
        number = locked.version_count + 1
        snap = {
            **evidence,
            "evidence_hash": current_hash,
            "report": {
                "number": locked.number,
                "version": number,
                "kind": kind,
                "recipient": locked.recipient,
                "scope": locked.scope,
                "remarks": remarks,
                "reason": reason,
                "amends_version": previous.number if previous else None,
                "issued_by": display_name(actor),
                "issued_by_id": actor.pk,
                "issued_at": ev.iso(issued_at),
                "lot_revision": lot.revision,
            },
        }
        try:
            data = render_certificate(
                snap, synthetic_notice=getattr(settings, "REPORT_SYNTHETIC_DATA_NOTICE", True)
            )
        except RenderError as exc:
            raise ValidationError(f"The certificate could not be rendered: {exc}") from exc
        ReportVersion.objects.create(
            report=locked,
            number=number,
            kind=kind,
            supersedes=previous,
            reason=reason,
            remarks=remarks,
            issued_by=actor,
            issued_at=issued_at,
            lot_revision=lot.revision,
            report_revision=locked.revision + 1,
            evidence_hash=current_hash,
            snapshot=snap,
            snapshot_hash=ev.canonical_hash(snap),
            pdf=data,
            pdf_sha256=hashlib.sha256(data).hexdigest(),
            pdf_size=len(data),
        )
        locked.state = "issued"
        locked.version_count = number
        locked.current_snapshot_hash = ev.canonical_hash(snap)
        locked.current_pdf_sha256 = hashlib.sha256(data).hexdigest()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=report,
        expected_revision=report.revision,
        meaning=meaning,
        reason=reason,
        permission=ISSUE_ROLE,
        apply=apply,
    )


@sensitive_variables("pin")
def _issue_preflight(*, actor, pin, lot, evidence_hash, reason, scope):
    """Every refusal that can be decided before a series head exists, so a refused issue does
    not leave a numbered head behind. All of it is rechecked under lock when signing; a failed
    PIN is recorded by `verify_pin` in its own transaction, as for any signing."""
    require_role(actor, ISSUE_ROLE)
    if not reason.strip():
        raise ValidationError("A reason is required.")
    signing_context(actor)
    evidence, current_hash, problems = preview(lot, scope)
    if current_hash != evidence_hash:
        raise ValidationError("The evidence changed since you reviewed it. Review again.")
    if problems:
        raise ValidationError(["Certificate cannot be issued:", *problems])
    if ev.independence_conflict(evidence, actor):
        raise PermissionDenied("You cannot issue a certificate for records you authored.")
    verify_pin(actor, pin)


@sensitive_variables("pin")
def issue_report(*, actor, pin, lot, recipient, evidence_hash, reason, remarks="", scope=""):
    """Sign and issue version 1 for a released lot (creating the series head if needed), for
    all of the lot's requirements or, with ``scope``, for one scope of the lot: its
    specification's tests and limits, refused unless every result meets them."""
    scope = (scope or "").strip()
    _issue_preflight(
        actor=actor, pin=pin, lot=lot, evidence_hash=evidence_hash, reason=reason, scope=scope
    )
    report = open_report(actor=actor, lot=lot, recipient=recipient, scope=scope)
    return _transition(
        actor=actor,
        pin=pin,
        report=report,
        kind="issue",
        expected_version=0,
        evidence_hash=evidence_hash,
        reason=reason,
        remarks=remarks,
    )


@sensitive_variables("pin")
def amend_report(*, actor, pin, report, expected_version, evidence_hash, reason, remarks=""):
    """Sign an amendment: a new version that supersedes, and never alters, the issued one."""
    return _transition(
        actor=actor,
        pin=pin,
        report=report,
        kind="amendment",
        expected_version=expected_version,
        evidence_hash=evidence_hash,
        reason=reason,
        remarks=remarks,
    )


def withdraw_refusal(report):
    """Why this certificate cannot be withdrawn now, or "" (rechecked under lock when signing)."""
    if report.state == "withdrawn":
        return ALREADY_WITHDRAWN
    if report.state != "issued":
        return NOT_ISSUED
    return ""


@sensitive_variables("pin")
def withdraw_report(*, actor, pin, report, expected_revision, reason, reference=""):
    """Sign the withdrawal of an issued certificate (meaning ``withdrawn``): final, and every
    issued version stays as issued. There is no independence rule: withdrawal protects the
    recipient, so the quality person who issued the certificate may withdraw it."""
    reason = reason.strip()
    reference = reference.strip()

    def apply(locked):
        if refused := withdraw_refusal(locked):
            raise ValidationError(refused)
        locked.state = "withdrawn"
        locked.withdrawn_at = locked._signing_timestamp
        locked.withdrawal_reason = reason
        locked.withdrawal_reference = reference

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=report,
        expected_revision=expected_revision,
        meaning="withdrawn",
        reason=reason,
        permission=ISSUE_ROLE,
        apply=apply,
    )


def withdrawal_signature(report):
    """The electronic signature that withdrew this certificate, or None."""
    if report.state != "withdrawn":
        return None
    return ElectronicSignature.objects.filter(
        object_type="reporting.report", object_id=str(report.pk), meaning="withdrawn"
    ).first()


@transaction.atomic
def record_notification(*, actor, report, recipient, notified_on, means, evidence_ref, note=""):
    """Record that a recipient was told that the certificate is withdrawn. Append-only
    evidence: the certificate's head and its signed revision do not change."""
    require_role(actor, ISSUE_ROLE)
    recipient = (recipient or "").strip()
    evidence_ref = (evidence_ref or "").strip()
    note = (note or "").strip()
    lock_account(actor)
    locked = Report.objects.select_for_update().get(pk=report.pk)
    if locked.state != "withdrawn":
        raise ValidationError(NOT_WITHDRAWN)
    errors = {}
    if not recipient:
        errors["recipient"] = "Name the recipient who was notified."
    elif len(recipient) > RecipientNotification._meta.get_field("recipient").max_length:
        errors["recipient"] = "Ensure this value has at most 160 characters."
    if means not in RecipientNotification.Means.values:
        errors["means"] = "Choose how the recipient was notified."
    elif means == RecipientNotification.Means.OTHER and not note:
        errors["note"] = "Describe how the recipient was notified."
    if not evidence_ref:
        errors["evidence_ref"] = "Say where the notice and any acknowledgement are kept."
    elif len(evidence_ref) > RecipientNotification._meta.get_field("evidence_ref").max_length:
        errors["evidence_ref"] = "Ensure this value has at most 200 characters."
    withdrawn_on = timezone.localdate(locked.withdrawn_at)
    if notified_on is None:
        errors["notified_on"] = "Give the date the recipient was notified."
    elif notified_on > timezone.localdate():
        errors["notified_on"] = "The date notified cannot be in the future."
    elif notified_on < withdrawn_on:
        errors["notified_on"] = (
            f"The certificate was withdrawn on {withdrawn_on.isoformat()}; the date notified "
            "cannot be earlier."
        )
    if errors:
        raise ValidationError(errors)
    notification = RecipientNotification.objects.create(
        report=locked,
        recipient=recipient,
        notified_on=notified_on,
        means=means,
        evidence_ref=evidence_ref,
        note=note,
        recorded_by=actor,
    )
    record_event(
        actor=actor,
        action="report.recipient_notified",
        obj=locked,
        after={"notification": notification.pk, **snapshot(notification)},
        reason=f"{recipient} notified of the withdrawal ({notification.get_means_display()}).",
    )
    return notification


def signature_for(version):
    """The electronic signature that issued this version."""
    return ElectronicSignature.objects.filter(
        object_type="reporting.report",
        object_id=str(version.report_id),
        revision=version.report_revision,
    ).first()


def read_pdf(*, actor, version):
    """Authorized retrieval of the stored bytes, checksum-verified and audited."""
    require_reader(actor)
    data = bytes(version.pdf)
    if hashlib.sha256(data).hexdigest() != version.pdf_sha256 or len(data) != version.pdf_size:
        raise ValidationError("The stored certificate failed its integrity check.")
    with transaction.atomic():
        record_event(
            actor=actor,
            action="report.downloaded",
            obj=version.report,
            after={"version": version.number, "pdf_sha256": version.pdf_sha256},
            reason="Authorized retrieval of the issued certificate.",
        )
    return data
