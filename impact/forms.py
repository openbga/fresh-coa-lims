from django import forms
from django.utils import timezone

from core.lookups import LOOKUPS, RemoteSelect
from laboratory.forms import SigningForm, reason_field
from laboratory.models import ContractLaboratory, Equipment, ReagentLot
from suppliers.models import Supplier

from .models import Assessment, Item

DATE = {"widget": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


def remote(lookup, queryset, **kwargs):
    """An optional choice from a registered remote lookup, labelled as the lookup labels it."""
    field = forms.ModelChoiceField(
        queryset=queryset, widget=RemoteSelect(lookup), required=False, **kwargs
    )
    field.label_from_instance = LOOKUPS[lookup].label
    return field


class StartForm(forms.Form):
    """Start an assessment. The service checks the dates and that the cause names its record."""

    cause = forms.ChoiceField(
        label="What failed",
        choices=Assessment.Cause.choices,
        help_text="The system finds the affected records for equipment, a reagent or standard "
        "lot, a supplier or a contract laboratory. For another cause quality adds them.",
    )
    equipment = remote(
        "equipment",
        Equipment.objects.all(),
        help_text="For equipment: the instrument or chamber.",
    )
    reagent_lot = remote(
        "reagent-lots",
        ReagentLot.objects.all(),
        label="Reagent or standard lot",
        help_text="For a reagent or standard: the lot. Solutions prepared from it are included.",
    )
    supplier = remote(
        "suppliers",
        Supplier.objects.all(),
        help_text="For a supplier: the lots received from it in the period are included.",
    )
    contract_laboratory = remote(
        "contract-laboratories",
        ContractLaboratory.objects.all(),
        help_text="For a contract laboratory: the results it reported in the period are included.",
    )
    title = forms.CharField(label="Problem", max_length=160)
    description = forms.CharField(
        label="What happened",
        widget=forms.Textarea(attrs={"rows": 4}),
        max_length=4000,
        help_text="What failed, how and when it was found, and what is known of its extent.",
    )
    found_on = forms.DateField(label="Date found", initial=timezone.localdate, **DATE)
    period_from = forms.DateField(
        label="Period of concern from",
        help_text="First day the problem may have affected work: for equipment, the last "
        "accepted passing calibration before the failure.",
        **DATE,
    )
    period_until = forms.DateField(
        label="Period of concern until",
        initial=timezone.localdate,
        help_text="Last day (inclusive), not after today: when the equipment was taken out of "
        "service, the lot set aside or the problem ended.",
        **DATE,
    )
    quality_reference = forms.CharField(
        label="Quality-system reference",
        max_length=200,
        required=False,
        help_text="The deviation, CAPA or change record in the quality system, if there is one.",
    )


class FindForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class AddRecordForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    kind = forms.ChoiceField(label="Kind of record", choices=Item.Kind.choices)
    identifier = forms.CharField(
        label="Record",
        max_length=120,
        help_text="A test number (T-12), a lot number, a stability study identifier or a "
        "certificate number (CoA-...).",
    )
    reason = reason_field("Why it may be affected", max_length=2000)


class DecisionForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    decision = forms.ChoiceField(choices=Item.Decision.choices, widget=forms.RadioSelect)
    rationale = reason_field("Reason for the decision", max_length=4000)
    follow_up = forms.CharField(
        label="Follow-up",
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=4000,
        required=False,
        help_text="Required when affected: for example a retest under an investigation, a "
        "hold, a reassessment, a certificate withdrawn or amended, a record in the quality "
        "system.",
    )
    follow_up_reference = forms.CharField(
        label="Follow-up reference",
        max_length=200,
        required=False,
        help_text="The investigation, hold, certificate or quality-system record, if any.",
    )

    def clean(self):
        data = super().clean()
        if data.get("decision") == Item.Decision.AFFECTED and not data.get("follow_up"):
            self.add_error("follow_up", "Say what is done about it.")
        return data


class HoldForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Why the lot is held", max_length=2000)


class AssessmentSigningForm(SigningForm):
    """Conclusion and withdrawal: the revision shown, the reason and the PIN."""
