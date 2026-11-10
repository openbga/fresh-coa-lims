from django import forms
from django.utils import timezone

from catalog.forms import TZ, GroupedForm, LocalDateTimeInput, effective_fields, reason_field
from catalog.models import Material, Stage
from catalog.units import QUANTITY_UNITS
from core.forms import SignatureIdentityForm
from quality.models import Sample

from .models import SamplingBasis, SamplingPlan, SamplingPurpose, SamplingRecord


class PlanRevisionForm(GroupedForm):
    basis = forms.ChoiceField(choices=SamplingBasis.choices)
    parameter = forms.DecimalField(
        max_digits=8,
        decimal_places=3,
        required=False,
        help_text="Containers for a fixed plan, or percent for a percentage plan; otherwise blank.",
    )
    minimum_quantity = forms.DecimalField(
        label="Minimum total amount", max_digits=14, decimal_places=4, min_value=0
    )
    quantity_unit = forms.ChoiceField(label="Amount unit", choices=QUANTITY_UNITS)
    composite_allowed = forms.BooleanField(label="Compositing allowed", required=False)
    instructions = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    rationale = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why the plan is representative. A sampling scheme is a configured choice "
        "reviewed by quality, not a legal requirement.",
    )
    reason = reason_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(effective_fields())

    groups = [
        ("Containers to sample", ["basis", "parameter", "composite_allowed"]),
        ("Amount", ["minimum_quantity", "quantity_unit"]),
        ("Procedure", ["instructions", "rationale"]),
        ("Effective period", ["effective_from", "effective_until"]),
        ("Change control", ["reason"]),
    ]

    def clean_minimum_quantity(self):
        value = self.cleaned_data["minimum_quantity"]
        if value <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return value


class PlanForm(PlanRevisionForm):
    code = forms.SlugField(max_length=60)
    title = forms.CharField(max_length=200)
    material = forms.ModelChoiceField(queryset=Material.objects.all())
    stage = forms.ChoiceField(choices=Stage.choices)
    groups = [("Plan", ["code", "title", "material", "stage"]), *PlanRevisionForm.groups]

    def clean_code(self):
        code = self.cleaned_data["code"]
        if SamplingPlan.objects.filter(code=code).exists():
            raise forms.ValidationError("This plan code already exists.")
        return code

    def clean(self):
        data = super().clean()
        if (
            data.get("material")
            and data.get("stage")
            and SamplingPlan.objects.filter(material=data["material"], stage=data["stage"]).exists()
        ):
            raise forms.ValidationError(
                "A sampling plan already exists for this material and stage. Create a new "
                "version of it instead."
            )
        return data


class AssignForm(GroupedForm):
    material = forms.ModelChoiceField(
        queryset=Material.objects.all(), help_text="The controlled material this lot is."
    )
    stage = forms.ChoiceField(choices=Stage.choices)
    scope = forms.SlugField(
        max_length=60, initial="general", help_text="general, or a named market/customer overlay."
    )
    reason = reason_field("Reason")
    groups = [("Applicability", ["material", "stage", "scope"]), ("Change control", ["reason"])]


class ObservationForm(GroupedForm):
    sampled_at = forms.DateTimeField(
        label=f"Sampled at ({TZ})", widget=LocalDateTimeInput(), initial=timezone.now
    )
    location = forms.CharField(max_length=160, help_text="Where the sample was taken.")
    containers_total = forms.IntegerField(label="Containers in lot", min_value=1)
    containers_sampled = forms.IntegerField(min_value=1)
    container_ids = forms.CharField(
        label="Container identifiers",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Identifiers of the containers sampled, e.g. C1, C4, C8.",
    )
    quantity = forms.DecimalField(
        label="Total amount collected", max_digits=14, decimal_places=4, min_value=0
    )
    quantity_unit = forms.ChoiceField(label="Amount unit", choices=QUANTITY_UNITS)
    deviation = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when fewer containers or less material than the plan were sampled.",
    )
    reason = reason_field("Reason")

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return value

    groups = [
        ("Sampling", ["sampled_at", "location"]),
        ("Containers", ["containers_total", "containers_sampled", "container_ids"]),
        ("Amount", ["quantity", "quantity_unit"]),
        ("Deviation and reason", ["deviation", "reason"]),
    ]


class SamplingForm(ObservationForm):
    reference = forms.CharField(label="Sample reference", max_length=80)
    purpose = forms.ChoiceField(
        choices=SamplingPurpose.choices,
        initial=SamplingPurpose.ROUTINE,
        required=False,
        help_text="A resample is new material collected for an investigation.",
    )
    resample_of = forms.ModelChoiceField(
        label="Original sample",
        queryset=None,
        required=False,
        help_text="Resamples only: the sampled original this resample replaces.",
    )
    groups = [("Sample", ["reference", "purpose", "resample_of"]), *ObservationForm.groups]

    def __init__(self, *args, lot=None, **kwargs):
        super().__init__(*args, **kwargs)
        sampled = SamplingRecord.objects.filter(lot=lot).values("sample_id")
        self.fields["resample_of"].queryset = Sample.objects.filter(
            lot=lot, pk__in=sampled
        ).order_by("reference")

    def clean_purpose(self):
        return self.cleaned_data.get("purpose") or SamplingPurpose.ROUTINE

    def clean_reference(self):
        reference = self.cleaned_data["reference"]
        if Sample.objects.filter(reference=reference).exists():
            raise forms.ValidationError("This sample reference already exists.")
        return reference


class CorrectionForm(ObservationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].label = "Reason for correction"


class DeviationForm(SignatureIdentityForm):
    decision = forms.ChoiceField(
        choices=[("accept", "Accept the deviation"), ("reject", "Reject the deviation")],
        widget=forms.RadioSelect,
    )
    reason = forms.CharField(
        label="Assessment",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why the sample is or is not still representative.",
    )
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "inputmode": "numeric"}, render_value=False
        ),
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    field_order = ["decision", "reason", "signature_username", "pin", "expected_revision"]
