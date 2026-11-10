from django import forms

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
    raw_reference = forms.CharField(
        label="Original record",
        max_length=200,
        help_text="Notebook page, instrument file or worksheet holding the original observation.",
    )


class CorrectionForm(ObservationForm):
    reason = _reason("Reason for correction", "The original value stays visible in the record.")


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
