from django.conf import settings
from django.db import models
from django.db.models import F, Q

from .units import RESULT_UNITS, plain


class Stage(models.TextChoices):
    INCOMING = "incoming", "Incoming material"
    IN_PROCESS = "in_process", "In-process"
    FINISHED = "finished", "Finished product"
    STABILITY = "stability", "Stability"


class MaterialKind(models.TextChoices):
    RAW_MATERIAL = "raw_material", "Raw material or ingredient"
    COMPONENT = "component", "Component or part"
    PACKAGING = "packaging", "Packaging material"
    INTERMEDIATE = "intermediate", "Intermediate or bulk"
    FINISHED_PRODUCT = "finished_product", "Finished product"


class RevisionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    WITHDRAWN = "withdrawn", "Withdrawn"


class Material(models.Model):
    """Identity of a controlled material or product. Immutable once created."""

    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=24, choices=MaterialKind.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class ControlledRevision(models.Model):
    """Version of a controlled document: draft until independently signed, then frozen.

    ``version`` numbers versions of one parent; ``revision`` is the record revision signed.
    Approved intervals are finite, half-open [effective_from, effective_until) and never overlap.
    """

    PARENT_FIELD = ""

    version = models.PositiveIntegerField()
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=12, choices=RevisionStatus.choices, default=RevisionStatus.DRAFT
    )
    effective_from = models.DateTimeField()
    effective_until = models.DateTimeField()
    change_reason = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_content = models.JSONField(null=True, blank=True)
    approved_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        abstract = True
        ordering = ["-version"]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_until__gt=F("effective_from")),
                name="%(app_label)s_%(class)s_interval",
            ),
            models.CheckConstraint(
                condition=~Q(status="approved") | Q(approved_content__isnull=False),
                name="%(app_label)s_%(class)s_frozen",
            ),
        ]

    @property
    def parent(self):
        return getattr(self, self.PARENT_FIELD)

    @property
    def is_draft(self):
        return self.status == RevisionStatus.DRAFT

    def is_effective(self, at):
        return (
            self.status == RevisionStatus.APPROVED
            and self.effective_from <= at < self.effective_until
        )

    def content(self):
        raise NotImplementedError


class Method(models.Model):
    code = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.title}"


class SuitabilityKind(models.TextChoices):
    VALIDATION = "validation", "Method validation"
    COMPENDIAL_VERIFICATION = "compendial_verification", "Compendial method verification"
    TRANSFER = "transfer", "Method transfer"
    FIT_FOR_PURPOSE = "fit_for_purpose", "Documented fitness for intended use"


class MethodRevision(ControlledRevision):
    PARENT_FIELD = "method"

    method = models.ForeignKey(Method, on_delete=models.PROTECT, related_name="revisions")
    technique = models.CharField(max_length=120)
    document_ref = models.CharField(
        "Controlled procedure",
        max_length=160,
        help_text="Document ID and revision, e.g. SOP-QC-014 rev 3.",
    )
    suitability_kind = models.CharField(max_length=32, choices=SuitabilityKind.choices)
    suitability_ref = models.CharField(
        "Suitability evidence",
        max_length=200,
        help_text="Stable ID or location of the approved validation/verification evidence.",
    )
    summary = models.TextField(blank=True)
    requires_batch = models.BooleanField(
        "Runs in a QC batch",
        default=False,
        help_text="Results must be produced in an analytical batch whose QC checks pass.",
    )

    class Meta(ControlledRevision.Meta):
        constraints = ControlledRevision.Meta.constraints + [
            models.UniqueConstraint(fields=["method", "version"], name="method_version_unique")
        ]

    def __str__(self):
        return f"{self.method.code} v{self.version}"

    def content(self):
        return {
            "schema": "oq.method/1",
            "method": {"id": self.method_id, "code": self.method.code, "title": self.method.title},
            "version": self.version,
            "technique": self.technique,
            "document_ref": self.document_ref,
            "suitability_kind": self.suitability_kind,
            "suitability_ref": self.suitability_ref,
            "summary": self.summary,
            "requires_batch": self.requires_batch,
            "qc_checks": [check.content() for check in self.qc_checks.all()],
            "effective_from": self.effective_from.isoformat(),
            "effective_until": self.effective_until.isoformat(),
        }


class MethodQCCheck(models.Model):
    """Batch QC acceptance check of a method version. Editable only while the version is a draft."""

    method_revision = models.ForeignKey(
        MethodRevision, on_delete=models.PROTECT, related_name="qc_checks"
    )
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=24, choices=RESULT_UNITS)
    lower_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    upper_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["method_revision", "code"], name="method_qc_unique"),
            models.CheckConstraint(
                condition=(Q(lower_limit__isnull=False) | Q(upper_limit__isnull=False))
                & (
                    Q(lower_limit__isnull=True)
                    | Q(upper_limit__isnull=True)
                    | Q(lower_limit__lte=F("upper_limit"))
                ),
                name="method_qc_limits",
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"

    def content(self):
        return {
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "lower_limit": plain(self.lower_limit),
            "upper_limit": plain(self.upper_limit),
        }


class Specification(models.Model):
    """One specification identity: a material at a stage for one general/market/customer scope."""

    code = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=200)
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="specifications")
    stage = models.CharField(max_length=16, choices=Stage.choices)
    scope = models.SlugField(
        max_length=60,
        default="general",
        help_text="general, or an explicit market/customer overlay such as eu-market.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["material", "stage", "scope"], name="specification_applicability_unique"
            )
        ]

    def __str__(self):
        return f"{self.code} · {self.title}"


class SpecificationRevision(ControlledRevision):
    PARENT_FIELD = "specification"

    specification = models.ForeignKey(
        Specification, on_delete=models.PROTECT, related_name="revisions"
    )
    basis = models.TextField(help_text="Scientific or contractual basis for these limits.")

    class Meta(ControlledRevision.Meta):
        constraints = ControlledRevision.Meta.constraints + [
            models.UniqueConstraint(
                fields=["specification", "version"], name="specification_version_unique"
            )
        ]

    def __str__(self):
        return f"{self.specification.code} v{self.version}"

    def content(self):
        spec = self.specification
        return {
            "schema": "oq.specification/1",
            "specification": {
                "id": spec.pk,
                "code": spec.code,
                "title": spec.title,
                "material": spec.material.code,
                "stage": spec.stage,
                "scope": spec.scope,
            },
            "version": self.version,
            "basis": self.basis,
            "effective_from": self.effective_from.isoformat(),
            "effective_until": self.effective_until.isoformat(),
            "tests": [line.content() for line in self.tests.select_related("method")],
        }


class ResultType(models.TextChoices):
    NUMERIC = "numeric", "Numeric with limits"
    COUNT = "count", "Count (whole number)"
    QUALITATIVE = "qualitative", "Qualitative (expected outcome)"


class ExpectedResult(models.TextChoices):
    """Expected outcome of a qualitative test; each has one deviating counterpart."""

    CONFORMS = "conforms", "Conforms"
    ABSENT = "absent", "Absent"
    PRESENT = "present", "Present"


class SpecificationTest(models.Model):
    """One required test line. Editable only while its revision is a draft (database enforced)."""

    specification_revision = models.ForeignKey(
        SpecificationRevision, on_delete=models.PROTECT, related_name="tests"
    )
    position = models.PositiveSmallIntegerField(default=1)
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=160)
    method = models.ForeignKey(Method, on_delete=models.PROTECT, related_name="+")
    result_type = models.CharField(max_length=12, choices=ResultType.choices)
    unit = models.CharField(max_length=24, choices=RESULT_UNITS, blank=True)
    lower_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    lower_inclusive = models.BooleanField(default=True)
    upper_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    upper_inclusive = models.BooleanField(default=True)
    reporting_decimals = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="If set, results are rounded half up to this many decimals before comparison.",
    )
    expected_text = models.CharField(max_length=160, blank=True)
    # Blank on numeric/count lines and on qualitative lines approved before outcomes existed;
    # services require it for new qualitative lines and refuse to approve a draft without it.
    expected_result = models.CharField(
        max_length=12, choices=ExpectedResult.choices, blank=True, default=""
    )
    required = models.BooleanField(
        default=True, help_text="Required tests must be complete before QC disposition."
    )
    replicates = models.PositiveSmallIntegerField(
        default=1, help_text="Replicate determinations averaged into the reportable value."
    )
    replicate_limits = models.BooleanField(
        "Each replicate must meet the limits",
        default=True,
        help_text="If set, every replicate must conform, not only the reportable mean.",
    )
    max_retests = models.PositiveSmallIntegerField(
        "Maximum retests",
        default=0,
        help_text="Retests allowed only under an approved investigation; 0 allows none.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["position", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["specification_revision", "code"], name="specification_test_unique"
            ),
            models.CheckConstraint(
                condition=Q(lower_limit__isnull=True)
                | Q(upper_limit__isnull=True)
                | Q(lower_limit__lte=F("upper_limit")),
                name="specification_limits_ordered",
            ),
            models.CheckConstraint(
                condition=(
                    Q(result_type__in=["numeric", "count"])
                    & ~Q(unit="")
                    & (Q(lower_limit__isnull=False) | Q(upper_limit__isnull=False))
                    & Q(expected_text="")
                    & Q(expected_result="")
                )
                | (
                    Q(result_type="qualitative")
                    & Q(lower_limit__isnull=True)
                    & Q(upper_limit__isnull=True)
                    & Q(reporting_decimals__isnull=True)
                    & ~Q(expected_text="")
                    & Q(expected_result__in=["", "conforms", "absent", "present"])
                ),
                name="specification_test_shape",
            ),
            models.CheckConstraint(
                condition=Q(replicates__gte=1, replicates__lte=10, max_retests__lte=3),
                name="specification_test_replication",
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"

    def content(self):
        return {
            "code": self.code,
            "name": self.name,
            "position": self.position,
            "method": self.method.code,
            "result_type": self.result_type,
            "unit": self.unit,
            "lower_limit": plain(self.lower_limit),
            "lower_inclusive": self.lower_inclusive,
            "upper_limit": plain(self.upper_limit),
            "upper_inclusive": self.upper_inclusive,
            "reporting_decimals": self.reporting_decimals,
            "expected_text": self.expected_text,
            "expected_result": self.expected_result,
            "required": self.required,
            "replicates": self.replicates,
            "replicate_limits": self.replicate_limits,
            "max_retests": self.max_retests,
        }

    @property
    def limit_text(self):
        from .services import describe_limits

        return describe_limits(self.content())
