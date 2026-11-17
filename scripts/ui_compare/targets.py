# Run by capture.py inside `manage.py shell -c`: prints {"target": "/path/", ...} as one JSON line.
# Each target picks a record in the state the page id names, from whatever synthetic data the
# database holds; a target with no matching record is left out and listed as a capture gap.
import json
import os

from django.urls import reverse

from analytical.models import AnalyticalTest, Investigation, QCBatch
from catalog.models import MethodRevision, SpecificationRevision
from core.models import RuleSet
from quality.models import Lot
from reporting.models import Report
from sampling.models import LotAssignment
from stability.models import Hold, Pull, Study


def lot_path(lot):
    return reverse("quality:lot_detail", args=[lot.pk]) if lot else None


def first(qs):
    return qs.order_by("pk").first()


def quarantine():
    return Lot.objects.filter(state="quarantine")


def ready_lot():
    from analytical import gates

    held = set(Hold.objects.filter(state="active").values_list("lot_id", flat=True))
    for lot in quarantine().exclude(pk__in=held).order_by("pk"):
        tests = AnalyticalTest.objects.filter(lot=lot)
        if (
            tests.exists()
            and not tests.exclude(state__in=["reviewed", "invalidated", "superseded"]).exists()
            and not gates.lot_blockers(lot)
            and LotAssignment.objects.filter(lot=lot, status="ready").exists()
        ):
            return lot
    return None


def test_path(test):
    return reverse("analytical:test_detail", args=[test.pk]) if test else None


def resolve(key):
    if key == "lot-quarantine":
        return lot_path(
            first(
                quarantine().filter(
                    pk__in=AnalyticalTest.objects.filter(state="open", kind="original").values(
                        "lot_id"
                    )
                )
            )
        )
    if key in ("lot-ready", "sign-disposition"):
        lot = ready_lot()
        if key == "lot-ready":
            return lot_path(lot)
        return reverse("quality:disposition", args=[lot.pk]) if lot else None
    if key == "lot-applicability":
        hold = first(LotAssignment.objects.filter(status="hold"))
        return lot_path(hold.lot) if hold else None
    if key == "lot-oos":
        inv = first(Investigation.objects.exclude(phase="closed"))
        return lot_path(inv.lot if hasattr(inv, "lot") else None) if inv else None
    if key == "lot-stability-hold":
        hold = first(Hold.objects.filter(state="active", lot__state="quarantine"))
        return lot_path(hold.lot) if hold else None
    if key == "lot-released":
        report = first(Report.objects.filter(version_count=1))
        return lot_path(report.lot) if report else None
    if key == "lot-amended":
        report = first(Report.objects.filter(version_count__gt=1))
        return lot_path(report.lot) if report else None
    if key == "lot-rejected":
        return lot_path(first(Lot.objects.filter(state="rejected")))
    if key == "lot-cancelled":
        return lot_path(first(Lot.objects.filter(state="cancelled")))
    if key == "lot-testing":
        inv = first(Investigation.objects.exclude(phase="closed"))
        lot = inv.lot if inv else first(quarantine())
        return reverse("analytical:lot_testing", args=[lot.pk]) if lot else None
    if key == "test-open":
        return test_path(first(AnalyticalTest.objects.filter(state="open", kind="original")))
    if key == "test-submitted":
        return test_path(first(AnalyticalTest.objects.filter(state="submitted")))
    if key == "test-oos":
        inv = first(Investigation.objects.exclude(phase="closed"))
        return test_path(inv.test if inv else None)
    if key == "test-invalidated":
        return test_path(first(AnalyticalTest.objects.filter(state="invalidated")))
    if key == "test-superseded":
        return test_path(first(AnalyticalTest.objects.filter(state="superseded")))
    if key == "test-retest":
        return test_path(first(AnalyticalTest.objects.filter(kind="retest")))
    if key == "investigation":
        inv = first(Investigation.objects.exclude(phase="closed")) or first(Investigation.objects)
        return reverse("analytical:investigation_detail", args=[inv.pk]) if inv else None
    if key == "batch":
        batch = first(QCBatch.objects.filter(state="open")) or first(QCBatch.objects)
        return reverse("analytical:batch_detail", args=[batch.pk]) if batch else None
    if key == "sampling-lot":
        assignment = first(LotAssignment.objects.filter(status="ready"))
        return reverse("sampling:lot", args=[assignment.lot_id]) if assignment else None
    if key in ("certificate", "certificate-version", "sign-coa-amend"):
        report = first(Report.objects.filter(version_count__gt=1)) or first(Report.objects)
        if not report:
            return None
        if key == "certificate":
            return reverse("reporting:detail", args=[report.pk])
        if key == "certificate-version":
            return reverse("reporting:version", args=[report.pk, 1])
        return reverse("reporting:amend_preview", args=[report.pk])
    if key == "sign-coa-issue":
        lot = first(Lot.objects.filter(state="released", reports__isnull=True))
        return reverse("reporting:issue_preview", args=[lot.pk]) if lot else None
    if key == "study":
        study = first(Study.objects.filter(state="active"))
        return reverse("stability:study_detail", args=[study.pk]) if study else None
    if key == "pull-overdue":
        for pull in Pull.objects.filter(state="scheduled").order_by("due_date"):
            if pull.timing()[0] == "overdue":
                return reverse("stability:pull_detail", args=[pull.pk])
        return None
    if key == "test-not-completed":
        return test_path(first(AnalyticalTest.objects.filter(state="not_completed")))
    if key == "sign-not-completed":
        test = first(AnalyticalTest.objects.filter(state="open", kind="original"))
        return reverse("analytical:test_not_completed", args=[test.pk]) if test else None
    if key == "sign-review":
        test = first(AnalyticalTest.objects.filter(state="submitted"))
        return reverse("analytical:test_review", args=[test.pk]) if test else None
    if key == "sign-rule":
        rule = first(RuleSet.objects.filter(status="draft"))
        return reverse("core:rule_approve", args=[rule.pk]) if rule else None
    if key == "sign-spec":
        revision = first(SpecificationRevision.objects.filter(status="draft"))
        return reverse("catalog:specification_approve", args=[revision.pk]) if revision else None
    if key == "sign-method":
        revision = first(MethodRevision.objects.filter(status="draft"))
        return reverse("catalog:method_approve", args=[revision.pk]) if revision else None
    raise KeyError(key)


found = {}
for key in filter(None, os.environ.get("UI_COMPARE_TARGETS", "").split(",")):
    try:
        path = resolve(key)
    except Exception as exc:  # noqa: BLE001 - reported as a capture gap
        path = None
        print(f"target {key}: {type(exc).__name__}: {exc}")
    if path:
        found[key] = path
print(json.dumps(found))
