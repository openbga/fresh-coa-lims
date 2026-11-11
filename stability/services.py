"""Stability, reserve, retention and hold transitions.

Same contract as the other domain modules: authorize on the server, lock and recheck current
state, and commit state, attributed audit event and any signature in one transaction.
Independence: whoever authored, pulled or placed something cannot be the signer for it.
"""

import hashlib
import json
from datetime import datetime, time, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone

from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import require_role, sign_transition
from laboratory.eligibility import equipment_eligibility
from laboratory.models import Qualification, ResourceUse
from laboratory.services import lock_account
from quality.models import Lot, Sample

from .evidence import sample_evidence
from .models import (
    Hold,
    Protocol,
    ProtocolCondition,
    ProtocolTimepoint,
    Pull,
    ReserveSample,
    RetentionObligation,
    Study,
)

AUTHORS = ("analyst", "quality")
ANY_SCIENTIFIC = ("analyst", "reviewer", "quality")
PROTOCOL_LOCK = 681242


def _lock(model, obj):
    return model.objects.select_for_update().get(pk=obj.pk)


def _bump(obj, **changes):
    for name, value in changes.items():
        setattr(obj, name, value)
    obj.revision += 1
    obj.full_clean()
    obj.save()
    return obj


def _touch_lot(lot_id):
    """Make an in-flight lot signature stale. Released lots are immutable and need no bump."""
    lot = Lot.objects.select_for_update().get(pk=lot_id)
    if lot.state == "quarantine":
        lot.revision += 1
        lot.save(update_fields=["revision"])
    return lot


def _need_reason(reason):
    if not reason or not reason.strip():
        raise ValidationError("A reason is required.")


# --- Protocols -------------------------------------------------------------------------------


def protocol_digest(protocol):
    payload = {
        "conditions": [
            {
                "label": c.label,
                "setpoint": c.setpoint,
                "temperature_c": None if c.temperature_c is None else str(c.temperature_c),
                "humidity_pct": None if c.humidity_pct is None else str(c.humidity_pct),
                "timepoints": [
                    {
                        "label": t.label,
                        "interval_days": t.interval_days,
                        "window_days": t.window_days,
                        "test_codes": t.test_codes,
                    }
                    for t in c.timepoints.order_by("interval_days")
                ],
            }
            for c in protocol.conditions.order_by("pk")
        ]
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@transaction.atomic
def create_protocol(*, actor, code, reason, **values):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [PROTOCOL_LOCK])
    latest = Protocol.objects.filter(code=code).order_by("-version").first()
    if latest and latest.state == Protocol.State.DRAFT:
        raise ValidationError(f"{latest.identifier} is still a draft; approve or leave it.")
    protocol = Protocol(
        code=code, version=latest.version + 1 if latest else 1, author=actor, **values
    )
    protocol.full_clean()
    protocol.save()
    record_event(
        actor=actor,
        action="protocol.created",
        obj=protocol,
        after=snapshot(protocol),
        reason=reason,
    )
    return protocol


def _draft_for_author(actor, protocol):
    protocol = _lock(Protocol, protocol)
    if protocol.state != Protocol.State.DRAFT:
        raise ValidationError("An approved protocol is frozen; create a new version.")
    if protocol.author_id != actor.pk:
        raise PermissionDenied("Only the protocol author edits a draft.")
    return protocol


def _refresh_digest(actor, protocol, action, obj, reason):
    before = snapshot(protocol)
    protocol.content_digest = protocol_digest(protocol)
    _bump(protocol)
    record_event(
        actor=actor,
        action=action,
        obj=obj,
        before={"protocol_revision": before["revision"]},
        after={**snapshot(obj), "protocol_revision": protocol.revision},
        reason=reason,
    )


@transaction.atomic
def add_condition(*, actor, protocol, reason, **values):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    protocol = _draft_for_author(actor, protocol)
    condition = ProtocolCondition(protocol=protocol, **values)
    condition.full_clean()
    condition.save()
    _refresh_digest(actor, protocol, "protocol.condition_added", condition, reason)
    return condition


@transaction.atomic
def add_timepoint(*, actor, protocol, condition, reason, **values):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    protocol = _draft_for_author(actor, protocol)
    if condition.protocol_id != protocol.pk:
        raise ValidationError("The condition belongs to a different protocol.")
    timepoint = ProtocolTimepoint(protocol=protocol, condition=condition, **values)
    timepoint.full_clean()
    timepoint.save()
    _refresh_digest(actor, protocol, "protocol.timepoint_added", timepoint, reason)
    return timepoint


def approve_protocol(*, actor, pin, protocol, expected_revision, reason):
    def apply(locked):
        if locked.state != Protocol.State.DRAFT:
            raise ValidationError("Only a draft protocol can be approved.")
        if locked.author_id == actor.pk:
            raise PermissionDenied("The protocol author cannot approve it.")
        conditions = list(locked.conditions.all())
        if not conditions:
            raise ValidationError("The protocol has no storage conditions.")
        if any(not c.timepoints.exists() for c in conditions):
            raise ValidationError("Every storage condition needs at least one timepoint.")
        if protocol_digest(locked) != locked.content_digest:
            raise ValidationError("Protocol content changed. Reload and review before signing.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [PROTOCOL_LOCK])
        for older in Protocol.objects.select_for_update().filter(
            code=locked.code, state=Protocol.State.APPROVED
        ):
            before = snapshot(older)
            _bump(older, state=Protocol.State.SUPERSEDED)
            record_event(
                actor=actor,
                action="protocol.superseded",
                obj=older,
                before=before,
                after=snapshot(older),
                reason=f"Superseded by {locked.identifier}.",
            )
        locked.state = Protocol.State.APPROVED
        locked.approved_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=protocol,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=apply,
    )


# --- Studies and pulls -----------------------------------------------------------------------


@transaction.atomic
def start_study(*, actor, identifier, protocol, lot, container_closure, start_date, reason):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    if start_date > timezone.localdate():
        raise ValidationError(
            "Time zero cannot be in the future: this workflow records studies that have "
            "actually started."
        )
    lock_account(actor)
    protocol = _lock(Protocol, protocol)
    if protocol.state != Protocol.State.APPROVED:
        raise ValidationError("Studies start only on the current approved protocol revision.")
    lot = Lot.objects.select_for_update().get(pk=lot.pk)
    rules = lot.rules
    study = Study(
        identifier=identifier,
        protocol=protocol,
        lot=lot,
        container_closure=container_closure,
        start_date=start_date,
        rule_basis=f"{rules.code} v{rules.version} r{rules.revision}",
        created_by=actor,
    )
    study.full_clean()
    study.save()  # the transaction rolls back if the schedule is refused below
    pulls = []
    for tp in protocol.timepoints.select_related("condition").order_by(
        "interval_days", "condition_id"
    ):
        try:
            pull = Pull(
                study=study, timepoint=tp, due_date=start_date + timedelta(days=tp.interval_days)
            )
            pull.window  # noqa: B018  (both window ends must be representable dates)
        except OverflowError:
            raise ValidationError(
                f"{tp.condition.label} {tp.label}: the pull date or its window falls outside "
                "the supported calendar range from this time zero."
            ) from None
        pulls.append(pull)
    Pull.objects.bulk_create(pulls)
    record_event(
        actor=actor,
        action="study.started",
        obj=study,
        after={**snapshot(study), "pulls": len(pulls), "protocol": protocol.identifier},
        reason=reason,
    )
    return study


def _resolve_sample(study, reference):
    reference = (reference or "").strip()
    if not reference:
        return None
    sample = Sample.objects.filter(reference=reference).first()
    if sample is None:
        raise ValidationError("No sample has this reference.")
    if sample.lot_id != study.lot_id:
        raise ValidationError("The sample belongs to a different lot than the study.")
    return sample


def _pull_start(pull):
    return timezone.make_aware(datetime.combine(pull.pulled_on, time.min))


def _check_pull_sample(pull, sample):
    """A sample is evidence for exactly one pull and must have been collected for it."""
    collected_on = timezone.localdate(sample.collected_at)
    if collected_on != pull.pulled_on:
        raise ValidationError(
            f"The sample was collected on {collected_on.isoformat()}, not on the pull date "
            f"{pull.pulled_on.isoformat()}; it cannot be this pull's evidence."
        )
    if sample.collected_at > timezone.now():
        raise ValidationError("The sample cannot be collected in the future.")
    other = Pull.objects.filter(sample=sample).exclude(pk=pull.pk).select_related("timepoint")
    reused = other.first()
    if reused is not None:
        raise ValidationError(
            f"The sample is already evidence for {reused.label}; each pull needs its own sample."
        )


@transaction.atomic
def record_pull(
    *,
    actor,
    pull,
    pulled_on,
    quantity,
    quantity_unit,
    storage_location,
    reason,
    chamber=None,
    deviation_reason="",
):
    require_role(actor, "analyst")
    _need_reason(reason)
    lock_account(actor)
    pull = _lock(Pull, pull)
    study = _lock(Study, pull.study)
    if study.state != Study.State.ACTIVE:
        raise ValidationError("The study is no longer active.")
    if pull.state != Pull.State.SCHEDULED:
        raise ValidationError("This pull is not awaiting collection.")
    if pulled_on > timezone.localdate():
        raise ValidationError("A pull cannot be dated in the future.")
    opens, closes = pull.window
    if not opens <= pulled_on <= closes and not deviation_reason.strip():
        raise ValidationError(
            f"The pull is outside its window ({opens.isoformat()} to {closes.isoformat()}); "
            "record the deviation reason."
        )
    if chamber is not None:
        chamber = _lock(type(chamber), chamber)
        # Approval and revocation lock the qualification row they sign; locking the chamber's
        # rows serializes this check with them, and eligibility reads them after the lock.
        list(Qualification.objects.select_for_update().filter(equipment=chamber).order_by("pk"))
        finding = equipment_eligibility(chamber)
        if not finding.ok:
            raise ValidationError(f"{chamber.asset_id}: " + " ".join(finding.reasons))
        ResourceUse.objects.create(
            equipment=chamber,
            context_type="stability.pull",
            context_id=str(pull.pk),
            activity="stability-storage",
            used_by=actor,
            eligibility=finding.evidence,
        )
    before = snapshot(pull)
    _bump(
        pull,
        state=Pull.State.PULLED,
        pulled_on=pulled_on,
        pulled_by=actor,
        quantity=quantity,
        quantity_unit=quantity_unit,
        storage_location=storage_location,
        chamber=chamber,
        deviation_reason=deviation_reason.strip(),
    )
    record_event(
        actor=actor,
        action="pull.recorded",
        obj=pull,
        before=before,
        after=snapshot(pull),
        reason=reason,
    )
    return pull


@transaction.atomic
def attach_pull_evidence(
    *,
    actor,
    pull,
    reason,
    sample_reference="",
    external_sample_ref="",
    evidence_ref="",
    evidence_url="",
):
    """Link the testing spine (a sample) or an external stability system's evidence. Allowed
    until acceptance; before/after values are retained in the audit trail."""
    require_role(actor, "analyst")
    _need_reason(reason)
    lock_account(actor)
    pull = _lock(Pull, pull)
    study = _lock(Study, pull.study)
    if study.state != Study.State.ACTIVE or pull.state != Pull.State.PULLED:
        raise ValidationError("Evidence can be linked only to a pulled, unaccepted pull.")
    sample = _resolve_sample(study, sample_reference)
    if sample is not None:
        _check_pull_sample(pull, sample)
    if not (sample or (external_sample_ref.strip() and evidence_ref.strip())):
        raise ValidationError("Link a sample, or give the external sample and evidence references.")
    before = snapshot(pull)
    _bump(
        pull,
        sample=sample,
        external_sample_ref=external_sample_ref.strip(),
        evidence_ref=evidence_ref.strip(),
        evidence_url=evidence_url,
        evidence_recorded_by=actor,
    )
    record_event(
        actor=actor,
        action="pull.evidence_linked",
        obj=pull,
        before=before,
        after=snapshot(pull),
        reason=reason,
    )
    return pull


@transaction.atomic
def mark_pull_missed(*, actor, pull, reason):
    """A missed pull stays visible forever; it is never deleted or silently rescheduled."""
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    pull = _lock(Pull, pull)
    study = _lock(Study, pull.study)
    if study.state != Study.State.ACTIVE or pull.state != Pull.State.SCHEDULED:
        raise ValidationError("Only a scheduled pull of an active study can be marked missed.")
    if timezone.localdate() <= pull.window[1]:
        raise ValidationError("The pull window has not closed yet.")
    before = snapshot(pull)
    _bump(pull, state=Pull.State.MISSED, missed_reason=reason.strip())
    record_event(
        actor=actor,
        action="pull.missed",
        obj=pull,
        before=before,
        after=snapshot(pull),
        reason=reason,
    )
    return pull


def pull_author_ids(pull):
    """Users who may not accept the pull: its puller, everyone who ever linked its evidence and,
    for a linked sample, the sample's creator and every data or investigation author of its
    tests."""
    from analytical.gates import data_author_ids, investigation_author_ids
    from analytical.models import AnalyticalTest, Investigation

    ids = {pull.pulled_by_id, pull.evidence_recorded_by_id}
    # Re-linking overwrites `evidence_recorded_by`; the append-only audit trail keeps every
    # earlier recorder (and the puller) attributed.
    ids.update(
        AuditEvent.objects.filter(
            object_type=Pull._meta.label_lower,
            object_id=str(pull.pk),
            action__in=("pull.recorded", "pull.evidence_linked"),
        ).values_list("actor_id", flat=True)
    )
    if pull.sample_id:
        ids.add(Sample.objects.values_list("created_by_id", flat=True).get(pk=pull.sample_id))
        for test in AnalyticalTest.objects.filter(sample_id=pull.sample_id):
            ids |= data_author_ids(test)
        ids |= investigation_author_ids(Investigation.objects.filter(test__sample=pull.sample_id))
    ids.discard(None)
    return ids


def accept_pull(*, actor, pin, pull, expected_revision, reason):
    def apply(locked):
        study = Study.objects.select_for_update().get(pk=locked.study_id)
        if study.state != Study.State.ACTIVE or locked.state != Pull.State.PULLED:
            raise ValidationError("This pull is not awaiting acceptance.")
        if actor.pk in pull_author_ids(locked):
            raise PermissionDenied(
                "You cannot accept a pull you pulled, documented or produced test data for."
            )
        if locked.sample_id:
            _check_pull_sample(locked, locked.sample)
            codes = list(locked.timepoint.test_codes)
            blockers, _ = sample_evidence(locked.sample, codes, _pull_start(locked))
            if blockers:
                raise ValidationError("Testing is not complete: " + " ".join(blockers))
        elif not (locked.external_sample_ref and locked.evidence_ref):
            raise ValidationError("Link a sample or external stability evidence first.")
        locked.state = Pull.State.ACCEPTED
        locked.accepted_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=pull,
        expected_revision=expected_revision,
        meaning="reviewed",
        reason=reason,
        permission="reviewer",
        apply=apply,
    )


def close_study(*, actor, pin, study, expected_revision, outcome, reason):
    if outcome not in (Study.State.COMPLETED, Study.State.TERMINATED):
        raise ValidationError("Choose completed or terminated.")

    def apply(locked):
        if locked.state != Study.State.ACTIVE:
            raise ValidationError("This study is already closed.")
        if locked.created_by_id == actor.pk:
            raise PermissionDenied("The person who started a study cannot close it.")
        pending = locked.pulls.filter(state__in=[Pull.State.SCHEDULED, Pull.State.PULLED])
        if outcome == Study.State.COMPLETED and pending.exists():
            raise ValidationError(
                f"{pending.count()} pull(s) are not accepted or missed; terminate instead "
                "or finish them."
            )
        locked.state = outcome
        locked.closed_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=study,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=apply,
    )


# --- Reserves and retention ------------------------------------------------------------------


@transaction.atomic
def record_reserve(*, actor, lot, reason, **values):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    lot = Lot.objects.select_for_update().get(pk=lot.pk)
    reserve = ReserveSample(lot=lot, recorded_by=actor, **values)
    reserve.full_clean()
    reserve.save()
    record_event(
        actor=actor,
        action="reserve.recorded",
        obj=reserve,
        after={**snapshot(reserve), "meets_minimum": reserve.meets_minimum},
        reason=reason,
    )
    return reserve


@transaction.atomic
def add_obligation(*, actor, lot, reason, reserve=None, **values):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    lot = Lot.objects.select_for_update().get(pk=lot.pk)
    if reserve is not None and reserve.lot_id != lot.pk:
        raise ValidationError("The reserve sample belongs to a different lot.")
    obligation = RetentionObligation(lot=lot, reserve=reserve, recorded_by=actor, **values)
    obligation.full_clean()
    obligation.save()
    record_event(
        actor=actor,
        action="retention.recorded",
        obj=obligation,
        after={**snapshot(obligation), "retain_until": str(obligation.retain_until)},
        reason=reason,
    )
    return obligation


@transaction.atomic
def set_anchor(*, actor, obligation, anchor_date, reason):
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    obligation = _lock(RetentionObligation, obligation)
    if obligation.anchor_date is not None:
        raise ValidationError(
            "The anchor is already set. Record a new obligation if the anchor moved."
        )
    before = snapshot(obligation)
    obligation.anchor_date = anchor_date
    obligation.anchor_set_by = actor
    obligation.anchor_set_at = timezone.now()
    obligation.full_clean()
    obligation.save()
    record_event(
        actor=actor,
        action="retention.anchor_set",
        obj=obligation,
        before=before,
        after={**snapshot(obligation), "retain_until": str(obligation.retain_until)},
        reason=reason,
    )
    return obligation


# --- Holds -----------------------------------------------------------------------------------


@transaction.atomic
def place_hold(*, actor, lot, kind, reason, reference="", reserve=None):
    """Protective, so any scientific role may place one; release needs an independent signature."""
    require_role(actor, *ANY_SCIENTIFIC)
    _need_reason(reason)
    lock_account(actor)
    lot = _touch_lot(lot.pk)
    if reserve is not None and reserve.lot_id != lot.pk:
        raise ValidationError("The reserve sample belongs to a different lot.")
    hold = Hold(
        lot=lot,
        reserve=reserve,
        kind=kind,
        reason=reason.strip(),
        reference=reference,
        placed_by=actor,
    )
    hold.full_clean()
    hold.save()
    record_event(actor=actor, action="hold.placed", obj=hold, after=snapshot(hold), reason=reason)
    return hold


def release_hold(*, actor, pin, hold, expected_revision, reason):
    def apply(locked):
        if locked.state != Hold.State.ACTIVE:
            raise ValidationError("This hold is already released.")
        if locked.placed_by_id == actor.pk:
            raise PermissionDenied("The person who placed a hold cannot release it.")
        _touch_lot(locked.lot_id)
        locked.state = Hold.State.RELEASED
        locked.released_at = timezone.now()

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=hold,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=apply,
    )
