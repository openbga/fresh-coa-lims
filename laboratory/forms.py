from django import forms

from core.forms import SignatureIdentityForm
from quality.models import Sample

from .eligibility import users_with_roles
from .models import Calibration, Equipment, ReagentLot

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


def datetime_field(**kwargs):
    return forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_FORMAT),
        input_formats=[DATETIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
        help_text="Deployment time zone (UTC by default).",
        **kwargs,
    )


def date_field(**kwargs):
    return forms.DateField(widget=DATE, **kwargs)


def reason_field(label="Reason", **kwargs):
    return forms.CharField(label=label, widget=forms.Textarea(attrs={"rows": 3}), **kwargs)


class ReasonForm(forms.Form):
    reason = reason_field(max_length=2000)


class SigningForm(SignatureIdentityForm):
    """PIN entry is never repopulated; the revision is the one the signer reviewed.
    `signature_username` is verified against the authenticated account by
    core.session_control.signing_context (called from core.services.sign_transition) and is
    never passed to the domain services."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Reason for signing", max_length=2000)
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "inputmode": "numeric"}),
        help_text="Re-enter your PIN for every signature.",
    )


class ImpactSigningForm(SigningForm):
    reason = reason_field("Impact assessment", max_length=2000)
    # The affected uses and failed calibrations shown when the page opened ("1,2|3").
    assessed = forms.CharField(widget=forms.HiddenInput, required=False, strip=False)

    @staticmethod
    def scope_token(scope):
        uses, failures = scope
        return ",".join(map(str, uses)) + "|" + ",".join(map(str, failures))

    def clean(self):
        data = super().clean()
        try:
            uses, failures = (
                [int(pk) for pk in part.split(",") if pk]
                for part in data.get("assessed", "").split("|")
            )
        except ValueError:
            # Shown as a page-level error: the hidden field has no visible error slot.
            self.add_error(None, "The assessed scope is missing or invalid. Reload and reassess.")
        else:
            data["assessed"] = (uses, failures)
        return data


class EquipmentForm(forms.ModelForm):
    reason = reason_field(max_length=2000)

    class Meta:
        model = Equipment
        fields = ["asset_id", "description", "category", "location", "requires_qualification"]


class CalibrationForm(forms.ModelForm):
    performed_at = datetime_field()
    due_date = date_field()
    reason = reason_field(max_length=2000)

    class Meta:
        model = Calibration
        fields = [
            "performed_at",
            "due_date",
            "outcome",
            "standard_ref",
            "certificate_ref",
            "certificate_url",
            "tolerance_note",
        ]
        widgets = {"tolerance_note": forms.Textarea(attrs={"rows": 3})}


class QualificationForm(forms.Form):
    """Analyst qualification when `equipment` is absent, instrument qualification otherwise."""

    user = forms.ModelChoiceField(queryset=users_with_roles(), label="Qualified person")
    activity = forms.CharField(
        max_length=120, help_text="Method or activity code this evidence qualifies."
    )
    scope_note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    evidence_ref = forms.CharField(
        max_length=200, label="Evidence reference", help_text="Controlled record and revision."
    )
    evidence_url = forms.URLField(required=False, max_length=500, label="Evidence link")
    valid_from = date_field()
    valid_until = date_field(label="Valid until (inclusive)")
    reason = reason_field(max_length=2000)

    def __init__(self, *args, equipment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.equipment = equipment
        self.fields["user"].queryset = users_with_roles()
        if equipment is not None:
            del self.fields["user"]
            self.fields["activity"].label = "Stage or intended use"
            self.fields["activity"].help_text = "For example IQ, OQ, PQ or requalification."

    def clean_evidence_url(self):
        from .models import http_url

        url = self.cleaned_data["evidence_url"]
        if url:
            http_url(url)
        return url

    def clean(self):
        data = super().clean()
        start, end = data.get("valid_from"), data.get("valid_until")
        if start and end and end < start:
            self.add_error("valid_until", "Valid until cannot precede valid from.")
        return data


class ReagentForm(forms.ModelForm):
    received_on = date_field(label="Received or prepared on")
    expiry_date = date_field(label="Expiry date (last day of use)")
    reason = reason_field(max_length=2000)

    class Meta:
        model = ReagentLot
        fields = [
            "identifier",
            "kind",
            "name",
            "supplier",
            "lot_number",
            "received_on",
            "expiry_date",
            "assigned_purity",
            "purity_unit",
            "parent",
            "preparation_note",
            "certificate_ref",
            "certificate_url",
        ]
        widgets = {"preparation_note": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = ReagentLot.objects.filter(
            state=ReagentLot.State.RELEASED
        ).order_by("identifier")

    def clean(self):
        data = super().clean()
        purity, unit = data.get("assigned_purity"), data.get("purity_unit")
        if (purity is None) != (not unit):
            self.add_error("purity_unit", "Give the purity and its unit together.")
        return data


class UseForm(forms.Form):
    sample_reference = forms.CharField(
        max_length=80, help_text="Sample the work is performed on, exactly as recorded."
    )
    activity = forms.CharField(
        max_length=120, help_text="Method or activity code the analyst is qualified for."
    )
    test_code = forms.CharField(max_length=80, required=False)
    profile_ref = forms.CharField(
        max_length=120, required=False, label="Test profile revision", help_text="If known."
    )
    equipment = forms.ModelMultipleChoiceField(
        queryset=Equipment.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )
    reagents = forms.ModelMultipleChoiceField(
        queryset=ReagentLot.objects.none(),
        required=False,
        label="Reagents and standards",
        widget=forms.CheckboxSelectMultiple,
    )
    reason = reason_field("Reason or work context", max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipment"].queryset = Equipment.objects.all()
        self.fields["reagents"].queryset = ReagentLot.objects.exclude(
            state=ReagentLot.State.REJECTED
        )

    def clean_sample_reference(self):
        reference = self.cleaned_data["sample_reference"].strip()
        sample = Sample.objects.filter(reference=reference).first()
        if sample is None:
            raise forms.ValidationError("No sample has this reference.")
        self.sample = sample
        return reference

    def clean(self):
        data = super().clean()
        if not data.get("equipment") and not data.get("reagents") and not self.errors:
            raise forms.ValidationError("Select at least one piece of equipment or reagent lot.")
        return data
