"""Trend charts of release results, the limits they are judged by, and out-of-trend evaluations.

A chart follows one test of one material at one stage: the reviewed results of the lots assigned
to that material and stage, in the order their reviews were signed. Its limits are versions that
quality drafts and another quality person approves with a signature; each result is judged by the
version in force when its review was signed. A result that breaks a rule of that version raises an
out-of-trend alert. Alerts are worked out from the record whenever they are read, so none is
missed and none needs storing until quality evaluates it: an evaluation names the alerts it covers
and is concluded with a signature. The database refuses deleting any of these rows and changing
an approved version, a concluded evaluation or the alerts an evaluation covers (migration 0002).
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from catalog.models import Stage

DECIMAL = {"max_digits": 20, "decimal_places": 8}


class Chart(models.Model):
    """One test of one material at one stage, as the specification in force stated it when the
    chart was created. Never changed or deleted."""

    material = models.ForeignKey("catalog.Material", on_delete=models.PROTECT, related_name="+")
    stage = models.CharField(max_length=16, choices=Stage.choices)
    test_code = models.SlugField("Test code", max_length=80)
    name = models.CharField("Test", max_length=160)
    unit = models.CharField(max_length=24)
    decimals = models.PositiveSmallIntegerField(
        "Reporting decimals",
        null=True,
        blank=True,
        help_text="The reporting precision of the test line; computed limits carry two more "
        "decimals.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "trend chart"
        ordering = ["test_code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["material", "stage", "test_code"], name="trending_chart_unique"
            ),
            models.CheckConstraint(
                condition=~Q(test_code="") & ~Q(unit="") & ~Q(stage="stability"),
                name="trending_chart_stated",
            ),
        ]

    def __str__(self):
        return f"{self.identifier} {self.title}"

    @property
    def identifier(self):
        return f"TC-{self.pk}"

    @property
    def title(self):
        return f"{self.name} · {self.material.code}"


class Rule(models.TextChoices):
    """The trend rules a limits version can apply. A result outside the limits is always one."""

    BEYOND = "beyond", "A result outside the limits"
    RUN = "run", "Results in a row on the same side of the center line"
    TREND = "trend", "Results in a row each higher, or each lower, than the one before"
    TWO_OF_THREE = "two_of_three", "2 of 3 results in a row more than 2σ from the center line"
    FOUR_OF_FIVE = "four_of_five", "4 of 5 results in a row more than 1σ from the center line"


class Limits(models.Model):
    """One version of a chart's limits and rules: a draft that quality changes, then approved by
    another quality person with a signature that freezes ``content``. Approving a later version
    ends this one (``superseded_at``); nothing else changes once approved."""

    class Basis(models.TextChoices):
        COMPUTED = "computed", "Computed from a baseline of results"
        ENTERED = "entered", "Entered"

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    chart = models.ForeignKey(Chart, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT)
    basis = models.CharField(max_length=12, choices=Basis.choices)
    baseline_from = models.DateField(
        "Baseline from",
        null=True,
        blank=True,
        help_text="The first day of the baseline: results whose review was signed from this day.",
    )
    baseline_to = models.DateField(
        "Baseline to",
        null=True,
        blank=True,
        help_text="The last day of the baseline, not after today.",
    )
    baseline = models.JSONField(
        default=list,
        blank=True,
        help_text="The results the computed limits were worked out from: test, lot and value.",
    )
    computed_at = models.DateTimeField(
        "Worked out",
        null=True,
        blank=True,
        help_text="When the computed figures were worked out; a result reviewed later is not "
        "part of the baseline.",
    )
    center = models.DecimalField("Center line", null=True, blank=True, **DECIMAL)
    sigma = models.DecimalField(
        "Standard deviation (σ)",
        null=True,
        blank=True,
        help_text="Estimated from the average moving range divided by 1.128 for computed limits.",
        **DECIMAL,
    )
    lower = models.DecimalField("Lower limit", null=True, blank=True, **DECIMAL)
    upper = models.DecimalField("Upper limit", null=True, blank=True, **DECIMAL)
    rules = models.JSONField(default=list, help_text="The codes of the rules applied.")
    run_length = models.PositiveSmallIntegerField("Results in a run", default=8)
    trend_length = models.PositiveSmallIntegerField("Results in a trend", default=6)
    rationale = models.TextField(
        "Basis of the limits",
        help_text="Why these limits and rules: the data, the process knowledge or the procedure "
        "they come from.",
    )
    drafted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    drafted_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    content = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "limits version"
        ordering = ["chart", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["chart", "version"], name="trending_limits_version"),
            models.UniqueConstraint(
                fields=["chart"], condition=Q(state="draft"), name="trending_limits_one_draft"
            ),
            models.CheckConstraint(
                condition=Q(
                    state="draft",
                    approved_at__isnull=True,
                    content__isnull=True,
                    content_hash="",
                    superseded_at__isnull=True,
                )
                | Q(
                    ~Q(content_hash=""),
                    state="approved",
                    approved_at__isnull=False,
                    content__isnull=False,
                ),
                name="trending_limits_states",
            ),
            models.CheckConstraint(
                condition=Q(superseded_at__isnull=True) | Q(superseded_at__gte=F("approved_at")),
                name="trending_limits_superseded_after_approval",
            ),
            models.CheckConstraint(
                condition=Q(
                    basis="computed",
                    computed_at__isnull=False,
                    baseline_from__isnull=False,
                    baseline_to__isnull=False,
                    baseline_from__lte=F("baseline_to"),
                    center__isnull=False,
                    sigma__gt=0,
                    lower__isnull=False,
                    upper__isnull=False,
                )
                | Q(
                    Q(lower__isnull=False) | Q(upper__isnull=False),
                    Q(sigma__isnull=True) | Q(sigma__gt=0),
                    basis="entered",
                    computed_at__isnull=True,
                    baseline_from__isnull=True,
                    baseline_to__isnull=True,
                    baseline=[],
                ),
                name="trending_limits_basis",
            ),
            models.CheckConstraint(
                condition=Q(lower__isnull=True) | Q(upper__isnull=True) | Q(lower__lt=F("upper")),
                name="trending_limits_ordered",
            ),
            models.CheckConstraint(
                condition=Q(run_length__gte=6, run_length__lte=12)
                & Q(trend_length__gte=5, trend_length__lte=10),
                name="trending_limits_lengths",
            ),
            models.CheckConstraint(
                condition=~Q(rationale__regex=r"^\s*$"), name="trending_limits_rationale"
            ),
        ]

    def __str__(self):
        return f"{self.chart.identifier} v{self.version}"

    @property
    def identifier(self):
        return f"{self.chart.identifier} v{self.version}"


class Evaluation(models.Model):
    """An out-of-trend evaluation: the alerts of one chart that quality looked into, what was
    found and done, and the conclusion signed by a quality person who recorded none of the
    findings and none of the results' data. Never deleted; once concluded it never changes."""

    class State(models.TextChoices):
        OPEN = "open", "Open"
        CONCLUDED = "concluded", "Concluded"

    class Outcome(models.TextChoices):
        CONFIRMED = "confirmed", "Out of trend confirmed"
        NOT_CONFIRMED = "not_confirmed", "Not confirmed"

    chart = models.ForeignKey(Chart, on_delete=models.PROTECT, related_name="evaluations")
    state = models.CharField(max_length=12, choices=State.choices, default=State.OPEN)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    laboratory_check = models.TextField(
        "Laboratory check",
        blank=True,
        help_text="Whether a laboratory error explains the results: the data, calculations, "
        "instruments, standards and records checked, and what they showed.",
    )
    cause = models.TextField(
        "Cause",
        blank=True,
        help_text="The cause found, in the laboratory, the material or the process, or that "
        "none was found.",
    )
    effect = models.TextField(
        "Lots and results affected",
        blank=True,
        help_text="Whether the lots behind these results, and results already reported, are "
        "affected, and what was done about them.",
    )
    actions = models.TextField(
        "Actions", blank=True, help_text="What was done or is planned, by whom and when."
    )
    quality_reference = models.CharField(
        "Quality-system reference",
        max_length=200,
        blank=True,
        help_text="The deviation, investigation or CAPA record in the quality system.",
    )
    impact_assessment = models.ForeignKey(
        "impact.Assessment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Impact assessment",
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True)
    conclusion = models.TextField(blank=True)
    concluded_at = models.DateTimeField(null=True, blank=True)
    content = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "out-of-trend evaluation"
        ordering = ["-opened_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    state="open",
                    outcome="",
                    conclusion="",
                    concluded_at__isnull=True,
                    content__isnull=True,
                    content_hash="",
                )
                | Q(
                    ~Q(outcome=""),
                    ~Q(conclusion=""),
                    ~Q(content_hash=""),
                    state="concluded",
                    concluded_at__isnull=False,
                    content__isnull=False,
                ),
                name="trending_evaluation_states",
            ),
        ]

    def __str__(self):
        return f"{self.identifier} · {self.chart.identifier}"

    @property
    def identifier(self):
        return f"OOT-{self.pk}"


class EvaluationAlert(models.Model):
    """One alert an evaluation covers: the result, the limits version it was judged by and the
    rules it broke, as they stood when the alert was added. Added only while the evaluation is
    open; never changed or removed. A result is covered by one evaluation at most."""

    evaluation = models.ForeignKey(Evaluation, on_delete=models.PROTECT, related_name="alerts")
    test = models.OneToOneField(
        "analytical.AnalyticalTest", on_delete=models.PROTECT, related_name="+"
    )
    limits = models.ForeignKey(Limits, on_delete=models.PROTECT, related_name="+")
    value = models.DecimalField(**DECIMAL)
    reviewed_at = models.DateTimeField()
    rules = models.JSONField()
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "alert"
        ordering = ["reviewed_at", "id"]

    def __str__(self):
        return f"T-{self.test_id} in {self.evaluation.identifier}"
