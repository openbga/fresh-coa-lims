"""Which records an impact assessment must cover: found from its cause, then followed through.

Read-only. The cause gives the first records:

- equipment: the tests whose results or QC batch used it, and the lots whose samples it was used
  for outside native testing, in the period of concern; and, for a stability chamber, the
  studies with pulls stored in it that were not closed before the period began;
- a reagent or standard lot: the same, for the lot and every solution prepared from it;
- a supplier: the lots whose receipt in force names it, received in the period;
- a contract laboratory: the tests whose results it reported in the period;
- anything else: nothing; quality adds the records.

Then every test leads to its lot (a lot's own test or a reassessment's) or to its stability
study, a lot found from a supplier to its stability studies, and every lot in the assessment,
found or added, to each certificate issued for it. A record already in the assessment is not
proposed again; what an earlier assessment decided is not read.
"""

import datetime
import re
from dataclasses import dataclass

from django.utils import timezone

from .models import Assessment, Item

KIND = Item.Kind
CAUSE = Assessment.Cause
CANONICAL_ID = re.compile(r"[1-9][0-9]{0,17}")
# A design default for a laboratory of moderate size: a cause that finds more is assessed in
# narrower periods, so that each record still gets a decision someone actually made.
MAX_RECORDS = 500


@dataclass(frozen=True)
class Candidate:
    kind: str
    pk: int
    basis: str

    @property
    def key(self):
        return (self.kind, self.pk)


def window(assessment):
    """The period of concern as [start, end) in the laboratory's time zone."""
    zone = timezone.get_current_timezone()
    start = datetime.datetime.combine(assessment.period_from, datetime.time.min, zone)
    end = datetime.datetime.combine(
        assessment.period_until + datetime.timedelta(days=1), datetime.time.min, zone
    )
    return start, end


def _day(moment):
    return timezone.localdate(moment).isoformat()


def reagent_lineage(reagent_id):
    """The reagent or standard lot and every solution prepared from it, at any depth."""
    from laboratory.models import ReagentLot

    found, frontier = {reagent_id}, {reagent_id}
    while frontier:
        children = set(
            ReagentLot.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)
        )
        frontier = children - found
        found |= frontier
    return found


def _uses(assessment):
    from laboratory.models import ResourceUse

    start, end = window(assessment)
    uses = ResourceUse.objects.filter(used_at__gte=start, used_at__lt=end)
    if assessment.cause == CAUSE.EQUIPMENT:
        uses = uses.filter(equipment_id=assessment.equipment_id)
    else:
        uses = uses.filter(reagent_lot_id__in=reagent_lineage(assessment.reagent_lot_id))
    return uses.select_related("equipment", "reagent_lot").order_by("used_at", "pk")


def _resource_name(use):
    if use.equipment_id:
        return use.equipment.asset_id
    return use.reagent_lot.identifier


def _from_uses(assessment, add):
    from analytical.models import AnalyticalTest
    from quality.models import Sample

    uses = list(_uses(assessment))
    tests, batches, samples = {}, {}, {}
    for use in uses:
        ident = str(use.context_id)
        if not CANONICAL_ID.fullmatch(ident):
            continue
        what = f"{_resource_name(use)} used on {_day(use.used_at)}"
        if use.context_type == "analytical.analyticaltest":
            tests.setdefault(int(ident), what)
        elif use.context_type == "analytical.qcbatch":
            batches.setdefault(int(ident), what)
        elif use.context_type == "quality.sample":
            samples.setdefault(int(ident), what)
    for pk, what in tests.items():
        add(Candidate(KIND.TEST, pk, f"{what} for this test."))
    for test in AnalyticalTest.objects.filter(batch_id__in=batches).select_related("batch"):
        add(
            Candidate(
                KIND.TEST,
                test.pk,
                f"{batches[test.batch_id]} for QC batch {test.batch.number}, which holds this "
                "test.",
            )
        )
    for sample in Sample.objects.filter(pk__in=samples):
        add(
            Candidate(
                KIND.LOT,
                sample.lot_id,
                f"{samples[sample.pk]} for sample {sample.reference}, outside native testing.",
            )
        )


def _chamber_studies(assessment, add):
    from stability.models import Pull

    start, _ = window(assessment)
    pulls = (
        Pull.objects.filter(chamber_id=assessment.equipment_id)
        # A study closed (completed or terminated) before the period began was not affected.
        .exclude(study__closed_at__lt=start)
        .select_related("study")
        .order_by("study_id", "pk")
    )
    for pull in pulls:
        add(
            Candidate(
                KIND.STUDY,
                pull.study_id,
                f"Pulls of this study were stored in {assessment.equipment.asset_id}.",
            )
        )


def _from_supplier(assessment, add):
    from quality.models import LotReceipt

    receipts = LotReceipt.objects.filter(
        supplier_id=assessment.supplier_id,
        corrected_by__isnull=True,
        received_on__gte=assessment.period_from,
        received_on__lte=assessment.period_until,
    ).order_by("received_on", "pk")
    for receipt in receipts:
        add(
            Candidate(
                KIND.LOT,
                receipt.lot_id,
                f"Received from {assessment.supplier.code} on {receipt.received_on.isoformat()}.",
            )
        )


def _from_contract_laboratory(assessment, add):
    from laboratory.models import ContractUse

    uses = ContractUse.objects.filter(
        approval__laboratory_id=assessment.contract_laboratory_id,
        context_type="analytical.analyticaltest",
        report_date__gte=assessment.period_from,
        report_date__lte=assessment.period_until,
    ).order_by("report_date", "pk")
    for use in uses:
        if CANONICAL_ID.fullmatch(str(use.context_id)):
            add(
                Candidate(
                    KIND.TEST,
                    int(use.context_id),
                    f"Reported by {assessment.contract_laboratory.code} in report "
                    f"{use.report_number} of {use.report_date.isoformat()}.",
                )
            )


def direct(assessment):
    """{key: Candidate} found from the cause alone, in a stable order."""
    found = {}

    def add(candidate):
        found.setdefault(candidate.key, candidate)

    if assessment.cause in (CAUSE.EQUIPMENT, CAUSE.REAGENT):
        _from_uses(assessment, add)
        if assessment.cause == CAUSE.EQUIPMENT:
            _chamber_studies(assessment, add)
    elif assessment.cause == CAUSE.SUPPLIER:
        _from_supplier(assessment, add)
    elif assessment.cause == CAUSE.CONTRACT:
        _from_contract_laboratory(assessment, add)
    return found


def _item_key(item):
    return (item.kind, item.target_id)


def candidates(assessment, items=None):
    """{key: Candidate} the assessment must cover: what the cause finds, then the lots, studies
    and certificates its tests and lots lead to, including those of records quality added."""
    from analytical.models import AnalyticalTest
    from reporting.models import Report
    from stability.models import Study

    items = list(assessment.items.all()) if items is None else items
    found = direct(assessment)

    def add(candidate):
        found.setdefault(candidate.key, candidate)

    present = {_item_key(item) for item in items} | set(found)
    test_ids = {pk for kind, pk in present if kind == KIND.TEST}
    for test in AnalyticalTest.objects.filter(pk__in=test_ids).select_related(
        "reassessment", "pull"
    ):
        if test.lot_id:
            add(Candidate(KIND.LOT, test.lot_id, f"Its test {test.label} is in the assessment."))
        elif test.reassessment_id:
            add(
                Candidate(
                    KIND.LOT,
                    test.reassessment.lot_id,
                    f"Its reassessment {test.reassessment.label} has test {test.label} in the "
                    "assessment.",
                )
            )
        elif test.pull_id:
            add(
                Candidate(
                    KIND.STUDY,
                    test.pull.study_id,
                    f"Its pull test {test.label} is in the assessment.",
                )
            )
    if assessment.cause == CAUSE.SUPPLIER:
        supplied = [pk for (kind, pk) in direct(assessment) if kind == KIND.LOT]
        for study in Study.objects.filter(lot_id__in=supplied).order_by("pk"):
            add(Candidate(KIND.STUDY, study.pk, f"A stability study of lot {study.lot.number}."))
    lot_ids = {pk for kind, pk in set(found) | present if kind == KIND.LOT}
    reports = Report.objects.filter(lot_id__in=lot_ids, version_count__gt=0).select_related("lot")
    for report in reports.order_by("lot_id", "sequence"):
        add(Candidate(KIND.CERTIFICATE, report.pk, f"Issued for lot {report.lot.number}."))
    return found


def missing(assessment, items=None):
    """Candidates that are not yet records of the assessment, in a stable order."""
    items = list(assessment.items.all()) if items is None else items
    present = {_item_key(item) for item in items}
    return [c for key, c in candidates(assessment, items).items() if key not in present]
