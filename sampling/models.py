from django.conf import settings
from django.db import models
from django.db.models import Q

from catalog.models import ControlledRevision, Stage
from catalog.units import QUANTITY_UNITS, plain


class SamplingBasis(models.TextChoices):
    FIXED = "fixed", "Fixed number of containers"
    SQRT_PLUS_ONE = "sqrt_plus_one", "1 + √N containers, rounded up"
    ALL = "all", "Every container"
    PERCENT = "percent", "Percentage of containers, rounded up"


class SamplingPlan(models.Model):
    """Identity of the sampling plan for one material at one stage."""

    code = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=200)
    material = models.ForeignKey(
        "catalog.Material", on_delete=models.PROTECT, related_name="sampling_plans"
    )
    stage = models.CharField(max_length=16, choices=Stage.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["material", "stage"], name="sampling_plan_unique")
        ]

    def __str__(self):
        return f"{self.code} · {self.title}"


class SamplingPlanRevision(ControlledRevision):
    PARENT_FIELD = "plan"

    plan = models.ForeignKey(SamplingPlan, on_delete=models.PROTECT, related_name="revisions")
    basis = models.CharField(max_length=16, choices=SamplingBasis.choices)
    parameter = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Container count for a fixed plan, or percentage for a percentage plan.",
    )
    minimum_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        help_text="Minimum total amount to collect, including any reserve.",
    )
    quantity_unit = models.CharField(max_length=8, choices=QUANTITY_UNITS)
    composite_allowed = models.BooleanField(default=False)
    instructions = models.TextField(
        help_text="Sampling tools, location, precautions and labelling."
    )
    rationale = models.TextField(
        help_text="Why this plan is representative; required for reduced or subset sampling."
    )

    class Meta(ControlledRevision.Meta):
        constraints = ControlledRevision.Meta.constraints + [
            models.UniqueConstraint(
                fields=["plan", "version"], name="sampling_plan_version_unique"
            ),
            models.CheckConstraint(
                condition=Q(minimum_quantity__gt=0), name="sampling_plan_quantity_positive"
            ),
            models.CheckConstraint(
                condition=(Q(basis__in=["fixed", "percent"]) & Q(parameter__gt=0))
                | (Q(basis__in=["sqrt_plus_one", "all"]) & Q(parameter__isnull=True)),
                name="sampling_plan_parameter_shape",
            ),
        ]

    def __str__(self):
        return f"{self.plan.code} v{self.version}"

    def content(self):
        return {
            "schema": "oq.sampling_plan/1",
            "plan": {
                "id": self.plan_id,
                "code": self.plan.code,
                "title": self.plan.title,
                "material": self.plan.material.code,
                "stage": self.plan.stage,
            },
            "version": self.version,
            "basis": self.basis,
            "parameter": plain(self.parameter),
            "minimum_quantity": plain(self.minimum_quantity),
            "quantity_unit": self.quantity_unit,
            "composite_allowed": self.composite_allowed,
            "instructions": self.instructions,
            "rationale": self.rationale,
            "effective_from": self.effective_from.isoformat(),
            "effective_until": self.effective_until.isoformat(),
        }


class AssignmentStatus(models.TextChoices):
    READY = "ready", "Requirements assigned"
    HOLD = "hold", "Applicability hold"


class LotAssignment(models.Model):
    """Frozen requirements applied to a lot, or an explicit hold. Append-only; latest is current."""

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="qc_assignments")
    material = models.ForeignKey("catalog.Material", on_delete=models.PROTECT, related_name="+")
    stage = models.CharField(max_length=16, choices=Stage.choices)
    scope = models.SlugField(max_length=60, default="general")
    status = models.CharField(max_length=8, choices=AssignmentStatus.choices)
    hold_reasons = models.JSONField(default=list, blank=True)
    specification_revision = models.ForeignKey(
        "catalog.SpecificationRevision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    plan_revision = models.ForeignKey(
        SamplingPlanRevision, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    payload = models.JSONField(null=True, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    supersedes = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )
    reason = models.TextField()
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="ready")
                    & Q(payload__isnull=False)
                    & Q(specification_revision__isnull=False)
                    & Q(plan_revision__isnull=False)
                )
                | (Q(status="hold") & Q(payload__isnull=True)),
                name="lot_assignment_shape",
            )
        ]

    def __str__(self):
        return f"{self.lot} requirements #{self.pk}"


class SamplingPurpose(models.TextChoices):
    ROUTINE = "routine", "Routine sampling"
    RESAMPLE = "resample", "Resample for an investigation"


class SamplingRecord(models.Model):
    """What was actually sampled, by whom, against which approved plan. Corrections add a record."""

    lot = models.ForeignKey(
        "quality.Lot", on_delete=models.PROTECT, related_name="sampling_records"
    )
    sample = models.ForeignKey(
        "quality.Sample", on_delete=models.PROTECT, related_name="sampling_records"
    )
    assignment = models.ForeignKey(LotAssignment, on_delete=models.PROTECT, related_name="+")
    plan_revision = models.ForeignKey(
        SamplingPlanRevision, on_delete=models.PROTECT, related_name="+"
    )
    containers_total = models.PositiveIntegerField()
    containers_required = models.PositiveIntegerField()
    containers_sampled = models.PositiveIntegerField()
    container_ids = models.TextField(help_text="Identifiers of the containers sampled.")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    quantity_unit = models.CharField(max_length=8, choices=QUANTITY_UNITS)
    location = models.CharField(max_length=160)
    sampled_at = models.DateTimeField()
    sampled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    deviation = models.TextField(blank=True)
    reason = models.TextField()
    corrects = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrected_by"
    )
    purpose = models.CharField(
        max_length=12, choices=SamplingPurpose.choices, default=SamplingPurpose.ROUTINE
    )
    resample_of = models.ForeignKey(
        "quality.Sample", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["recorded_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sampling_quantity_positive"),
            models.CheckConstraint(
                condition=Q(containers_sampled__gte=1)
                & Q(containers_sampled__lte=models.F("containers_total")),
                name="sampling_containers_within_lot",
            ),
            models.CheckConstraint(
                condition=(Q(purpose="routine") & Q(resample_of__isnull=True))
                | (Q(purpose="resample") & Q(resample_of__isnull=False)),
                name="sampling_resample_link",
            ),
        ]

    def __str__(self):
        return f"Sampling of {self.sample}"

    @property
    def deviates(self):
        return bool(self.deviation)


class DeviationStatus(models.TextChoices):
    PENDING = "pending", "Awaiting quality assessment"
    ACCEPTED = "accepted", "Accepted by quality"
    REJECTED = "rejected", "Rejected by quality"


class DeviationReview(models.Model):
    """Independent signed quality assessment of one sampling record's deviation."""

    record = models.OneToOneField(
        SamplingRecord, on_delete=models.PROTECT, related_name="deviation_review"
    )
    status = models.CharField(
        max_length=10, choices=DeviationStatus.choices, default=DeviationStatus.PENDING
    )
    revision = models.PositiveIntegerField(default=1)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(status="pending") & Q(decided_by__isnull=True))
                | (
                    ~Q(status="pending") & Q(decided_by__isnull=False) & Q(decided_at__isnull=False)
                ),
                name="deviation_review_decided",
            )
        ]

    def __str__(self):
        return f"Deviation review of {self.record.sample}"
