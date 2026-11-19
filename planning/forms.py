from django import forms
from django.core.exceptions import ValidationError

from catalog.forms import GroupedForm
from core.lookups import RemoteSelect, user_label

from . import services
from .models import MAX_TARGET_DAYS, Work


def _date(label, help_text):
    return forms.DateField(
        label=label,
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text=help_text,
    )


class AnalystChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return user_label(obj)


class InstrumentChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.asset_id} · {obj.description}"


class PlanForm(GroupedForm):
    """What to change on every selected test; a field left blank keeps each test's own value.
    ``token`` names the tests and the plan revision the page showed."""

    token = forms.CharField(widget=forms.HiddenInput)
    due_on = _date("Due date", "Every selected test is due on this day. Leave blank to keep each.")
    use_target = forms.BooleanField(
        label="Use the turnaround target instead",
        required=False,
        help_text="Each test is due again by the target in force when it was assigned.",
    )
    analyst = AnalystChoice(
        label="Analyst",
        queryset=services.analysts(),
        required=False,
        widget=RemoteSelect("analysts"),
        help_text="An active analyst. Leave blank to keep each test's analyst.",
    )
    no_analyst = forms.BooleanField(label="Remove the analyst", required=False)
    equipment = InstrumentChoice(
        label="Instrument",
        queryset=services.instruments(),
        required=False,
        widget=RemoteSelect("instruments-in-service"),
        help_text="Equipment in service. Planning does not check its calibration: recording a "
        "result does.",
    )
    no_equipment = forms.BooleanField(label="Remove the instrument", required=False)
    reason = forms.CharField(
        label="Reason",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional. Kept with the change in the audit trail.",
    )
    groups = [
        ("Due date", ["due_on", "use_target"]),
        ("Analyst", ["analyst", "no_analyst"]),
        ("Instrument", ["equipment", "no_equipment"]),
        ("Change", ["reason"]),
    ]

    def clean(self):
        data = super().clean()
        for value, clear, words in (
            ("due_on", "use_target", "a due date or the turnaround target"),
            ("analyst", "no_analyst", "an analyst or no analyst"),
            ("equipment", "no_equipment", "an instrument or no instrument"),
        ):
            if data.get(value) and data.get(clear):
                self.add_error(clear, f"Choose {words}, not both.")
        return data

    def changes(self):
        """Keyword arguments of services.plan_tests: only what the planner chose to change."""
        data = self.cleaned_data
        changes = {}
        for value, clear, key in (
            ("due_on", "use_target", "due_on"),
            ("analyst", "no_analyst", "analyst"),
            ("equipment", "no_equipment", "equipment"),
        ):
            if data.get(clear):
                changes[key] = None
            elif data.get(value):
                changes[key] = data[value]
        return changes


class TakeForm(forms.Form):
    """Hidden fields of the Assign to me button: the plan revision the row showed and the list
    to return to."""

    expected_revision = forms.IntegerField(widget=forms.HiddenInput, min_value=0)
    next = forms.CharField(widget=forms.HiddenInput, required=False, max_length=2000)


class TargetForm(forms.Form):
    """The turnaround target of each kind of work, in calendar days; blank: no target."""

    expected = forms.CharField(widget=forms.HiddenInput, required=False)
    reason = forms.CharField(
        label="Reason",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Why the targets change, for example the procedure that sets them.",
    )

    def __init__(self, *args, current=None, **kwargs):
        super().__init__(*args, **kwargs)
        current = current or {}
        fields = {}
        for work, label in Work.choices:
            target = current.get(work)
            fields[work] = forms.IntegerField(
                label=label,
                required=False,
                min_value=1,
                max_value=MAX_TARGET_DAYS,
                initial=target.days if target else None,
                widget=forms.NumberInput(attrs={"unit": "days", "min": 1}),
                help_text="Leave blank for no target.",
            )
        reason = self.fields.pop("reason")
        self.fields.update(fields)
        self.fields["reason"] = reason
        if not self.is_bound:
            self.initial["expected"] = encode_expected(current)

    def days(self):
        return {work: self.cleaned_data.get(work) for work in Work.values}

    def expected_targets(self):
        return decode_expected(self.cleaned_data.get("expected", ""))


def encode_expected(current):
    return ",".join(f"{work}:{target.pk if target else ''}" for work, target in current.items())


def decode_expected(text):
    try:
        pairs = dict(part.split(":") for part in text.split(",") if part)
        return {work: int(pairs[work]) if pairs[work] else None for work in Work.values}
    except KeyError, ValueError:
        raise ValidationError("The page's targets are not readable. Open it again.") from None


WINDOWS = [(7, "7 days"), (14, "14 days"), (30, "30 days"), (60, "60 days"), (90, "90 days")]
DEFAULT_WINDOW = 30


class ReminderFilterForm(forms.Form):
    within = forms.TypedChoiceField(
        label="Within", choices=WINDOWS, coerce=int, required=False, initial=DEFAULT_WINDOW
    )
    kind = forms.ChoiceField(
        label="Kind",
        required=False,
        choices=[
            ("", "All reminders"),
            ("calibration", "Calibrations"),
            ("pull", "Stability pulls"),
            ("reagent", "Reagents and standards"),
        ],
    )


class WorkFilterForm(forms.Form):
    """The work list's filters; GET-bound so the address is the whole state."""

    q = forms.CharField(required=False, label="Search", max_length=100)
    due = forms.ChoiceField(
        label="Due", required=False, choices=[("", "Any due date"), *services.DUE_CHOICES]
    )
    analyst = forms.ChoiceField(label="Analyst", required=False)
    state = forms.ChoiceField(
        label="Status",
        required=False,
        choices=[
            ("", "Open or awaiting review"),
            ("open", "Open"),
            ("submitted", "Awaiting review"),
        ],
    )
    equipment = forms.ChoiceField(label="Instrument", required=False)
    work = forms.ChoiceField(
        label="Work", required=False, choices=[("", "All work"), *Work.choices]
    )

    def __init__(self, *args, instruments=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["analyst"].choices = [
            ("", "Anyone"),
            ("me", "Assigned to me"),
            ("none", "Not assigned"),
            *((str(user.pk), user_label(user)) for user in services.assignable()),
        ]
        self.fields["equipment"].choices = [
            ("", "Any instrument"),
            ("none", "No instrument planned"),
            *((str(item.pk), f"{item.asset_id} · {item.description}") for item in instruments),
        ]
