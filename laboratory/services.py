"""Laboratory-operations transitions. Every mutation authorizes on the server, locks and rechecks
current state, and commits state, attributed audit event (and signature when signed) together.

Independence: the person who recorded evidence, the person it is about, and the signer must be
different individuals, whatever roles they hold.

Lock order: every unsigned write locks its actor's account first (`lock_account`), as signing
does; then records, with reagent lineages newest first, as releasing a lot does.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q, prefetch_related_objects
from django.utils import timezone

from core.audit import record_event, snapshot
from core.services import require_role, sign_transition

from .eligibility import (
    affected_uses,
    check_use,
    equipment_queryset,
    equipment_status,
    latest_calibration,
    qualification_valid,
    reagent_eligibility,
    reagent_lineage,
    reagent_status,
    unassessed_failures,
)
from .models import Calibration, Equipment, Qualification, ReagentLot, ResourceUse

RECORDERS = ("analyst", "quality")
ANY_SCIENTIFIC = ("analyst", "reviewer", "quality")


class UseBlocked(ValidationError):
    """Raised when eligibility gates refuse work; carries the findings."""

    def __init__(self, findings):
        self.findings = findings
        messages = [f"{f.subject}: {reason}" for f in findings if not f.ok for reason in f.reasons]
        super().__init__(messages)


def lock_account(actor):
    """Lock the actor's account row first in every unsigned write, FOR NO KEY UPDATE.

    Signing locks the signer's account (FOR UPDATE) before any record, and this lock conflicts
    with it, so the same person's write and signature serialize before either holds a record.
    It does not conflict with the FOR KEY SHARE that foreign-key checks on the account take at
    commit, so rows referencing the account never wait on it.
    """
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)


def _lock(model, obj):
    return model.objects.select_for_update().get(pk=obj.pk)


def _lock_lineage(reagents):
    """Lock the reagents' whole source chains, newest first, so a rejection of any ancestor
    serializes with use and release. Releasing a lot locks it and then its sources (always
    older), so every lineage lock follows that order. Accepts lots or plain ids."""
    ids, frontier = set(), {getattr(r, "pk", r) for r in reagents}
    while frontier:
        ids |= frontier
        frontier = (
            set(
                ReagentLot.objects.filter(pk__in=frontier, parent__isnull=False)
                .values_list("parent_id", flat=True)
                .distinct()
            )
            - ids
        )
    list(ReagentLot.objects.select_for_update(of=("self",)).filter(pk__in=ids).order_by("-pk"))


def _bump(obj, **changes):
    for name, value in changes.items():
        setattr(obj, name, value)
    obj.revision += 1
    obj.full_clean()
    obj.save()
    return obj


# --- Equipment -------------------------------------------------------------------------------


@transaction.atomic
def register_equipment(*, actor, reason, **values):
    require_role(actor, *RECORDERS)
    lock_account(actor)
    equipment = Equipment(created_by=actor, **values)
    equipment.full_clean()
    equipment.save()
    record_event(
        actor=actor,
        action="equipment.registered",
        obj=equipment,
        after=snapshot(equipment),
        reason=reason,
    )
    return equipment


def _set_state(equipment, actor, state, action, reason):
    before = snapshot(equipment)
    _bump(
        equipment,
        state=state,
        status_changed_by=actor,
        status_changed_at=timezone.now(),
    )
    record_event(
        actor=actor,
        action=action,
        obj=equipment,
        before=before,
        after=snapshot(equipment),
        reason=reason,
    )


@transaction.atomic
def take_out_of_service(*, actor, equipment, reason):
    """Protective, so any scientific role may do it; returning to service needs a signature."""
    require_role(actor, *ANY_SCIENTIFIC)
    if not reason.strip():
        raise ValidationError("State why the equipment is unfit for use.")
    lock_account(actor)
    equipment = _lock(Equipment, equipment)
    if equipment.state == Equipment.State.OUT_OF_SERVICE:
        raise ValidationError("Equipment is already out of service.")
    _set_state(equipment, actor, Equipment.State.OUT_OF_SERVICE, "equipment.out_of_service", reason)
    return equipment


def impact_scope(equipment):
    """(affected use ids, unassessed failed calibration ids) a return to service assesses."""
    uses = list(affected_uses(equipment).values_list("pk", flat=True))
    failures = list(unassessed_failures(equipment).values_list("pk", flat=True))
    return uses, failures


def return_to_service(
    *, actor, pin, equipment, expected_revision, impact_assessment, assessed=None
):
    # `assessed` is the scope shown to the signer when the page opened (read now if not given).
    # It is rechecked under the equipment lock before signing: a failure recorded meanwhile
    # does not change the equipment revision, and recording a use locks the same equipment row.
    assessed = (
        impact_scope(equipment) if assessed is None else (list(assessed[0]), list(assessed[1]))
    )

    def apply(locked):
        if locked.state != Equipment.State.OUT_OF_SERVICE:
            raise ValidationError("Equipment is already in service.")
        if locked.status_changed_by_id == actor.pk:
            raise PermissionDenied(
                "The person who removed equipment from service cannot return it."
            )
        if impact_scope(locked) != assessed:
            raise ValidationError(
                "Recorded uses or failures changed while you assessed them. Reload and reassess."
            )
        now = timezone.now()
        latest = latest_calibration(locked, now)
        if latest is None or latest.outcome != Calibration.Outcome.PASS:
            raise ValidationError(
                "A passing calibration after any failure must be independently accepted first."
            )
        if latest.due_date < timezone.localdate():
            raise ValidationError("The latest accepted calibration has expired.")
        if locked.requires_qualification and not any(
            qualification_valid(q, now) for q in locked.qualifications.all()
        ):
            raise ValidationError("Approved, current qualification evidence is required.")
        locked.state = Equipment.State.IN_SERVICE
        locked.status_changed_by = actor
        locked.status_changed_at = now

    uses, failures = assessed
    reason = (
        f"{impact_assessment.strip()}\n"
        f"Failed calibrations assessed: {failures or 'none'}\n"
        f"Affected uses assessed: {uses or 'none'}"
    )
    return sign_transition(
        actor=actor,
        pin=pin,
        obj=equipment,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=apply,
    )


# --- Calibration -----------------------------------------------------------------------------


@transaction.atomic
def record_calibration(*, actor, equipment, reason, **values):
    require_role(actor, *RECORDERS)
    lock_account(actor)
    equipment = _lock(Equipment, equipment)
    calibration = Calibration(equipment=equipment, recorded_by=actor, **values)
    if calibration.performed_at and calibration.performed_at > timezone.now():
        raise ValidationError("A calibration cannot be performed in the future.")
    calibration.full_clean()
    calibration.save()
    record_event(
        actor=actor,
        action="calibration.recorded",
        obj=calibration,
        after=snapshot(calibration),
        reason=reason,
    )
    if calibration.outcome == Calibration.Outcome.FAIL:
        if equipment.state == Equipment.State.IN_SERVICE:
            _set_state(
                equipment,
                actor,
                Equipment.State.OUT_OF_SERVICE,
                "equipment.out_of_service",
                f"Failed calibration {calibration.pk}: prior results need impact assessment.",
            )
    return calibration


def accept_calibration(*, actor, pin, calibration, expected_revision, reason):
    def apply(locked):
        if locked.state != Calibration.State.RECORDED:
            raise ValidationError("This calibration has already been accepted.")
        if locked.recorded_by_id == actor.pk:
            raise PermissionDenied("You cannot accept a calibration you recorded.")
        locked.state = Calibration.State.ACCEPTED
        locked.accepted_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=calibration,
        expected_revision=expected_revision,
        meaning="reviewed",
        reason=reason,
        permission="reviewer",
        apply=apply,
    )


# --- Qualification ---------------------------------------------------------------------------


@transaction.atomic
def record_qualification(*, actor, reason, user=None, equipment=None, **values):
    require_role(actor, *ANY_SCIENTIFIC)
    if user is not None and user.pk == actor.pk:
        raise PermissionDenied("You cannot record qualification evidence for yourself.")
    if user is not None and not user.is_active:
        raise ValidationError("The qualified person's account is inactive.")
    lock_account(actor)
    qualification = Qualification(user=user, equipment=equipment, recorded_by=actor, **values)
    qualification.full_clean()
    qualification.save()
    record_event(
        actor=actor,
        action="qualification.recorded",
        obj=qualification,
        after=snapshot(qualification),
        reason=reason,
    )
    return qualification


def approve_qualification(*, actor, pin, qualification, expected_revision, reason):
    def apply(locked):
        if locked.state != Qualification.State.RECORDED:
            raise ValidationError("Only recorded qualifications can be approved.")
        if actor.pk in (locked.recorded_by_id, locked.user_id):
            raise PermissionDenied(
                "The recorder and the qualified person cannot approve this qualification."
            )
        if locked.valid_until < timezone.localdate():
            raise ValidationError("The qualification has already expired.")
        locked.state = Qualification.State.APPROVED
        locked.approved_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=qualification,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=apply,
    )


def revoke_qualification(*, actor, pin, qualification, expected_revision, reason):
    def apply(locked):
        if locked.state != Qualification.State.APPROVED:
            raise ValidationError("Only approved qualifications can be revoked.")
        if locked.user_id == actor.pk:
            raise PermissionDenied("You cannot revoke your own qualification.")
        locked.state = Qualification.State.REVOKED
        locked.revoked_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=qualification,
        expected_revision=expected_revision,
        meaning="revoked",
        reason=reason,
        permission="quality",
        apply=apply,
    )


# --- Reagents and standards ------------------------------------------------------------------


@transaction.atomic
def receive_reagent(*, actor, reason, **values):
    require_role(actor, *RECORDERS)
    parent = values.get("parent")
    kind = values["kind"]
    if values["received_on"] > timezone.localdate():
        raise ValidationError("Receipt or preparation cannot be dated in the future.")
    lock_account(actor)
    if kind == ReagentLot.Kind.PREPARED:
        if parent is None:
            raise ValidationError("A prepared solution needs its source lot.")
        _lock_lineage([parent])
        parent = _lock(ReagentLot, parent)
        finding = reagent_eligibility(parent)
        if not finding.ok:
            raise ValidationError(
                "The source lot must be released for use and still eligible: "
                + " ".join(finding.reasons)
            )
        if values["expiry_date"] > parent.expiry_date:
            raise ValidationError("A prepared solution cannot outlive its source lot.")
        values["parent"] = parent
    elif parent is not None:
        raise ValidationError("Only a prepared solution has a source lot.")
    reagent = ReagentLot(recorded_by=actor, **values)
    reagent.full_clean()
    reagent.save()
    record_event(
        actor=actor,
        action="reagent.received",
        obj=reagent,
        after=snapshot(reagent),
        reason=reason,
    )
    return reagent


def release_reagent(*, actor, pin, reagent, expected_revision, reason):
    def apply(locked):
        if locked.state != ReagentLot.State.RECEIVED:
            raise ValidationError("This lot is not awaiting release.")
        if locked.recorded_by_id == actor.pk:
            raise PermissionDenied("You cannot release a lot you recorded.")
        if locked.expiry_date < timezone.localdate():
            raise ValidationError("The lot has already expired.")
        if locked.received_on > timezone.localdate():
            raise ValidationError("Receipt or preparation cannot be dated in the future.")
        if locked.parent_id:
            _lock_lineage([locked])
            sources = reagent_lineage(ReagentLot.objects.select_related("parent").get(pk=locked.pk))
            if any(source.state != ReagentLot.State.RELEASED for source in sources):
                raise ValidationError("Every source lot must be released for use.")
        locked.state = ReagentLot.State.RELEASED
        locked.released_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=reagent,
        expected_revision=expected_revision,
        meaning="reviewed",
        reason=reason,
        permission="reviewer",
        apply=apply,
    )


@transaction.atomic
def reject_reagent(*, actor, reagent, reason):
    """Protective and irreversible: a rejected lot never returns; prepared lots follow it."""
    require_role(actor, *ANY_SCIENTIFIC)
    if not reason.strip():
        raise ValidationError("State why the lot is rejected.")
    lock_account(actor)
    reagent = _lock(ReagentLot, reagent)
    if reagent.state == ReagentLot.State.REJECTED:
        raise ValidationError("The lot is already rejected.")
    before = snapshot(reagent)
    _bump(reagent, state=ReagentLot.State.REJECTED)
    record_event(
        actor=actor,
        action="reagent.rejected",
        obj=reagent,
        before=before,
        after=snapshot(reagent),
        reason=reason,
    )
    return reagent


# --- Use authorization -----------------------------------------------------------------------


def _lock_and_check(*, actor, activity, equipment_ids, reagent_ids):
    """Lock, then check. Returns (locked equipment, locked reagents, findings).

    Lock order is fixed so concurrent state changes cannot interleave with the check: account,
    equipment, reagent lineage, qualifications. Approval and revocation lock the qualification row
    they sign, so locking the analyst's and the equipment's rows serializes this check with them.
    Evidence is read only after the locks are held.
    """
    lock_account(actor)
    locked_equipment = list(
        Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk")
    )
    _lock_lineage(reagent_ids)
    locked_reagents = list(
        ReagentLot.objects.select_for_update(of=("self",))
        .filter(pk__in=reagent_ids)
        .order_by("pk")
        .select_related("parent")
    )
    missing = (set(equipment_ids) - {e.pk for e in locked_equipment}) | (
        set(reagent_ids) - {r.pk for r in locked_reagents}
    )
    if missing:
        raise ValidationError("A selected equipment item or reagent lot does not exist.")
    list(
        Qualification.objects.select_for_update()
        .filter(
            Q(user=actor, activity__iexact=activity.strip()) | Q(equipment__in=locked_equipment)
        )
        .order_by("pk")
    )
    prefetch_related_objects(locked_equipment, "calibrations", "qualifications")
    findings = check_use(
        analyst=actor, activity=activity, equipment=locked_equipment, reagents=locked_reagents
    )
    return locked_equipment, locked_reagents, findings


def _record_uses(
    *,
    actor,
    context_type,
    context_id,
    activity,
    test_code,
    profile_ref,
    equipment,
    reagents,
    findings,
    reason,
):
    """Write one ResourceUse per resource with its evidence, and the audit event (if any)."""
    analyst_evidence = findings[0].evidence
    uses = []
    for item, finding in zip([*equipment, *reagents], findings[1:], strict=True):
        uses.append(
            ResourceUse.objects.create(
                equipment=item if isinstance(item, Equipment) else None,
                reagent_lot=item if isinstance(item, ReagentLot) else None,
                context_type=context_type,
                context_id=str(context_id),
                activity=activity.strip(),
                test_code=test_code,
                profile_ref=profile_ref,
                used_by=actor,
                eligibility={**finding.evidence, "analyst": analyst_evidence},
            )
        )
    if uses:
        record_event(
            actor=actor,
            action="resource.used",
            obj=uses[0],
            after={
                "context": f"{context_type}:{context_id}",
                "activity": activity.strip(),
                "uses": [u.pk for u in uses],
            },
            reason=reason,
        )
    return uses


def _refusals(findings):
    return [{"subject": f.subject, "reasons": list(f.reasons)} for f in findings if not f.ok]


def record_blocked_use(*, actor, activity, context_type, context_id, refusals, reason):
    """Audit a refused use in its own transaction, so it survives the caller's rollback."""
    with transaction.atomic():
        record_event(
            actor=actor,
            action="resource.use_blocked",
            obj=actor,
            after={
                "context": f"{context_type}:{context_id}",
                "activity": (activity or "").strip(),
                "refusals": [
                    {"subject": r["subject"], "reasons": list(r["reasons"])} for r in refusals
                ],
            },
            reason=reason,
        )


def authorize_use(
    *,
    actor,
    context_type,
    context_id,
    activity,
    test_code="",
    profile_ref="",
    equipment=(),
    reagents=(),
    reason,
):
    """Gate and record the use of equipment/reagents by a qualified analyst for one test.

    Refusals are recorded as attributed audit events in their own transaction (they survive the
    rejection) and raise UseBlocked. Success writes one ResourceUse row per resource, each with
    the evidence relied on, atomically with the audit event.
    """
    require_role(actor, "analyst")
    if not (equipment or reagents):
        raise ValidationError("Select at least one piece of equipment or reagent lot.")
    if not reason.strip():
        raise ValidationError("A reason is required.")
    blocked = None
    try:
        with transaction.atomic():
            locked_equipment, locked_reagents, findings = _lock_and_check(
                actor=actor,
                activity=activity,
                equipment_ids=[e.pk for e in equipment],
                reagent_ids=[r.pk for r in reagents],
            )
            if not all(f.ok for f in findings):
                blocked = UseBlocked(findings)
                raise blocked
            return _record_uses(
                actor=actor,
                context_type=context_type,
                context_id=context_id,
                activity=activity,
                test_code=test_code,
                profile_ref=profile_ref,
                equipment=locked_equipment,
                reagents=locked_reagents,
                findings=findings,
                reason=reason,
            )
    except UseBlocked:
        pass
    record_blocked_use(
        actor=actor,
        activity=activity,
        context_type=context_type,
        context_id=context_id,
        refusals=_refusals(blocked.findings),
        reason=reason,
    )
    raise blocked


def _ids(values, noun):
    try:
        return sorted({int(v) for v in values})
    except TypeError, ValueError:
        raise ValidationError(f"A selected {noun} is not valid.") from None


def use_in_work(
    *,
    actor,
    activity,
    context_type,
    context_id,
    test_code="",
    equipment_ids=(),
    reagent_ids=(),
    reason,
):
    """Check the analyst and the selected resources for work being recorded by the caller, and
    record their use, inside the caller's transaction.

    The caller owns authorization of the actor's role and the lock on its own records. Nothing is
    written when a check fails (UseBlocked); the caller rolls back and then calls
    `record_blocked_use` outside its transaction. Returns the evidence relied on.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("Resource use must be recorded in the caller's transaction.")
    equipment_ids = _ids(equipment_ids, "equipment item")
    reagent_ids = _ids(reagent_ids, "reagent lot")
    locked_equipment, locked_reagents, findings = _lock_and_check(
        actor=actor, activity=activity, equipment_ids=equipment_ids, reagent_ids=reagent_ids
    )
    if not all(f.ok for f in findings):
        raise UseBlocked(findings)
    uses = _record_uses(
        actor=actor,
        context_type=context_type,
        context_id=context_id,
        activity=activity,
        test_code=test_code,
        profile_ref="",
        equipment=locked_equipment,
        reagents=locked_reagents,
        findings=findings,
        reason=reason,
    )
    by_resource = {(u.equipment_id, u.reagent_lot_id): u for u in uses}
    return {
        "user": actor.pk,
        "activity": activity.strip(),
        "qualification": findings[0].evidence.get("qualification"),
        "equipment": [
            {
                **finding.evidence,
                "id": item.pk,
                "asset_id": item.asset_id,
                "use": by_resource[(item.pk, None)].pk,
            }
            for item, finding in zip(locked_equipment, findings[1:], strict=False)
        ],
        "reagents": [
            {
                **finding.evidence,
                "id": item.pk,
                "identifier": item.identifier,
                "use": by_resource[(None, item.pk)].pk,
            }
            for item, finding in zip(
                locked_reagents, findings[1 + len(locked_equipment) :], strict=True
            )
        ],
    }


# --- Choices for work entry -------------------------------------------------------------------


def bench_choices():
    """Equipment and reagent lots offered when recording work: (pk, label) pairs, two queries.

    Labels name the item and its current status in words. Rejected lots are not offered."""
    today = timezone.localdate()
    equipment = [
        (item.pk, f"{item.asset_id} · {item.description} · {equipment_status(item, today)[0]}")
        for item in equipment_queryset(today).order_by("asset_id", "pk")
    ]
    reagents = [
        (
            lot.pk,
            f"{lot.identifier} · {lot.name} ({lot.get_kind_display()}) · "
            + ("ready" if (word := reagent_status(lot, today)[0]) == "Released" else word.lower()),
        )
        for lot in ReagentLot.objects.exclude(state=ReagentLot.State.REJECTED).order_by(
            "identifier", "pk"
        )
    ]
    return {"equipment": equipment, "reagents": reagents}
