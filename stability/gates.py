"""Read-only gates published for QC disposition (integrator), reporting and any disposal path.

Call inside the disposition/report/disposal transaction after locking the lot row. Holds bump the
lot revision while the lot is in quarantine, so a signature dialog opened before a hold was placed
goes stale instead of signing past it.
"""

from django.utils import timezone

from .models import Hold, RetentionObligation

SCHEMA = "stability.lot-holds/1"


def active_holds(lot, reserve=None):
    holds = Hold.objects.filter(lot_id=lot.pk, state=Hold.State.ACTIVE)
    if reserve is not None:
        holds = holds.filter(reserve__isnull=True) | holds.filter(reserve=reserve)
    return holds.select_related("reserve")


def lot_blockers(lot):
    """Messages that must block QC disposition; empty means no active hold applies."""
    return [
        f"{h.identifier} ({h.get_kind_display().lower()} hold) is active: {h.reason}"
        for h in active_holds(lot)
    ]


def disposal_blockers(lot, reserve=None, today=None):
    """Everything that currently prevents disposal. No disposal path exists in this foundation;
    this gate lets a later one prove every obligation and hold has cleared."""
    today = today or timezone.localdate()
    obligations = RetentionObligation.objects.filter(lot_id=lot.pk)
    if reserve is not None:
        obligations = obligations.filter(reserve__isnull=True) | obligations.filter(reserve=reserve)
    obligations = list(obligations)
    blockers = []
    if not obligations:
        blockers.append("No retention obligation is recorded; applicability is unresolved.")
    blockers += [b for o in obligations if (b := o.blocker(today))]
    blockers += (
        lot_blockers(lot)
        if reserve is None
        else [f"{h.identifier} is active: {h.reason}" for h in active_holds(lot, reserve)]
    )
    return blockers


def lot_hold_evidence(lot):
    """Frozen-ready JSON of holds and retention for a lot; nothing is recomputed later."""
    holds = Hold.objects.filter(lot_id=lot.pk).order_by("pk")
    obligations = RetentionObligation.objects.filter(lot_id=lot.pk).order_by("pk")
    return {
        "schema": SCHEMA,
        "lot": lot.number,
        "lot_revision": lot.revision,
        "holds": [
            {
                "hold": h.identifier,
                "kind": h.kind,
                "state": h.state,
                "reason": h.reason,
                "reference": h.reference,
                "placed_at": h.placed_at.isoformat(),
                "released_at": h.released_at.isoformat() if h.released_at else None,
            }
            for h in holds
        ],
        "retention": [
            {
                "anchor": o.anchor_kind,
                "anchor_date": o.anchor_date.isoformat() if o.anchor_date else None,
                "offset_months": o.offset_months,
                "retain_until": o.retain_until.isoformat() if o.retain_until else None,
                "basis": o.basis,
            }
            for o in obligations
        ],
    }
