from functools import cached_property

from django.conf import settings
from django.db import models
from django.db.models import Q

from .contracts import LESS_THAN, OUTCOMES, Reading, parse_method, parse_requirement

DECIMAL = {"max_digits": 20, "decimal_places": 8}


class QCBatch(models.Model):
    class State(models.TextChoices):
        OPEN = "open", "Open"
        REJECTED = "rejected", "Rejected"

    number = models.CharField(max_length=80, unique=True)
    method_code = models.CharField(max_length=80)
    method = models.JSONField()
    method_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "QC batch"
        verbose_name_plural = "QC batches"

    def __str__(self):
        return self.number

    @cached_property
    def method_spec(self):
        return parse_method(self.method)

    def current_qc(self):
        return self.qc_results.filter(correction__isnull=True).select_related("recorded_by")

    def qc_status(self):
        """Return (status, checks) where status is incomplete, failed or passed."""
        current = {r.check_code: r for r in self.current_qc()}
        checks, status = [], "passed"
        for check in self.method_spec.qc_checks:
            result = current.get(check.code)
            conforms = None if result is None else check.conforms(result.value)
            checks.append({"check": check, "result": result, "conforms": conforms})
            if conforms is False:
                status = "failed"
            elif conforms is None and status != "failed":
                status = "incomplete"
        return status, checks


class QCResult(models.Model):
    batch = models.ForeignKey(QCBatch, on_delete=models.PROTECT, related_name="qc_results")
    check_code = models.CharField(max_length=40)
    value = models.DecimalField(**DECIMAL)
    value_text = models.CharField(max_length=40, help_text="Value exactly as entered")
    unit = models.CharField(max_length=40)
    raw_reference = models.CharField(max_length=200)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="correction"
    )
    reason = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["check_code", "recorded_at", "pk"]


class AnalyticalTest(models.Model):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "Original"
        RETEST = "retest", "Retest"
        RESAMPLE = "resample", "Resample"
        RERUN = "rerun", "Rerun after QC failure"

    class State(models.TextChoices):
        OPEN = "open", "Open"
        SUBMITTED = "submitted", "Awaiting review"
        REVIEWED = "reviewed", "Reviewed"
        INVALIDATED = "invalidated", "Invalidated"

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="+")
    sample = models.ForeignKey("quality.Sample", on_delete=models.PROTECT, related_name="+")
    test_code = models.CharField(max_length=80)
    requirement = models.JSONField()
    requirement_hash = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ORIGINAL)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    investigation = models.ForeignKey(
        "Investigation", null=True, blank=True, on_delete=models.PROTECT, related_name="tests"
    )
    batch = models.ForeignKey(
        QCBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="tests"
    )
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    mean_value = models.DecimalField(null=True, blank=True, **DECIMAL)
    reportable_value = models.DecimalField(null=True, blank=True, **DECIMAL)
    reportable_text = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Reportable result as frozen at submission, e.g. 99.8, <10 or Absent",
    )
    conforms = models.BooleanField(null=True, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["lot_id", "sample_id", "test_code", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "test_code"],
                condition=Q(kind="original"),
                name="analytical_one_original_test",
            ),
            models.CheckConstraint(
                condition=(Q(kind="original") & Q(parent__isnull=True))
                | (~Q(kind="original") & Q(parent__isnull=False)),
                name="analytical_test_lineage",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["original", "rerun"]) | Q(investigation__isnull=False),
                name="analytical_retest_has_investigation",
            ),
        ]

    def __str__(self):
        return f"T-{self.pk} {self.test_code}"

    @property
    def label(self):
        return f"T-{self.pk}"

    @cached_property
    def spec(self):
        return parse_requirement(self.requirement)

    @property
    def reportable_display(self):
        """Reportable result as frozen at submission, e.g. 99.8, <10 or Absent ("" if none).

        Tests submitted before the text was frozen fall back to formatting the numeric value at
        the approved reporting precision.
        """
        if self.reportable_text:
            return self.reportable_text
        if self.reportable_value is None:
            return ""
        return self.spec.format_value(self.reportable_value)

    @property
    def reportable_with_unit(self):
        text = self.reportable_display
        unit = self.spec.unit
        return f"{text} {unit}" if text and unit else text

    def current_observations(self):
        return self.observations.filter(correction__isnull=True).select_related("recorded_by")


class Observation(models.Model):
    """One replicate observation. Rows are append-only; a correction is a new linked row."""

    test = models.ForeignKey(AnalyticalTest, on_delete=models.PROTECT, related_name="observations")

    class Qualifier(models.TextChoices):
        NONE = "", "As recorded"
        LESS_THAN = LESS_THAN, "Less than"

    replicate = models.PositiveSmallIntegerField()
    value = models.DecimalField(
        null=True, blank=True, help_text="Numeric value; empty for a qualitative result", **DECIMAL
    )
    qualifier = models.CharField(
        max_length=1, choices=Qualifier.choices, blank=True, default=Qualifier.NONE
    )
    outcome = models.CharField(
        max_length=20,
        choices=list(OUTCOMES.items()),
        blank=True,
        default="",
        help_text="Qualitative outcome; blank for a numeric or count result",
    )
    value_text = models.CharField(max_length=40, help_text="Result exactly as recorded")
    observed_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="What was observed; required for a qualitative result",
    )
    unit = models.CharField(max_length=40, blank=True, help_text="Blank for a qualitative result")
    raw_reference = models.CharField(max_length=200)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="correction"
    )
    reason = models.TextField(blank=True)
    eligibility = models.JSONField(
        default=dict, blank=True, help_text="Analyst qualification evidence at acceptance"
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["replicate", "recorded_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~Q(outcome="")
                    & Q(value__isnull=True)
                    & Q(qualifier="")
                    & ~Q(observed_text__regex=r"^\s*$")
                )
                | (Q(outcome="") & Q(value__isnull=False) & Q(qualifier__in=["", LESS_THAN])),
                name="analytical_observation_shape",
            ),
        ]

    @property
    def reading(self):
        return Reading(
            value=self.value, qualifier=self.qualifier, outcome=self.outcome, text=self.value_text
        )


class Investigation(models.Model):
    class Phase(models.TextChoices):
        LABORATORY = "laboratory", "Phase I laboratory investigation"
        FULL = "full", "Phase II full investigation"
        CLOSED = "closed", "Closed"

    class Outcome(models.TextChoices):
        INVALIDATED = "invalidated", "Original result invalidated: assignable cause"
        CONFIRMED = "confirmed", "Out-of-specification result confirmed"

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="+")
    test = models.OneToOneField(
        AnalyticalTest, on_delete=models.PROTECT, related_name="triggered_investigation"
    )
    trigger = models.CharField(max_length=200)
    phase = models.CharField(max_length=16, choices=Phase.choices, default=Phase.LABORATORY)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True)
    assignable_cause = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-opened_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(phase="closed") & ~Q(outcome="") & Q(closed_at__isnull=False))
                | (~Q(phase="closed") & Q(outcome="") & Q(closed_at__isnull=True)),
                name="analytical_investigation_closure",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return f"INV-{self.pk}"

    @property
    def is_open(self):
        return self.phase != self.Phase.CLOSED


class InvestigationEntry(models.Model):
    class Kind(models.TextChoices):
        ASSESSMENT = "assessment", "Laboratory assessment"
        HYPOTHESIS = "hypothesis", "Hypothesis or test plan"
        EVIDENCE = "evidence", "Evidence"
        ESCALATION = "escalation", "Escalation"
        PLAN = "plan", "Authorized retest or resample"
        IMPACT = "impact", "Impact on other lots or products"

    investigation = models.ForeignKey(
        Investigation, on_delete=models.PROTECT, related_name="entries"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    text = models.TextField()
    external_reference = models.CharField(max_length=200, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name_plural = "investigation entries"


class RawDataFile(models.Model):
    """A file of raw data attached to a test, kept exactly as received. Rows are append-only."""

    test = models.ForeignKey(AnalyticalTest, on_delete=models.PROTECT, related_name="raw_files")
    filename = models.CharField(max_length=200, help_text="Base name of the uploaded file")
    content_type = models.CharField(
        max_length=100, blank=True, help_text="Type declared by the browser; informational only"
    )
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    content = models.BinaryField()
    description = models.CharField(max_length=200, help_text="What the file is")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["test", "sha256"], name="analytical_rawfile_unique"),
            models.CheckConstraint(condition=Q(size__gt=0), name="analytical_rawfile_not_empty"),
        ]

    def __str__(self):
        return self.filename
