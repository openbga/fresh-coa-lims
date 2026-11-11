"""Laboratory operations evidence: equipment fitness, analyst qualification, reagents/standards.

Records are append-oriented. Controlled fields are frozen by PostgreSQL triggers (see migration
0002); only the lifecycle columns named there can change, and every change bumps `revision`.
Dates named `*_date`/`valid_*` are inclusive calendar days in the deployment time zone.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone

http_url = URLValidator(schemes=["http", "https"])


def evidence_url():
    """External controlled-document link. Untrusted text: only http(s) is accepted."""
    return models.URLField(blank=True, max_length=500, validators=[http_url])


class Equipment(models.Model):
    class State(models.TextChoices):
        IN_SERVICE = "in_service", "In service"
        OUT_OF_SERVICE = "out_of_service", "Out of service"

    asset_id = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=160)
    category = models.CharField(max_length=80, help_text="For example balance, HPLC, chamber.")
    location = models.CharField(max_length=120, blank=True)
    requires_qualification = models.BooleanField(
        default=True,
        help_text="Require approved installation/operational/performance qualification evidence.",
    )
    state = models.CharField(max_length=20, choices=State, default=State.IN_SERVICE)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["asset_id"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return self.asset_id


class Calibration(models.Model):
    """One calibration/verification event. Failed events block use as soon as recorded;
    passing events count only after independent signed acceptance."""

    class Outcome(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting acceptance"
        ACCEPTED = "accepted", "Accepted"

    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="calibrations")
    performed_at = models.DateTimeField()
    due_date = models.DateField(help_text="Last day the calibration remains valid (inclusive).")
    outcome = models.CharField(max_length=8, choices=Outcome)
    standard_ref = models.CharField(
        max_length=200, help_text="Reference standard or certificate providing traceability."
    )
    certificate_ref = models.CharField(max_length=200, blank=True)
    certificate_url = evidence_url()
    tolerance_note = models.TextField(blank=True, help_text="As-found/as-left values and limits.")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-performed_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state="recorded", accepted_at__isnull=True)
                | models.Q(state="accepted", accepted_at__isnull=False),
                name="calibration_acceptance_time",
            )
        ]

    def clean(self):
        if self.performed_at and self.due_date:
            # Dates are calendar days in the deployment (laboratory) time zone, not UTC.
            performed_on = (
                timezone.localdate(self.performed_at)
                if timezone.is_aware(self.performed_at)
                else self.performed_at.date()
            )
            if self.due_date < performed_on:
                raise ValidationError("The due date cannot precede the calibration date.")

    def __str__(self):
        return f"{self.equipment} calibration {self.performed_at:%Y-%m-%d}"


class Qualification(models.Model):
    """Approved evidence that an analyst is qualified for an activity/method, or that an
    instrument is qualified for its intended use. Exactly one subject."""

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REVOKED = "revoked", "Revoked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    equipment = models.ForeignKey(
        Equipment, null=True, blank=True, on_delete=models.PROTECT, related_name="qualifications"
    )
    activity = models.CharField(
        max_length=120, help_text="Method, activity or qualification stage (e.g. IQ/OQ/PQ)."
    )
    scope_note = models.TextField(blank=True)
    evidence_ref = models.CharField(
        max_length=200, help_text="Controlled training or qualification record and revision."
    )
    evidence_url = evidence_url()
    valid_from = models.DateField()
    valid_until = models.DateField(help_text="Last day of validity (inclusive).")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    approved_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False, equipment__isnull=True)
                | models.Q(user__isnull=True, equipment__isnull=False),
                name="qualification_one_subject",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__gte=models.F("valid_from")),
                name="qualification_interval_ordered",
            ),
        ]

    @property
    def subject(self):
        return self.user or self.equipment

    def __str__(self):
        return f"{self.subject} · {self.activity}"


class ReagentLot(models.Model):
    """Reagent, reference standard or prepared solution with provenance and independent release."""

    class Kind(models.TextChoices):
        REAGENT = "reagent", "Reagent"
        STANDARD = "reference_standard", "Reference standard"
        PREPARED = "prepared_solution", "Prepared solution"

    class State(models.TextChoices):
        RECEIVED = "received", "Awaiting release"
        RELEASED = "released", "Released for use"
        REJECTED = "rejected", "Rejected"

    identifier = models.CharField(max_length=60, unique=True)
    kind = models.CharField(max_length=24, choices=Kind)
    name = models.CharField(max_length=160)
    supplier = models.CharField(max_length=160, blank=True)
    lot_number = models.CharField(max_length=80)
    received_on = models.DateField(help_text="Receipt or preparation date.")
    expiry_date = models.DateField(help_text="Last day of use (inclusive).")
    assigned_purity = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    purity_unit = models.CharField(max_length=20, blank=True, help_text="For example % w/w.")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="preparations",
        help_text="Source lot for a prepared solution.",
    )
    preparation_note = models.TextField(blank=True, help_text="Diluent, amounts and calculation.")
    certificate_ref = models.CharField(max_length=200, blank=True)
    certificate_url = evidence_url()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECEIVED)
    released_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expiry_date__gte=models.F("received_on")),
                name="reagent_expiry_after_receipt",
            ),
            models.CheckConstraint(
                condition=models.Q(assigned_purity__isnull=True, purity_unit="")
                | models.Q(assigned_purity__isnull=False) & ~models.Q(purity_unit=""),
                name="reagent_purity_has_unit",
            ),
        ]

    def __str__(self):
        return f"{self.identifier} {self.name}"


class ResourceUse(models.Model):
    """Append-only evidence that an eligible resource was used for a piece of work."""

    equipment = models.ForeignKey(
        Equipment, null=True, blank=True, on_delete=models.PROTECT, related_name="uses"
    )
    reagent_lot = models.ForeignKey(
        ReagentLot, null=True, blank=True, on_delete=models.PROTECT, related_name="uses"
    )
    context_type = models.CharField(max_length=60, help_text="For example quality.sample.")
    context_id = models.CharField(max_length=64)
    activity = models.CharField(max_length=120)
    test_code = models.CharField(max_length=80, blank=True)
    profile_ref = models.CharField(
        max_length=120, blank=True, help_text="Stable test-profile revision, when known."
    )
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    used_at = models.DateTimeField(auto_now_add=True)
    eligibility = models.JSONField(default=dict)

    class Meta:
        ordering = ["-used_at", "-id"]
        indexes = [models.Index(fields=["context_type", "context_id"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(equipment__isnull=False, reagent_lot__isnull=True)
                | models.Q(equipment__isnull=True, reagent_lot__isnull=False),
                name="resource_use_one_resource",
            )
        ]

    @property
    def resource(self):
        return self.equipment or self.reagent_lot
