"""Read-only eligibility gates published for analytical/testing and reporting modules.

Each gate returns a `Finding` with the current reasons for refusal and the evidence relied on.
`at` allows boundary evaluation of dated evidence; state flags (out of service, rejected) are the
current state, so historical use is proven by `ResourceUse`, never re-derived.
"""

from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from .models import Calibration, Equipment, Qualification, ReagentLot, ResourceUse

EQUIPMENT_STATES = Equipment.State
DUE_SOON_DAYS = 30


@dataclass(frozen=True)
class Finding:
    subject: str
    ok: bool
    reasons: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)


def _today(at):
    return timezone.localdate(at)


def counted_calibrations(equipment, at):
    """Calibrations that decide fitness: any failure, and independently accepted passes."""
    return [
        c
        for c in equipment.calibrations.all()
        if c.performed_at <= at
        and (
            c.outcome == Calibration.Outcome.FAIL
            or (c.state == Calibration.State.ACCEPTED and c.accepted_at and c.accepted_at <= at)
        )
    ]


def latest_calibration(equipment, at=None):
    at = at or timezone.now()
    return max(
        counted_calibrations(equipment, at), key=lambda c: (c.performed_at, c.pk), default=None
    )


def qualification_valid(qualification, at):
    return (
        qualification.state in (Qualification.State.APPROVED, Qualification.State.REVOKED)
        and qualification.approved_at is not None
        and qualification.approved_at <= at
        and qualification.valid_from <= _today(at) <= qualification.valid_until
        and (qualification.revoked_at is None or qualification.revoked_at > at)
    )


def equipment_eligibility(equipment, at=None):
    at = at or timezone.now()
    reasons = []
    evidence = {"asset_id": equipment.asset_id}
    if equipment.state != EQUIPMENT_STATES.IN_SERVICE:
        reasons.append("Equipment is out of service.")
    latest = latest_calibration(equipment, at)
    if latest is None:
        reasons.append("No independently accepted calibration is on record.")
    elif latest.outcome == Calibration.Outcome.FAIL:
        reasons.append(
            "The latest calibration failed; a passing calibration after the failure must be "
            "independently accepted."
        )
    else:
        evidence["calibration"] = latest.pk
        evidence["calibration_due"] = latest.due_date.isoformat()
        if _today(at) > latest.due_date:
            reasons.append(f"Calibration expired after {latest.due_date.isoformat()}.")
    if equipment.requires_qualification:
        qualified = [q for q in equipment.qualifications.all() if qualification_valid(q, at)]
        if qualified:
            evidence["qualification"] = max(qualified, key=lambda q: q.pk).pk
        else:
            reasons.append("No approved, current qualification evidence for this equipment.")
    return Finding(equipment.asset_id, not reasons, tuple(reasons), evidence)


def reagent_lineage(reagent):
    """Every ancestor source lot, nearest first (preparations may be nested)."""
    chain, seen, node = [], {reagent.pk}, reagent
    while node.parent_id and node.parent_id not in seen:
        node = node.parent
        seen.add(node.pk)
        chain.append(node)
    return chain


def reagent_eligibility(reagent, at=None):
    at = at or timezone.now()
    reasons = []
    evidence = {"identifier": reagent.identifier}
    if reagent.state == ReagentLot.State.REJECTED:
        reasons.append("Lot was rejected.")
    elif reagent.state != ReagentLot.State.RELEASED or (
        reagent.released_at is None or reagent.released_at > at
    ):
        reasons.append("Lot has not been independently released for use.")
    else:
        evidence["released_at"] = reagent.released_at.isoformat()
    if reagent.received_on > _today(at):
        reasons.append(
            f"Receipt or preparation is dated {reagent.received_on.isoformat()}, in the future."
        )
    if _today(at) > reagent.expiry_date:
        reasons.append(f"Lot expired after {reagent.expiry_date.isoformat()}.")
    ancestors = reagent_lineage(reagent)
    for source in ancestors:
        if source.state == ReagentLot.State.REJECTED:
            reasons.append(f"Source lot {source.identifier} was rejected.")
        elif source.state != ReagentLot.State.RELEASED:
            reasons.append(f"Source lot {source.identifier} is not released.")
        if _today(at) > source.expiry_date:
            reasons.append(f"Source lot {source.identifier} expired.")
    if ancestors:
        evidence["lineage"] = [source.identifier for source in ancestors]
    return Finding(reagent.identifier, not reasons, tuple(reasons), evidence)


def analyst_eligibility(user, activity, at=None):
    at = at or timezone.now()
    activity = (activity or "").strip()
    reasons = []
    evidence = {"user": user.pk, "activity": activity}
    if not user.is_active:
        reasons.append("The account is inactive.")
    candidates = Qualification.objects.filter(user=user, activity__iexact=activity)
    qualified = [q for q in candidates if qualification_valid(q, at)] if activity else []
    if qualified:
        evidence["qualification"] = max(qualified, key=lambda q: q.pk).pk
    else:
        reasons.append(f"No approved, current qualification for “{activity or 'activity'}”.")
    return Finding(user.get_username(), not reasons, tuple(reasons), evidence)


def check_use(*, analyst, activity, equipment=(), reagents=(), at=None):
    """All findings for one proposed piece of work; the work is allowed only if every one is ok."""
    at = at or timezone.now()
    findings = [analyst_eligibility(analyst, activity, at)]
    findings += [equipment_eligibility(item, at) for item in equipment]
    findings += [reagent_eligibility(item, at) for item in reagents]
    return findings


def unassessed_failures(equipment):
    """Failed calibrations recorded since the last signed return to service (or ever)."""
    from core.models import ElectronicSignature

    returned = (
        ElectronicSignature.objects.filter(
            object_type="laboratory.equipment", object_id=str(equipment.pk), meaning="approved"
        )
        .order_by("-signed_at")
        .values_list("signed_at", flat=True)
        .first()
    )
    failures = equipment.calibrations.filter(outcome=Calibration.Outcome.FAIL)
    if returned is not None:
        failures = failures.filter(recorded_at__gt=returned)
    return failures.order_by("performed_at", "pk")


def affected_uses(equipment):
    """Uses since the last independently accepted passing calibration before the earliest
    failure not yet assessed by a signed return to service. A later passing calibration does not
    erase the interval: only the signed assessment closes it."""
    first = unassessed_failures(equipment).first()
    if first is None:
        return ResourceUse.objects.none()
    good = (
        equipment.calibrations.filter(
            outcome=Calibration.Outcome.PASS,
            state=Calibration.State.ACCEPTED,
            performed_at__lt=first.performed_at,
        )
        .order_by("-performed_at")
        .first()
    )
    uses = ResourceUse.objects.filter(equipment=equipment)
    if good:
        uses = uses.filter(used_at__gte=good.performed_at)
    return uses.order_by("used_at", "pk")


def equipment_queryset(today=None):
    """Equipment annotated with the latest deciding calibration and qualification status, so
    list filters and sorting run over the whole authorized queryset in SQL."""
    today = today or timezone.localdate()
    now = timezone.now()
    counted = Calibration.objects.filter(equipment=OuterRef("pk"), performed_at__lte=now).filter(
        Q(outcome=Calibration.Outcome.FAIL)
        | Q(state=Calibration.State.ACCEPTED, accepted_at__lte=now)
    )
    latest = counted.order_by("-performed_at", "-id")
    qualified = Qualification.objects.filter(
        equipment=OuterRef("pk"),
        state__in=[Qualification.State.APPROVED, Qualification.State.REVOKED],
        approved_at__lte=now,
        valid_from__lte=today,
        valid_until__gte=today,
    ).filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=now))
    return Equipment.objects.annotate(
        last_outcome=Subquery(latest.values("outcome")[:1]),
        last_due=Subquery(latest.values("due_date")[:1]),
        qualified=Exists(qualified),
    )


def equipment_status(equipment, today=None):
    """Display status from annotations: (label, tone, key). Agrees with equipment_eligibility."""
    today = today or timezone.localdate()
    if equipment.state != EQUIPMENT_STATES.IN_SERVICE:
        return "Out of service", "danger", "out_of_service"
    if equipment.last_outcome is None:
        return "Not calibrated", "warning", "unfit"
    if equipment.last_outcome == Calibration.Outcome.FAIL:
        return "Calibration failed", "danger", "unfit"
    if today > equipment.last_due:
        return "Calibration overdue", "danger", "overdue"
    if equipment.requires_qualification and not equipment.qualified:
        return "Not qualified", "warning", "unfit"
    if (equipment.last_due - today).days <= DUE_SOON_DAYS:
        return "Due soon", "warning", "due_soon"
    return "Ready", "success", "ready"


def equipment_filter(queryset, key, today=None):
    """SQL equivalent of equipment_status keys, for server-side filtering."""
    from datetime import timedelta

    today = today or timezone.localdate()
    in_service = Q(state=EQUIPMENT_STATES.IN_SERVICE)
    passing = Q(last_outcome=Calibration.Outcome.PASS)
    fit_q = Q(requires_qualification=False) | Q(qualified=True)
    if key == "out_of_service":
        return queryset.exclude(in_service)
    if key == "overdue":
        return queryset.filter(in_service, passing, last_due__lt=today)
    if key == "due_soon":
        return queryset.filter(
            in_service,
            passing,
            fit_q,
            last_due__gte=today,
            last_due__lte=today + timedelta(days=DUE_SOON_DAYS),
        )
    if key == "ready":
        return queryset.filter(
            in_service,
            passing,
            fit_q,
            last_due__gt=today + timedelta(days=DUE_SOON_DAYS),
        )
    if key == "unfit":
        return queryset.filter(in_service).filter(
            Q(last_outcome__isnull=True)
            | Q(last_outcome=Calibration.Outcome.FAIL)
            | (passing & Q(last_due__gte=today) & ~fit_q)
        )
    return queryset


def users_with_roles():
    return get_user_model().objects.filter(is_active=True).order_by("username")
