"""Stability studies, reserve samples, retention obligations and holds.

Protocols, studies and pulls reuse the foundation lot identity. Native scheduling is
deliberately thin: a controlled protocol and the pulls it implies. A pull is tested in the
system (its tests belong to the pull, never to the lot's record), or it links a sample of a lot
still in quarantine or an external stability system. Controlled fields are frozen by PostgreSQL
triggers (migration 0002); every lifecycle change bumps `revision`.
"""

import calendar
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from laboratory.models import evidence_url


def add_months(day, months):
    """Calendar-month arithmetic; the day is clamped to the target month's length."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


class Protocol(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        SUPERSEDED = "superseded", "Superseded"
        # A draft that will not be approved; the next version of its code can then be drafted.
        WITHDRAWN = "withdrawn", "Withdrawn"

    code = models.CharField(max_length=60)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=160)
    product = models.CharField(max_length=160, help_text="Product or material under study.")
    document_ref = models.CharField(
        max_length=200, help_text="Approved protocol document and revision in the QMS."
    )
    document_url = evidence_url()
    test_profile_ref = models.CharField(
        max_length=200, blank=True, help_text="Stable specification/test-profile revision."
    )
    specification = models.ForeignKey(
        "catalog.Specification",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The specification whose approved version in force states the acceptance "
        "criteria of the protocol's tests. Without one, pulls are not tested in the system.",
    )
    basis = models.TextField(
        help_text="Why these conditions and schedule apply. No universal defaults are assumed."
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.DRAFT)
    content_digest = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 over the conditions and timepoints, so the approval signature binds "
        "the complete protocol, not only its header.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["code", "-version"]
        constraints = [models.UniqueConstraint(fields=["code", "version"], name="protocol_version")]

    @property
    def identifier(self):
        return f"{self.code} v{self.version}"

    def __str__(self):
        return self.identifier


class ProtocolCondition(models.Model):
    protocol = models.ForeignKey(Protocol, on_delete=models.PROTECT, related_name="conditions")
    label = models.CharField(max_length=80, help_text="For example long-term, accelerated.")
    setpoint = models.CharField(max_length=200, help_text="Storage condition as approved.")
    temperature_c = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    humidity_pct = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["protocol", "label"], name="protocol_condition_label")
        ]

    def __str__(self):
        return f"{self.protocol} · {self.label}"


class ProtocolTimepoint(models.Model):
    protocol = models.ForeignKey(Protocol, on_delete=models.PROTECT, related_name="timepoints")
    condition = models.ForeignKey(
        ProtocolCondition, on_delete=models.PROTECT, related_name="timepoints"
    )
    label = models.CharField(max_length=40, help_text="For example 3 months.")
    interval_days = models.PositiveIntegerField(help_text="Days from time zero; 0 is time zero.")
    window_days = models.PositiveIntegerField(
        default=0, help_text="Allowed deviation before and after the due date, in days."
    )
    test_codes = models.JSONField(default=list)

    class Meta:
        ordering = ["condition_id", "interval_days"]
        constraints = [
            models.UniqueConstraint(
                fields=["condition", "interval_days"], name="protocol_timepoint_interval"
            )
        ]

    def clean(self):
        codes = self.test_codes
        if (
            not isinstance(codes, list)
            or not codes
            or any(not isinstance(c, str) or not c.strip() for c in codes)
            or len(set(codes)) != len(codes)
        ):
            raise ValidationError({"test_codes": "List one or more distinct test codes."})

    def __str__(self):
        return f"{self.condition.label} {self.label}"


class Study(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        TERMINATED = "terminated", "Terminated"

    identifier = models.CharField(max_length=60, unique=True)
    protocol = models.ForeignKey(Protocol, on_delete=models.PROTECT, related_name="studies")
    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="+")
    container_closure = models.CharField(
        max_length=200, help_text="Marketed or proposed container/closure system."
    )
    start_date = models.DateField(help_text="Time zero.")
    rule_basis = models.CharField(
        max_length=120, help_text="Lot rule revision in force when the study started."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.ACTIVE)
    closed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "studies"
        constraints = [
            models.UniqueConstraint(
                fields=["protocol", "lot", "container_closure"], name="study_unique_scope"
            )
        ]

    def __str__(self):
        return self.identifier


class Pull(models.Model):
    class State(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        PULLED = "pulled", "Pulled"
        ACCEPTED = "accepted", "Accepted"
        MISSED = "missed", "Missed"

    class Outcome(models.TextChoices):
        CONFORMS = "conforms", "Meets the acceptance criteria"
        FAILS = "fails", "Does not meet the acceptance criteria"

    study = models.ForeignKey(Study, on_delete=models.PROTECT, related_name="pulls")
    timepoint = models.ForeignKey(ProtocolTimepoint, on_delete=models.PROTECT, related_name="+")
    due_date = models.DateField()
    state = models.CharField(max_length=12, choices=State, default=State.SCHEDULED)
    pulled_on = models.DateField(null=True, blank=True)
    pulled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    quantity_unit = models.CharField(max_length=20, blank=True)
    storage_location = models.CharField(max_length=120, blank=True)
    chamber = models.ForeignKey(
        "laboratory.Equipment", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sample = models.ForeignKey(
        "quality.Sample", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    external_sample_ref = models.CharField(
        max_length=120, blank=True, help_text="Sample or study ID in the external stability system."
    )
    evidence_ref = models.CharField(max_length=200, blank=True)
    evidence_url = evidence_url()
    evidence_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    deviation_reason = models.TextField(blank=True)
    missed_reason = models.TextField(blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    # Set when a pull tested in the system is accepted: how its reviewed results compare with
    # the acceptance criteria frozen on its tests, and the results the signature rests on.
    # Blank for a pull accepted on a linked sample or on external evidence.
    # The database keeps both defaults, so a release that does not know the columns can still
    # insert pulls while both are running.
    outcome = models.CharField(max_length=8, choices=Outcome, blank=True, db_default="")
    result_evidence = models.JSONField(default=dict, db_default={}, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["due_date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["study", "timepoint"], name="pull_unique_timepoint"),
            models.UniqueConstraint(
                fields=["sample"],
                condition=models.Q(sample__isnull=False),
                name="pull_sample_unique",
            ),
            # An outcome and its evidence belong to an accepted pull, together or not at all.
            models.CheckConstraint(
                condition=models.Q(outcome="", result_evidence={})
                | (
                    models.Q(state="accepted")
                    & ~models.Q(outcome="")
                    & ~models.Q(result_evidence={})
                ),
                name="pull_outcome_when_accepted",
            ),
        ]

    @property
    def window(self):
        days = timedelta(days=self.timepoint.window_days)
        return self.due_date - days, self.due_date + days

    def timing(self, today=None):
        """('on_time'|'due'|'overdue'|'late'|'early', label) for display and queues."""
        today = today or timezone.localdate()
        opens, closes = self.window
        if self.state == self.State.SCHEDULED:
            if today > closes:
                return "overdue", "Overdue"
            if today >= opens:
                return "due", "Due"
            return "upcoming", "Upcoming"
        return "closed", self.get_state_display()

    @property
    def label(self):
        return f"{self.study.identifier} · {self.timepoint}"

    def __str__(self):
        return self.label


class ReserveSample(models.Model):
    """Identified reserve/retain sample. Immutable after recording; retention and holds sit in
    separate append-only records."""

    identifier = models.CharField(max_length=60, unique=True)
    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="+")
    container_description = models.CharField(
        max_length=200, help_text="Packaging as retained (for example full marketed package)."
    )
    storage_location = models.CharField(max_length=120)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4, validators=[MinValueValidator(0)]
    )
    test_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        validators=[MinValueValidator(0)],
        help_text="Quantity needed for one complete set of required tests.",
    )
    quantity_unit = models.CharField(max_length=20)
    minimum_multiple = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2,
        validators=[MinValueValidator(0)],
        help_text="Minimum multiple of the test quantity to keep. The default 2 reflects "
        "researched drug and supplement reserve rules; the quality owner confirms applicability.",
    )
    retained_on = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(test_quantity__gt=0), name="reserve_test_quantity_positive"
            )
        ]

    @property
    def multiple(self):
        return self.quantity / self.test_quantity

    @property
    def meets_minimum(self):
        return self.multiple >= self.minimum_multiple

    def __str__(self):
        return self.identifier


class RetentionObligation(models.Model):
    """One retention deadline from its own anchor. Append-only; the anchor may be set once when
    unknown at recording (for example last distribution). Every obligation must clear."""

    class Anchor(models.TextChoices):
        EXPIRY = "expiry", "Expiry or shelf-life date"
        LAST_DISTRIBUTION = "last_distribution", "Last associated batch distribution"
        PREPARATION = "preparation", "Preparation or record date"
        DISCONTINUED = "discontinued_use", "Discontinued use"

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="+")
    reserve = models.ForeignKey(
        ReserveSample, null=True, blank=True, on_delete=models.PROTECT, related_name="obligations"
    )
    anchor_kind = models.CharField(max_length=24, choices=Anchor)
    anchor_date = models.DateField(null=True, blank=True)
    offset_months = models.PositiveIntegerField(help_text="Months retained after the anchor.")
    basis = models.CharField(
        max_length=200,
        help_text="Controlled basis, for example the regulatory-matrix row confirmed by quality.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    anchor_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    anchor_set_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["lot_id", "pk"]

    @property
    def retain_until(self):
        if self.anchor_date is None:
            return None
        return add_months(self.anchor_date, self.offset_months)

    def clean(self):
        if self.anchor_date is not None and self.offset_months is not None:
            try:
                self.retain_until  # noqa: B018
            except ValueError, OverflowError:
                raise ValidationError(
                    {"offset_months": "The retention date falls outside the supported calendar."}
                ) from None

    def blocker(self, today=None):
        today = today or timezone.localdate()
        if self.anchor_date is None:
            return f"{self.get_anchor_kind_display()} is not yet known."
        if today <= self.retain_until:
            return f"Retention under {self.basis} runs through {self.retain_until.isoformat()}."
        return ""

    def __str__(self):
        return f"{self.lot} retention {self.get_anchor_kind_display()}"


class Hold(models.Model):
    class Kind(models.TextChoices):
        INVESTIGATION = "investigation", "Investigation"
        REGULATORY = "regulatory", "Regulatory"
        LEGAL = "legal", "Legal"
        QUALITY = "quality", "Quality"

    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="+")
    reserve = models.ForeignKey(
        ReserveSample, null=True, blank=True, on_delete=models.PROTECT, related_name="holds"
    )
    kind = models.CharField(max_length=16, choices=Kind)
    reason = models.TextField()
    reference = models.CharField(
        max_length=200, blank=True, help_text="Investigation, CAPA or legal-matter ID."
    )
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    placed_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.ACTIVE)
    released_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-placed_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state="active", released_at__isnull=True)
                | models.Q(state="released", released_at__isnull=False),
                name="hold_release_time",
            )
        ]

    @property
    def identifier(self):
        return f"HOLD-{self.pk}"

    def __str__(self):
        return self.identifier


class ShelfLifeEvaluation(models.Model):
    """A statistical evaluation of the shelf life (or retest period) that one test supports at
    one storage condition, from the results of the studies of one protocol and container
    closure (ICH Q1E, Appendix B; ``stability.regression``).

    Quality drafts it: the test's acceptance criterion is taken from the version in force of the
    protocol's specification and kept with the draft, and quality chooses the studies and the
    direction the attribute is expected to change in. The results and the figures are worked
    out from the record whenever a draft is read. A quality person who neither drafted nor
    changed it, and who produced none of its results' data, concludes it with a signature that
    freezes the results, the figures and the shelf life recorded. A draft that will not be
    concluded is withdrawn. Nothing is deleted, and a concluded or withdrawn evaluation never
    changes (migration 0007).
    """

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONCLUDED = "concluded", "Concluded"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Direction(models.TextChoices):
        DECREASES = "decreases", "Expected to decrease"
        INCREASES = "increases", "Expected to increase"
        EITHER = "either", "Could change either way, or not known"

    class Outcome(models.TextChoices):
        SUPPORTED = "supported", "Shelf life supported"
        NOT_SUPPORTED = "not_supported", "No shelf life supported"

    protocol_code = models.CharField("Protocol", max_length=60)
    product = models.CharField(max_length=160)
    container_closure = models.CharField(max_length=200)
    condition = models.CharField("Storage condition", max_length=80)
    specification = models.ForeignKey(
        "catalog.Specification", on_delete=models.PROTECT, related_name="+"
    )
    specification_version = models.PositiveIntegerField()
    test_code = models.SlugField("Test code", max_length=80)
    name = models.CharField("Test", max_length=160)
    unit = models.CharField(max_length=24)
    decimals = models.PositiveSmallIntegerField("Reporting decimals", null=True, blank=True)
    lower_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    upper_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    direction = models.CharField(
        "Expected change",
        max_length=12,
        choices=Direction.choices,
        help_text="Decides which confidence limit is compared with the acceptance criterion: "
        "the lower one-sided limit for a decrease, the upper for an increase, two-sided limits "
        "otherwise.",
    )
    purpose = models.TextField(
        help_text="Why the shelf life is evaluated now, for example the data for a proposed "
        "shelf life or the annual review of the studies."
    )
    drafted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    drafted_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True)
    shelf_life_months = models.PositiveSmallIntegerField(
        "Shelf life (months)", null=True, blank=True
    )
    conclusion = models.TextField(blank=True)
    concluded_at = models.DateTimeField(null=True, blank=True)
    content = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "shelf-life evaluation"
        ordering = ["-drafted_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["protocol_code", "container_closure", "condition", "test_code"],
                condition=models.Q(state="draft"),
                name="stability_shelf_life_one_draft",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state="draft",
                    outcome="",
                    shelf_life_months__isnull=True,
                    conclusion="",
                    concluded_at__isnull=True,
                    content__isnull=True,
                    content_hash="",
                    withdrawn_at__isnull=True,
                )
                | models.Q(
                    ~models.Q(conclusion=""),
                    ~models.Q(content_hash=""),
                    models.Q(outcome="supported", shelf_life_months__gt=0)
                    | models.Q(outcome="not_supported", shelf_life_months__isnull=True),
                    state="concluded",
                    concluded_at__isnull=False,
                    content__isnull=False,
                    withdrawn_at__isnull=True,
                )
                | models.Q(
                    state="withdrawn",
                    outcome="",
                    shelf_life_months__isnull=True,
                    conclusion="",
                    concluded_at__isnull=True,
                    content__isnull=True,
                    content_hash="",
                    withdrawn_at__isnull=False,
                ),
                name="stability_shelf_life_states",
            ),
            models.CheckConstraint(
                condition=models.Q(direction="decreases", lower_limit__isnull=False)
                | models.Q(direction="increases", upper_limit__isnull=False)
                | models.Q(
                    models.Q(lower_limit__isnull=False) | models.Q(upper_limit__isnull=False),
                    direction="either",
                ),
                name="stability_shelf_life_criterion",
            ),
            models.CheckConstraint(
                condition=models.Q(lower_limit__isnull=True)
                | models.Q(upper_limit__isnull=True)
                | models.Q(lower_limit__lt=models.F("upper_limit")),
                name="stability_shelf_life_ordered",
            ),
            models.CheckConstraint(
                condition=~models.Q(purpose__regex=r"^\s*$"), name="stability_shelf_life_purpose"
            ),
        ]

    @property
    def identifier(self):
        return f"SLE-{self.pk}"

    @property
    def title(self):
        return f"{self.name} · {self.protocol_code} · {self.condition}"

    def __str__(self):
        return f"{self.identifier} {self.title}"


class ShelfLifeStudy(models.Model):
    """A study whose results a shelf-life evaluation uses: a study of the evaluation's protocol
    code and container closure. Added and removed only while the evaluation is a draft."""

    evaluation = models.ForeignKey(
        ShelfLifeEvaluation, on_delete=models.PROTECT, related_name="study_links"
    )
    study = models.ForeignKey(Study, on_delete=models.PROTECT, related_name="shelf_life_links")

    class Meta:
        verbose_name = "study of a shelf-life evaluation"
        ordering = ["study_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "study"], name="stability_shelf_life_study_unique"
            )
        ]

    def __str__(self):
        return f"{self.study} in {self.evaluation.identifier}"
