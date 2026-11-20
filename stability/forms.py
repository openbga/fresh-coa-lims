from django import forms
from django.utils import timezone

from catalog.models import Specification
from core.lookups import RemoteSelect
from laboratory.eligibility import equipment_eligibility
from laboratory.forms import (
    DATE,
    ReasonForm,
    SigningForm,
    date_field,
    reason_field,
)
from laboratory.models import Equipment
from quality.models import Lot, LotState

from .models import (
    Hold,
    Protocol,
    ProtocolCondition,
    ProtocolTimepoint,
    ReserveSample,
    RetentionObligation,
    Study,
)

# A lot cancelled as received in error has no material to keep, study or hold.
WITH_MATERIAL = Lot.objects.exclude(state=LotState.CANCELLED)

__all__ = ["ReasonForm", "SigningForm"]


class SpecificationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.code} · {obj.title} ({obj.material.code}, {obj.get_stage_display()}, "
            f"scope {obj.scope})"
        )


class ProtocolForm(forms.ModelForm):
    specification = SpecificationChoiceField(
        queryset=Specification.objects.none(),
        widget=RemoteSelect("specifications"),
        required=False,
        label="Acceptance criteria (specification)",
        help_text="The specification whose approved version in force states the acceptance "
        "criterion of each test, for example the shelf-life specification of the product. "
        "Pulls are then tested in the system. Leave empty to link samples or external "
        "evidence instead. It cannot be changed later; a new protocol version names another.",
    )
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
            "specification",
            "basis",
        ]
        widgets = {"basis": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["specification"].queryset = Specification.objects.select_related(
            "material"
        ).order_by("code")


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
    lot = forms.ModelChoiceField(queryset=Lot.objects.none(), widget=RemoteSelect("study-lots"))
    container_closure = forms.CharField(max_length=200, label="Container and closure")
    start_date = date_field(
        label="Time zero", help_text="Date the study actually started; today or earlier."
    )
    reason = reason_field(max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["protocol"].queryset = Protocol.objects.filter(state="approved")
        self.fields["lot"].queryset = Lot.objects.exclude(
            state__in=[LotState.REJECTED, LotState.CANCELLED]
        ).order_by("number")

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


class PullTestsForm(ReasonForm):
    """Assign a pull's tests. ``criteria`` is the token of the acceptance criteria the page
    shows; the service refuses the assignment when the criteria in force differ from it."""

    criteria = forms.CharField(widget=forms.HiddenInput, max_length=64)


class WithdrawProtocolForm(ReasonForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


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
        widgets = {"lot": RemoteSelect("lots")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = WITH_MATERIAL.order_by("number")


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
            self.fields["lot"] = forms.ModelChoiceField(
                queryset=WITH_MATERIAL.order_by("number"), widget=RemoteSelect("lots")
            )
            self.order_fields(["lot", *self.Meta.fields, "reason"])


class AnchorForm(forms.Form):
    anchor_date = date_field()
    reason = reason_field(max_length=2000)


class HoldForm(forms.Form):
    lot = forms.ModelChoiceField(queryset=Lot.objects.none(), widget=RemoteSelect("lots"))
    kind = forms.ChoiceField(choices=Hold.Kind.choices)
    reference = forms.CharField(
        max_length=200, required=False, help_text="Investigation, CAPA or matter ID."
    )
    reason = reason_field("Reason for hold", max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = WITH_MATERIAL.order_by("number")


# --- Shelf-life evaluations ----------------------------------------------------------------------


def _shelf_life_help(name):
    from .models import ShelfLifeEvaluation

    return ShelfLifeEvaluation._meta.get_field(name).help_text


def shelf_life_study_label(study):
    return (
        f"{study.identifier} · {study.protocol.code} · lot {study.lot.number} · "
        f"{study.container_closure}"
    )


def evaluable_studies():
    """Studies whose protocol names a specification: their pulls are tested in the system."""
    return Study.objects.filter(protocol__specification__isnull=False).select_related(
        "protocol", "lot"
    )


class StudyChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return shelf_life_study_label(obj)


class ShelfLifeStudyForm(forms.Form):
    """The first step of a new evaluation: a study of the protocol and container closure."""

    study = StudyChoice(
        queryset=Study.objects.none(),
        widget=RemoteSelect("shelf-life-studies"),
        help_text="Any study of the protocol and container closure to evaluate: the evaluation "
        "uses every study of both, and you can leave some out afterwards. Only studies whose "
        "protocol names a specification are tested in the system.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["study"].queryset = evaluable_studies()


DIRECTION_HELP = (
    "Expected to decrease: the lower one-sided 95 % confidence limit is compared with the lower "
    "limit, as for an assay. Expected to increase: the upper one-sided limit with the upper "
    "limit, as for a degradation product. Either way or not known: two-sided 95 % limits with "
    "both."
)


class ShelfLifeForm(forms.Form):
    """A new evaluation for one study's protocol: the condition and test choices are its own."""

    condition = forms.ChoiceField(
        label="Storage condition",
        help_text="The protocol's condition whose results are evaluated, usually the long-term "
        "one. A study's time-zero result counts at every condition that has none of its own.",
    )
    test_code = forms.ChoiceField(
        label="Test",
        help_text="A numeric or count test of the protocol with a limit, as the version in "
        "force of its specification states it now. That criterion is kept with the evaluation.",
    )
    direction = forms.ChoiceField(
        label="Expected change",
        choices=[],
        widget=forms.RadioSelect,
        help_text=DIRECTION_HELP,
    )
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
        help_text=_shelf_life_help("purpose"),
    )
    reason = reason_field(max_length=2000)

    def __init__(self, *args, conditions=(), lines=(), **kwargs):
        from .models import ShelfLifeEvaluation

        super().__init__(*args, **kwargs)
        self.fields["condition"].choices = [(label, label) for label in conditions]
        self.fields["test_code"].choices = [(line.code, line.label) for line in lines]
        self.fields["direction"].choices = ShelfLifeEvaluation.Direction.choices


class ShelfLifeChangeForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    studies = forms.TypedMultipleChoiceField(
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
        help_text="The studies whose results are evaluated: the primary batches of the product "
        "in this container closure, at least three where the data exist.",
    )
    direction = forms.ChoiceField(
        label="Expected change", choices=[], widget=forms.RadioSelect, help_text=DIRECTION_HELP
    )
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
        help_text=_shelf_life_help("purpose"),
    )
    reason = reason_field(max_length=2000)

    def __init__(self, *args, studies=(), **kwargs):
        from .models import ShelfLifeEvaluation

        super().__init__(*args, **kwargs)
        self.fields["studies"].choices = [
            (study.pk, f"{study.identifier} · lot {study.lot.number} · {study.protocol.identifier}")
            for study in studies
        ]
        self.fields["direction"].choices = ShelfLifeEvaluation.Direction.choices


class ShelfLifeWithdrawForm(ReasonForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class ShelfLifeConcludeForm(SigningForm):
    data_hash = forms.CharField(widget=forms.HiddenInput, max_length=64)
    outcome = forms.ChoiceField(
        label="Outcome",
        choices=[],
        widget=forms.RadioSelect,
        help_text="Supported: the shelf life you record, in whole months, is no longer than the "
        "estimate. None supported: the data do not support a shelf life yet, or at all.",
    )
    shelf_life_months = forms.IntegerField(
        label="Shelf life (months)",
        required=False,
        min_value=1,
        max_value=999,
        help_text="Whole months, at most the estimate rounded down. Leave empty when none is "
        "supported.",
    )
    conclusion = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        max_length=4000,
        help_text="What the data support and on what basis: the model, the batches, any "
        "extrapolation beyond the period the data cover and the supporting data it rests on.",
    )
    field_order = [
        "expected_revision",
        "data_hash",
        "outcome",
        "shelf_life_months",
        "conclusion",
        "reason",
        "signature_username",
        "pin",
    ]

    def __init__(self, *args, **kwargs):
        from .models import ShelfLifeEvaluation

        super().__init__(*args, **kwargs)
        self.fields["outcome"].choices = ShelfLifeEvaluation.Outcome.choices
