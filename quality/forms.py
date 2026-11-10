from django import forms
from django.utils import timezone

from core.models import RuleSet

from .models import Lot, Sample


class StyledForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LotForm(StyledForm):
    number = forms.CharField(max_length=80)
    material = forms.CharField(max_length=160)
    rules = forms.ModelChoiceField(queryset=RuleSet.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rules"].queryset = RuleSet.objects.filter(status="approved")

    def clean_number(self):
        number = self.cleaned_data["number"]
        if Lot.objects.filter(number=number).exists():
            raise forms.ValidationError("This lot number already exists.")
        return number


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
    pin = forms.CharField(
        label="Signature PIN",
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "inputmode": "numeric"}),
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
