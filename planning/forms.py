from datetime import date, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from catalog.forms import GroupedForm
from core.lookups import RemoteSelect, user_label

from . import figures, services
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
            ("qualification", "Qualifications"),
            ("proficiency", "Proficiency testing"),
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


# --- Figures ---------------------------------------------------------------------------------


# Days a period may name: far enough from the calendar's ends that a period's bounds and its
# default 30 days never leave it.
EARLIEST, LATEST = date(1900, 1, 1), date(9998, 12, 31)


class PeriodForm(forms.Form):
    """A period of review days: From and To (both optional: the last 30 days by default), at
    most a year. GET-bound so the address is the whole state."""

    start = _date("From", "")
    end = _date("To", "")

    def _within(self, name):
        value = self.cleaned_data.get(name)
        if value and not EARLIEST <= value <= LATEST:
            raise ValidationError(f"Enter a date from {EARLIEST} to {LATEST}.")
        return value

    def clean_start(self):
        return self._within("start")

    def clean_end(self):
        return self._within("end")

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end:
            if start > end:
                self.add_error("end", "The period ends before it starts.")
            elif (end - start).days >= figures.MAX_PERIOD_DAYS:
                self.add_error("end", f"Choose a period of at most {figures.MAX_PERIOD_DAYS} days.")
        return cleaned

    def period(self, today):
        """(start, end) of the period asked for, or the default one when it is invalid or
        names none. From alone: 30 days from it, at most to today; To alone: 30 days to it."""
        data = self.cleaned_data if self.is_bound and self.is_valid() else {}
        start, end = data.get("start"), data.get("end")
        span = timedelta(days=figures.DEFAULT_PERIOD_DAYS - 1)
        if start and not end:
            end = max(start, min(today, start + span))
        end = end or today
        return start or end - span, end


WORK_CHOICES = [("", "All work"), *Work.choices]


class FigureFilterForm(PeriodForm):
    by = forms.ChoiceField(label="Figures by", required=False, choices=figures.GROUPS)
    work = forms.ChoiceField(label="Work", required=False, choices=WORK_CHOICES)


class ReviewedFilterForm(PeriodForm):
    q = forms.CharField(required=False, label="Search", max_length=100)
    first_time = forms.ChoiceField(
        label="First time",
        required=False,
        choices=[("", "Any"), *figures.FIRST_TIME_CHOICES],
    )
    timeliness = forms.ChoiceField(
        label="Due date", required=False, choices=[("", "Any"), *figures.TIMELINESS]
    )
    work = forms.ChoiceField(label="Work", required=False, choices=WORK_CHOICES)
    material = forms.ChoiceField(label="Material", required=False)
    method = forms.ChoiceField(label="Method", required=False)
    analyst = forms.ChoiceField(label="Analyst", required=False)
    result = forms.ChoiceField(
        label="Result", required=False, choices=[("", "Any result"), *figures.RESULTS]
    )

    def __init__(self, *args, options=None, **kwargs):
        """``options``: figures.filter_options of the period. A value the address names that
        the period does not hold stays a choice (it lists no test) rather than an error."""
        super().__init__(*args, **kwargs)
        options = options or {"material": [], "method": [], "analyst": set()}
        asked = self.data if self.is_bound else {}
        for name in ("material", "method"):
            values = list(options[name])
            if asked.get(name) and asked[name] not in values:
                values.append(asked[name])
            self.fields[name].choices = [
                ("", f"Any {name}"),
                *((value, value) for value in values),
            ]
        ids = set(options["analyst"])
        if str(asked.get("analyst", "")).isdigit():
            ids.add(int(asked["analyst"]))
        people = get_user_model().objects.filter(pk__in=ids).order_by("username")
        self.fields["analyst"].choices = [
            ("", "Anyone"),
            *((str(user.pk), user_label(user)) for user in people),
            ("none", "No analyst recorded"),
        ]
