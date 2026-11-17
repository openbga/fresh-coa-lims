from django import forms

from catalog.forms import GroupedForm, reason_field
from core.lookups import RemoteSelect
from laboratory.forms import SigningForm
from suppliers.models import http_url

from .models import Rehearsal
from .services import owner_candidates


def _text(label=None, rows=3, required=True, help_text="", max_length=4000):
    return forms.CharField(
        label=label,
        required=required,
        max_length=max_length,
        widget=forms.Textarea(attrs={"rows": rows}),
        help_text=help_text,
    )


class OwnerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = obj.get_full_name()
        return f"{name} ({obj.get_username()})" if name else obj.get_username()


class UseAcceptanceForm(GroupedForm):
    title = forms.CharField(
        max_length=160, help_text="Short name of the use, e.g. QC release testing at Site A."
    )
    intended_use = _text(
        rows=4,
        help_text="What the laboratory uses the system for: the materials and stages, the "
        "records it keeps and the decisions taken in it.",
    )
    exclusions = _text(
        "Outside the intended use",
        required=False,
        help_text="Functions the laboratory does not use, and records it keeps elsewhere.",
    )
    method_codes = forms.MultipleChoiceField(
        label="Supported assays",
        widget=forms.CheckboxSelectMultiple,
        help_text="The methods the laboratory validated for this use. Only methods with an "
        "approved version in force can be chosen; the acceptance freezes that version.",
    )
    process_owner = OwnerChoiceField(
        queryset=None,
        widget=RemoteSelect("owner-candidates"),
        help_text="The person responsible for the business process.",
    )
    system_owner = OwnerChoiceField(
        queryset=None,
        widget=RemoteSelect("owner-candidates"),
        help_text="The person responsible for the availability and maintenance of the system "
        "and for the security of its data.",
    )
    other_responsibilities = _text(
        "Other responsibilities",
        required=False,
        help_text="Others named for this use, e.g. key users or the administrator, and what "
        "each is responsible for.",
    )
    validation_ref = forms.CharField(
        label="Validation report",
        max_length=200,
        help_text="The laboratory's validation report for this use, with its revision.",
    )
    validation_url = forms.URLField(required=False, max_length=500, label="Validation report link")
    open_issues = _text(
        "Known issues and conditions",
        required=False,
        help_text="Issues found in validation and how each is resolved or restricted.",
    )
    reason = reason_field("Reason")
    groups = [
        ("Intended use", ["title", "intended_use", "exclusions", "method_codes"]),
        ("Responsibilities", ["process_owner", "system_owner", "other_responsibilities"]),
        ("Validation evidence", ["validation_ref", "validation_url", "open_issues"]),
        ("Change control", ["reason"]),
    ]

    def __init__(self, *args, methods, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method_codes"].choices = [
            (code, f"{title} ({code})") for code, title in methods.items()
        ]
        for name in ("process_owner", "system_owner"):
            self.fields[name].queryset = owner_candidates()

    def clean_validation_url(self):
        url = self.cleaned_data["validation_url"]
        if url:
            http_url(url)
        return url


DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class RehearsalForm(GroupedForm):
    kind = forms.ChoiceField(choices=Rehearsal.Kind.choices, label="Rehearsal of")
    title = forms.CharField(max_length=160)
    performed_on = forms.DateField(widget=DATE, help_text="The day it was performed.")
    previous_release = forms.CharField(
        label="Release before",
        max_length=80,
        required=False,
        help_text="For an upgrade: the release or source revision upgraded from.",
    )
    release = forms.CharField(
        label="Release",
        max_length=80,
        help_text="The release or source revision rehearsed; for an upgrade, the one upgraded to.",
    )
    environment = forms.CharField(
        max_length=200,
        help_text="Where it was performed, e.g. an isolated copy on the validation server.",
    )
    procedure_ref = forms.CharField(
        label="Procedure", max_length=200, help_text="The procedure followed, with its revision."
    )
    acceptance_criteria = _text(
        help_text="What had to be shown, e.g. the restore check passes, recovery takes at most "
        "4 hours and no more than one day of work is lost."
    )
    outcome = forms.ChoiceField(choices=Rehearsal.Outcome.choices, widget=forms.RadioSelect)
    observations = _text(
        rows=4,
        help_text="What was done and found: the steps, measured times, records reconciled and "
        "checks run.",
    )
    issues_and_actions = _text(
        "Issues and actions",
        required=False,
        help_text="Deviations found and how each was or will be corrected. Required when the "
        "criteria were not met.",
    )
    reason = reason_field("Reason")
    groups = [
        ("Rehearsal", ["kind", "title", "performed_on", "previous_release", "release"]),
        ("How it was performed", ["environment", "procedure_ref", "acceptance_criteria"]),
        ("Result", ["outcome", "observations", "issues_and_actions"]),
        ("Change control", ["reason"]),
    ]

    def clean(self):
        data = super().clean()
        if data.get("kind") == Rehearsal.Kind.UPGRADE and not data.get("previous_release"):
            self.add_error("previous_release", "An upgrade names the release before it.")
        if data.get("outcome") == Rehearsal.Outcome.NOT_MET and not data.get("issues_and_actions"):
            self.add_error(
                "issues_and_actions", "State what was not met and the actions taken or planned."
            )
        return data


class AcceptUseForm(SigningForm):
    # The configuration, release and current acceptance the signer reviewed (a SHA-256).
    token = forms.CharField(widget=forms.HiddenInput, max_length=64)


class WithdrawForm(forms.Form):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = reason_field("Reason for withdrawing")
