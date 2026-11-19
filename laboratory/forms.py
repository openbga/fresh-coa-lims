from django import forms

from core import device_formats
from core.forms import SignatureIdentityForm
from core.lookups import RemoteSelect, RemoteSelectMultiple
from quality.models import Sample

from .eligibility import users_with_roles
from .models import (
    Calibration,
    DeviceConnection,
    Equipment,
    Qualification,
    ReagentLot,
    TrainingRecord,
)

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


def _factory_settings():
    return "; ".join(
        f"{f.label}: {f.baud_rate} baud, {f.data_bits}{f.parity[0].upper()}{f.stop_bits}"
        for f in device_formats.FORMATS.values()
    )


class DeviceConnectionForm(forms.ModelForm):
    """How readings are taken from a balance or meter; ``replacing`` is the connection shown as
    current when the page opened."""

    replacing = forms.IntegerField(required=False, widget=forms.HiddenInput)
    reason = reason_field(max_length=2000)

    class Meta:
        model = DeviceConnection
        fields = [
            "device_format",
            "baud_rate",
            "data_bits",
            "parity",
            "stop_bits",
            "flow_control",
            "serial_number",
            "verification_ref",
        ]
        help_texts = {
            "device_format": "The format the instrument answers in. Set the instrument to "
            "answer requests only, without automatic or continuous output.",
            "baud_rate": "As set on the instrument. Factory settings: " + _factory_settings() + ".",
            "flow_control": "Software flow control (XON/XOFF) is not available: set the "
            "instrument's handshake to none or hardware.",
        }


class EndConnectionForm(forms.Form):
    """Ends the data connection shown when the page opened (``connection``)."""

    connection = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field(max_length=2000)


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


def training_label(record):
    trainee = record.trainee.get_username() if record.trainee_id else ""
    done = record.completed_on.isoformat() if record.completed_on else ""
    return (
        f"{record.identifier} · {trainee} · {record.activity} · {record.get_kind_display()}, {done}"
    )


def supporting_training():
    """Training records a qualification may rely on: acknowledged, and not an assessment that
    found the trainee not yet competent (the service checks the person and the activity)."""
    return (
        TrainingRecord.objects.filter(state=TrainingRecord.State.ACKNOWLEDGED)
        .exclude(outcome=TrainingRecord.Outcome.NOT_YET_COMPETENT)
        .select_related("trainee")
    )


class TrainingChoice(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return training_label(obj)


class TrainingForm(forms.Form):
    trainee = forms.ModelChoiceField(
        queryset=users_with_roles(), label="Trainee", widget=RemoteSelect("active-users")
    )
    activity = forms.CharField(
        max_length=120,
        help_text="Method or activity code, as the qualification it supports will name it.",
    )
    document_ref = forms.CharField(
        max_length=200,
        label="Procedure or course",
        help_text="The controlled procedure, method or course trained on, with its revision.",
    )
    kind = forms.ChoiceField(label="Kind of training", choices=TrainingRecord.Kind.choices)
    outcome = forms.ChoiceField(
        choices=TrainingRecord.Outcome.choices,
        help_text="Completed for training; competent or not yet competent for an assessment.",
    )
    trainer = forms.CharField(
        max_length=160,
        label="Trainer or assessor",
        help_text="Who gave the training or assessed it, or the provider of an outside course.",
    )
    completed_on = date_field(label="Completed on")
    evidence_ref = forms.CharField(
        max_length=200,
        required=False,
        label="Evidence reference",
        help_text="Where the signed training record, test or certificate is kept.",
    )
    evidence_url = forms.URLField(required=False, max_length=500, label="Evidence link")
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    reason = reason_field(max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["trainee"].queryset = users_with_roles()

    def clean_evidence_url(self):
        from .models import http_url

        url = self.cleaned_data["evidence_url"]
        if url:
            http_url(url)
        return url

    def clean(self):
        data = super().clean()
        kind, outcome = data.get("kind"), data.get("outcome")
        if kind and outcome:
            assessment = kind == TrainingRecord.Kind.ASSESSMENT
            if assessment and outcome == TrainingRecord.Outcome.COMPLETED:
                self.add_error(
                    "outcome", "An assessment finds the trainee competent or not yet competent."
                )
            elif not assessment and outcome != TrainingRecord.Outcome.COMPLETED:
                self.add_error(
                    "outcome", "Only an assessment of competence finds a trainee competent."
                )
        return data


class QualificationForm(forms.Form):
    """Analyst qualification when `equipment` is absent, instrument qualification otherwise."""

    user = forms.ModelChoiceField(
        queryset=users_with_roles(), label="Qualified person", widget=RemoteSelect("active-users")
    )
    activity = forms.CharField(
        max_length=120,
        help_text="Method or activity code this evidence qualifies. For release decisions or "
        "certificates, the activity a rule set names for them.",
    )
    work = forms.ChoiceField(
        label="Qualified for",
        choices=Qualification.Work.choices,
        initial=Qualification.Work.PERFORM,
        help_text="Performing the work; reviewing its results where a method version asks for "
        "qualified reviewers; or release decisions or issuing certificates where a rule set "
        "reserves them, for a person with the quality role. Each needs its own qualification.",
    )
    training = TrainingChoice(
        queryset=supporting_training(),
        required=False,
        label="Training records",
        widget=RemoteSelectMultiple("training-records"),
        help_text="The person's acknowledged training in this activity that the evidence "
        "relies on.",
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
        self.fields["training"].queryset = supporting_training()
        if equipment is not None:
            del self.fields["user"]
            del self.fields["work"]
            del self.fields["training"]
            self.fields["activity"].label = "Stage or intended use"
            self.fields["activity"].help_text = (
                "For example IQ, OQ, PQ or requalification. To qualify the instrument for one "
                "method, enter the method's code: a method version can ask for it. Any approved "
                "qualification counts as the instrument's qualification evidence."
            )

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


class ContractLaboratoryForm(forms.Form):
    code = forms.SlugField(max_length=60, help_text="Short stable identifier, e.g. cl-syn-001.")
    name = forms.CharField(max_length=160)
    location = forms.CharField(
        max_length=160, help_text="Site that performs the testing: town and country."
    )
    reason = reason_field(max_length=2000)

    def clean_code(self):
        from .models import ContractLaboratory

        code = self.cleaned_data["code"]
        if ContractLaboratory.objects.filter(code=code).exists():
            raise forms.ValidationError("This contract laboratory code already exists.")
        return code


class ContractApprovalForm(forms.Form):
    method_code = forms.CharField(
        max_length=80,
        label="Method code",
        help_text="Code of the test method, exactly as in the method catalog. The approval "
        "applies to every version of that method.",
    )
    scope_note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        max_length=2000,
        label="Scope",
        help_text="Limits of the approval, for example the materials it covers. It is shown "
        "with every result that relies on the approval; the software does not check it.",
    )
    evidence_ref = forms.CharField(
        max_length=200,
        label="Evidence reference",
        help_text="Quality agreement, audit report or accreditation certificate, with its "
        "revision.",
    )
    evidence_url = forms.URLField(required=False, max_length=500, label="Evidence link")
    valid_from = date_field()
    valid_until = date_field(label="Valid until (inclusive)")
    reason = reason_field(max_length=2000)

    def clean_method_code(self):
        """A code the method catalog does not hold would approve nothing; refuse the typo."""
        from django.apps import apps

        code = self.cleaned_data["method_code"].strip()
        if not apps.is_installed("catalog"):
            return code
        method = apps.get_model("catalog", "Method").objects.filter(code__iexact=code).first()
        if method is None:
            raise forms.ValidationError(
                "The method catalog holds no method with this code. Enter the code as it "
                "appears under Specifications, Methods."
            )
        return method.code

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
