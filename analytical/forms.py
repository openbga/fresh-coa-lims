from django import forms
from django.utils.html import escape

from core.forms import SignatureIdentityForm, StyledForm

from .models import AnalyticalTest, Investigation, InvestigationEntry

VALUE = {"max_digits": 20, "decimal_places": 8}


def _reason(label="Reason", help_text=""):
    return forms.CharField(
        label=label,
        help_text=help_text,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


def _raw_reference():
    return forms.CharField(
        label="Original record",
        max_length=200,
        help_text="Notebook page, instrument file or worksheet holding the original observation.",
    )


class ReasonForm(StyledForm):
    reason = _reason()


class RevisionReasonForm(ReasonForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class ObservationForm(StyledForm):
    value = forms.DecimalField(
        label="Observed value",
        help_text="Exact value as read; at most 8 decimal places. Never enter a nondetect as zero.",
        **VALUE,
    )
    raw_reference = _raw_reference()


class CorrectionForm(ObservationForm):
    """QC result correction (batch QC checks stay numeric)."""

    reason = _reason("Reason for correction", "The original value stays visible in the record.")


class ReadingForm(StyledForm):
    """A test observation shaped by its frozen requirement.

    Numeric and count: a value with an optional "reported as less than" choice. Qualitative: one
    outcome from the requirement's controlled pair plus what was observed. ``cleaned_data`` holds
    exactly the service's reading arguments (value, qualifier, outcome, observed_text).
    """

    raw_reference = _raw_reference()

    def __init__(self, *args, spec, **kwargs):
        super().__init__(*args, **kwargs)
        self.spec = spec
        fields = {}
        if spec.is_qualitative:
            fields["outcome"] = forms.ChoiceField(
                label="Observed result",
                choices=spec.outcomes,
                widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
                help_text=f"Acceptance: {escape(spec.acceptance)}.",  # help text renders unescaped
            )
            fields["observed_text"] = forms.CharField(
                label="What was observed",
                max_length=200,
                help_text="Describe the observation itself, e.g. what was seen or how the "
                "test reacted; the outcome is recorded separately.",
            )
        else:
            count = spec.result_type == "count"
            fields["value"] = forms.DecimalField(
                label="Observed count" if count else "Observed value",
                help_text=(
                    "Whole number of zero or more, exactly as read. "
                    if count
                    else "Exact value as read; at most 8 decimal places. "
                )
                + "Never enter a nondetect as zero: enter the reporting limit and choose "
                "\u201cReported as less than this value\u201d.",
                **VALUE,
            )
            fields["less_than"] = forms.BooleanField(
                label="Reported as less than this value",
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
                help_text="For a result below the reporting or detection limit (shown as &lt;10). "
                "It is stored as recorded and never converted to zero or to the number.",
            )
        for field in fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        reason = self.fields.pop("reason", None)
        self.fields = {**fields, **self.fields}
        if reason is not None:
            self.fields["reason"] = reason

    def clean(self):
        data = super().clean()
        if self.spec.is_qualitative:
            data["value"], data["qualifier"] = None, ""
        else:
            data["qualifier"] = "<" if data.pop("less_than", False) else ""
            data["outcome"], data["observed_text"] = "", ""
        return data


class ReadingCorrectionForm(ReadingForm):
    reason = _reason("Reason for correction", "The original result stays visible in the record.")


class BatchForm(StyledForm):
    number = forms.CharField(label="Batch number", max_length=80)
    method_code = forms.ChoiceField(label="Method revision")
    reason = _reason()

    def __init__(self, *args, methods=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method_code"].choices = [
            (code, f"{code} revision {payload['revision']}") for code, payload in methods
        ]


class BatchAssignForm(StyledForm):
    batch = forms.ModelChoiceField(label="Open QC batch", queryset=None)
    reason = _reason()

    def __init__(self, *args, batches, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = batches


class EntryForm(StyledForm):
    kind = forms.ChoiceField(
        label="Entry type",
        choices=[
            (k.value, k.label)
            for k in (
                InvestigationEntry.Kind.ASSESSMENT,
                InvestigationEntry.Kind.HYPOTHESIS,
                InvestigationEntry.Kind.EVIDENCE,
                InvestigationEntry.Kind.IMPACT,
            )
        ],
    )
    text = forms.CharField(label="Entry", max_length=4000, widget=forms.Textarea(attrs={"rows": 4}))
    external_reference = forms.CharField(
        label="Controlled reference",
        max_length=200,
        required=False,
        help_text="Deviation, CAPA or document number in the external quality system, if any.",
    )


class SigningForm(SignatureIdentityForm):
    """Signing username and PIN are checked by the shared signing service, never stored here."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "inputmode": "numeric"}),
    )
    reason = _reason()

    field_order = ["signature_username", "pin", "reason", "expected_revision"]


class RetestForm(SigningForm):
    kind = forms.ChoiceField(
        label="Authorize",
        choices=[
            (AnalyticalTest.Kind.RETEST.value, "Retest of the original sample"),
            (AnalyticalTest.Kind.RESAMPLE.value, "Resample: test a newly collected sample"),
        ],
        widget=forms.RadioSelect,
    )
    sample = forms.ModelChoiceField(
        label="New sample (resample only)", queryset=None, required=False
    )
    reason = _reason("Scientific justification and plan")

    field_order = ["kind", "sample", "reason", "signature_username", "pin", "expected_revision"]

    def __init__(self, *args, samples, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sample"].queryset = samples


class ConcludeForm(SigningForm):
    outcome = forms.ChoiceField(
        label="Outcome", choices=Investigation.Outcome.choices, widget=forms.RadioSelect
    )
    assignable_cause = forms.CharField(
        label="Assignable laboratory cause",
        required=False,
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required to invalidate the original result; cite the supporting evidence.",
    )
    reason = _reason("Conclusion")

    field_order = [
        "outcome",
        "assignable_cause",
        "reason",
        "signature_username",
        "pin",
        "expected_revision",
    ]
