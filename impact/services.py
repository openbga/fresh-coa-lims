"""Transitions of an impact assessment.

Quality starts an assessment, which adds the records found from its cause (``scope``); adds
what else it judges affected; records for each record whether it was affected, why, and the
follow-up; and may place a protective hold on an affected lot through it (``stability``'s own
hold, which blocks the lot's disposition or its certificates until it is released with an
independent signature). A different quality person, who started none of it, added and decided
no record of it, placed none of its holds and produced none of the data of its tests, concludes
it with a signature (meaning ``impact_assessed``) once every record has a decision and the cause
finds nothing that is not in the assessment; the conclusion freezes the records and decisions
(``oq.impact-assessment/1``). An assessment started in error is withdrawn with a signature,
once no hold placed through it is active.

Locks: the actor's account, then the assessment, then the record, then (placing a hold) the lot.
Every change to a record advances the assessment's revision, so a conclusion page opened before
it goes stale.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event
from core.services import require_role, sign_transition

from . import scope
from .models import Assessment, Item

QUALITY = "quality"
READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
EVIDENCE_SCHEMA = "oq.impact-assessment/1"
STATE = Assessment.State
CAUSE = Assessment.Cause
KIND = Item.Kind
DECISION = Item.Decision

NOT_OPEN = "This impact assessment is no longer open."
SELF_CONCLUSION = (
    "You started this assessment, added or decided one of its records, placed one of its holds "
    "or took part in the work it assesses. Another quality person concludes it."
)
SOURCES = {
    CAUSE.EQUIPMENT: "equipment",
    CAUSE.REAGENT: "reagent_lot",
    CAUSE.SUPPLIER: "supplier",
    CAUSE.CONTRACT: "contract_laboratory",
}


def _lock_account(actor):
    """The actor's account first, FOR NO KEY UPDATE, as every laboratory write and signature."""
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


def _lock(assessment, expected_revision=None):
    locked = Assessment.objects.select_for_update().get(pk=assessment.pk)
    if locked.state != STATE.OPEN:
        raise ValidationError(NOT_OPEN)
    if expected_revision is not None and locked.revision != expected_revision:
        raise ValidationError("The assessment changed since you opened it. Reload and review.")
    return locked


def _advance(assessment):
    assessment.revision += 1
    assessment.save(update_fields=["revision"])


def status_of(assessment):
    """(label, tone) of an assessment."""
    if assessment.state == STATE.CONCLUDED:
        return "Concluded", "success"
    if assessment.state == STATE.WITHDRAWN:
        return "Withdrawn", "neutral"
    return "Open", "progress"


def source_label(assessment):
    """The record named as the cause, as people name it, or "" for another cause."""
    if assessment.equipment_id:
        return f"{assessment.equipment.asset_id} · {assessment.equipment.description}"
    if assessment.reagent_lot_id:
        return f"{assessment.reagent_lot.identifier} · {assessment.reagent_lot.name}"
    if assessment.supplier_id:
        return f"{assessment.supplier.code} · {assessment.supplier.name}"
    if assessment.contract_laboratory_id:
        laboratory = assessment.contract_laboratory
        return f"{laboratory.code} · {laboratory.name}"
    return ""


def content(assessment):
    """The assessment as audit evidence."""
    return {
        "cause": assessment.cause,
        "source": source_label(assessment),
        "title": assessment.title,
        "description": assessment.description,
        "found_on": assessment.found_on.isoformat(),
        "period_from": assessment.period_from.isoformat(),
        "period_until": assessment.period_until.isoformat(),
        "quality_reference": assessment.quality_reference,
    }


def item_content(item):
    return {
        "assessment": item.assessment_id,
        "kind": item.kind,
        "record": item.target_id,
        "origin": item.origin,
        "basis": item.basis,
        "decision": item.decision,
        "rationale": item.rationale,
        "follow_up": item.follow_up,
        "follow_up_reference": item.follow_up_reference,
        "hold": item.hold_id,
    }


def _is_date(value):
    return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)


def _add_found(assessment, actor, found):
    """Add the found candidates as records; returns the records created."""
    created = [
        Item.objects.create(
            assessment=assessment,
            kind=candidate.kind,
            origin=Item.Origin.FOUND,
            basis=candidate.basis,
            added_by=actor,
            **{_field(candidate.kind): candidate.pk},
        )
        for candidate in found
    ]
    return created


def _field(kind):
    return {KIND.TEST: "test_id", KIND.LOT: "lot_id", KIND.STUDY: "study_id"}.get(kind, "report_id")


def _too_many(count, added=False):
    if count <= scope.MAX_RECORDS:
        return
    if added:
        raise ValidationError(
            f"An assessment covers at most {scope.MAX_RECORDS} records; assess the rest in "
            "another assessment."
        )
    raise ValidationError(
        f"The cause finds {count} records, more than the {scope.MAX_RECORDS} one assessment "
        "covers. Narrow the period of concern and assess the rest in another assessment."
    )


@transaction.atomic
def start(
    *,
    actor,
    cause,
    title,
    description,
    found_on,
    period_from,
    period_until,
    quality_reference="",
    equipment=None,
    reagent_lot=None,
    supplier=None,
    contract_laboratory=None,
):
    """Start an assessment and add the records found from its cause."""
    require_role(actor, QUALITY)
    if cause not in CAUSE.values:
        raise ValidationError({"cause": "Choose what failed."})
    named = {
        "equipment": equipment,
        "reagent_lot": reagent_lot,
        "supplier": supplier,
        "contract_laboratory": contract_laboratory,
    }
    errors = {}
    wanted = SOURCES.get(cause)
    for name, value in named.items():
        if name == wanted and value is None:
            errors[name] = "Choose the record that failed."
        elif name != wanted and value is not None:
            errors[name] = "Only the record of the cause chosen is named."
    if not (title or "").strip():
        errors["title"] = "Name the problem."
    if not (description or "").strip():
        errors["description"] = "Describe what happened and how it was found."
    today = timezone.localdate()
    if not _is_date(found_on):
        errors["found_on"] = "Enter a date."
    elif found_on > today:
        errors["found_on"] = "The date found cannot be in the future."
    if not _is_date(period_from):
        errors["period_from"] = "Enter a date."
    if not _is_date(period_until):
        errors["period_until"] = "Enter a date."
    elif period_until > today:
        errors["period_until"] = "The period of concern cannot end in the future."
    if _is_date(period_from) and _is_date(period_until) and period_from > period_until:
        errors["period_until"] = "The period of concern ends on or after the day it begins."
    if _is_date(period_from) and _is_date(found_on) and period_from > found_on:
        errors["period_from"] = "The period of concern begins on or before the date found."
    if errors:
        raise ValidationError(errors)
    _lock_account(actor)
    assessment = Assessment(
        cause=cause,
        title=title.strip(),
        description=description.strip(),
        found_on=found_on,
        period_from=period_from,
        period_until=period_until,
        quality_reference=(quality_reference or "").strip(),
        started_by=actor,
        **named,
    )
    assessment.full_clean()
    assessment.save()
    found = scope.missing(assessment, items=[])
    _too_many(len(found))
    record_event(
        actor=actor,
        action="impact.started",
        obj=assessment,
        after=content(assessment),
        reason=assessment.description,
    )
    if created := _add_found(assessment, actor, found):
        _record_found(actor, assessment, created)
    return assessment


def _record_found(actor, assessment, created):
    record_event(
        actor=actor,
        action="impact.records_found",
        obj=assessment,
        after={"records": [item_content(item) for item in created]},
        reason=f"{len(created)} record(s) found from the cause.",
    )


@transaction.atomic
def find_records(*, actor, assessment, expected_revision):
    """Add the records the cause finds now that are not in the assessment yet."""
    require_role(actor, QUALITY)
    _lock_account(actor)
    locked = _lock(assessment, expected_revision)
    items = list(locked.items.all())
    # No limit here: a record the cause finds must be in the assessment before it is concluded,
    # so finding it again is never refused (the limit applies at the start and to records added
    # by hand).
    found = scope.missing(locked, items)
    created = _add_found(locked, actor, found)
    if created:
        _record_found(actor, locked, created)
        _advance(locked)
    return created


def resolve(kind, identifier):
    """The record a person names when adding it: a test number (T-12), a lot number, a stability
    study identifier or a certificate number. ValidationError when there is none."""
    from analytical.models import AnalyticalTest
    from quality.models import Lot
    from reporting.models import Report
    from stability.models import Study

    text = (identifier or "").strip()
    if not text:
        raise ValidationError({"identifier": "Name the record."})
    found = None
    if kind == KIND.TEST:
        digits = text[2:] if text.upper().startswith("T-") else text
        if scope.CANONICAL_ID.fullmatch(digits):
            found = AnalyticalTest.objects.filter(pk=int(digits)).first()
    elif kind == KIND.LOT:
        found = Lot.objects.filter(number=text).first()
    elif kind == KIND.STUDY:
        found = Study.objects.filter(identifier=text).first()
    elif kind == KIND.CERTIFICATE:
        found = Report.objects.filter(number=text, version_count__gt=0).first()
    else:
        raise ValidationError({"kind": "Choose the kind of record."})
    if found is None:
        noun = {
            KIND.TEST: "test",
            KIND.LOT: "lot",
            KIND.STUDY: "stability study",
            KIND.CERTIFICATE: "issued certificate",
        }[kind]
        raise ValidationError({"identifier": f"No {noun} is called {text}."})
    return found


@transaction.atomic
def add_record(*, actor, assessment, expected_revision, kind, identifier, reason):
    """Add a record that quality judges possibly affected, with the reason."""
    require_role(actor, QUALITY)
    if not (reason or "").strip():
        raise ValidationError({"reason": "Say why the record may be affected."})
    target = resolve(kind, identifier)
    _lock_account(actor)
    locked = _lock(assessment, expected_revision)
    field = _field(kind)
    if locked.items.filter(**{field: target.pk}).exists():
        raise ValidationError({"identifier": "This record is already in the assessment."})
    _too_many(locked.items.count() + 1, added=True)
    item = Item.objects.create(
        assessment=locked,
        kind=kind,
        origin=Item.Origin.ADDED,
        basis=reason.strip(),
        added_by=actor,
        **{field: target.pk},
    )
    record_event(
        actor=actor,
        action="impact.record_added",
        obj=item,
        after=item_content(item),
        reason=item.basis,
    )
    _advance(locked)
    return item


def _lock_item(item, expected_revision):
    """Lock the assessment, then the record, and check the record's revision."""
    _lock(item.assessment)
    locked = Item.objects.select_for_update().select_related("assessment").get(pk=item.pk)
    if locked.revision != expected_revision:
        raise ValidationError("The record changed since you opened it. Reload and review.")
    return locked


@transaction.atomic
def decide(
    *, actor, item, expected_revision, decision, rationale, follow_up="", follow_up_reference=""
):
    """Record whether the record was affected, why, and the follow-up. A decision may be
    changed while the assessment is open; the audit trail keeps every earlier one."""
    require_role(actor, QUALITY)
    errors = {}
    if decision not in DECISION.values:
        errors["decision"] = "Choose whether the record was affected."
    if not (rationale or "").strip():
        errors["rationale"] = "Give the reason for the decision."
    if decision == DECISION.AFFECTED and not (follow_up or "").strip():
        errors["follow_up"] = "Say what is done about it."
    if errors:
        raise ValidationError(errors)
    _lock_account(actor)
    locked = _lock_item(item, expected_revision)
    before = item_content(locked)
    locked.decision = decision
    locked.rationale = rationale.strip()
    locked.follow_up = (follow_up or "").strip()
    locked.follow_up_reference = (follow_up_reference or "").strip()
    locked.decided_by = actor
    locked.decided_at = timezone.now()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="impact.record_decided",
        obj=locked,
        before=before,
        after=item_content(locked),
        reason=locked.rationale,
    )
    _advance(locked.assessment)
    return locked


def hold_refusal(item):
    """Why a hold cannot be placed through this record now, or ""."""
    if item.kind != KIND.LOT:
        return "A hold is placed on a lot."
    if item.hold_id:
        return f"{item.hold.identifier} was placed through this assessment."
    if item.lot.state == "cancelled":
        return "The lot was cancelled; it takes no hold."
    return ""


@transaction.atomic
def place_hold(*, actor, item, expected_revision, reason):
    """Place a protective quality hold on the record's lot, referenced to the assessment."""
    from stability import services as stability

    require_role(actor, QUALITY)
    if not (reason or "").strip():
        raise ValidationError({"reason": "Say why the lot is held."})
    _lock_account(actor)
    locked = _lock_item(item, expected_revision)
    if refused := hold_refusal(locked):
        raise ValidationError(refused)
    assessment = locked.assessment
    reference = assessment.label
    if assessment.quality_reference:
        reference = f"{reference} · {assessment.quality_reference}"[:200]
    hold = stability.place_hold(
        actor=actor, lot=locked.lot, kind="quality", reason=reason, reference=reference
    )
    before = item_content(locked)
    locked.hold = hold
    locked.revision += 1
    locked.save(update_fields=["hold", "revision"])
    record_event(
        actor=actor,
        action="impact.hold_placed",
        obj=locked,
        before=before,
        after=item_content(locked),
        reason=reason,
    )
    _advance(assessment)
    return hold


# Conclusion ------------------------------------------------------------------------------------


# The audit actions that make their actor an author of the assessment. A decision changed later
# leaves its earlier decider an author: every decision ever recorded is read from the trail.
AUTHORED = ("impact.record_added", "impact.record_decided", "impact.hold_placed")


def author_ids(assessment, items=None):
    """Who may not conclude the assessment: whoever started it, added a record to it by hand,
    decided one of its records at any time or placed one of its holds; whoever used the failed
    equipment or reagent lot in the period, or recorded a contract laboratory's reports in it;
    and whoever produced or investigated the work assessed: the data and investigation authors
    of its tests and of every test of its lots (the independence the lot's disposition needs).
    A record found from the cause is not authored by whoever found it."""
    from analytical.gates import investigation_author_ids, tests_author_ids
    from analytical.models import AnalyticalTest, Investigation
    from core.models import AuditEvent

    items = list(assessment.items.select_related("hold")) if items is None else items
    ids = {assessment.started_by_id}
    for item in items:
        if item.origin == Item.Origin.ADDED:
            ids.add(item.added_by_id)
        if item.decided_by_id:
            ids.add(item.decided_by_id)
        if item.hold_id:
            ids.add(item.hold.placed_by_id)
    ids.update(
        AuditEvent.objects.filter(
            object_type=Item._meta.label_lower,
            object_id__in=[str(item.pk) for item in items],
            action__in=AUTHORED,
        ).values_list("actor_id", flat=True)
    )
    ids.update(scope.users_of_cause(assessment))
    test_ids = [i.test_id for i in items if i.test_id]
    lot_ids = [i.lot_id for i in items if i.lot_id]
    tests = AnalyticalTest.objects.filter(pk__in=test_ids) | AnalyticalTest.objects.filter(
        lot_id__in=lot_ids
    )
    investigations = Investigation.objects.filter(
        test_id__in=test_ids
    ) | Investigation.objects.filter(lot_id__in=lot_ids)
    return ids | tests_author_ids(tests) | investigation_author_ids(investigations)


def record_label(item):
    """The record as people name it."""
    target = item.target
    if item.kind == KIND.TEST:
        return f"{target.label} · {target.test_code} · lot {target.source_lot.number}"
    if item.kind == KIND.LOT:
        return f"{target.number} · {target.material}"
    if item.kind == KIND.STUDY:
        return f"{target.identifier} · lot {target.lot.number}"
    return f"{target.number} · lot {target.lot.number}"


def record_status(item):
    """(label, tone) of the record now."""
    target = item.target
    if item.kind == KIND.TEST:
        label = target.get_state_display()
        if target.conforms is False:
            return f"{label} · out of specification", "danger"
        return label, "neutral"
    if item.kind == KIND.LOT:
        tones = {"released": "success", "rejected": "danger", "quarantine": "warning"}
        return target.get_state_display(), tones.get(target.state, "neutral")
    if item.kind == KIND.STUDY:
        return target.get_state_display(), "neutral"
    return target.status_label, target.tone


def review(assessment):
    """What the conclusion page shows and the signature rechecks: the records, those without a
    decision, those the cause finds that are not in the assessment yet."""
    items = list(
        assessment.items.select_related(
            "test__lot",
            "test__pull__study__lot",
            "test__reassessment__lot",
            "lot",
            "study__lot",
            "report__lot",
            "hold",
            "decided_by",
        ).order_by("pk")
    )
    undecided = [item for item in items if not item.decision]
    # A closed assessment takes no more records: the cause is not searched again.
    found = scope.missing(assessment, items) if assessment.state == STATE.OPEN else []
    blockers = []
    if undecided:
        blockers.append(f"{len(undecided)} record(s) have no decision.")
    if found:
        blockers.append(
            f"The cause finds {len(found)} record(s) that are not in the assessment: find "
            "affected records again."
        )
    return items, undecided, found, blockers


def _frozen(assessment, items, authors):
    rows = []
    for item in items:
        label, _ = record_status(item)
        rows.append(
            {
                "kind": item.kind,
                "record": item.target_id,
                "label": record_label(item),
                "status": label,
                "origin": item.origin,
                "basis": item.basis,
                "decision": item.decision,
                "rationale": item.rationale,
                "follow_up": item.follow_up,
                "follow_up_reference": item.follow_up_reference,
                "decided_by": item.decided_by_id,
                "decided_at": item.decided_at.isoformat() if item.decided_at else None,
                "hold": ({"id": item.hold_id, "state": item.hold.state} if item.hold_id else None),
            }
        )
    return {
        "schema": EVIDENCE_SCHEMA,
        "assessment": assessment.label,
        **content(assessment),
        "records": rows,
        "affected": sum(1 for item in items if item.decision == DECISION.AFFECTED),
        "not_affected": sum(1 for item in items if item.decision == DECISION.NOT_AFFECTED),
        "author_ids": sorted(authors),
    }


def conclusion_refusal(assessment, actor, found=None):
    """Why ``actor`` cannot conclude the assessment now, or ""."""
    if assessment.state != STATE.OPEN:
        return NOT_OPEN
    items, _, _, blockers = found or review(assessment)
    if actor.pk in author_ids(assessment, items):
        return SELF_CONCLUSION
    return " ".join(blockers)


@sensitive_variables("pin")
def conclude(*, actor, pin, assessment, expected_revision, reason):
    """Conclude the assessment with a signature on the records and decisions shown."""

    def apply(locked):
        if locked.state != STATE.OPEN:
            raise ValidationError(NOT_OPEN)
        # Every change to a record advanced the revision under this lock, so what is read here
        # is what the signer saw; the cause is read again for what was recorded since.
        found = review(locked)
        items, _, _, blockers = found
        if actor.pk in author_ids(locked, items):
            raise PermissionDenied(SELF_CONCLUSION)
        if blockers:
            raise ValidationError(" ".join(blockers))
        locked.evidence = _frozen(locked, items, author_ids(locked, items))
        locked.state = STATE.CONCLUDED
        locked.decided_at = locked._signing_timestamp
        locked.decision_reason = reason.strip()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=assessment,
        expected_revision=expected_revision,
        meaning="impact_assessed",
        reason=reason,
        permission=QUALITY,
        apply=apply,
    )


def active_holds(assessment):
    from stability.models import Hold

    return Hold.objects.filter(
        pk__in=assessment.items.exclude(hold=None).values("hold_id"), state=Hold.State.ACTIVE
    )


def withdrawal_refusal(assessment):
    if assessment.state != STATE.OPEN:
        return NOT_OPEN
    held = list(active_holds(assessment).order_by("pk"))
    if held:
        names = ", ".join(hold.identifier for hold in held)
        return (
            f"A hold placed through this assessment is active ({names}). Release it with its "
            "signature first, or conclude the assessment."
        )
    return ""


@sensitive_variables("pin")
def withdraw(*, actor, pin, assessment, expected_revision, reason):
    """Withdraw an assessment started in error, with a signature; its records are kept."""

    def apply(locked):
        if refused := withdrawal_refusal(locked):
            raise ValidationError(refused)
        locked.state = STATE.WITHDRAWN
        locked.decided_at = locked._signing_timestamp
        locked.decision_reason = reason.strip()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=assessment,
        expected_revision=expected_revision,
        meaning="withdrawn",
        reason=reason,
        permission=QUALITY,
        apply=apply,
    )


def for_lot(lot):
    """The assessments that name the lot, one of its tests (its own, or of a reassessment of
    it), a stability study of it or one of its certificates, each with the lot's own record in
    it when there is one: [(assessment, item or None)], newest first."""
    from django.db.models import Q

    items = Item.objects.filter(
        Q(lot_id=lot.pk)
        | Q(test__lot_id=lot.pk)
        | Q(test__reassessment__lot_id=lot.pk)
        | Q(test__pull__study__lot_id=lot.pk)
        | Q(study__lot_id=lot.pk)
        | Q(report__lot_id=lot.pk)
    ).select_related("assessment", "hold")
    found = {}
    for item in items.order_by("-assessment_id", "pk"):
        entry = found.setdefault(item.assessment_id, [item.assessment, None])
        if item.kind == KIND.LOT:
            entry[1] = item
    return [tuple(entry) for entry in found.values()]
