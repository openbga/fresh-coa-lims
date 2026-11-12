from django import forms
from django.conf import settings

from core.forms import SignatureIdentityForm

from .models import (
    ExpectedResult,
    Material,
    MaterialKind,
    Method,
    ResultType,
    Specification,
    Stage,
    SuitabilityKind,
)
from .units import RESULT_UNITS

TZ = settings.TIME_ZONE


class LocalDateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%dT%H:%M")


def effective_fields():
    return {
        "effective_from": forms.DateTimeField(
            label=f"Effective from ({TZ})", widget=LocalDateTimeInput()
        ),
        "effective_until": forms.DateTimeField(
            label=f"Effective until ({TZ})",
            widget=LocalDateTimeInput(),
            help_text="Exclusive end. Approved versions of one record must not overlap.",
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
    reason = reason_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(effective_fields())

    groups = [
        ("Procedure", ["technique", "document_ref", "summary", "requires_batch"]),
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
    material = forms.ModelChoiceField(queryset=Material.objects.all())
    stage = forms.ChoiceField(choices=Stage.choices)
    scope = forms.SlugField(
        max_length=60,
        initial="general",
        help_text="general, or a named market/customer overlay. Overlays are never merged.",
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
    method = forms.ModelChoiceField(queryset=Method.objects.all())
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


class ReasonForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Reason")


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
