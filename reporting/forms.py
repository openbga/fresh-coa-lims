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


class ScopeForm(forms.Form):
    """What a certificate is issued for: all of the lot's requirements or the specification of
    one scope of the lot (a customer or a market). Read from the address; nothing is issued."""

    scope = forms.ChoiceField(
        label="Certificate for",
        required=False,
        widget=forms.RadioSelect,
        help_text="A certificate for a scope reports the tests its specification states, with "
        "its limits, and is issued only when every result meets them.",
    )

    def __init__(self, *args, scopes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scope"].choices = [("", "All of the lot's requirements")] + [
            (
                name,
                f"{name}: " + ", ".join(f"{s['code']} version {s['version']}" for s in specs),
            )
            for name, specs in (scopes or {}).items()
        ]


class IssueForm(SignReportForm):
    scope = forms.CharField(widget=forms.HiddenInput, required=False, max_length=60)
    recipient = forms.CharField(
        max_length=160,
        required=False,
        label="Issued to",
        help_text="Customer or consignee named on the certificate. Leave blank for a general one.",
    )
    field_order = [
        "recipient",
        "remarks",
        "reason",
        "evidence_hash",
        "scope",
        "signature_username",
        "pin",
    ]

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


class CheckForm(forms.Form):
    """A certificate to check: its file, or the SHA-256 of its file (reporting/checks.py)."""

    file = forms.FileField(
        label="Certificate file",
        required=False,
        help_text=(
            "The PDF of the certificate, or the certificate data file attached to it, exactly as "
            "received. The file is not kept: only its SHA-256 is calculated."
        ),
    )
    sha256 = forms.CharField(
        label="Or its SHA-256",
        required=False,
        max_length=200,
        help_text="The 64 characters (0-9 and a-f) a checksum tool shows for the file.",
    )

    def __init__(self, *args, refused_file="", **kwargs):
        from analytical.rawdata import max_bytes
        from core.uploads import size_text

        super().__init__(*args, **kwargs)
        # Why the file that was sent did not arrive (it was stopped while it arrived).
        self.refused_file = refused_file
        # static/js/app.js refuses a larger file in the browser, so it is never sent.
        self.fields["file"].widget.attrs.update(
            {
                "accept": ".pdf,.json",
                "data-vr-max-bytes": max_bytes(),
                "data-vr-max-label": size_text(max_bytes()),
            }
        )
        self.fields["sha256"].widget.attrs.update(
            {"autocomplete": "off", "spellcheck": "false", "class": "form-control vr-id"}
        )

    def clean(self):
        from .checks import digest_of, parse_digest

        cleaned = super().clean()
        upload, text = cleaned.get("file"), (cleaned.get("sha256") or "").strip()
        if self.refused_file:
            self.add_error("file", self.refused_file)
        if self.errors:
            return cleaned
        if upload and text:
            raise forms.ValidationError("Give the file or its SHA-256, not both.")
        if not upload and not text:
            raise forms.ValidationError("Choose the certificate file, or enter its SHA-256.")
        if text:
            digest = parse_digest(text)
            if digest is None:
                self.add_error("sha256", "A SHA-256 is 64 characters, 0-9 and a-f.")
                return cleaned
        else:
            digest = digest_of(upload)
        cleaned["digest"] = digest
        return cleaned
