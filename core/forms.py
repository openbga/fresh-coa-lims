from django import forms

# A signature PIN: numeric keypad, never autofilled, never rendered back into the page.
PIN_WIDGET_ATTRS = {"autocomplete": "off", "inputmode": "numeric"}


class PINForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="Current login password")
    pin = forms.CharField(
        widget=forms.PasswordInput(attrs=PIN_WIDGET_ATTRS), label="New signature PIN", min_length=8
    )


class RuleForm(forms.Form):
    code = forms.SlugField()
    segment = forms.SlugField()
    policy = forms.JSONField(
        initial={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        help_text="Optional keys: supplier_results, with own_tests, lets a qualified "
        "supplier's result stand in for a test other than those listed. applies_to, with "
        "materials, stages and scopes (at least one, each a list of codes), makes this an "
        "additional rule set: it is not chosen when a lot is received and applies to every "
        "lot whose requirements are assigned for a material, stage and scope it names.",
    )
    effective_from = forms.DateTimeField()
    effective_until = forms.DateTimeField(required=False)
    reason = forms.CharField(widget=forms.Textarea)


class SignatureIdentityForm(forms.Form):
    signature_username = forms.CharField(
        label="Signing username",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )


class SignForm(SignatureIdentityForm):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    pin = forms.CharField(widget=forms.PasswordInput(attrs=PIN_WIDGET_ATTRS), label="Signature PIN")
    reason = forms.CharField(widget=forms.Textarea)
