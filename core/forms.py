from django import forms


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not field.widget.is_hidden:
                field.widget.attrs.setdefault("class", "form-control")


class PINForm(StyledForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Current login password")
    pin = forms.CharField(widget=forms.PasswordInput, label="New signature PIN", min_length=8)


class RuleForm(StyledForm):
    code = forms.SlugField()
    segment = forms.SlugField()
    policy = forms.JSONField(
        initial={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        }
    )
    effective_from = forms.DateTimeField()
    effective_until = forms.DateTimeField(required=False)
    reason = forms.CharField(widget=forms.Textarea)


class SignForm(StyledForm):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    pin = forms.CharField(widget=forms.PasswordInput, label="Signature PIN")
    reason = forms.CharField(widget=forms.Textarea)
