import re

from django import forms
from django.utils import timezone
from django.utils.html import escape

from catalog.forms import GroupedForm, reason_field
from catalog.units import QUANTITY_UNITS
from core.forms import SignatureIdentityForm
from core.models import RuleSet
from core.services import APPLIES_TO, applies_at
from suppliers.models import Supplier

from . import certificates
from .models import Lot, ReceiptCondition, ReceiptSource, Sample
from .rejection import REFERENCE_MAX, RejectionGrounds
from .services import RECEIPT_FIELDS


class StyledForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


RECEIPT_GROUPS = [
    (
        "Source",
        [
            "source",
            "supplier",
            "supplier_lot",
            "manufacturer",
            "manufacturer_location",
            "manufacturer_lot",
        ],
    ),
    (
        "Delivery",
        [
            "shipment_ref",
            "received_on",
            "quantity",
            "quantity_unit",
            "containers",
            "container_description",
        ],
    ),
    ("Examination on receipt", ["condition", "condition_notes"]),
]


# Menus open on no choice: a source, a unit and an examination outcome are stated, not assumed.
UNSTATED = [("", "—")]


class ReceiptForm(GroupedForm):
    """Receipt details of one lot. The service repeats every rule under the lot lock."""

    source = forms.ChoiceField(choices=UNSTATED + ReceiptSource.choices)
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(),
        required=False,
        help_text="Required for a lot received from a supplier. A quality user adds suppliers "
        "to the register.",
    )
    supplier_lot = forms.CharField(
        label="Supplier lot number",
        max_length=80,
        required=False,
        help_text="As printed on the supplier's label or documents. Leave blank if not known.",
    )
    manufacturer = forms.CharField(
        max_length=160,
        required=False,
        help_text="The manufacturer, when it is not the supplier and is known.",
    )
    manufacturer_location = forms.CharField(max_length=160, required=False)
    manufacturer_lot = forms.CharField(
        label="Manufacturer lot number", max_length=80, required=False
    )
    shipment_ref = forms.CharField(
        label="Delivery or batch document",
        max_length=120,
        help_text="Delivery note, packing list or purchase order. For material made on site, "
        "the batch record or production order.",
    )
    received_on = forms.DateField(
        label="Date received",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        initial=timezone.localdate,
    )
    quantity = forms.DecimalField(label="Quantity received", max_digits=14, decimal_places=4)
    quantity_unit = forms.ChoiceField(label="Quantity unit", choices=UNSTATED + QUANTITY_UNITS)
    containers = forms.IntegerField(label="Number of containers", min_value=1)
    container_description = forms.CharField(
        label="Containers", max_length=160, help_text="Type and size, e.g. 25 kg fibre drums."
    )
    condition = forms.ChoiceField(
        label="Examination on receipt",
        choices=UNSTATED + ReceiptCondition.choices,
        help_text="Labels, seals, container condition and delivery documents, as your "
        "receiving procedure requires.",
    )
    condition_notes = forms.CharField(
        label="Examination notes",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when a discrepancy was found: what was wrong and with which "
        "containers.",
    )
    reason = reason_field("Reason")
    groups = [*RECEIPT_GROUPS, ("Change control", ["reason"])]

    def receipt_values(self):
        return {name: self.cleaned_data[name] for name in RECEIPT_FIELDS}


class ReceiptCorrectionForm(ReceiptForm):
    """A correction names the record it replaces, so a page opened before another correction
    is refused instead of replacing details the user never saw."""

    receipt = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Reason for correction")


class LotForm(ReceiptForm):
    number = forms.CharField(label="Lot number", max_length=80)
    material = forms.CharField(max_length=160)
    rules = forms.ModelChoiceField(label="Rule set", queryset=RuleSet.objects.none())
    groups = [
        ("Lot", ["number", "material", "rules"]),
        *RECEIPT_GROUPS,
        ("Change control", ["reason"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only versions in force: a lot is not received under a retired or expired version.
        # A rule set that states where it applies is added to a lot by its requirements,
        # never chosen here.
        self.fields["rules"].queryset = RuleSet.objects.filter(applies_at(timezone.now())).exclude(
            policy__has_key=APPLIES_TO
        )

    def clean_number(self):
        number = self.cleaned_data["number"]
        if Lot.objects.filter(number=number).exists():
            raise forms.ValidationError("This lot number already exists.")
        return number


PLAIN_NUMBER = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")


class StatedNumberField(forms.DecimalField):
    """A number as a certificate prints it: plain ASCII digits, so the text kept is the text
    entered. An exponent, a plus sign, digit separators or other scripts are refused, never
    reformatted."""

    def to_python(self, value):
        text = value.strip() if isinstance(value, str) else value
        if text in self.empty_values:
            return None
        if not isinstance(text, str) or not PLAIN_NUMBER.fullmatch(text):
            raise forms.ValidationError(certificates.NOT_PLAIN, code="invalid")
        return super().to_python(text)


CERTIFICATE_HEADER = ["number", "issued_by", "issued_on", "stated_lot", "document_ref", "notes"]
LINE_INCOMPLETE = "Enter the result, or clear this test if the certificate does not state it."


class CertificateForm(GroupedForm):
    """What a supplier's certificate states, with one group of fields per approved requirement.

    ``required`` is ``{test_code: (payload, requirement)}`` in specification order. A test whose
    fields are all blank is not stated on the certificate. The service repeats every rule under
    the lot lock and refuses a page opened before the requirements changed (``basis``).
    """

    number = forms.CharField(
        label="Certificate number", max_length=80, help_text="As printed on the certificate."
    )
    issued_by = forms.CharField(
        max_length=160, help_text="The company the certificate names as its issuer."
    )
    issued_on = forms.DateField(
        label="Date of the certificate",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    stated_lot = forms.CharField(
        label="Lot number on the certificate",
        max_length=80,
        help_text="As printed. It is shown beside the lot numbers of the receipt details.",
    )
    document_ref = forms.CharField(
        label="Where the certificate is kept",
        max_length=200,
        help_text="Document number or location in your controlled records.",
    )
    notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Anything else the certificate states, for example a test that is not in "
        "the specification or a result in another unit.",
    )
    basis = forms.CharField(widget=forms.HiddenInput)
    reason = reason_field("Reason")

    def __init__(self, *args, required, **kwargs):
        super().__init__(*args, **kwargs)
        self.required = required
        reason = self.fields.pop("reason")
        groups = [("Certificate", CERTIFICATE_HEADER)]
        for code, (_, spec) in required.items():
            fields = self._line_fields(code, spec)
            self.fields.update(fields)
            groups.append((f"{spec.name}: specification {spec.acceptance}", list(fields)))
        self.fields["reason"] = reason
        self.groups = [*groups, ("Change control", ["reason"])]

    @staticmethod
    def _line_fields(code, spec):
        name = spec.name
        fields = {}
        if spec.is_qualitative:
            fields[f"{code}__outcome"] = forms.ChoiceField(
                label=f"{name} result",
                choices=[("", "Not stated on the certificate"), *spec.outcomes],
                required=False,
            )
            fields[f"{code}__stated"] = forms.CharField(
                label=f"{name} wording on the certificate",
                max_length=200,
                required=False,
                help_text="The result in the certificate's own words, e.g. Complies.",
            )
        else:
            count = spec.result_type == "count"
            fields[f"{code}__value"] = StatedNumberField(
                label=f"{name} result ({spec.unit})",
                max_digits=20,
                decimal_places=8,
                required=False,
                help_text=("Whole number of zero or more, as stated" if count else "As stated")
                + f" on the certificate, in {escape(spec.unit)}. Do not convert a result stated "
                "in another unit: leave it blank and describe it in the notes.",
            )
            fields[f"{code}__less_than"] = forms.BooleanField(
                label=f"{name} stated as less than this value",
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
                help_text="For a result printed as &lt;10. It is kept as stated and never "
                "becomes zero or the number.",
            )
        fields[f"{code}__method"] = forms.CharField(
            label=f"{name} method on the certificate",
            max_length=200,
            required=False,
            help_text="The test method the certificate states. Leave blank if it states none.",
        )
        fields[f"{code}__limits"] = forms.CharField(
            label=f"{name} limits on the certificate",
            max_length=200,
            required=False,
            help_text="The supplier's own limits, as printed. Leave blank if it states none.",
        )
        return fields

    def clean(self):
        data = super().clean()
        if data.get("basis") != certificates.requirements_basis(self.required):
            self.add_error(None, certificates.REQUIREMENTS_STALE)
        results = []
        for code, (_, spec) in self.required.items():
            method = data.get(f"{code}__method", "")
            limits = data.get(f"{code}__limits", "")
            if spec.is_qualitative:
                key = f"{code}__outcome"
                entry = {
                    "value": None,
                    "qualifier": "",
                    "outcome": data.get(key, ""),
                    "stated_text": data.get(f"{code}__stated", ""),
                }
                given = entry["outcome"]
                other = entry["stated_text"] or method or limits
                if f"{code}__stated" in self.errors:
                    continue  # The wording has its own error; do not add a second one.
                if given and not entry["stated_text"].strip():
                    self.add_error(
                        f"{code}__stated", "Enter the wording of the result on the certificate."
                    )
                    continue
            else:
                key = f"{code}__value"
                less_than = data.get(f"{code}__less_than", False)
                entry = {
                    "value": data.get(key),
                    "qualifier": "<" if less_than else "",
                    "outcome": "",
                    "stated_text": "",
                }
                given = entry["value"] is not None
                other = less_than or method or limits
            if key in self.errors:
                continue
            if not given:
                if other:
                    self.add_error(key, LINE_INCOMPLETE)
                continue
            try:
                certificates.stated_result(spec, **entry)
            except forms.ValidationError as exc:
                self.add_error(key, exc.messages)
                continue
            results.append({"test_code": code, **entry, "method": method, "limits": limits})
        if not results and not self.errors:
            self.add_error(None, certificates.NO_RESULTS)
        self.stated_results = results
        return data

    def show_current_requirements(self):
        """A form shown again shows the lot's current requirements, so it carries their token:
        after reviewing them the user submits again without retyping."""
        if self.is_bound:
            data = self.data.copy()
            data["basis"] = certificates.requirements_basis(self.required)
            self.data = data

    def header_values(self):
        return {name: self.cleaned_data[name] for name in certificates.HEADER_FIELDS}

    def results(self):
        return self.stated_results

    @staticmethod
    def initial_from(certificate, required):
        """The current record as the starting values of a correction.

        A result is carried over only where the lot still has the requirement and it takes the
        same kind of result; anything else starts blank.
        """
        initial = {name: getattr(certificate, name) for name in certificates.HEADER_FIELDS}
        for line in certificate.results.all():
            if line.test_code not in required:
                continue
            code, spec = line.test_code, required[line.test_code][1]
            initial[f"{code}__method"] = line.method
            initial[f"{code}__limits"] = line.limits
            if spec.is_qualitative and line.outcome in dict(spec.outcomes):
                initial[f"{code}__outcome"] = line.outcome
                initial[f"{code}__stated"] = line.stated_text
            elif not spec.is_qualitative and not line.outcome:
                initial[f"{code}__value"] = line.value_text.removeprefix("<")
                initial[f"{code}__less_than"] = line.qualifier == "<"
        return initial


class CertificateCorrectionForm(CertificateForm):
    reason = reason_field("Reason for correction")


class CertificateWithdrawalForm(GroupedForm):
    reason = reason_field("Reason for withdrawal")
    groups = [("Change control", ["reason"])]


class AcceptanceProposalForm(GroupedForm):
    # Token of what the page showed the proposal would rely on; a stale page is refused.
    basis = forms.CharField(widget=forms.HiddenInput, required=False, max_length=64)
    reason = reason_field("Reason for relying on the supplier's result")
    groups = [("Change control", ["reason"])]


class AcceptanceWithdrawalForm(GroupedForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Reason for withdrawal")
    groups = [("Change control", ["reason"])]


class SampleForm(StyledForm):
    reference = forms.CharField(max_length=80)
    collected_at = forms.DateTimeField(initial=timezone.now)

    def clean_reference(self):
        reference = self.cleaned_data["reference"]
        if Sample.objects.filter(reference=reference).exists():
            raise forms.ValidationError("This sample reference already exists.")
        return reference


class ResultForm(StyledForm):
    test_code = forms.CharField(max_length=80, initial="identity")
    value = forms.DecimalField(max_digits=20, decimal_places=8)
    unit = forms.CharField(max_length=40)
    lower_limit = forms.DecimalField(max_digits=20, decimal_places=8)
    upper_limit = forms.DecimalField(max_digits=20, decimal_places=8)

    def clean(self):
        values = super().clean()
        if (
            values.get("lower_limit") is not None
            and values.get("upper_limit") is not None
            and values["lower_limit"] > values["upper_limit"]
        ):
            raise forms.ValidationError("The lower limit must not exceed the upper limit.")
        return values


class SigningForm(StyledForm):
    signature_username = forms.CharField(label="Signing username", max_length=150)
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "inputmode": "numeric"}),
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class ClosureForm(SignatureIdentityForm):
    """Signature on a lot's rejection or cancellation, as previewed (``basis``). The PIN is
    never shown again; the revision and the basis are those of the page the signer reviewed."""

    reference = forms.CharField(
        label="Record in the quality system",
        max_length=REFERENCE_MAX,
        required=False,
        help_text="Optional. The deviation or nonconformance record that covers this decision "
        "and what happens to the material, for example NCR-2026-014.",
    )
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "inputmode": "numeric"}, render_value=False
        ),
        help_text="Re-enter your PIN for every signature.",
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    basis = forms.CharField(max_length=64, widget=forms.HiddenInput)


class RejectionForm(ClosureForm):
    grounds = forms.ChoiceField(
        label="Grounds for the rejection",
        choices=UNSTATED + RejectionGrounds.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        label="Reason for the rejection",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="What does not meet the requirements, or why the lot cannot be used.",
    )
    field_order = [
        "grounds",
        "reason",
        "reference",
        "signature_username",
        "pin",
        "expected_revision",
        "basis",
    ]


class CancellationForm(ClosureForm):
    reason = forms.CharField(
        label="What was recorded in error",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="For example: the delivery was recorded twice, and the lot that holds it.",
    )
    field_order = ["reason", "reference", "signature_username", "pin", "expected_revision", "basis"]
