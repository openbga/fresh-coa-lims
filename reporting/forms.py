from django import forms

from core.forms import SignatureIdentityForm
from quality.models import Lot


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not field.widget.is_hidden:
                field.widget.attrs.setdefault("class", "form-control")


class LotPickForm(StyledForm):
    lot = forms.ModelChoiceField(
        queryset=Lot.objects.none(),
        label="Released lot",
        empty_label="Select a lot",
        help_text="Only lots with a signed QC disposition are listed.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.filter(state="released").order_by("number")
        self.fields["lot"].widget.attrs["class"] = "form-select"


class SignReportForm(SignatureIdentityForm):
    """Common signing fields; the PIN is never repopulated."""

    evidence_hash = forms.CharField(widget=forms.HiddenInput, max_length=64)
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), max_length=2000, label="Reason"
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        max_length=1000,
        required=False,
        label="Remarks on the certificate",
        help_text="Printed on the certificate. Optional.",
    )
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "inputmode": "numeric", "pattern": "[0-9]*"}
        ),
        help_text="Re-enter your signature PIN for every signing.",
    )


class IssueForm(SignReportForm):
    recipient = forms.CharField(
        max_length=160,
        required=False,
        label="Issued to",
        help_text="Customer or consignee named on the certificate. Leave blank for a general one.",
    )
    field_order = ["recipient", "remarks", "reason", "evidence_hash", "signature_username", "pin"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].label = "Reason for issuing"


class AmendForm(SignReportForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    field_order = [
        "reason",
        "remarks",
        "evidence_hash",
        "expected_version",
        "signature_username",
        "pin",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].label = "Reason for amendment"
        self.fields[
            "reason"
        ].help_text = "Printed on the amended certificate and kept in the audit trail."
