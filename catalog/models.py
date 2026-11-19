from django.conf import settings
from django.core.validators import URLValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from core import formulas

from .units import INPUT_UNITS, RESULT_UNITS, plain


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
    Approved intervals are finite and half-open, [effective_from, effective_until). Approving a
    later version whose period overlaps retires this one: ``superseded_from`` is the moment it
    stops applying and ``superseded_by`` the version that took over. The approved content and
    its signature are not touched, so the periods in which versions apply never overlap.
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
    superseded_from = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

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
            # Only an approved version is superseded, by a named version, inside its own period.
            models.CheckConstraint(
                condition=Q(superseded_from__isnull=True, superseded_by__isnull=True)
                | Q(
                    status="approved",
                    superseded_from__isnull=False,
                    superseded_by__isnull=False,
                    superseded_from__gte=F("effective_from"),
                    superseded_from__lt=F("effective_until"),
                ),
                name="%(app_label)s_%(class)s_superseded",
            ),
        ]

    @property
    def parent(self):
        return getattr(self, self.PARENT_FIELD)

    @property
    def is_draft(self):
        return self.status == RevisionStatus.DRAFT

    @property
    def applies_until(self):
        """The moment this version stops applying: its own end, or an earlier supersession."""
        return self.superseded_from or self.effective_until

    @property
    def never_applied(self):
        """Superseded from its own start: a later version took over before it began."""
        return self.superseded_from is not None and self.superseded_from <= self.effective_from

    def is_effective(self, at):
        return (
            self.status == RevisionStatus.APPROVED
            and self.effective_from <= at < self.applies_until
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


# An external link is untrusted text: only http(s) is accepted.
http_url = URLValidator(schemes=["http", "https"])

# Kinds of evidence that name where the procedure comes from: the pharmacopoeial text that is
# verified, or the laboratory that transfers it.
SOURCED_KINDS = (SuitabilityKind.COMPENDIAL_VERIFICATION, SuitabilityKind.TRANSFER)


def _stated(*names):
    condition = Q()
    for name in names:
        condition &= ~Q(**{f"{name}__regex": r"^\s*$"})
    return condition


class MethodEvidence(models.Model):
    """The laboratory's record of the evidence that a method is suitable for its intended use:
    a validation, the verification of a compendial procedure, a transfer from another
    laboratory, or another documented demonstration of fitness for use.

    It summarizes the report kept in the laboratory's document system: what was studied and for
    which use, each performance characteristic with its acceptance criterion and result, and the
    conclusion. Recorded and changed as a draft; a quality person who neither recorded nor
    changed it approves it with a signature, which freezes ``content``. An approved record is
    never edited or deleted (database guard, migration 0009); quality can withdraw it with a
    signature. A method version relies on an approved record through ``MethodRevision.evidence``.
    """

    class TransferApproach(models.TextChoices):
        COMPARATIVE = "comparative", "Comparative testing"
        COVALIDATION = "covalidation", "Co-validation between laboratories"
        REVALIDATION = "revalidation", "Revalidation or partial revalidation"
        WAIVER = "waiver", "Transfer waiver"

    class Conclusion(models.TextChoices):
        SUITABLE = "suitable", "Suitable for the intended use"
        NOT_SUITABLE = "not_suitable", "Not suitable"

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        WITHDRAWN = "withdrawn", "Withdrawn"

    method = models.ForeignKey(Method, on_delete=models.PROTECT, related_name="evidence")
    kind = models.CharField(max_length=32, choices=SuitabilityKind.choices)
    title = models.CharField(
        max_length=160, help_text="Short name, e.g. Validation of the assay in film-coated tablets."
    )
    procedure_ref = models.CharField(
        "Procedure studied",
        max_length=200,
        help_text="The controlled procedure that was studied, with its revision.",
    )
    intended_use = models.TextField(
        "Intended use",
        help_text="What the method is used for: the analyte or property, the materials or "
        "matrices, the range, and the decisions its results support.",
    )
    source = models.CharField(
        "Source of the procedure",
        max_length=200,
        blank=True,
        help_text="For a compendial verification, the pharmacopoeial text and its edition; for a "
        "transfer, the transferring laboratory.",
    )
    transfer_approach = models.CharField(
        max_length=16,
        blank=True,
        choices=TransferApproach.choices,
        help_text="For a transfer: how the receiving laboratory showed it can perform the method.",
    )
    protocol_ref = models.CharField(
        "Protocol",
        max_length=200,
        blank=True,
        help_text="The approved protocol with its revision, when the study had one.",
    )
    report_ref = models.CharField(
        "Report",
        max_length=200,
        help_text="The report with its revision, as kept in the laboratory's document system.",
    )
    report_url = models.URLField("Report link", blank=True, max_length=500, validators=[http_url])
    completed_on = models.DateField(help_text="The day the report was completed.")
    conclusion = models.CharField(max_length=16, choices=Conclusion.choices)
    statement = models.TextField(
        "Statement of suitability",
        help_text="The report's conclusion: whether and how the method is fit for its intended "
        "use, with any conditions of use.",
    )
    deviations = models.TextField(
        "Deviations",
        blank=True,
        help_text="Deviations from the protocol and criteria that were not met, and how each was "
        "assessed.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT)
    approved_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    # Frozen by the approval signature: every field above and each characteristic.
    content = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "method evidence record"
        ordering = ["-completed_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=_stated(
                    "title", "procedure_ref", "intended_use", "report_ref", "statement"
                ),
                name="method_evidence_stated",
            ),
            models.CheckConstraint(
                condition=~Q(kind__in=SOURCED_KINDS) | _stated("source"),
                name="method_evidence_source",
            ),
            models.CheckConstraint(
                condition=Q(
                    kind="transfer",
                    transfer_approach__in=["comparative", "covalidation", "revalidation", "waiver"],
                )
                | (~Q(kind="transfer") & Q(transfer_approach="")),
                name="method_evidence_transfer_approach",
            ),
            models.CheckConstraint(
                condition=Q(
                    state="draft",
                    approved_at__isnull=True,
                    withdrawn_at__isnull=True,
                    content__isnull=True,
                    content_hash="",
                )
                | Q(
                    ~Q(content_hash=""),
                    state="approved",
                    approved_at__isnull=False,
                    withdrawn_at__isnull=True,
                    content__isnull=False,
                )
                | Q(
                    Q(approved_at__isnull=True, content__isnull=True, content_hash="")
                    | Q(~Q(content_hash=""), approved_at__isnull=False, content__isnull=False),
                    state="withdrawn",
                    withdrawn_at__isnull=False,
                ),
                name="method_evidence_states",
            ),
        ]

    @property
    def identifier(self):
        return f"MEV-{self.pk}"

    @property
    def is_draft(self):
        return self.state == self.State.DRAFT

    @property
    def criteria_not_met(self):
        return [c for c in self.characteristics.all() if c.outcome == c.Outcome.NOT_MET]

    def __str__(self):
        return f"{self.identifier} · {self.title}"

    def frozen(self):
        """Everything the approval signature binds: the record and its characteristics."""
        return {
            "schema": "oq.method_evidence/1",
            "identifier": self.identifier,
            "method": {"id": self.method_id, "code": self.method.code},
            "kind": self.kind,
            "title": self.title,
            "procedure_ref": self.procedure_ref,
            "intended_use": self.intended_use,
            "source": self.source,
            "transfer_approach": self.transfer_approach,
            "protocol_ref": self.protocol_ref,
            "report_ref": self.report_ref,
            "report_url": self.report_url,
            "completed_on": self.completed_on.isoformat(),
            "conclusion": self.conclusion,
            "statement": self.statement,
            "deviations": self.deviations,
            "characteristics": [item.content() for item in self.characteristics.all()],
        }


class MethodEvidenceCharacteristic(models.Model):
    """One performance characteristic of a method evidence record: what was evaluated, its
    acceptance criterion, the result obtained and whether the criterion was met. Added and
    removed only while the record is a draft, never changed (database guard, migration 0009).

    Entry order is the order of creation (``id``)."""

    class Characteristic(models.TextChoices):
        SPECIFICITY = "specificity", "Specificity or selectivity"
        RANGE = "range", "Range and response (linearity)"
        ACCURACY = "accuracy", "Accuracy"
        REPEATABILITY = "repeatability", "Repeatability"
        INTERMEDIATE_PRECISION = "intermediate_precision", "Intermediate precision"
        REPRODUCIBILITY = "reproducibility", "Reproducibility"
        DETECTION_LIMIT = "detection_limit", "Detection limit"
        QUANTITATION_LIMIT = "quantitation_limit", "Quantitation limit"
        ROBUSTNESS = "robustness", "Robustness"
        COMPARISON = "comparison", "Comparison between laboratories"
        OTHER = "other", "Other"

    class Outcome(models.TextChoices):
        MET = "met", "Met"
        NOT_MET = "not_met", "Not met"

    evidence = models.ForeignKey(
        MethodEvidence, on_delete=models.PROTECT, related_name="characteristics"
    )
    characteristic = models.CharField(max_length=32, choices=Characteristic.choices)
    detail = models.CharField(
        max_length=160,
        blank=True,
        help_text="What was evaluated, e.g. recovery at 80, 100 and 120 % of the label claim. "
        "Required for Other.",
    )
    criterion = models.TextField("Acceptance criterion")
    result = models.TextField("Result obtained")
    outcome = models.CharField("Criterion", max_length=8, choices=Outcome.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=_stated("criterion", "result"),
                name="method_evidence_characteristic_stated",
            ),
            models.CheckConstraint(
                condition=~Q(characteristic="other") | _stated("detail"),
                name="method_evidence_characteristic_other",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        name = self.get_characteristic_display()
        return f"{name}: {self.detail}" if self.detail else name

    def content(self):
        return {
            "characteristic": self.characteristic,
            "detail": self.detail,
            "criterion": self.criterion,
            "result": self.result,
            "outcome": self.outcome,
        }


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
    # The approved record of the evidence this version relies on, when the laboratory keeps
    # it here; the kind and reference above are then taken from it. Set on a draft by services
    # and frozen with the approved content.
    evidence = models.ForeignKey(
        MethodEvidence,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="method_versions",
        verbose_name="Evidence record",
    )
    summary = models.TextField(blank=True)
    requires_batch = models.BooleanField(
        "Runs in a QC batch",
        default=False,
        help_text="Results must be produced in an analytical batch whose QC checks pass.",
    )
    requires_equipment = models.BooleanField(
        "Records an instrument",
        default=False,
        help_text="Every result and batch QC entry must record at least one instrument.",
    )
    requires_reagent = models.BooleanField(
        "Records a reagent or standard",
        default=False,
        help_text="Every result and batch QC entry must record at least one reagent or "
        "standard lot.",
    )
    requires_review_qualification = models.BooleanField(
        "Reviewers qualified for the method",
        default=False,
        help_text="Whoever reviews or returns a result of this version needs an approved, "
        "current qualification to review the method.",
    )
    # One optional calculation. Formula, unit and decimals are changed on a draft by services
    # (the database allows only these three columns to change on a draft); its inputs are
    # MethodCalculationInput rows. A version without a formula and without inputs has none.
    calculation_formula = models.CharField(max_length=formulas.MAX_LENGTH, blank=True)
    calculation_unit = models.CharField(max_length=40, blank=True, choices=RESULT_UNITS)
    calculation_decimals = models.PositiveSmallIntegerField(null=True, blank=True)
    # One optional instrument file import (``core.file_imports``): how the export of the
    # method's instrument is read into results. Changed on a draft by services, like the
    # calculation; frozen with the approved content.
    file_import = models.JSONField(null=True, blank=True)

    class Meta(ControlledRevision.Meta):
        constraints = ControlledRevision.Meta.constraints + [
            models.UniqueConstraint(fields=["method", "version"], name="method_version_unique"),
            models.CheckConstraint(
                condition=Q(calculation_decimals__isnull=True)
                | Q(calculation_decimals__lte=formulas.MAX_DECIMALS),
                name="method_calculation_decimals",
            ),
        ]

    def __str__(self):
        return f"{self.method.code} v{self.version}"

    def content(self):
        content = {
            "schema": "oq.method/1",
            "method": {"id": self.method_id, "code": self.method.code, "title": self.method.title},
            "version": self.version,
            "technique": self.technique,
            "document_ref": self.document_ref,
            "suitability_kind": self.suitability_kind,
            "suitability_ref": self.suitability_ref,
            "summary": self.summary,
            "requires_batch": self.requires_batch,
            "requires_equipment": self.requires_equipment,
            "requires_reagent": self.requires_reagent,
            "requires_review_qualification": self.requires_review_qualification,
            "qc_checks": [check.content() for check in self.qc_checks.all()],
            "calculation": self.calculation(),
            "file_import": self.file_import,
            "effective_from": self.effective_from.isoformat(),
            "effective_until": self.effective_until.isoformat(),
        }
        # Only a version that lists suitable resources carries the key, so the content (and the
        # hash) of every other version stays as it was.
        if self.pk and (resources := [item.content() for item in self.resources.all()]):
            content["resources"] = resources
        # Only a version that relies on a record kept here carries the key.
        if self.evidence_id:
            evidence = self.evidence
            content["evidence"] = {
                "id": evidence.pk,
                "identifier": evidence.identifier,
                "kind": evidence.kind,
                "conclusion": evidence.conclusion,
                "content_hash": evidence.content_hash,
            }
        return content

    @property
    def has_calculation(self):
        return bool(
            self.calculation_formula.strip()
            or self.calculation_unit
            or self.calculation_decimals is not None
            or (self.pk and self.calculation_inputs.exists())
        )

    @property
    def import_fields(self):
        """The fields a file import fills: the calculation's input codes in entry order, or
        ``value`` when the result is entered directly."""
        from core.file_imports import VALUE

        if self.has_calculation:
            return [item.code for item in self.calculation_inputs.all()]
        return [VALUE]

    def file_import_view(self):
        """The file import for the pages: {"facts": [(label, text)], "columns": [(field,
        column)]}, or None when there is none. Shows a draft as entered, valid or not."""
        from core import file_imports

        data = self.file_import
        if not data:
            return None
        delimiter = dict(file_imports.DELIMITER_CHOICES).get(data.get("delimiter"), "?")
        decimal = dict(file_imports.DECIMAL_CHOICES).get(data.get("decimal"), "?")
        encoding = dict(file_imports.ENCODING_CHOICES).get(data.get("encoding"), "?")
        rows = f"rows whose “{data.get('id_column', '')}” is the test number"
        if data.get("filter_column"):
            rows += f" and whose “{data['filter_column']}” is “{data.get('filter_value', '')}”"
        names = {item.code: item.name for item in self.calculation_inputs.all()}
        names.setdefault(file_imports.VALUE, "Result")
        mapped = {c.get("field"): c.get("column") for c in data.get("columns", [])}
        fields = self.import_fields
        columns = [(names.get(f, f), f, mapped.get(f, "")) for f in fields]
        columns += [(f, f, column) for f, column in mapped.items() if f not in fields]
        return {
            "facts": [
                ("Export", data.get("source", "")),
                ("Format", f"{delimiter} separated, decimal mark {decimal}, {encoding}"),
                ("Column names", f"Row {data.get('header_row', '?')}"),
                ("Rows read", rows),
            ],
            "columns": columns,
        }

    def calculation(self):
        """The calculation as frozen in the approved content, or None when there is none."""
        if not self.has_calculation:
            return None
        return {
            "formula": self.calculation_formula.strip(),
            "inputs": [item.content() for item in self.calculation_inputs.all()],
            "unit": self.calculation_unit,
            "decimals": self.calculation_decimals,
        }


class MethodCalculationInput(models.Model):
    """Named raw input of a method calculation. Editable only while the version is a draft.

    Entry order is the order of creation (``id``).
    """

    method_revision = models.ForeignKey(
        MethodRevision, on_delete=models.PROTECT, related_name="calculation_inputs"
    )
    code = models.CharField(
        max_length=40, help_text="Name used in the formula, e.g. peak_area or sample_mass."
    )
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=24, choices=INPUT_UNITS)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["method_revision", "code"], name="method_calculation_input_unique"
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"

    def content(self):
        return {"code": self.code, "name": self.name, "unit": self.unit}


MAX_METHOD_RESOURCES = 20


class MethodResource(models.Model):
    """A kind of instrument, or a reagent, reference standard or prepared solution, suitable for
    a method version. Added and removed only while the version is a draft (database guard in
    migration 0010) and frozen with its approved content.

    An instrument line names an equipment category; the other kinds name a reagent lot's kind and
    name as the laboratory register records them. ``required``: every result and batch QC entry
    records one. ``method_qualified`` (instruments only): the instrument also needs an approved,
    current qualification whose activity is the method's code.
    """

    class Kind(models.TextChoices):
        INSTRUMENT = "instrument", "Instrument"
        # The values of laboratory.ReagentLot.Kind, which a line is matched against.
        REAGENT = "reagent", "Reagent"
        STANDARD = "reference_standard", "Reference standard"
        PREPARED = "prepared_solution", "Prepared solution"

    method_revision = models.ForeignKey(
        MethodRevision, on_delete=models.PROTECT, related_name="resources"
    )
    kind = models.CharField(max_length=24, choices=Kind)
    name = models.CharField(
        max_length=160,
        help_text="The equipment category, or the name of the reagent, standard or solution, "
        "as the register records it.",
    )
    required = models.BooleanField("Recorded with every result", default=True)
    method_qualified = models.BooleanField("Qualified for the method", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                "method_revision", "kind", Lower("name"), name="method_resource_unique"
            ),
            models.CheckConstraint(
                condition=Q(kind="instrument") | Q(method_qualified=False),
                name="method_resource_qualified_instrument",
            ),
            models.CheckConstraint(condition=~Q(name=""), name="method_resource_named"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"

    @property
    def is_instrument(self):
        return self.kind == self.Kind.INSTRUMENT

    def content(self):
        return {
            "kind": self.kind,
            "name": self.name,
            "required": self.required,
            "method_qualified": self.method_qualified,
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
