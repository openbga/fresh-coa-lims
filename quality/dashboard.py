"""Dashboard: the QC flow as work queues (lot, samples, results, review, disposition, certificate).

Every queue is one aggregate query (its count and its oldest date) over the very queryset its
linked list filters by (LOT_QUEUES for the material lot list, the lists' own filters elsewhere),
so a count always equals the rows of the list it opens (tests/test_dashboard.py). Counts are not
scoped per user: every reader role sees the same laboratory, like the lists; the services decide
who may act. No queue loops over lots in Python. A lot can sit in two queues; a stage total is
the sum of its queues.
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


# The lot queues, by the key the material lot list filters on (?queue=<key>): the dashboard
# counts lot_queues()[key] and links to the list filtered by the same queryset.
LOT_QUEUES = {
    "not-assigned": "Requirements not assigned",
    "applicability-hold": "Applicability hold",
    "no-supplier-certificate": "Supplier certificate not recorded",
    "awaiting-sampling": "Awaiting sampling",
    "untested-samples": "Samples without assigned tests",
    "supplier-results": "Supplier results awaiting acceptance",
    "results-reviewed": "All results reviewed",
    "investigation": "Blocked by an investigation",
    "certificate": "Certificates to issue",
}


def lot_queues():
    """{key: Lot queryset} for LOT_QUEUES (lazy; nothing is queried until used)."""
    from analytical.models import AnalyticalTest, Investigation
    from reporting.models import Report
    from sampling.models import LotAssignment, SamplingRecord

    from . import dates

    latest = LotAssignment.objects.filter(lot=OuterRef("pk")).order_by("-assigned_at", "-id")
    quarantine = Lot.objects.filter(state="quarantine").annotate(
        requirement_status=Subquery(latest.values("status")[:1])
    )
    lot_tests = AnalyticalTest.objects.filter(lot=OuterRef("pk"))
    supplied = LotReceipt.objects.filter(
        lot=OuterRef("pk"), corrected_by__isnull=True, source="supplier"
    )
    certificate = SupplierCertificate.objects.filter(
        lot=OuterRef("pk"), corrected_by__isnull=True, withdrawal__isnull=True
    )
    return {
        "not-assigned": quarantine.filter(requirement_status__isnull=True),
        "applicability-hold": quarantine.filter(requirement_status="hold"),
        "no-supplier-certificate": quarantine.filter(Exists(supplied), ~Exists(certificate)),
        "awaiting-sampling": quarantine.filter(requirement_status="ready").filter(
            ~Exists(Sample.objects.filter(lot=OuterRef("pk"))),
            ~Exists(SamplingRecord.objects.filter(lot=OuterRef("pk"))),
        ),
        "untested-samples": quarantine.filter(
            Exists(
                Sample.objects.filter(lot=OuterRef("pk")).filter(
                    ~Exists(AnalyticalTest.objects.filter(sample=OuterRef("pk")))
                )
            )
        ),
        "supplier-results": quarantine.filter(
            Exists(SupplierResultAcceptance.objects.filter(lot=OuterRef("pk"), state="proposed"))
        ),
        "results-reviewed": quarantine.filter(requirement_status="ready").filter(
            Exists(lot_tests.filter(state="reviewed")),
            ~Exists(lot_tests.filter(state__in=("open", "submitted"))),
            ~Exists(Investigation.objects.filter(lot=OuterRef("pk")).exclude(phase="closed")),
        ),
        "investigation": quarantine.filter(
            Exists(
                Investigation.objects.filter(lot=OuterRef("pk")).filter(
                    ~Q(phase="closed") | Q(outcome="confirmed")
                )
            )
        ),
        # Lots that can take a certificate: not expired, not due for retest, still in use.
        "certificate": dates.usable(
            dates.annotate_in_force(Lot.objects.filter(state="released")), dates.today()
        ).filter(~Exists(Report.objects.filter(lot=OuterRef("pk"), state="issued"))),
    }


def lanes():
    from analytical.models import AnalyticalTest, Investigation
    from analytical.views import TEST_FILTERS
    from sampling.views import deviation_to_assess

    lots = lot_queues()
    lot_list = reverse("quality:lot_list")
    tests = reverse("analytical:test_list")

    def lot_queue(key, oldest="created_at", **options):
        return queue(LOT_QUEUES[key], lots[key], oldest, url=f"{lot_list}?queue={key}", **options)

    def test_queue(key, label, oldest, **options):
        return queue(
            label,
            AnalyticalTest.objects.filter(TEST_FILTERS[key][1]),
            oldest,
            url=f"{tests}?state={key}",
            **options,
        )

    return [
        Lane(
            "lots",
            "Lots",
            "box-seam",
            [
                lot_queue("not-assigned", tone="warning", status="Not assigned"),
                lot_queue("applicability-hold", tone="warning", status="Applicability hold"),
                lot_queue("no-supplier-certificate", tone="info"),
            ],
        ),
        Lane(
            "samples",
            "Samples",
            "eyedropper",
            [
                lot_queue("awaiting-sampling", tone="neutral", status="Requirements assigned"),
                queue(
                    "Sampling deviations to assess",
                    deviation_to_assess(),
                    "created_at",
                    tone="warning",
                    status="Awaiting quality assessment",
                    url=reverse("sampling:lots") + "?status=deviation",
                ),
                lot_queue("untested-samples", tone="neutral"),
            ],
        ),
        Lane(
            "results",
            "Results",
            "clipboard2-data",
            [
                test_queue("open", "Tests open", "created_at", tone="neutral", status="Open"),
                queue(
                    "Out of specification, investigation open",
                    Investigation.objects.exclude(phase="closed"),
                    "opened_at",
                    tone="danger",
                    status="Investigation open",
                    url=reverse("analytical:investigation_list") + "?state=open",
                ),
                test_queue(
                    "repeats",
                    "Retests and resamples not done",
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
                test_queue(
                    "submitted",
                    "Awaiting review",
                    "evaluated_at",
                    tone="info",
                    status="Awaiting review",
                ),
                lot_queue("supplier-results", tone="info", status="Awaiting acceptance"),
            ],
        ),
        Lane(
            "disposition",
            "Disposition",
            "clipboard-check",
            [
                lot_queue("results-reviewed", tone="success", status="Complete"),
                lot_queue("investigation", tone="warning", status="Blocked"),
            ],
        ),
        Lane(
            "certificates",
            "Certificates",
            "file-earmark-check",
            [lot_queue("certificate", tone="neutral", status="Not issued")],
        ),
    ]


def gates():
    """Retest, stability and laboratory queues, from the same base and filters as the lists
    they link to."""
    from laboratory.eligibility import equipment_filter, equipment_queryset
    from laboratory.models import ReagentLot
    from stability.models import Hold, Pull
    from stability.views import _pull_filter

    from . import dates

    today = timezone.localdate()
    pulls = Pull.objects.all()  # the pull list's own base: its filters decide what is due
    pull_list = reverse("stability:pull_list")
    # The material lot list's own base and Dates filter, on the same local date.
    lots = dates.annotate_in_force(Lot.objects.all())
    lot_list = reverse("quality:lot_list")
    on = dates.today()
    return [
        queue(
            "Retest due",
            dates.filter_in_force(lots, dates.RETEST_DUE, on),
            "date_retest",
            tone="warning",
            status="Retest due",
            url=f"{lot_list}?dates={dates.RETEST_DUE}",
        ),
        queue(
            "Reassessments open",
            dates.filter_in_force(lots, dates.REASSESSING, on),
            "created_at",
            tone="progress",
            status="Reassessment open",
            url=f"{lot_list}?dates={dates.REASSESSING}",
        ),
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
            _pull_filter(pulls, "pulled", today),
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
            status="Calibration overdue",
            url=reverse("laboratory:equipment_list") + "?status=overdue",
        ),
        queue(
            "Reagent lots awaiting release",
            ReagentLot.objects.filter(state="received"),
            "received_on",
            tone="info",
            status=ReagentLot.State.RECEIVED.label,
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
