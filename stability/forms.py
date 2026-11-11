from django import forms
from django.utils import timezone

from laboratory.eligibility import equipment_eligibility
from laboratory.forms import (
    DATE,
    ReasonForm,
    SigningForm,
    date_field,
    reason_field,
)
from laboratory.models import Equipment
from quality.models import Lot

from .models import (
    Hold,
    Protocol,
    ProtocolCondition,
    ProtocolTimepoint,
    ReserveSample,
    RetentionObligation,
    Study,
)

__all__ = ["ReasonForm", "SigningForm"]


class ProtocolForm(forms.ModelForm):
    reason = reason_field(max_length=2000)

    class Meta:
        model = Protocol
        fields = [
            "code",
            "title",
            "product",
            "document_ref",
            "document_url",
            "test_profile_ref",
            "basis",
        ]
        widgets = {"basis": forms.Textarea(attrs={"rows": 3})}


class ConditionForm(forms.ModelForm):
    reason = reason_field(max_length=2000)

    class Meta:
        model = ProtocolCondition
        fields = ["label", "setpoint", "temperature_c", "humidity_pct"]
        labels = {"temperature_c": "Temperature (°C)", "humidity_pct": "Relative humidity (%)"}


class TimepointForm(forms.ModelForm):
    test_codes = forms.CharField(
        label="Tests", help_text="Test codes separated by commas, from the approved profile."
    )
    reason = reason_field(max_length=2000)

    class Meta:
        model = ProtocolTimepoint
        fields = ["condition", "label", "interval_days", "window_days", "test_codes"]
        labels = {"interval_days": "Interval (days)", "window_days": "Window (± days)"}

    def __init__(self, *args, protocol, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["condition"].queryset = protocol.conditions.all()

    def clean_test_codes(self):
        codes = [c.strip() for c in self.cleaned_data["test_codes"].split(",") if c.strip()]
        if not codes or len(set(codes)) != len(codes):
            raise forms.ValidationError("List one or more distinct test codes.")
        return codes


class StudyForm(forms.Form):
    identifier = forms.CharField(max_length=60)
    protocol = forms.ModelChoiceField(queryset=Protocol.objects.none(), label="Approved protocol")
    lot = forms.ModelChoiceField(queryset=Lot.objects.none())
    container_closure = forms.CharField(max_length=200, label="Container and closure")
    start_date = date_field(
        label="Time zero", help_text="Date the study actually started; today or earlier."
    )
    reason = reason_field(max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["protocol"].queryset = Protocol.objects.filter(state="approved")
        self.fields["lot"].queryset = Lot.objects.order_by("number")

    def clean_identifier(self):
        identifier = self.cleaned_data["identifier"]
        if Study.objects.filter(identifier=identifier).exists():
            raise forms.ValidationError("This study identifier already exists.")
        return identifier

    def clean_start_date(self):
        start = self.cleaned_data["start_date"]
        if start > timezone.localdate():
            raise forms.ValidationError(
                "Time zero cannot be in the future: this workflow records studies that have "
                "actually started."
            )
        return start


class PullForm(forms.Form):
    pulled_on = date_field()
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    quantity_unit = forms.CharField(max_length=20)
    storage_location = forms.CharField(max_length=120, label="Where the pull is held")
    chamber = forms.ModelChoiceField(
        queryset=Equipment.objects.none(),
        required=False,
        label="Storage chamber",
        help_text="Only equipment fit for use now is listed; fitness is checked again on save.",
    )
    deviation_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when the pull is outside its window.",
    )
    reason = reason_field(max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Same fitness predicate as the locked check when the pull is saved; the save still
        # rechecks, because fitness can change between opening the form and submitting it.
        fit = [
            item.pk
            for item in Equipment.objects.prefetch_related("calibrations", "qualifications")
            if equipment_eligibility(item).ok
        ]
        self.fields["chamber"].queryset = Equipment.objects.filter(pk__in=fit)


class EvidenceForm(forms.Form):
    sample_reference = forms.CharField(
        max_length=80,
        required=False,
        help_text="Sample registered for testing, exactly as recorded.",
    )
    external_sample_ref = forms.CharField(
        max_length=120, required=False, label="External sample ID"
    )
    evidence_ref = forms.CharField(
        max_length=200, required=False, label="External evidence reference"
    )
    evidence_url = forms.URLField(max_length=500, required=False, label="External evidence link")
    reason = reason_field(max_length=2000)

    def clean_evidence_url(self):
        from laboratory.models import http_url

        url = self.cleaned_data["evidence_url"]
        if url:
            http_url(url)
        return url


class CloseStudyForm(SigningForm):
    outcome = forms.ChoiceField(
        choices=[
            ("completed", "Completed: every pull accepted or missed"),
            ("terminated", "Terminated early"),
        ]
    )
    field_order = ["expected_revision", "outcome", "reason", "signature_username", "pin"]


class ReserveForm(forms.ModelForm):
    retained_on = date_field()
    reason = reason_field(max_length=2000)

    class Meta:
        model = ReserveSample
        fields = [
            "identifier",
            "lot",
            "container_description",
            "storage_location",
            "quantity",
            "test_quantity",
            "quantity_unit",
            "minimum_multiple",
            "retained_on",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.order_by("number")


class ObligationForm(forms.ModelForm):
    anchor_date = forms.DateField(widget=DATE, required=False, help_text="Leave blank if unknown.")
    reason = reason_field(max_length=2000)

    class Meta:
        model = RetentionObligation
        fields = ["anchor_kind", "anchor_date", "offset_months", "basis"]
        labels = {"offset_months": "Months retained after the anchor"}

    def __init__(self, *args, with_lot=False, **kwargs):
        super().__init__(*args, **kwargs)
        if with_lot:
            self.fields["lot"] = forms.ModelChoiceField(queryset=Lot.objects.order_by("number"))
            self.order_fields(["lot", *self.Meta.fields, "reason"])


class AnchorForm(forms.Form):
    anchor_date = date_field()
    reason = reason_field(max_length=2000)


class HoldForm(forms.Form):
    lot = forms.ModelChoiceField(queryset=Lot.objects.none())
    kind = forms.ChoiceField(choices=Hold.Kind.choices)
    reference = forms.CharField(
        max_length=200, required=False, help_text="Investigation, CAPA or matter ID."
    )
    reason = reason_field("Reason for hold", max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.order_by("number")
