"""Stability studies, reserve samples, retention obligations and holds.

Protocols, studies and pulls reuse the foundation lot/sample identities. Native scheduling is
deliberately thin: a controlled protocol, the pulls it implies, and links to the testing/review
spine or to an external stability system. Controlled fields are frozen by PostgreSQL triggers
(migration 0002); every lifecycle change bumps `revision`.
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
