"""Dashboard: the QC flow as work queues (lot, samples, results, review, disposition, certificate).

Every queue is one aggregate query (its count and its oldest date) on the same conditions the
linked list uses where a list filter exists, so a count and its list agree. Counts are not scoped
per user: every reader role sees the same laboratory, like the lists; the services decide who may
act. No queue loops over lots in Python. A lot can sit in two queues; a stage total is the sum of
its queues.
"""

from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Exists, Min, OuterRef, Q, Subquery
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Lot, LotReceipt, Sample, SupplierCertificate, SupplierResultAcceptance


@dataclass
class Queue:
    label: str
    count: int
    oldest: object  # a date or datetime, or None
    tone: str  # status tone shown when count > 0
    status: str  # the status label of what is queued ("" for none)
    url: str  # the list (or filtered list) that shows the queue, or ""


@dataclass
class Lane:
    key: str
    label: str
    icon: str
    queues: list

    @property
    def total(self):
        return sum(queue.count for queue in self.queues)


def queue(label, queryset, oldest_field, *, tone, status="", url=""):
    """One aggregate query: the count and, when the queue has a date, its oldest."""
    if oldest_field is None:
        return Queue(label, queryset.count(), None, tone, status, url)
    values = queryset.aggregate(n=Count("pk"), oldest=Min(oldest_field))
    return Queue(label, values["n"], values["oldest"], tone, status, url)


def lanes():
    from analytical.models import AnalyticalTest, Investigation
    from reporting.models import Report
    from sampling.models import DeviationReview, LotAssignment, SamplingRecord

    latest = LotAssignment.objects.filter(lot=OuterRef("pk")).order_by("-assigned_at", "-id")
    quarantine = Lot.objects.filter(state="quarantine").annotate(
        requirement_status=Subquery(latest.values("status")[:1])
    )
    lot_tests = AnalyticalTest.objects.filter(lot__isnull=False)
    open_investigation = Investigation.objects.filter(lot=OuterRef("pk")).exclude(phase="closed")
    sampling = reverse("sampling:lots")
    tests = reverse("analytical:test_list")
    lots = reverse("quality:lot_list")
    supplied = LotReceipt.objects.filter(
        lot=OuterRef("pk"), corrected_by__isnull=True, source="supplier"
    )
    certificate = SupplierCertificate.objects.filter(
        lot=OuterRef("pk"), corrected_by__isnull=True, withdrawal__isnull=True
    )
    return [
        Lane(
            "lots",
            "Lots",
            "box-seam",
            [
                queue(
                    "Requirements not assigned",
                    quarantine.filter(requirement_status__isnull=True),
                    "created_at",
                    tone="warning",
                    status="Not assigned",
                    url=f"{sampling}?status=none",
                ),
                queue(
                    "Applicability hold",
                    quarantine.filter(requirement_status="hold"),
                    "created_at",
                    tone="warning",
                    status="Applicability hold",
                    url=f"{sampling}?status=hold",
                ),
                queue(
                    "Supplier certificate not recorded",
                    quarantine.filter(Exists(supplied), ~Exists(certificate)),
                    "created_at",
                    tone="info",
                ),
            ],
        ),
        Lane(
            "samples",
            "Samples",
            "eyedropper",
            [
                queue(
                    "Awaiting sampling",
                    quarantine.filter(requirement_status="ready").filter(
                        ~Exists(Sample.objects.filter(lot=OuterRef("pk"))),
                        ~Exists(SamplingRecord.objects.filter(lot=OuterRef("pk"))),
                    ),
                    "created_at",
                    tone="neutral",
                    status="Requirements assigned",
                    url=f"{sampling}?status=ready",
                ),
                queue(
                    "Sampling deviations to assess",
                    DeviationReview.objects.filter(
                        status="pending",
                        record__corrected_by__isnull=True,
                        record__lot__state="quarantine",
                    ),
                    "created_at",
                    tone="warning",
                ),
                queue(
                    "Samples without assigned tests",
                    Sample.objects.filter(lot__state="quarantine").filter(
                        ~Exists(AnalyticalTest.objects.filter(sample=OuterRef("pk")))
                    ),
                    "collected_at",
                    tone="neutral",
                ),
            ],
        ),
        Lane(
            "results",
            "Results",
            "clipboard2-data",
            [
                queue(
                    "Tests open",
                    lot_tests.filter(state="open"),
                    "created_at",
                    tone="neutral",
                    status="Open",
                    url=f"{tests}?state=open",
                ),
                queue(
                    "Out of specification, investigation open",
                    Investigation.objects.filter(lot__isnull=False).exclude(phase="closed"),
                    "opened_at",
                    tone="danger",
                    status="Investigation open",
                    url=reverse("analytical:investigation_list") + "?state=open",
                ),
                queue(
                    "Retests and resamples not done",
                    lot_tests.filter(
                        kind__in=("retest", "resample"), state__in=("open", "submitted")
                    ),
                    "created_at",
                    tone="progress",
                ),
            ],
        ),
        Lane(
            "review",
            "Review",
            "clipboard2-check",
            [
                queue(
                    "Awaiting review",
                    lot_tests.filter(state="submitted"),
                    "evaluated_at",
                    tone="info",
                    status="Awaiting review",
                    url=f"{tests}?state=submitted",
                ),
                queue(
                    "Supplier results awaiting acceptance",
                    SupplierResultAcceptance.objects.filter(state="proposed"),
                    "proposed_at",
                    tone="info",
                    status="Awaiting acceptance",
                ),
            ],
        ),
        Lane(
            "disposition",
            "Disposition",
            "clipboard-check",
            [
                queue(
                    "All results reviewed",
                    quarantine.filter(requirement_status="ready").filter(
                        Exists(lot_tests.filter(lot=OuterRef("pk"), state="reviewed")),
                        ~Exists(
                            lot_tests.filter(lot=OuterRef("pk"), state__in=("open", "submitted"))
                        ),
                        ~Exists(open_investigation),
                    ),
                    "created_at",
                    tone="success",
                    status="Quarantine",
                    url=f"{lots}?state=quarantine",
                ),
                queue(
                    "Blocked by an investigation",
                    quarantine.filter(
                        Exists(
                            Investigation.objects.filter(lot=OuterRef("pk")).filter(
                                ~Q(phase="closed") | Q(outcome="confirmed")
                            )
                        )
                    ),
                    "created_at",
                    tone="danger",
                    status="Quarantine",
                    url=f"{lots}?state=quarantine",
                ),
            ],
        ),
        Lane(
            "certificates",
            "Certificates",
            "file-earmark-check",
            [
                queue(
                    "Certificates to issue",
                    Lot.objects.filter(state="released").filter(
                        ~Exists(Report.objects.filter(lot=OuterRef("pk"), state="issued"))
                    ),
                    "created_at",
                    tone="neutral",
                    status="Not issued",
                    url=reverse("reporting:list"),
                ),
            ],
        ),
    ]


def gates():
    """Stability and laboratory queues, from the same filters as their own overview pages."""
    from laboratory.eligibility import equipment_filter, equipment_queryset
    from laboratory.models import ReagentLot
    from stability.models import Hold, Pull, Study
    from stability.views import _pull_filter

    today = timezone.localdate()
    pulls = Pull.objects.filter(study__state=Study.State.ACTIVE)
    pull_list = reverse("stability:pull_list")
    return [
        queue(
            "Pulls overdue",
            _pull_filter(pulls, "overdue", today),
            "due_date",
            tone="danger",
            status="Overdue",
            url=f"{pull_list}?status=overdue",
        ),
        queue(
            "Pulls due now",
            _pull_filter(pulls, "due", today),
            "due_date",
            tone="warning",
            status="Due now",
            url=f"{pull_list}?status=due",
        ),
        queue(
            "Pulls awaiting acceptance",
            pulls.filter(state="pulled"),
            "due_date",
            tone="info",
            status="Awaiting acceptance",
            url=f"{pull_list}?status=pulled",
        ),
        queue(
            "Active holds",
            Hold.objects.filter(state=Hold.State.ACTIVE),
            "placed_at",
            tone="hold",
            status="Active",
            url=reverse("stability:hold_list") + "?status=active",
        ),
        queue(
            "Calibration overdue",
            equipment_filter(equipment_queryset(today), "overdue", today),
            None,
            tone="danger",
            url=reverse("laboratory:equipment_list") + "?status=overdue",
        ),
        queue(
            "Reagent lots awaiting release",
            ReagentLot.objects.filter(state="received"),
            "received_on",
            tone="info",
            url=reverse("laboratory:reagent_list") + "?status=received",
        ),
    ]


@login_required
@require_GET
def dashboard(request):
    """The home page: the QC flow's queues, recently received lots, stability and lab gates."""
    from accounts.services import ROLES

    from . import route
    from .views import access

    if not request.user.groups.filter(name__in=ROLES).exists():
        return redirect("accounts:access")
    access(request.user)
    flow = lanes()
    recent = list(
        route.annotate_route(Lot.objects.select_related("rules").order_by("-created_at", "-pk"))[:8]
    )
    for lot in recent:
        lot.route = route.list_route(lot)
        lot.route_summary = route.summary(lot.route)
        lot.hold_labels = route.hold_labels(lot)
    return render(
        request,
        "quality/dashboard.html",
        {
            "page_title": "Dashboard",
            "lanes": flow,
            "total": sum(lane.total for lane in flow),
            "recent": recent,
            "gates": gates(),
            "can_receive": request.user.groups.filter(name="analyst").exists(),
        },
    )
