"""Where a lot is in the QC flow: six stages derived from recorded data only (Line §5).

Lot (requirements), Samples, Results, Review, Disposition, Certificate. Presentation only: it
reads the assignment status, sample and test counts, the lot state and issued certificates, and
decides nothing. The lot record shows the full route (route()); the lot list annotates the same
counts in its one query (annotate_route()) and shows the micro route with one line of text.
Each stage is {key, label, state, progress, detail}; state is done | current | held | rejected |
pending, progress is the current stage's done fraction in steps of 10 (CSS attribute rules).
"""

from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

COUNTED = Q(state__in=("open", "submitted", "reviewed"))  # superseded/invalidated never count
LABELS = ("Lot", "Samples", "Results", "Review", "Disposition", "Certificate")


def _progress(done, total):
    return round(done * 10 / total) * 10 if total else 0


def stages(*, state, assignment, samples, tests, entered, reviewed, issued, investigation_open):
    """The six stages from plain counts (shared by the record and the list)."""
    if state == "cancelled":
        details = ("Received in error", "", "", "", "", "")
        return [
            {"key": label.lower(), "label": label, "state": "pending", "progress": 0, "detail": d}
            for label, d in zip(LABELS, details, strict=True)
        ]
    decided = state in ("released", "rejected")
    result = []

    def add(label, done, detail, *, held=False, progress=0):
        reached = all(s["state"] == "done" for s in result)
        if done:
            kind = "done"
        elif held and reached:
            kind = "held"
        elif reached:
            kind = "current"
        else:
            kind = "pending"
        result.append(
            {
                "key": label.lower(),
                "label": label,
                "state": kind,
                "progress": progress if kind in ("current", "held") else 0,
                "detail": detail,
            }
        )

    if assignment == "ready":
        add("Lot", True, "Requirements assigned")
    elif assignment == "hold":
        add("Lot", decided, "Applicability hold", held=True)
    else:
        add("Lot", decided, "Not assigned")
    add("Samples", samples > 0 or decided, f"{samples} sample{'s' if samples != 1 else ''}")
    add(
        "Results",
        (tests > 0 and entered == tests) or decided,
        f"{entered} of {tests} entered" if tests else "No tests",
        progress=_progress(entered, tests),
    )
    add(
        "Review",
        (tests > 0 and reviewed == tests) or decided,
        f"{reviewed} of {tests} reviewed" if tests else "No tests",
        held=investigation_open,
        progress=_progress(reviewed, tests),
    )
    if state == "released":
        add("Disposition", True, "Released")
    elif state == "rejected":
        result.append(
            {
                "key": "disposition",
                "label": "Disposition",
                "state": "rejected",
                "progress": 0,
                "detail": "Rejection signed",
            }
        )
    else:
        add(
            "Disposition",
            False,
            "Investigation open" if investigation_open else "Not decided",
            held=investigation_open,
        )
    if state == "released":
        add("Certificate", issued, "Certificate issued" if issued else "Not issued")
    else:
        result.append(
            {
                "key": "certificate",
                "label": "Certificate",
                "state": "pending",
                "progress": 0,
                "detail": "",
            }
        )
    return result


def summary(route):
    """One line for the lot list: the current (or held) stage's detail, else the last done one."""
    for stage in route:
        if stage["state"] in ("current", "held", "rejected"):
            return stage["detail"]
    done = [s for s in route if s["state"] == "done"]
    if done:
        return done[-1]["detail"]
    return route[0]["detail"]


def route(lot, *, assignment, tests, investigations, reports):
    """The lot record's route from what its view already loaded."""
    counted = [t for t in tests if t.state in ("open", "submitted", "reviewed")]
    return stages(
        state=lot.state,
        assignment=assignment.status if assignment else "",
        samples=lot.samples.count(),
        tests=len(counted),
        entered=sum(1 for t in counted if t.state in ("submitted", "reviewed")),
        reviewed=sum(1 for t in counted if t.state == "reviewed"),
        issued=any(r.state == "issued" for r in reports),
        investigation_open=any(i.is_open for i in investigations),
    )


def annotate_route(lots):
    """The lot list's queryset with the route counts, in the same single query."""
    from analytical.models import AnalyticalTest, Investigation
    from reporting.models import Report
    from sampling.models import LotAssignment

    def count(filter_q):
        subquery = (
            AnalyticalTest.objects.filter(lot=OuterRef("pk"))
            .filter(filter_q)
            .order_by()
            .values("lot")
            .annotate(n=Count("pk"))
            .values("n")
        )
        return Coalesce(Subquery(subquery, output_field=IntegerField()), 0)

    samples = (
        lots.model.samples.rel.related_model.objects.filter(lot=OuterRef("pk"))
        .order_by()
        .values("lot")
        .annotate(n=Count("pk"))
        .values("n")
    )
    return lots.annotate(
        route_assignment=Subquery(
            LotAssignment.objects.filter(lot=OuterRef("pk"))
            .order_by("-assigned_at", "-id")
            .values("status")[:1]
        ),
        route_material_kind=Subquery(
            LotAssignment.objects.filter(lot=OuterRef("pk"))
            .order_by("-assigned_at", "-id")
            .values("material__kind")[:1]
        ),
        route_material_code=Subquery(
            LotAssignment.objects.filter(lot=OuterRef("pk"))
            .order_by("-assigned_at", "-id")
            .values("material__code")[:1]
        ),
        route_samples=Coalesce(Subquery(samples, output_field=IntegerField()), 0),
        route_tests=count(COUNTED),
        route_entered=count(Q(state__in=("submitted", "reviewed"))),
        route_reviewed=count(Q(state="reviewed")),
        route_issued=Exists(Report.objects.filter(lot=OuterRef("pk"), state="issued")),
        route_investigation=Exists(
            Investigation.objects.filter(lot=OuterRef("pk")).exclude(phase="closed")
        ),
        route_investigation_phase=Subquery(
            Investigation.objects.filter(lot=OuterRef("pk"))
            .exclude(phase="closed")
            .order_by("-opened_at", "-pk")
            .values("phase")[:1]
        ),
    )


def hold_labels(lot):
    """The second Status pills of an annotated lot: (label, tone) for an applicability hold and
    the newest open investigation's phase, with the app's own labels."""
    from analytical.models import Investigation
    from sampling.models import AssignmentStatus

    labels = []
    if lot.route_assignment == AssignmentStatus.HOLD:
        labels.append((AssignmentStatus.HOLD.label, "warning"))
    if lot.route_investigation_phase:
        labels.append((Investigation.Phase(lot.route_investigation_phase).label, "danger"))
    return labels


def list_route(lot):
    """The micro route of an annotated lot (annotate_route)."""
    return stages(
        state=lot.state,
        assignment=lot.route_assignment or "",
        samples=lot.route_samples,
        tests=lot.route_tests,
        entered=lot.route_entered,
        reviewed=lot.route_reviewed,
        issued=lot.route_issued,
        investigation_open=lot.route_investigation,
    )
