from django import forms
from django.conf import settings

from core import file_imports, formulas
from core.forms import LocalDateTimeInput, SignatureIdentityForm
from core.lookups import RemoteSelect

from .models import (
    ExpectedResult,
    Material,
    MaterialKind,
    Method,
    MethodEvidence,
    MethodEvidenceCharacteristic,
    ResultType,
    Specification,
    Stage,
    SuitabilityKind,
)
from .units import INPUT_UNITS, RESULT_UNITS

TZ = settings.TIME_ZONE


def effective_fields():
    return {
        "effective_from": forms.DateTimeField(
            label=f"Effective from ({TZ})", widget=LocalDateTimeInput()
        ),
        "effective_until": forms.DateTimeField(
            label=f"Effective until ({TZ})",
            widget=LocalDateTimeInput(),
            help_text="Exclusive end. Approving a later version that overlaps ends this one "
            "earlier.",
        ),
    }


def reason_field(label="Reason for change"):
    return forms.CharField(label=label, max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))


class GroupedForm(forms.Form):
    """Form whose fields render in labelled groups: ``groups = [(legend, [field names])]``."""

    groups = []

    def grouped(self):
        return [(legend, [self[name] for name in names]) for legend, names in self.groups]

    def clean(self):
        data = super().clean()
        start, end = data.get("effective_from"), data.get("effective_until")
        if start and end and end <= start:
            self.add_error("effective_until", "The effective end must be after the start.")
        return data


class MaterialForm(GroupedForm):
    code = forms.SlugField(max_length=60, help_text="Short stable identifier, e.g. api-syn-001.")
    name = forms.CharField(max_length=160)
    kind = forms.ChoiceField(choices=MaterialKind.choices)
    reason = reason_field("Reason")
    groups = [("Material", ["code", "name", "kind"]), ("Change control", ["reason"])]

    def clean_code(self):
        code = self.cleaned_data["code"]
        if Material.objects.filter(code=code).exists():
            raise forms.ValidationError("This material code already exists.")
        return code


class MethodRevisionForm(GroupedForm):
    technique = forms.CharField(max_length=120, help_text="e.g. HPLC-UV, FTIR, plate count.")
    document_ref = forms.CharField(
        label="Controlled procedure",
        max_length=160,
        help_text="Document ID and revision of the approved procedure.",
    )
    suitability_kind = forms.ChoiceField(label="Suitability basis", choices=SuitabilityKind.choices)
    suitability_ref = forms.CharField(
        label="Suitability evidence",
        max_length=200,
        help_text="Stable ID or location of the approved validation or verification report.",
    )
    summary = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    requires_batch = forms.BooleanField(
        label="Runs in a QC batch",
        required=False,
        help_text="If set, add the batch QC checks to the draft before approval.",
    )
    requires_equipment = forms.BooleanField(
        label="Records an instrument",
        required=False,
        help_text="If set, every result and batch QC entry must record at least one instrument.",
    )
    requires_reagent = forms.BooleanField(
        label="Records a reagent or standard",
        required=False,
        help_text="If set, every result and batch QC entry must record at least one reagent "
        "or standard lot.",
    )
    requires_review_qualification = forms.BooleanField(
        label="Reviewers qualified for the method",
        required=False,
        help_text="If set, whoever reviews or returns a result of this version needs an "
        "approved, current qualification to review this method, beyond the reviewer role.",
    )
    reason = reason_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(effective_fields())

    groups = [
        ("Procedure", ["technique", "document_ref", "summary", "requires_batch"]),
        ("Resources recorded with results", ["requires_equipment", "requires_reagent"]),
        ("Review", ["requires_review_qualification"]),
        ("Suitability", ["suitability_kind", "suitability_ref"]),
        ("Effective period", ["effective_from", "effective_until"]),
        ("Change control", ["reason"]),
    ]


class MethodForm(MethodRevisionForm):
    code = forms.SlugField(max_length=60)
    title = forms.CharField(max_length=200)
    groups = [("Method", ["code", "title"]), *MethodRevisionForm.groups]

    def clean_code(self):
        code = self.cleaned_data["code"]
        if Method.objects.filter(code=code).exists():
            raise forms.ValidationError("This method code already exists.")
        return code


class SpecificationRevisionForm(GroupedForm):
    basis = forms.CharField(
        label="Basis",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Scientific, compendial or contractual basis for these limits.",
    )
    reason = reason_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(effective_fields())

    groups = [
        ("Basis", ["basis"]),
        ("Effective period", ["effective_from", "effective_until"]),
        ("Change control", ["reason"]),
    ]


class SpecificationForm(SpecificationRevisionForm):
    code = forms.SlugField(max_length=60)
    title = forms.CharField(max_length=200)
    material = forms.ModelChoiceField(
        queryset=Material.objects.all(), widget=RemoteSelect("materials")
    )
    stage = forms.ChoiceField(choices=Stage.choices)
    scope = forms.SlugField(
        max_length=60,
        initial="general",
        help_text="general, or a named market or customer overlay such as eu-market. A lot is "
        "assigned under every scope it falls under and each specification applies in full; "
        "where two state a test differently the lot is held for a quality decision.",
    )
    groups = [
        ("Specification", ["code", "title", "material", "stage", "scope"]),
        *SpecificationRevisionForm.groups,
    ]

    def clean_code(self):
        code = self.cleaned_data["code"]
        if Specification.objects.filter(code=code).exists():
            raise forms.ValidationError("This specification code already exists.")
        return code

    def clean(self):
        data = super().clean()
        if (
            data.get("material")
            and data.get("stage")
            and data.get("scope")
            and Specification.objects.filter(
                material=data["material"], stage=data["stage"], scope=data["scope"]
            ).exists()
        ):
            raise forms.ValidationError(
                "A specification already exists for this material, stage and scope. "
                "Create a new version of it instead."
            )
        return data


class TestLineForm(GroupedForm):
    code = forms.SlugField(max_length=80, help_text="Stable test code, e.g. assay or identity.")
    name = forms.CharField(max_length=160)
    method = forms.ModelChoiceField(queryset=Method.objects.all(), widget=RemoteSelect("methods"))
    position = forms.IntegerField(min_value=1, max_value=999, initial=1)
    result_type = forms.ChoiceField(
        choices=ResultType.choices,
        help_text="Numeric and count tests use the unit, limits and rounding fields; count "
        "results and limits are whole numbers of 0 or more. Qualitative tests use the expected "
        "outcome and criterion fields instead.",
    )
    unit = forms.ChoiceField(
        choices=[("", "—")] + RESULT_UNITS,
        required=False,
        help_text="Numeric and count tests only.",
    )
    lower_limit = forms.DecimalField(
        max_digits=20,
        decimal_places=8,
        required=False,
        help_text="Numeric and count tests: enter at least one limit. Equal lower and upper "
        "limits must both be inclusive.",
    )
    lower_inclusive = forms.BooleanField(
        label="Lower limit is inclusive (≥)",
        required=False,
        initial=True,
        help_text="Clear for a strict limit (>).",
    )
    upper_limit = forms.DecimalField(max_digits=20, decimal_places=8, required=False)
    upper_inclusive = forms.BooleanField(
        label="Upper limit is inclusive (≤)",
        required=False,
        initial=True,
        help_text="Clear for a strict limit (<).",
    )
    reporting_decimals = forms.IntegerField(
        label="Round to decimals before comparison",
        min_value=0,
        max_value=8,
        required=False,
        help_text="Numeric and count tests only. Leave blank to compare the exact recorded value.",
    )
    expected_result = forms.ChoiceField(
        label="Expected outcome",
        choices=[("", "—")] + ExpectedResult.choices,
        required=False,
        help_text="Qualitative tests only: the outcome that conforms. Conforms is recorded "
        "against Does not conform; Absent or Present against the other.",
    )
    expected_text = forms.CharField(
        label="Criterion",
        max_length=160,
        required=False,
        help_text="Qualitative tests only: the approved wording, e.g. White crystalline powder "
        "or Not detected in 25 g.",
    )
    required = forms.BooleanField(label="Required for QC disposition", required=False, initial=True)
    replicates = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
        help_text="Determinations averaged into the reportable value.",
    )
    replicate_limits = forms.BooleanField(
        label="Each replicate must meet the limits",
        required=False,
        initial=True,
        help_text="Numeric and count tests. Every replicate of a qualitative test must match "
        "the expected outcome.",
    )
    max_retests = forms.IntegerField(
        label="Maximum retests",
        min_value=0,
        max_value=3,
        initial=0,
        help_text="Allowed only under an approved investigation; 0 allows none.",
    )
    reason = reason_field()
    groups = [
        ("Test", ["code", "name", "method", "position", "required"]),
        ("Replication", ["replicates", "replicate_limits", "max_retests"]),
        (
            "Acceptance criterion",
            [
                "result_type",
                "unit",
                "lower_limit",
                "lower_inclusive",
                "upper_limit",
                "upper_inclusive",
                "reporting_decimals",
                "expected_result",
                "expected_text",
            ],
        ),
        ("Change control", ["reason"]),
    ]

    def clean(self):
        data = super().clean()
        if data.get("result_type") == ResultType.QUALITATIVE:
            # Bound and replicate options do not apply to a qualitative test; they are stored as
            # set so the line keeps the one shape the analytical contract accepts.
            data.update(lower_inclusive=True, upper_inclusive=True, replicate_limits=True)
        return data


class QCCheckForm(GroupedForm):
    code = forms.SlugField(max_length=40, help_text="e.g. blank or control.")
    name = forms.CharField(max_length=160)
    unit = forms.ChoiceField(choices=RESULT_UNITS)
    lower_limit = forms.DecimalField(max_digits=20, decimal_places=8, required=False)
    upper_limit = forms.DecimalField(max_digits=20, decimal_places=8, required=False)
    reason = reason_field()
    groups = [
        ("QC check", ["code", "name"]),
        ("Acceptance limits (inclusive)", ["unit", "lower_limit", "upper_limit"]),
        ("Change control", ["reason"]),
    ]


class CalculationInputForm(GroupedForm):
    code = forms.CharField(
        max_length=40,
        help_text="The name the formula uses: a lower-case letter, then lower-case letters, "
        "digits or underscores, e.g. peak_area.",
    )
    name = forms.CharField(max_length=160, help_text="What the analyst enters, e.g. Sample mass.")
    unit = forms.ChoiceField(choices=INPUT_UNITS)
    reason = reason_field()
    groups = [
        ("Input", ["code", "name", "unit"]),
        ("Change control", ["reason"]),
    ]

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not formulas.is_name(code):
            raise forms.ValidationError(
                "Use a lower-case letter followed by lower-case letters, digits or underscores "
                "(40 at most)."
            )
        return code


class CalculationForm(GroupedForm):
    formula = forms.CharField(
        max_length=formulas.MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Arithmetic over the input codes: + - * / and brackets, e.g. "
        "(peak_area * standard_mass) / (standard_area * sample_mass) * 100. "
        "No functions or exponents.",
    )
    unit = forms.ChoiceField(label="Unit of the calculated result", choices=RESULT_UNITS)
    decimals = forms.IntegerField(
        label="Decimals of the calculated result",
        min_value=0,
        max_value=formulas.MAX_DECIMALS,
        help_text="The result is rounded half up to this many decimals when it is recorded.",
    )
    reason = reason_field()
    groups = [
        ("Calculation", ["formula", "unit", "decimals"]),
        ("Change control", ["reason"]),
    ]


class FileImportForm(GroupedForm):
    """How the instrument's export file is read. One column field per calculation input (blank:
    the analyst enters that input), or one for the result when there is no calculation."""

    source = forms.CharField(
        label="Export",
        max_length=file_imports.MAX_SOURCE,
        help_text="What produces the file, for example the spectrometer's result table "
        "export. Analysts see it when they import.",
    )
    delimiter = forms.ChoiceField(label="Column separator", choices=file_imports.DELIMITER_CHOICES)
    decimal = forms.ChoiceField(label="Decimal mark", choices=file_imports.DECIMAL_CHOICES)
    encoding = forms.ChoiceField(label="Text encoding", choices=file_imports.ENCODING_CHOICES)
    header_row = forms.IntegerField(
        label="Row of the column names",
        min_value=1,
        max_value=file_imports.MAX_HEADER_ROW,
        initial=1,
        help_text="1 when the first row names the columns. Rows above it are not read.",
    )
    id_column = forms.CharField(
        label="Column naming the test",
        max_length=file_imports.MAX_COLUMN,
        help_text="The column that holds the test number (for example T-12) on each row, as "
        "the analyst enters it as the sample name on the instrument.",
    )
    filter_column = forms.CharField(
        label="Column selecting rows",
        max_length=file_imports.MAX_COLUMN,
        required=False,
        help_text="Optional: for a file with several rows per sample, such as one per peak or "
        "wavelength.",
    )
    filter_value = forms.CharField(
        label="Value selecting rows",
        max_length=file_imports.MAX_COLUMN,
        required=False,
        help_text="Only rows with this value in the column above are read.",
    )
    reason = reason_field()

    def __init__(self, *args, revision, **kwargs):
        super().__init__(*args, **kwargs)
        self.mapped = []
        if revision.has_calculation:
            for item in revision.calculation_inputs.all():
                name = f"column_{item.code}"
                self.fields[name] = forms.CharField(
                    label=f"Column for {item.name} ({item.code}, {item.unit})",
                    max_length=file_imports.MAX_COLUMN,
                    required=False,
                    help_text="Leave blank when the analyst enters this input for each row.",
                )
                self.mapped.append((item.code, name))
        else:
            self.fields["column_value"] = forms.CharField(
                label="Column holding the result",
                max_length=file_imports.MAX_COLUMN,
                help_text="One row of the file is one replicate.",
            )
            self.mapped.append((file_imports.VALUE, "column_value"))
        self.groups = [
            ("Export", ["source", "delimiter", "decimal", "encoding", "header_row"]),
            ("Rows of the test", ["id_column", "filter_column", "filter_value"]),
            ("Columns", [name for _, name in self.mapped]),
            ("Change control", ["reason"]),
        ]
        current = revision.file_import
        if current and not self.is_bound:
            columns = {c["field"]: c["column"] for c in current.get("columns", [])}
            for key in (
                "source",
                "delimiter",
                "decimal",
                "encoding",
                "header_row",
                "id_column",
                "filter_column",
                "filter_value",
            ):
                self.initial.setdefault(key, current.get(key))
            for field, name in self.mapped:
                self.initial.setdefault(name, columns.get(field, ""))

    def clean(self):
        data = super().clean()
        if self.mapped and not any((data.get(name) or "").strip() for _, name in self.mapped):
            self.add_error(None, "Name the column of at least one input.")
        if bool((data.get("filter_column") or "").strip()) != bool(
            (data.get("filter_value") or "").strip()
        ):
            self.add_error("filter_value", "Give both the column and the value, or neither.")
        return data

    def import_data(self):
        """The service's keyword arguments."""
        data = self.cleaned_data
        return {
            "source": data["source"],
            "delimiter": data["delimiter"],
            "decimal": data["decimal"],
            "encoding": data["encoding"],
            "header_row": data["header_row"],
            "id_column": data["id_column"],
            "filter_column": data["filter_column"],
            "filter_value": data["filter_value"],
            "columns": {field: data.get(name) or "" for field, name in self.mapped},
            "reason": data["reason"],
        }


class ReasonForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Reason")


# Method evidence ---------------------------------------------------------------------------


def _text(label=None, rows=3, required=True, help_text=""):
    return forms.CharField(
        label=label,
        required=required,
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": rows}),
        help_text=help_text,
    )


def _model_help(name):
    return MethodEvidence._meta.get_field(name).help_text


class EvidenceChangeForm(GroupedForm):
    """The fields of a method evidence record, as a draft is changed."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    kind = forms.ChoiceField(label="Kind of evidence", choices=SuitabilityKind.choices)
    title = forms.CharField(max_length=160, help_text=_model_help("title"))
    procedure_ref = forms.CharField(
        label="Procedure studied", max_length=200, help_text=_model_help("procedure_ref")
    )
    intended_use = _text("Intended use", help_text=_model_help("intended_use"))
    source = forms.CharField(
        label="Source of the procedure",
        max_length=200,
        required=False,
        help_text=_model_help("source"),
    )
    transfer_approach = forms.ChoiceField(
        label="Transfer approach",
        required=False,
        choices=[("", "Not a transfer"), *MethodEvidence.TransferApproach.choices],
        help_text=_model_help("transfer_approach"),
    )
    protocol_ref = forms.CharField(
        label="Protocol", max_length=200, required=False, help_text=_model_help("protocol_ref")
    )
    report_ref = forms.CharField(
        label="Report", max_length=200, help_text=_model_help("report_ref")
    )
    report_url = forms.URLField(
        label="Report link",
        max_length=500,
        required=False,
        help_text="Optional http or https link to the report in the document system.",
    )
    completed_on = forms.DateField(
        label="Report completed on",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Not in the future.",
    )
    conclusion = forms.ChoiceField(choices=MethodEvidence.Conclusion.choices)
    statement = _text("Statement of suitability", help_text=_model_help("statement"))
    deviations = _text("Deviations", required=False, help_text=_model_help("deviations"))
    reason = reason_field()

    groups = [
        ("Evidence", ["kind", "title"]),
        (
            "What was studied",
            ["procedure_ref", "intended_use", "source", "transfer_approach", "protocol_ref"],
        ),
        ("Report", ["report_ref", "report_url", "completed_on"]),
        ("Conclusion", ["conclusion", "statement", "deviations"]),
        ("Change control", ["reason"]),
    ]

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        if kind == SuitabilityKind.TRANSFER and not data.get("transfer_approach"):
            self.add_error("transfer_approach", "Choose how the transfer was performed.")
        if kind and kind != SuitabilityKind.TRANSFER and data.get("transfer_approach"):
            self.add_error("transfer_approach", "Only a transfer has a transfer approach.")
        return data

    def values(self):
        return {
            name: value
            for name, value in self.cleaned_data.items()
            if name not in ("expected_revision", "reason", "method")
        }


class EvidenceForm(EvidenceChangeForm):
    """A new record: also the method it is for."""

    method = forms.ModelChoiceField(
        queryset=Method.objects.all(),
        widget=RemoteSelect("methods"),
        help_text="The method whose suitability the record shows.",
    )
    groups = [
        ("Evidence", ["method", "kind", "title"]),
        *EvidenceChangeForm.groups[1:],
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["expected_revision"]
        self.fields["reason"].label = "Reason"


class CharacteristicForm(GroupedForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    characteristic = forms.ChoiceField(choices=MethodEvidenceCharacteristic.Characteristic.choices)
    detail = forms.CharField(
        max_length=160,
        required=False,
        help_text=MethodEvidenceCharacteristic._meta.get_field("detail").help_text,
    )
    criterion = _text("Acceptance criterion", rows=2)
    result = _text("Result obtained", rows=2)
    outcome = forms.ChoiceField(
        label="Criterion", choices=MethodEvidenceCharacteristic.Outcome.choices
    )
    reason = reason_field("Reason")

    groups = [
        ("Characteristic", ["characteristic", "detail"]),
        ("Criterion and result", ["criterion", "result", "outcome"]),
        ("Change control", ["reason"]),
    ]

    def clean(self):
        data = super().clean()
        if data.get("characteristic") == "other" and not (data.get("detail") or "").strip():
            self.add_error("detail", "Say what was evaluated.")
        return data


class SuitabilityForm(GroupedForm):
    """What a draft method version relies on: an approved record of its method, or an external
    reference only."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    evidence = forms.ModelChoiceField(
        label="Evidence record",
        queryset=MethodEvidence.objects.none(),
        required=False,
        empty_label="None: an external reference only",
        help_text="An approved record of this method that concludes it is suitable. Its kind "
        "and report are used.",
    )
    suitability_kind = forms.ChoiceField(
        label="Suitability basis",
        required=False,
        choices=[("", "Choose"), *SuitabilityKind.choices],
        help_text="Only without an evidence record.",
    )
    suitability_ref = forms.CharField(
        label="Suitability evidence",
        max_length=200,
        required=False,
        help_text="Only without an evidence record: the report and where it is kept.",
    )
    reason = reason_field()

    groups = [
        ("Evidence kept here", ["evidence"]),
        ("Or an external reference", ["suitability_kind", "suitability_ref"]),
        ("Change control", ["reason"]),
    ]

    def __init__(self, *args, choices, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["evidence"].queryset = choices
        self.fields["evidence"].label_from_instance = lambda item: (
            f"{item.identifier} · {item.title} ({item.get_kind_display()}, {item.report_ref})"
        )

    def clean(self):
        data = super().clean()
        if not data.get("evidence"):
            if not data.get("suitability_kind"):
                self.add_error("suitability_kind", "Choose the kind of evidence.")
            if not (data.get("suitability_ref") or "").strip():
                self.add_error("suitability_ref", "Name the report and where it is kept.")
        return data


class ApprovalForm(SignatureIdentityForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(
        label="Approval comment",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="What you checked before approving.",
    )
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "inputmode": "numeric"}, render_value=False
        ),
    )

    field_order = ["reason", "signature_username", "pin", "expected_revision"]

    def signing_data(self):
        return {
            "pin": self.cleaned_data["pin"],
            "expected_revision": self.cleaned_data["expected_revision"],
            "reason": self.cleaned_data["reason"],
        }
