from django import forms

from core.forms import SignatureIdentityForm
from core.lookups import RemoteSelect
from quality.models import Lot

from .models import RecipientNotification, Report


class LotPickForm(forms.Form):
    lot = forms.ModelChoiceField(
        queryset=Lot.objects.none(),
        label="Released lot",
        widget=RemoteSelect("released-lots"),
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


class WithdrawForm(SignatureIdentityForm):
    """Sign a certificate's withdrawal; the PIN is never repopulated."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reference = forms.CharField(
        label="Reference",
        max_length=200,
        required=False,
        help_text=Report._meta.get_field("withdrawal_reference").help_text + " Optional.",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
        label="Reason for withdrawal",
        help_text="Why the certificate is no longer valid. Kept with your signature and shown on "
        "the certificate record.",
    )
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "inputmode": "numeric", "pattern": "[0-9]*"}
        ),
        help_text="Re-enter your signature PIN for every signing.",
    )


class NotificationForm(forms.Form):
    """Record that a recipient was told that the certificate is withdrawn."""

    recipient = forms.CharField(
        label="Recipient notified",
        max_length=160,
        help_text="The person or company told that the certificate is withdrawn.",
    )
    notified_on = forms.DateField(
        label="Date notified",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Not before the withdrawal and not in the future.",
    )
    means = forms.ChoiceField(
        label="Means",
        choices=[("", "Select how"), *RecipientNotification.Means.choices],
    )
    evidence_ref = forms.CharField(
        label="Evidence reference",
        max_length=200,
        help_text="Where the notice and any acknowledgement are kept, for example a document "
        "number or the location in your controlled records.",
    )
    note = forms.CharField(
        label="Note",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when the means is Other.",
    )


class LotRecordForm(forms.Form):
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=500,
        label="Purpose of the export",
        help_text=(
            "For example an inspection request, an annual product review or a customer "
            "complaint. It is printed in the record and kept with the export in the audit trail."
        ),
    )
