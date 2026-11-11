"""CoA issue, amendment and retrieval.

Signed transitions use the shared `sign_transition` contract: the report head is locked, the lot
is locked and the evidence recollected and compared with what the signer reviewed, the PDF is
rendered inside the same transaction, and signature, audit event, version row and head update
commit together. Any failure, including a render failure, leaves no issued version.
"""

import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.audit import record_event, snapshot
from core.models import ElectronicSignature
from core.services import require_role, sign_transition, verify_pin
from core.session_control import signing_context
from quality.models import Lot

from . import evidence as ev
from .models import Report, ReportVersion
from .render import RenderError, render_certificate

READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
ISSUE_ROLE = "quality"
HISTORY_ROLES = ("quality", "auditor", "admin")


def require_reader(actor):
    require_role(actor, *READ_ROLES)


def display_name(user):
    return user.get_full_name() or user.get_username()


def preview(lot):
    """Current evidence, its hash and any blockers (no mutation, no authorization)."""
    evidence = ev.collect_evidence(lot)
    return evidence, ev.canonical_hash(evidence), ev.blockers(evidence)


def lock_account(actor):
    """The actor's account row first, FOR NO KEY UPDATE: it serializes with the same person's
    signing (which locks the account FOR UPDATE before any record) without blocking the
    foreign-key checks that rows referencing the account take at commit."""
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


@transaction.atomic
def open_report(*, actor, lot, recipient):
    """Create (or fetch) the CoA series head for a released lot and recipient."""
    require_role(actor, ISSUE_ROLE)
    recipient = recipient.strip()
    lock_account(actor)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    if locked.state != "released":
        raise ValidationError("A certificate needs a lot with a signed QC disposition.")
    existing = Report.objects.filter(lot=locked, recipient=recipient).first()
    if existing:
        return existing
    sequence = (Report.objects.filter(lot=locked).count()) + 1
    report = Report.objects.create(
        lot=locked,
        recipient=recipient,
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


def _transition(*, actor, pin, report, kind, expected_version, evidence_hash, reason, remarks):
    meaning = "issued" if kind == "issue" else "amended"
    reason = reason.strip()
    remarks = remarks.strip()
    if not reason:
        raise ValidationError("A reason is required.")

    def apply(locked):
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
        problems = ev.blockers(evidence)
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


def _issue_preflight(*, actor, pin, lot, evidence_hash, reason):
    """Every refusal that can be decided before a series head exists, so a refused issue does
    not leave a numbered head behind. All of it is rechecked under lock when signing; a failed
    PIN is recorded by `verify_pin` in its own transaction, as for any signing."""
    require_role(actor, ISSUE_ROLE)
    if not reason.strip():
        raise ValidationError("A reason is required.")
    signing_context(actor)
    evidence, current_hash, problems = preview(lot)
    if current_hash != evidence_hash:
        raise ValidationError("The evidence changed since you reviewed it. Review again.")
    if problems:
        raise ValidationError(["Certificate cannot be issued:", *problems])
    if ev.independence_conflict(evidence, actor):
        raise PermissionDenied("You cannot issue a certificate for records you authored.")
    verify_pin(actor, pin)


def issue_report(*, actor, pin, lot, recipient, evidence_hash, reason, remarks=""):
    """Sign and issue version 1 for a released lot (creating the series head if needed)."""
    _issue_preflight(actor=actor, pin=pin, lot=lot, evidence_hash=evidence_hash, reason=reason)
    report = open_report(actor=actor, lot=lot, recipient=recipient)
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
