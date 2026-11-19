from django import forms


class LocalDateTimeInput(forms.DateTimeInput):
    """The shared date-time control (templates/django/forms/widgets/date.html): the laboratory's
    local time to the minute, typed or picked; every DateTimeField in a form uses it."""

    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%dT%H:%M")


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
        "lot whose requirements are assigned for a material, stage and scope it names. "
        "material_dates (expiry, retest, expiry_or_retest or expiry_and_retest) states which "
        "of a lot's dates must be recorded before it is released. authorization, with "
        "release, certificate or both, each an activity code, reserves the release of the "
        "rule set's lots, and the certificates issued for them, for people holding an "
        "approved, current qualification for that activity.",
    )
    effective_from = forms.DateTimeField(widget=LocalDateTimeInput)
    effective_until = forms.DateTimeField(required=False, widget=LocalDateTimeInput)
    reason = forms.CharField(widget=forms.Textarea)


SIGNING_FIELDS = ("reason", "signature_username", "pin")


class SigningFieldOrder:
    """Every signature asks in one order, whatever the form: its own fields (also those a form
    adds as it is built), then the reason, then the signing username and the PIN
    (docs/ui-standards.md, signing). Rendering iterates the form, so this decides the order."""

    def __iter__(self):
        last = [name for name in SIGNING_FIELDS if name in self.fields]
        for name in [n for n in self.fields if n not in last] + last:
            yield self[name]


class SignatureIdentityForm(SigningFieldOrder, forms.Form):
    signature_username = forms.CharField(
        label="Signing username",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )


class SignForm(SignatureIdentityForm):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    pin = forms.CharField(widget=forms.PasswordInput(attrs=PIN_WIDGET_ATTRS), label="Signature PIN")
    reason = forms.CharField(widget=forms.Textarea)
