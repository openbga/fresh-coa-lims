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


def bench_fields(choices, method):
    """Equipment and reagent or standard lot checkboxes from the bench's choices.

    A kind is required when the method requires it; a kind with no choices that the method does
    not require is left out. ``cleaned_data`` keys are the service's ``equipment_ids`` and
    ``reagent_ids``.
    """
    fields = {}
    for key, choice_key, label, required, noun in [
        ("equipment_ids", "equipment", "Equipment used", method.requires_equipment, "instrument"),
        (
            "reagent_ids",
            "reagents",
            "Reagent and standard lots used",
            method.requires_reagent,
            "reagent or standard lot",
        ),
    ]:
        options = list(choices.get(choice_key, []))
        if not options and not required:
            continue
        if required:
            help_text = f"This method requires at least one {noun}."
            if not options:
                help_text += f" No {noun} is available to select."
        else:
            help_text = f"Select every {noun} used, if any."
        fields[key] = forms.TypedMultipleChoiceField(
            label=label,
            choices=[(str(pk), text) for pk, text in options],
            coerce=int,
            required=required,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            help_text=help_text,
            error_messages={"required": f"Select the {noun} used; this method requires one."},
        )
    return fields


class BenchForm(StyledForm):
    """A form recording work at the bench: adds the equipment and lot checkboxes before the
    original record. Pass ``choices`` (from the bench) and the frozen ``method``."""

    def __init__(self, *args, choices, method, **kwargs):
        super().__init__(*args, **kwargs)
        extra = bench_fields(choices, method)
        if extra:
            fields = dict(self.fields)
            ordered = {}
            for name, field in fields.items():
                if name == "raw_reference":
                    ordered.update(extra)
                ordered[name] = field
            self.fields = ordered

    def bench_field(self, subject):
        """The checkbox field whose selected choice names ``subject``, or None."""
        for name in ("equipment_ids", "reagent_ids"):
            field = self.fields.get(name)
            selected = {str(v) for v in self.cleaned_data.get(name, [])} if field else set()
            for value, text in field.choices if field else ():
                if value in selected and subject in str(text).split():
                    return name
        return None


class ObservationForm(BenchForm):
    """Batch QC result (batch QC checks stay numeric and directly entered)."""

    value = forms.DecimalField(
        label="Observed value",
        help_text="Exact value as read; at most 8 decimal places. Never enter a nondetect as zero.",
        **VALUE,
    )
    raw_reference = _raw_reference()


class CorrectionForm(ObservationForm):
    """QC result correction (batch QC checks stay numeric)."""

    reason = _reason("Reason for correction", "The original value stays visible in the record.")


class ReadingForm(BenchForm):
    """A test observation shaped by its frozen requirement.

    Numeric and count: a value with an optional "reported as less than" choice. Qualitative: one
    outcome from the requirement's controlled pair plus what was observed. Calculated (the
    method has a calculation): one value per approved input; the server calculates the result.
    ``cleaned_data`` holds exactly the service's arguments (value, qualifier, outcome,
    observed_text, inputs, equipment_ids, reagent_ids).
    """

    raw_reference = _raw_reference()

    def __init__(self, *args, spec, choices, **kwargs):
        super().__init__(*args, choices=choices, method=spec.method, **kwargs)
        self.spec = spec
        fields = {}
        calculation = spec.calculation
        if calculation is not None:
            for item in calculation.inputs:
                fields[f"input_{item.code}"] = forms.DecimalField(
                    label=item.label,
                    help_text=f"Exact value as read, in {escape(item.unit)}; "
                    "at most 8 decimal places.",
                    **VALUE,
                )
        elif spec.is_qualitative:
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
        calculation = self.spec.calculation
        if calculation is not None:
            data["inputs"] = {i.code: data.pop(f"input_{i.code}", None) for i in calculation.inputs}
            data["value"], data["qualifier"] = None, ""
            data["outcome"], data["observed_text"] = "", ""
        elif self.spec.is_qualitative:
            data["value"], data["qualifier"] = None, ""
        else:
            data["qualifier"] = "<" if data.pop("less_than", False) else ""
            data["outcome"], data["observed_text"] = "", ""
        return data


class ContractResultForm(StyledForm):
    """What a contract laboratory's report states for a test: the laboratory, the report and
    every replicate, shaped by the frozen requirement.

    ``cleaned_data`` holds exactly the service's arguments (expected_revision, laboratory_id,
    report_number, report_date, raw_reference, readings and, for a correction, reason).
    """

    laboratory_id = forms.TypedChoiceField(
        label="Contract laboratory",
        coerce=int,
        help_text="Laboratories with a signed approval for this method. The approval must cover "
        "the date of the report.",
        error_messages={"required": "Select the contract laboratory that issued the report."},
    )
    report_number = forms.CharField(
        label="Report number",
        max_length=120,
        help_text="As printed on the laboratory's report or certificate of analysis.",
    )
    report_date = forms.DateField(
        label="Date of the report",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="As printed. It cannot be in the future.",
    )
    raw_reference = forms.CharField(
        label="Where the report is kept",
        max_length=200,
        help_text="Document number or location in your controlled records.",
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, spec, laboratories, correcting=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.spec = spec
        self.fields["laboratory_id"].choices = [
            ("", "Select the laboratory"),
            *[(str(pk), label) for pk, label in laboratories],
        ]
        fields = {}
        for number in range(1, spec.replicates + 1):

            def label(text, number=number):
                if spec.replicates == 1:
                    return text
                return f"Replicate {number} {text[0].lower()}{text[1:]}"

            if spec.is_qualitative:
                fields[f"outcome_{number}"] = forms.ChoiceField(
                    label=label("Reported result"),
                    choices=spec.outcomes,
                    widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
                    help_text=f"Acceptance: {escape(spec.acceptance)}.",  # renders unescaped
                )
                fields[f"observed_text_{number}"] = forms.CharField(
                    label=label("Wording on the report"),
                    max_length=200,
                    help_text="The result in the report's own words, e.g. Complies.",
                )
            else:
                count = spec.result_type == "count"
                fields[f"value_{number}"] = forms.DecimalField(
                    label=label("Reported value") + (f" ({spec.unit})" if spec.unit else ""),
                    help_text=(
                        "Whole number of zero or more, as the report states it. "
                        if count
                        else "As the report states it; at most 8 decimal places. "
                    )
                    + "Do not convert a result stated in another unit, and never enter a "
                    "nondetect as zero.",
                    **VALUE,
                )
                fields[f"less_than_{number}"] = forms.BooleanField(
                    label=label("Reported as less than this value"),
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
                    help_text="For a result printed as &lt;10. It is kept as reported and never "
                    "becomes zero or the number.",
                )
        for field in fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        hidden = self.fields.pop("expected_revision")
        self.fields.update(fields)
        if correcting:
            self.fields["reason"] = _reason(
                "Reason for correction", "The result recorded before stays visible in the record."
            )
        self.fields["expected_revision"] = hidden

    def clean(self):
        data = super().clean()
        readings = []
        for number in range(1, self.spec.replicates + 1):
            if self.spec.is_qualitative:
                readings.append(
                    {
                        "value": None,
                        "qualifier": "",
                        "outcome": data.pop(f"outcome_{number}", ""),
                        "observed_text": data.pop(f"observed_text_{number}", ""),
                    }
                )
            else:
                readings.append(
                    {
                        "value": data.pop(f"value_{number}", None),
                        "qualifier": "<" if data.pop(f"less_than_{number}", False) else "",
                        "outcome": "",
                        "observed_text": "",
                    }
                )
        data["readings"] = readings
        return data

    def bench_field(self, subject):
        """A refusal names the laboratory; show it beside the laboratory selected."""
        return "laboratory_id"

    @staticmethod
    def initial_from(test, observations):
        """Initial values for correcting a recorded contract laboratory result."""
        source = observations[0].contract
        initial = {
            "laboratory_id": str(source["laboratory"].get("id", "")),
            "report_number": source["report"].get("number", ""),
            "report_date": source["report"].get("date", ""),
            "raw_reference": observations[0].raw_reference,
        }
        for observation in observations:
            number = observation.replicate
            if test.spec.is_qualitative:
                initial[f"outcome_{number}"] = observation.outcome
                initial[f"observed_text_{number}"] = observation.observed_text
            else:
                initial[f"value_{number}"] = observation.value_text.removeprefix("<")
                initial[f"less_than_{number}"] = observation.qualifier == "<"
        return initial


class ReadingCorrectionForm(ReadingForm):
    reason = _reason("Reason for correction", "The original result stays visible in the record.")


class BatchForm(StyledForm):
    number = forms.CharField(label="Batch number", max_length=80)
    method_code = forms.ChoiceField(label="Method revision")
    reason = _reason()

    def __init__(self, *args, methods=(), earlier=(), **kwargs):
        """``methods``: (code, payload) of the revisions in force. ``earlier``: (code, revision)
        of earlier revisions that tests in progress are frozen to, offered as ``code@revision``
        (a method code is a slug and holds no ``@``)."""
        super().__init__(*args, **kwargs)
        self.fields["method_code"].choices = [
            (code, f"{code} revision {payload['revision']}") for code, payload in methods
        ] + [
            (
                f"{code}@{revision}",
                f"{code} revision {revision} · earlier version, for tests in progress",
            )
            for code, revision in earlier
        ]

    def batch_data(self):
        """The form's values as ``create_batch`` takes them."""
        data = dict(self.cleaned_data)
        code, _, revision = data["method_code"].partition("@")
        data["method_code"] = code
        if revision:
            data["revision"] = int(revision)
        return data


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
        """``samples`` are the untested samples a resample may use; ``None`` for the
        investigation of a stability pull, which is retested on the material pulled."""
        super().__init__(*args, **kwargs)
        if samples is None:
            del self.fields["sample"]
            self.fields["kind"].choices = [
                (AnalyticalTest.Kind.RETEST.value, "Retest of the material that was pulled"),
            ]
            self.fields["kind"].initial = AnalyticalTest.Kind.RETEST.value
        else:
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
