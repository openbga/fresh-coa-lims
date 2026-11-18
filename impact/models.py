"""The quality-owned assessment of what a failure affected.

An equipment, reagent or standard, supplier or contract-laboratory problem, or any other one, is
assessed for the tests, lots, stability studies and certificates it may have affected. The
system finds the records it can from the cause and the period of concern; quality adds any
other, records a decision for each, may place a protective hold on an affected lot through the
assessment, and another quality person concludes it with a signature. The assessment changes
none of the records it names: tests, lots, studies and certificates are acted on through their
own signed transitions, and recall, manufacturer batch release and reports to authorities stay
in the manufacturer's quality system.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class Assessment(models.Model):
    class Cause(models.TextChoices):
        EQUIPMENT = "equipment", "Equipment"
        REAGENT = "reagent", "Reagent or standard lot"
        SUPPLIER = "supplier", "Supplier"
        CONTRACT = "contract_laboratory", "Contract laboratory"
        OTHER = "other", "Other"

    class State(models.TextChoices):
        OPEN = "open", "Open"
        CONCLUDED = "concluded", "Concluded"
        WITHDRAWN = "withdrawn", "Withdrawn"

    cause = models.CharField(max_length=24, choices=Cause)
    equipment = models.ForeignKey(
        "laboratory.Equipment", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reagent_lot = models.ForeignKey(
        "laboratory.ReagentLot",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="reagent or standard lot",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    contract_laboratory = models.ForeignKey(
        "laboratory.ContractLaboratory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    title = models.CharField(max_length=160, help_text="The problem in a few words.")
    description = models.TextField(help_text="What happened, how and when it was found.")
    found_on = models.DateField("Date found")
    period_from = models.DateField(
        "Period of concern from", help_text="First day the problem may have affected work."
    )
    period_until = models.DateField(
        "Period of concern until",
        help_text="Last day (inclusive) the problem may have affected work.",
    )
    quality_reference = models.CharField(
        "Quality-system reference",
        max_length=200,
        blank=True,
        help_text="The deviation, CAPA or change record in the quality system.",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.OPEN)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
    # The records and decisions as concluded (oq.impact-assessment/1); empty until then.
    evidence = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "impact assessment"
        constraints = [
            models.CheckConstraint(
                condition=Q(cause="equipment", equipment__isnull=False)
                | ~Q(cause="equipment") & Q(equipment__isnull=True),
                name="impact_equipment_cause",
            ),
            models.CheckConstraint(
                condition=Q(cause="reagent", reagent_lot__isnull=False)
                | ~Q(cause="reagent") & Q(reagent_lot__isnull=True),
                name="impact_reagent_cause",
            ),
            models.CheckConstraint(
                condition=Q(cause="supplier", supplier__isnull=False)
                | ~Q(cause="supplier") & Q(supplier__isnull=True),
                name="impact_supplier_cause",
            ),
            models.CheckConstraint(
                condition=Q(cause="contract_laboratory", contract_laboratory__isnull=False)
                | ~Q(cause="contract_laboratory") & Q(contract_laboratory__isnull=True),
                name="impact_contract_cause",
            ),
            models.CheckConstraint(
                condition=Q(period_until__gte=models.F("period_from")),
                name="impact_period_ordered",
            ),
            models.CheckConstraint(
                condition=Q(state="open", decided_at__isnull=True)
                | Q(state__in=["concluded", "withdrawn"], decided_at__isnull=False),
                name="impact_decided_when_closed",
            ),
        ]

    @property
    def label(self):
        return f"IA-{self.pk}"

    @property
    def identifier(self):
        return self.label

    def __str__(self):
        return f"{self.label} {self.title}"

    @property
    def source(self):
        """The record named as the cause, or None for another cause."""
        return self.equipment or self.reagent_lot or self.supplier or self.contract_laboratory


class Item(models.Model):
    """One record the assessment names as possibly affected, with quality's decision on it."""

    class Kind(models.TextChoices):
        TEST = "test", "Test"
        LOT = "lot", "Lot"
        STUDY = "study", "Stability study"
        CERTIFICATE = "certificate", "Certificate"

    class Origin(models.TextChoices):
        FOUND = "found", "Found from the cause"
        ADDED = "added", "Added by quality"

    class Decision(models.TextChoices):
        NOT_AFFECTED = "not_affected", "Not affected"
        AFFECTED = "affected", "Affected"

    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="items")
    kind = models.CharField(max_length=12, choices=Kind)
    test = models.ForeignKey(
        "analytical.AnalyticalTest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    lot = models.ForeignKey(
        "quality.Lot", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    study = models.ForeignKey(
        "stability.Study", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    report = models.ForeignKey(
        "reporting.Report", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    origin = models.CharField(max_length=8, choices=Origin)
    basis = models.TextField(help_text="Why the record is in the assessment.")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    decision = models.CharField(max_length=16, choices=Decision, blank=True)
    rationale = models.TextField(blank=True)
    follow_up = models.TextField(blank=True)
    follow_up_reference = models.CharField(max_length=200, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    # The protective hold placed on the lot through this record of the assessment.
    hold = models.OneToOneField(
        "stability.Hold", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["assessment_id", "id"]
        verbose_name = "affected record"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    kind="test",
                    test__isnull=False,
                    lot__isnull=True,
                    study__isnull=True,
                    report__isnull=True,
                )
                | Q(
                    kind="lot",
                    test__isnull=True,
                    lot__isnull=False,
                    study__isnull=True,
                    report__isnull=True,
                )
                | Q(
                    kind="study",
                    test__isnull=True,
                    lot__isnull=True,
                    study__isnull=False,
                    report__isnull=True,
                )
                | Q(
                    kind="certificate",
                    test__isnull=True,
                    lot__isnull=True,
                    study__isnull=True,
                    report__isnull=False,
                ),
                name="impact_item_one_record",
            ),
            models.CheckConstraint(
                condition=Q(decision="", decided_at__isnull=True, decided_by__isnull=True)
                | Q(
                    decision__in=["not_affected", "affected"],
                    decided_at__isnull=False,
                    decided_by__isnull=False,
                )
                & ~Q(rationale__regex=r"^\s*$"),
                name="impact_item_decided",
            ),
            models.CheckConstraint(
                condition=~Q(decision="affected") | ~Q(follow_up__regex=r"^\s*$"),
                name="impact_item_follow_up",
            ),
            models.CheckConstraint(
                condition=Q(hold__isnull=True) | Q(kind="lot"), name="impact_item_hold_on_lot"
            ),
            models.UniqueConstraint(
                fields=["assessment", "test"],
                condition=Q(test__isnull=False),
                name="impact_item_test_once",
            ),
            models.UniqueConstraint(
                fields=["assessment", "lot"],
                condition=Q(lot__isnull=False),
                name="impact_item_lot_once",
            ),
            models.UniqueConstraint(
                fields=["assessment", "study"],
                condition=Q(study__isnull=False),
                name="impact_item_study_once",
            ),
            models.UniqueConstraint(
                fields=["assessment", "report"],
                condition=Q(report__isnull=False),
                name="impact_item_report_once",
            ),
        ]

    @property
    def target(self):
        return self.test or self.lot or self.study or self.report

    @property
    def target_id(self):
        return self.test_id or self.lot_id or self.study_id or self.report_id

    def __str__(self):
        return f"{self.assessment.label} {self.get_kind_display().lower()} {self.target_id}"
