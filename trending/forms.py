from django import forms

from catalog.forms import AssessmentChoice, GroupedForm, _date, _text, reason_field
from core.lookups import RemoteSelect
from laboratory.forms import SigningForm

from . import services
from .models import Evaluation, Limits, Rule


def _help(model, name):
    return model._meta.get_field(name).help_text


class LineChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return services.line_label(obj)


class ChartForm(GroupedForm):
    line = LineChoice(
        label="Test",
        queryset=None,
        widget=RemoteSelect("trend-lines"),
        help_text="A numeric or count test of a specification version in force. The chart "
        "follows this test for the specification's material and stage, in its unit.",
    )
    reason = reason_field("Reason")
    groups = [("Chart", ["line"]), ("Change control", ["reason"])]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["line"].queryset = services.chart_lines(uncharted=True)


def _decimal(label, help_text=""):
    return forms.DecimalField(
        label=label, max_digits=20, decimal_places=8, required=False, help_text=help_text
    )


class LimitsForm(GroupedForm):
    """A draft of a chart's limits and rules."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)
    basis = forms.ChoiceField(
        label="Limits",
        choices=Limits.Basis.choices,
        widget=forms.RadioSelect,
        help_text="Computed: the center line is the mean of the baseline results and the limits "
        "are 3σ either side, σ from the average moving range divided by 1.128. Entered: your "
        "own alert limits, for example from a procedure or a longer history.",
    )
    baseline_from = _date(
        "Baseline from", _help(Limits, "baseline_from") + " Computed limits only.", False
    )
    baseline_to = _date(
        "Baseline to", _help(Limits, "baseline_to") + " Computed limits only.", False
    )
    center = _decimal(
        "Center line", "Entered limits only. Needed by the run, 2 of 3 and 4 of 5 rules."
    )
    sigma = _decimal(
        "Standard deviation (σ)",
        "Entered limits only, optional. Needed by the 2 of 3 and 4 of 5 rules.",
    )
    lower = _decimal(
        "Lower limit", "Entered limits only. Enter a lower limit, an upper limit or both."
    )
    upper = _decimal("Upper limit", "Entered limits only.")
    rules = forms.MultipleChoiceField(
        label="Rules",
        choices=Rule.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="A result outside the limits always raises an alert. Each further rule finds "
        "smaller shifts and also raises more alerts on results that are only chance variation.",
    )
    run_length = forms.IntegerField(
        label="Results in a run",
        min_value=6,
        max_value=12,
        initial=8,
        help_text="For the run rule: how many results in a row on one side of the center line.",
    )
    trend_length = forms.IntegerField(
        label="Results in a trend",
        min_value=5,
        max_value=10,
        initial=6,
        help_text="For the trend rule: how many results in a row, each higher or each lower.",
    )
    rationale = _text("Basis of the limits", help_text=_help(Limits, "rationale"))
    reason = reason_field()

    groups = [
        ("Limits", ["basis", "baseline_from", "baseline_to", "center", "sigma", "lower", "upper"]),
        ("Rules", ["rules", "run_length", "trend_length"]),
        ("Basis", ["rationale"]),
        ("Change control", ["reason"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rules"].initial = [Rule.BEYOND]

    def values(self):
        return {name: self.cleaned_data.get(name) for name in services.LIMIT_FIELDS}


class AlertsForm(GroupedForm):
    """The open alerts of a chart to evaluate: ``choices`` are (test id, label)."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)
    alerts = forms.TypedMultipleChoiceField(
        label="Alerts",
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
        help_text=f"The results whose alerts this evaluation covers, at most "
        f"{services.MAX_ALERTS}.",
    )
    reason = reason_field("Reason")
    groups = [("Alerts", ["alerts"]), ("Change control", ["reason"])]

    def __init__(self, *args, choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["alerts"].choices = list(choices)


class FindingsForm(GroupedForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    laboratory_check = _text(
        "Laboratory check", help_text=_help(Evaluation, "laboratory_check"), required=False
    )
    cause = _text("Cause", help_text=_help(Evaluation, "cause"), required=False)
    effect = _text(
        "Lots and results affected", help_text=_help(Evaluation, "effect"), required=False
    )
    actions = _text("Actions", help_text=_help(Evaluation, "actions"), required=False)
    quality_reference = forms.CharField(
        label="Quality-system reference",
        max_length=200,
        required=False,
        help_text=_help(Evaluation, "quality_reference"),
    )
    impact_assessment = AssessmentChoice(
        label="Impact assessment",
        queryset=None,
        required=False,
        widget=RemoteSelect("impact-assessments"),
        help_text="Optional: an impact assessment of the lots and results affected. It must be "
        "concluded before the evaluation is.",
    )
    reason = reason_field()

    groups = [
        ("Findings", ["laboratory_check", "cause", "effect"]),
        ("Follow-up", ["actions", "quality_reference", "impact_assessment"]),
        ("Change control", ["reason"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["impact_assessment"].queryset = services.assessment_choices()

    def values(self):
        return {name: self.cleaned_data[name] for name in services.FINDING_FIELDS}


class ConcludeForm(SigningForm):
    outcome = forms.ChoiceField(
        label="Outcome",
        choices=Evaluation.Outcome.choices,
        widget=forms.RadioSelect,
        help_text="Confirmed: the results show a real shift or trend, and the actions say what "
        "was done. Not confirmed: chance variation, or a laboratory error that was corrected.",
    )
    conclusion = _text(
        "Conclusion",
        rows=4,
        help_text="What the evaluation concludes about the results and the lots behind them.",
    )
