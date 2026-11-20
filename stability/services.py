"""Stability, reserve, retention and hold transitions.

Same contract as the other domain modules: authorize on the server, lock and recheck current
state, and commit state, attributed audit event and any signature in one transaction.
Independence: whoever authored, pulled or placed something cannot be the signer for it.

A pull is tested in the system (`testing`, with the tests assigned and worked in the testing
module) or linked to a sample of its lot or to external evidence, never both. Accepting a
pull tested in the system records how its reviewed results compare with the acceptance
criteria frozen on its tests and freezes those results with the signature.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from analytical.models import AnalyticalTest
from catalog.units import plain
from core.audit import record_event, snapshot
from core.models import AuditEvent
from core.services import require_role, sign_transition
from laboratory.eligibility import equipment_eligibility
from laboratory.models import Qualification, ResourceUse
from laboratory.services import lock_account
from quality.models import Lot, LotState, Sample

from . import testing
from .evidence import (
    frozen_results,
    has_tests,
    pull_results,
    pull_testing_in_progress,
    sample_evidence,
    test_author_ids,
    testing_in_progress,
)
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


def _refuse_cancelled(lot):
    """A lot cancelled as received in error has no material: nothing is kept, studied or held."""
    if lot.state == LotState.CANCELLED:
        raise ValidationError(
            f"Lot {lot.number} was cancelled as received in error; it has no material."
        )


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
    # ``values`` may name the specification that states the acceptance criteria; like the
    # rest of the header it is fixed from here on (a new version names another).
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
        raise ValidationError(
            f"{protocol.identifier} is {protocol.get_state_display().lower()} and frozen; "
            "create a new version."
        )
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
        # A protocol that names a specification is approved only while the version in force
        # states every test of every time point, with a method in force.
        if problems := testing.protocol_problems(locked):
            raise ValidationError(problems)
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


@transaction.atomic
def withdraw_protocol(*, actor, protocol, expected_revision, reason):
    """Withdraw a draft that will not be approved, for example one whose specification cannot
    state a test of a time point. The draft keeps its content; the next version of the code
    can then be drafted. Its author or a quality person withdraws it, with a reason."""
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    # The row lock serializes this with approval and with edits of the draft. Approval takes
    # the row before the protocol lock, so this takes no protocol lock: a new version drafted
    # meanwhile reads the draft as it was committed and is refused until this commits.
    locked = _lock(Protocol, protocol)
    if locked.state != Protocol.State.DRAFT:
        raise ValidationError("Only a draft protocol can be withdrawn.")
    if locked.author_id != actor.pk and not actor.groups.filter(name="quality").exists():
        raise PermissionDenied("Only the draft's author or a quality person withdraws it.")
    if locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before withdrawing.")
    before = snapshot(locked)
    _bump(locked, state=Protocol.State.WITHDRAWN)
    record_event(
        actor=actor,
        action="protocol.withdrawn",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


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
    _refuse_cancelled(lot)
    if lot.state == LotState.REJECTED:
        raise ValidationError(
            f"Lot {lot.number} was rejected. A study starts on a lot in quarantine or released."
        )
    if problem := testing.material_problem(protocol, lot):
        raise ValidationError(problem)
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


TESTED_HERE = (
    "This pull is tested in the system: its own tests are its evidence. A pull is tested in "
    "the system or linked to other evidence, never both."
)


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
    if has_tests(pull):
        raise ValidationError(TESTED_HERE)
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


def missed_refusal(pull, study=None):
    """Why the pull cannot be recorded as missed now, or None. A scheduled pull is missed
    once its window has closed. A pulled pull is missed when its material cannot be tested
    (lost or insufficient): nothing of its testing may be in progress, it may not be ready for
    acceptance (missing it would skip the reviewer's signed outcome), and no result of it may
    have failed (a failure is recorded through acceptance). Its conforming reviewed results
    stay in the record and its untouched tests take no more work."""
    study = study or pull.study
    if study.state != Study.State.ACTIVE:
        return "Only a pull of an active study can be marked missed."
    if pull.state == Pull.State.SCHEDULED:
        if timezone.localdate() <= pull.window[1]:
            return "The pull window has not closed yet."
        return None
    if pull.state == Pull.State.PULLED:
        if reasons := pull_testing_in_progress(pull):
            return "Testing of this pull is in progress; finish it first: " + " ".join(reasons)
        _, rows, outcome = pull_results(pull)
        if outcome:
            return (
                "Every test of this pull has a decided result: a reviewer accepts the pull "
                "with its outcome instead."
            )
        failing = [
            test.label
            for row in rows
            for test in row["lineage"]
            if test.state == AnalyticalTest.State.REVIEWED and test.conforms is False
        ]
        if failing or any(row["outcome"] == "fails" for row in rows):
            return (
                f"A result of this pull did not meet the acceptance criteria "
                f"({', '.join(failing)}); it is not recorded as missed. Complete its tests "
                "and have a reviewer accept the pull, or terminate the study."
            )
        return None
    return "Only a scheduled or pulled pull can be marked missed."


@transaction.atomic
def mark_pull_missed(*, actor, pull, reason):
    """A missed pull stays visible forever; it is never deleted or silently rescheduled.

    Locks the pull, then its study; testing locks a test before its pull, so work recorded
    on a test at the same moment either commits first and refuses this, or is refused."""
    require_role(actor, *AUTHORS)
    _need_reason(reason)
    lock_account(actor)
    pull = _lock(Pull, pull)
    study = _lock(Study, pull.study)
    if refusal := missed_refusal(pull, study):
        raise ValidationError(refusal)
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
    """Users who may not accept the pull: its puller, everyone who ever linked its evidence,
    for a linked sample the sample's creator and every data or investigation author of its
    tests, and for a pull tested in the system every data or investigation author of the
    pull's own tests."""
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
    ids |= test_author_ids(pull)
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
        if has_tests(locked):
            # Tested in the system. Every evidence change of the pull's tests advanced this
            # pull's revision under its lock, so what is read here is what the signer saw.
            results = pull_results(locked)
            blockers, _, outcome = results
            if blockers or not outcome:
                raise ValidationError("Testing is not complete: " + " ".join(blockers))
            locked.outcome = outcome
            locked.result_evidence = frozen_results(locked, results)
        elif locked.sample_id:
            _check_pull_sample(locked, locked.sample)
            codes = list(locked.timepoint.test_codes)
            blockers, _ = sample_evidence(locked.sample, codes, _pull_start(locked))
            if blockers:
                raise ValidationError("Testing is not complete: " + " ".join(blockers))
        elif not (locked.external_sample_ref and locked.evidence_ref):
            raise ValidationError(
                "Assign and complete the pull's tests, or link a sample or external "
                "stability evidence first."
            )
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
        # Every testing transition locks the study after its tests and pull, so what is read
        # here under the study lock cannot gain work before this commits.
        if reasons := testing_in_progress(locked):
            raise ValidationError(
                "Testing of the study's pulls is in progress; finish it first: " + " ".join(reasons)
            )
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
    _refuse_cancelled(lot)
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
    _refuse_cancelled(lot)
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
    _refuse_cancelled(lot)
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


# --- Shelf-life evaluations ------------------------------------------------------------------

SHELF_LIFE_DRAFTERS = ("shelf_life.drafted", "shelf_life.changed")
INDEPENDENT_SHELF_LIFE = (
    "You drafted or changed this evaluation, or produced data of a result it uses; another "
    "quality person concludes it."
)
STALE_SHELF_LIFE = (
    "The results or the evaluation changed since this page was opened. Reload it and review "
    "the figures before signing."
)


@dataclass(frozen=True)
class ShelfLifeLine:
    """A test line of the protocol's specification in force, as an evaluation keeps it."""

    code: str
    name: str
    unit: str
    decimals: int | None
    lower_limit: Decimal | None
    upper_limit: Decimal | None

    @property
    def criterion(self):
        lower, upper = self.lower_limit, self.upper_limit
        if lower is not None and upper is not None:
            return f"{plain(lower)} to {plain(upper)} {self.unit}"
        if lower is not None:
            return f"not less than {plain(lower)} {self.unit}"
        return f"not more than {plain(upper)} {self.unit}"

    @property
    def label(self):
        return f"{self.name} ({self.code}) · {self.criterion}"


def shelf_life_lines(protocol, at=None):
    """The test lines a shelf-life evaluation of ``protocol``'s studies can follow: the numeric
    and count lines with a lower or upper limit that the version in force of the protocol's
    specification states for the tests the protocol names. (revision, [line]) or (None, [])."""
    from analytical.contracts import RequirementHold

    from .shelf_life import USED_TYPES

    specification = protocol.specification
    if specification is None:
        return None, []
    try:
        read, revision = testing._read(specification, at)
    except RequirementHold:
        return None, []
    codes = []
    for timepoint in protocol.timepoints.order_by("pk"):
        codes += [code for code in timepoint.test_codes if code not in codes]
    lines = []
    for code in codes:
        line, _ = testing._line(read, revision, specification, code)
        if line is None or line["result_type"] not in USED_TYPES:
            continue
        lower, upper = (
            None if line[name] in (None, "") else Decimal(str(line[name]))
            for name in ("lower_limit", "upper_limit")
        )
        if lower is not None or upper is not None:
            lines.append(
                ShelfLifeLine(
                    code=line["code"],
                    name=line["name"],
                    unit=line["unit"],
                    decimals=line["reporting_decimals"],
                    lower_limit=lower,
                    upper_limit=upper,
                )
            )
    return revision, lines


def _direction_problem(direction, lower, upper):
    from .models import ShelfLifeEvaluation

    Direction = ShelfLifeEvaluation.Direction
    if direction not in Direction.values:
        return "Choose how the result is expected to change."
    if direction == Direction.DECREASES and lower is None:
        return "The test has no lower limit, so a decrease never meets it: choose another."
    if direction == Direction.INCREASES and upper is None:
        return "The test has no upper limit, so an increase never meets it: choose another."
    return None


def _evaluation_studies(protocol_code, container_closure, study_ids):
    from .shelf_life import MAX_STUDIES, studies_of

    wanted = {int(pk) for pk in study_ids}
    if not wanted:
        raise ValidationError({"studies": "Choose at least one study."})
    if len(wanted) > MAX_STUDIES:
        raise ValidationError({"studies": f"An evaluation uses at most {MAX_STUDIES} studies."})
    found = list(studies_of(protocol_code, container_closure).filter(pk__in=wanted))
    if len(found) != len(wanted):
        raise ValidationError(
            {"studies": f"Choose studies of protocol {protocol_code} in {container_closure}."}
        )
    return found


SHELF_LIFE_LOCK = 681243


def _lock_scope(*parts):
    """Serialize the drafts of one scope (protocol code, container closure, condition, test),
    so two are never drafted at once. An advisory lock, so no protocol row is locked against
    an approval; the partial unique constraint stays the backstop."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
            [SHELF_LIFE_LOCK, "\x1f".join(parts)],
        )


def _shelf_life_after(evaluation, studies):
    return {**snapshot(evaluation), "studies": [study.identifier for study in studies]}


@transaction.atomic
def draft_shelf_life(*, actor, study, condition, test_code, direction, purpose, reason):
    """Draft a shelf-life evaluation of ``test_code`` at ``condition`` for the studies of
    ``study``'s protocol code and container closure, all of them to begin with. The acceptance
    criterion is the one the protocol's specification in force states now."""
    from .models import ShelfLifeEvaluation, ShelfLifeStudy
    from .shelf_life import MAX_STUDIES, studies_of

    require_role(actor, "quality")
    _need_reason(reason)
    lock_account(actor)
    study = Study.objects.select_related("protocol__specification").get(pk=study.pk)
    protocol = study.protocol
    errors = {}
    if condition not in set(protocol.conditions.values_list("label", flat=True)):
        errors["condition"] = f"Choose a storage condition of {protocol.identifier}."
    revision, lines = shelf_life_lines(protocol)
    line = next((line for line in lines if line.code == test_code), None)
    if line is None:
        errors["test_code"] = (
            "Choose a numeric or count test with a limit that the protocol names and its "
            "specification in force states."
        )
    elif problem := _direction_problem(direction, line.lower_limit, line.upper_limit):
        errors["direction"] = problem
    if not (purpose or "").strip():
        errors["purpose"] = "State why the shelf life is evaluated."
    if errors:
        raise ValidationError(errors)
    _lock_scope(protocol.code, study.container_closure, condition, line.code)
    if ShelfLifeEvaluation.objects.filter(
        protocol_code=protocol.code,
        container_closure=study.container_closure,
        condition=condition,
        test_code=line.code,
        state=ShelfLifeEvaluation.State.DRAFT,
    ).exists():
        raise ValidationError(
            "A draft evaluation of this test at this condition exists: change it, or withdraw "
            "it first."
        )
    evaluation = ShelfLifeEvaluation(
        protocol_code=protocol.code,
        product=protocol.product,
        container_closure=study.container_closure,
        condition=condition,
        specification=protocol.specification,
        specification_version=revision.version,
        test_code=line.code,
        name=line.name,
        unit=line.unit,
        decimals=line.decimals,
        lower_limit=line.lower_limit,
        upper_limit=line.upper_limit,
        direction=direction,
        purpose=purpose.strip(),
        drafted_by=actor,
    )
    evaluation.full_clean()
    evaluation.save()
    studies = list(studies_of(protocol.code, study.container_closure)[:MAX_STUDIES])
    if study not in studies:
        studies[-1:] = [study]
    ShelfLifeStudy.objects.bulk_create(
        ShelfLifeStudy(evaluation=evaluation, study=item) for item in studies
    )
    record_event(
        actor=actor,
        action="shelf_life.drafted",
        obj=evaluation,
        after={
            **_shelf_life_after(evaluation, studies),
            "specification": {"code": protocol.specification.code, "version": revision.version},
        },
        reason=reason,
    )
    return evaluation


def _locked_shelf_life(evaluation, expected_revision):
    from .models import ShelfLifeEvaluation

    locked = ShelfLifeEvaluation.objects.select_for_update().get(pk=evaluation.pk)
    if locked.state != ShelfLifeEvaluation.State.DRAFT:
        raise ValidationError(
            f"{locked.identifier} is {locked.get_state_display().lower()}: it no longer changes."
        )
    if expected_revision is None or locked.revision != expected_revision:
        raise ValidationError("Record changed. Reload before saving.")
    return locked


def _linked_studies(evaluation):
    return list(
        Study.objects.filter(shelf_life_links__evaluation=evaluation).order_by("start_date", "pk")
    )


@transaction.atomic
def change_shelf_life(*, actor, evaluation, expected_revision, reason, studies, direction, purpose):
    """Change a draft's studies (ids), expected change or purpose. Whoever changes a draft
    cannot conclude it."""
    from .models import ShelfLifeStudy

    require_role(actor, "quality")
    _need_reason(reason)
    lock_account(actor)
    locked = _locked_shelf_life(evaluation, expected_revision)
    chosen = _evaluation_studies(locked.protocol_code, locked.container_closure, studies)
    errors = {}
    if problem := _direction_problem(direction, locked.lower_limit, locked.upper_limit):
        errors["direction"] = problem
    if not (purpose or "").strip():
        errors["purpose"] = "State why the shelf life is evaluated."
    if errors:
        raise ValidationError(errors)
    current = _linked_studies(locked)
    if (
        {study.pk for study in current} == {study.pk for study in chosen}
        and direction == locked.direction
        and purpose.strip() == locked.purpose
    ):
        raise ValidationError("Nothing was changed.")
    before = _shelf_life_after(locked, current)
    removed = {study.pk for study in current} - {study.pk for study in chosen}
    added = [study for study in chosen if study.pk not in {s.pk for s in current}]
    ShelfLifeStudy.objects.filter(evaluation=locked, study_id__in=removed).delete()
    ShelfLifeStudy.objects.bulk_create(
        ShelfLifeStudy(evaluation=locked, study=study) for study in added
    )
    locked.direction = direction
    locked.purpose = purpose.strip()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="shelf_life.changed",
        obj=locked,
        before=before,
        after=_shelf_life_after(locked, _linked_studies(locked)),
        reason=reason,
    )
    return locked


@transaction.atomic
def withdraw_shelf_life(*, actor, evaluation, expected_revision, reason):
    """Withdraw a draft that will not be concluded; a new draft of its scope can follow."""
    from .models import ShelfLifeEvaluation

    require_role(actor, "quality")
    _need_reason(reason)
    lock_account(actor)
    locked = _locked_shelf_life(evaluation, expected_revision)
    before = snapshot(locked)
    locked.state = ShelfLifeEvaluation.State.WITHDRAWN
    locked.withdrawn_at = timezone.now()
    locked.revision += 1
    locked.full_clean()
    locked.save()
    record_event(
        actor=actor,
        action="shelf_life.withdrawn",
        obj=locked,
        before=before,
        after=snapshot(locked),
        reason=reason,
    )
    return locked


def shelf_life_drafters(evaluation):
    return set(
        AuditEvent.objects.filter(
            object_type=evaluation._meta.label_lower,
            object_id=str(evaluation.pk),
            action__in=SHELF_LIFE_DRAFTERS,
        ).values_list("actor_id", flat=True)
    ) | {evaluation.drafted_by_id}


def shelf_life_authors(evaluation, result):
    """Who may not conclude the evaluation: its drafters and the authors of its results' data.
    Reviewing a result or accepting a pull is not authorship."""
    from .evidence import results_author_ids

    return shelf_life_drafters(evaluation) | results_author_ids(result.tests)


def shelf_life_problems(result, outcome=None, months=None):
    """Why a conclusion with ``outcome`` and ``months`` cannot be signed, in the page's words."""
    from .models import ShelfLifeEvaluation

    Outcome = ShelfLifeEvaluation.Outcome
    if result.analysis is None:
        return [result.problem]
    problems = []
    longest = result.longest_supported
    if outcome == Outcome.SUPPORTED:
        if longest == 0 and result.estimate.months == 0:
            problems.append(
                "The confidence limit meets the acceptance criterion at time zero, so the data "
                "support no shelf life."
            )
        elif longest == 0:
            problems.append(
                "The estimate is under one month, so the data support no whole month of shelf life."
            )
        elif months is None or months < 1:
            problems.append("State the shelf life in whole months.")
        elif months > longest:
            problems.append(
                f"The data support at most {longest} months: the estimate rounded down to "
                "whole months."
            )
    elif outcome == Outcome.NOT_SUPPORTED and months is not None:
        problems.append("Leave the shelf life empty when the data support none.")
    elif outcome is not None and outcome not in Outcome.values:
        problems.append("Choose the outcome.")
    return problems


def shelf_life_denial(actor, evaluation, result):
    """Why ``actor`` cannot conclude ``evaluation`` now, or "". Signing checks again under
    lock."""
    from .models import ShelfLifeEvaluation

    if evaluation.state != ShelfLifeEvaluation.State.DRAFT:
        return f"{evaluation.identifier} is {evaluation.get_state_display().lower()}."
    if actor.pk in shelf_life_authors(evaluation, result):
        return INDEPENDENT_SHELF_LIFE
    if problems := shelf_life_problems(result):
        return "Not ready to conclude. " + " ".join(problems)
    return ""


@sensitive_variables("pin")
def conclude_shelf_life(
    *,
    actor,
    pin,
    evaluation,
    expected_revision,
    data_hash,
    reason,
    outcome,
    shelf_life_months,
    conclusion,
):
    """Conclude a draft with a signature that freezes its results, its figures and the shelf
    life recorded. The signer saw the figures of ``data_hash``; a change since refuses it."""
    from .models import ShelfLifeEvaluation
    from .shelf_life import data_digest, frozen
    from .shelf_life import of as result_of

    def lock():
        # A pull acceptance locks its study, so no result of these studies is added while the
        # conclusion reads them.
        list(
            Study.objects.select_for_update(no_key=True)
            .filter(shelf_life_links__evaluation_id=evaluation.pk)
            .order_by("pk")
        )

    def apply(locked):
        if locked.state != ShelfLifeEvaluation.State.DRAFT:
            raise ValidationError(
                f"{locked.identifier} is {locked.get_state_display().lower()}: it no longer "
                "changes."
            )
        result = result_of(locked)
        if actor.pk in shelf_life_authors(locked, result):
            raise PermissionDenied(INDEPENDENT_SHELF_LIFE)
        if data_digest(locked, result) != data_hash:
            raise ValidationError(STALE_SHELF_LIFE)
        if outcome not in ShelfLifeEvaluation.Outcome.values:
            raise ValidationError({"outcome": "Choose the outcome."})
        if not (conclusion or "").strip():
            raise ValidationError({"conclusion": "State the conclusion and its basis."})
        if problems := shelf_life_problems(result, outcome, shelf_life_months):
            raise ValidationError(problems)
        locked.outcome = outcome
        locked.shelf_life_months = (
            shelf_life_months if outcome == ShelfLifeEvaluation.Outcome.SUPPORTED else None
        )
        locked.conclusion = conclusion.strip()
        locked.content, locked.content_hash = frozen(locked, result)
        locked.state = ShelfLifeEvaluation.State.CONCLUDED
        locked.concluded_at = locked._signing_timestamp

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=evaluation,
        expected_revision=expected_revision,
        meaning="concluded",
        reason=reason,
        permission="quality",
        apply=apply,
        prepare=lock,
    )
