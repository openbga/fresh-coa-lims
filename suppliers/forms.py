from django import forms

from catalog.forms import GroupedForm, reason_field

from .models import Supplier


class SupplierForm(GroupedForm):
    code = forms.SlugField(max_length=60, help_text="Short stable identifier, e.g. sup-syn-001.")
    name = forms.CharField(max_length=160)
    location = forms.CharField(
        max_length=160, help_text="Site the material is supplied from: town and country."
    )
    reason = reason_field("Reason")
    groups = [("Supplier", ["code", "name", "location"]), ("Change control", ["reason"])]

    def clean_code(self):
        code = self.cleaned_data["code"]
        if Supplier.objects.filter(code=code).exists():
            raise forms.ValidationError("This supplier code already exists.")
        return code


class MaterialChoiceForm(forms.Form):
    """First step of recording a qualification: the material fixes the tests to choose from."""

    material = forms.ModelChoiceField(
        queryset=None,
        help_text="The tests a qualification can cover are those of this material's "
        "specifications.",
    )

    def __init__(self, *args, **kwargs):
        from catalog.models import Material

        super().__init__(*args, **kwargs)
        self.fields["material"].queryset = Material.objects.order_by("code")


class QualificationForm(GroupedForm):
    test_codes = forms.MultipleChoiceField(
        label="Tests covered",
        widget=forms.CheckboxSelectMultiple,
        help_text="A result the supplier's certificate states for a test selected here may "
        "stand in for the laboratory's own test. Leave out every test the laboratory "
        "performs itself, such as identity.",
    )
    basis = forms.CharField(
        label="How the supplier was qualified",
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="How the reliability of the supplier's results was established, for example "
        "the lots tested in full and compared with the certificates, and the audit.",
    )
    evidence_ref = forms.CharField(
        label="Evidence reference",
        max_length=200,
        help_text="Qualification report, audit report or comparison record, with its revision.",
    )
    evidence_url = forms.URLField(required=False, max_length=500, label="Evidence link")
    valid_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="The qualification covers lots received from this day.",
    )
    valid_until = forms.DateField(
        label="Valid until (inclusive)",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Last day of receipt covered. Set it to when the supplier's results are to "
        "be confirmed again; a renewal is a new qualification.",
    )
    reason = reason_field("Reason")
    groups = [
        ("Scope", ["test_codes"]),
        ("Evidence", ["basis", "evidence_ref", "evidence_url"]),
        ("Validity", ["valid_from", "valid_until"]),
        ("Change control", ["reason"]),
    ]

    def __init__(self, *args, tests, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["test_codes"].choices = [
            (code, f"{name} ({code})") for code, name in tests.items()
        ]

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
            self.add_error("valid_until", "The last day of validity cannot be before the first.")
        return data
