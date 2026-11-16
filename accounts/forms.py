from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from core.forms import SignForm, StyledForm

from .models import LoginAnnouncement
from .services import ROLES

ROLE_CHOICES = [(r, r.title()) for r in sorted(ROLES)]
PASSWORD_WIDGET = forms.PasswordInput(attrs={"autocomplete": "new-password"})


class CreateAccountForm(SignForm):
    revision = None
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    roles = forms.MultipleChoiceField(
        choices=ROLE_CHOICES, required=False, widget=forms.CheckboxSelectMultiple
    )
    password = forms.CharField(label="Initial password", widget=PASSWORD_WIDGET)
    password_confirmation = forms.CharField(
        label="Confirm initial password", widget=PASSWORD_WIDGET
    )
    reason = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            [
                "username",
                "first_name",
                "last_name",
                "email",
                "roles",
                "password",
                "password_confirmation",
                "reason",
                "signature_username",
                "pin",
            ]
        )
        self.fields["roles"].widget.attrs.pop("class", None)

    def clean(self):
        values = super().clean()
        if values.get("password") != values.get("password_confirmation"):
            self.add_error("password_confirmation", "Passwords do not match.")
        if values.get("password"):
            user = get_user_model()(
                **{k: values.get(k, "") for k in ("username", "first_name", "last_name", "email")}
            )
            validate_password(values["password"], user)
        return values


class AccountChangeForm(SignForm):
    def __init__(self, *args, action, user, **kwargs):
        super().__init__(*args, **kwargs)
        if action == "roles":
            self.fields["roles"] = forms.MultipleChoiceField(
                choices=ROLE_CHOICES,
                required=False,
                widget=forms.CheckboxSelectMultiple,
                initial=list(user.groups.values_list("name", flat=True)),
                help_text=(
                    "Replaces the complete role set. Leave all unchecked to revoke all roles."
                ),
            )
        elif action == "identity":
            for name in ("first_name", "last_name", "email"):
                field = (
                    forms.EmailField(required=False)
                    if name == "email"
                    else forms.CharField(max_length=150)
                )
                field.initial = getattr(user, name)
                self.fields[name] = field
        elif action == "reset_password":
            self.fields["temporary_password"] = forms.CharField(
                required=False,
                widget=PASSWORD_WIDGET,
                label="Temporary password",
                help_text="Leave blank to require a change using the current password. "
                "If supplied, share it privately; the user must replace it after signing in.",
            )
            self.fields["password_confirmation"] = forms.CharField(
                required=False, widget=PASSWORD_WIDGET, label="Confirm temporary password"
            )
        for field in self.fields.values():
            if not field.widget.is_hidden and not isinstance(
                field.widget, forms.CheckboxSelectMultiple
            ):
                field.widget.attrs.setdefault("class", "form-control")
        self.fields["reason"].max_length = 2000
        self.order_fields(
            [
                "first_name",
                "last_name",
                "email",
                "roles",
                "temporary_password",
                "password_confirmation",
                "revision",
                "reason",
                "signature_username",
                "pin",
            ]
        )

    def clean(self):
        values = super().clean()
        if "temporary_password" in values and values.get("temporary_password") != values.get(
            "password_confirmation"
        ):
            self.add_error("password_confirmation", "Passwords do not match.")
        return values


class OwnPasswordForm(StyledForm):
    current_password = forms.CharField(label="Current password", widget=forms.PasswordInput)
    password = forms.CharField(label="New password", widget=PASSWORD_WIDGET)
    password_confirmation = forms.CharField(label="Confirm new password", widget=PASSWORD_WIDGET)
    reason = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        values = super().clean()
        if values.get("password") != values.get("password_confirmation"):
            self.add_error("password_confirmation", "Passwords do not match.")
        return values


class AnnouncementForm(SignForm):
    title = forms.CharField(
        max_length=120, required=False, help_text="Optional heading shown above the text."
    )
    body = forms.CharField(
        label="Announcement text",
        max_length=LoginAnnouncement.BODY_LIMIT,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control vr-announcement-input"}),
        help_text="Plain text. Blank lines separate paragraphs. Also supported: lists starting "
        "with - or 1., tables with | between columns, **bold**, *italic*, `code` and "
        "[link text](https://example.invalid/). HTML is shown as typed, not interpreted.",
    )
    published = forms.BooleanField(
        label="Show on the sign-in page",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="When unchecked, the text is kept here and the sign-in page shows no notice.",
    )
    reason = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            ["title", "body", "published", "revision", "reason", "signature_username", "pin"]
        )

    def clean(self):
        values = super().clean()
        if values.get("published") and not values.get("body"):
            self.add_error("body", "Enter the announcement text before publishing it.")
        return values


CODE_HELP = "The 6-digit code your authenticator app shows now, or one of your recovery codes."


class OneTimeCodeInput(forms.TextInput):
    """A visible code field that, like a PIN field, never puts a submitted code back in the page:
    a refused form may hold an unspent recovery code."""

    def get_context(self, name, value, attrs):
        return super().get_context(name, None, attrs)


def _code_field(label, help_text):
    return forms.CharField(
        label=label,
        max_length=64,
        help_text=help_text,
        widget=OneTimeCodeInput(
            attrs={
                "autocomplete": "one-time-code",
                "autocapitalize": "characters",
                "spellcheck": "false",
            }
        ),
    )


class SignInCodeForm(StyledForm):
    """A code, or a security key's answer that the page's script puts in security_key_response.

    keys: whether the account has security keys usable here; app: whether it has an
    authenticator app. Without an app only recovery codes are accepted in the code field.
    """

    otp_code = _code_field("Code", CODE_HELP)
    security_key_response = forms.CharField(
        required=False, widget=forms.HiddenInput, max_length=64 * 1024
    )

    def __init__(self, *args, keys=False, app=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.keys = keys
        field = self.fields["otp_code"]
        field.required = False
        if not app:
            field.label = "Recovery code"
            field.help_text = "One of the recovery codes you were given; each works once."
        if keys:
            field.help_text += " Leave it empty to use your security key."

    def clean(self):
        from .two_factor import code_kind

        values = super().clean()
        code = values.get("otp_code") or ""
        if self.keys and values.get("security_key_response"):
            values["otp_code"] = ""
            return values
        values["security_key_response"] = ""
        if not code.strip():
            self.add_error(
                "otp_code",
                "Use your security key, or enter a code."
                if self.keys
                else "Enter the 6-digit code from your authenticator app, or a recovery code.",
            )
        elif code_kind(code)[0] is None:
            self.add_error(
                "otp_code",
                "Enter the 6-digit code from your authenticator app, or a recovery code.",
            )
        return values


class TwoFactorStartForm(StyledForm):
    current_password = forms.CharField(label="Current password", widget=forms.PasswordInput)
    action = forms.ChoiceField(
        choices=[
            ("setup", "Set up with an authenticator app"),
            ("add_key", "Set up with a security key or passkey"),
        ]
    )

    def __init__(self, *args, required=False, keys=False, app=False, key_choices=(), **kwargs):
        # required only changes what an account with two-factor sign-in on may do.
        super().__init__(*args, **kwargs)


class TwoFactorChangeForm(SignInCodeForm):
    current_password = forms.CharField(label="Current password", widget=forms.PasswordInput)
    action = forms.ChoiceField(choices=[])

    def __init__(self, *args, required=False, keys=False, app=True, key_choices=(), **kwargs):
        super().__init__(*args, keys=keys, app=app, **kwargs)
        field = self.fields["otp_code"]
        field.label = (
            "Code from your authenticator app or a recovery code" if app else "Recovery code"
        )
        field.help_text = "A recovery code used here is spent, as it would be at sign-in." + (
            " Leave it empty to confirm with your security key." if keys else ""
        )
        choices = [
            ("add_key", "Add a security key or passkey"),
            ("codes", "Make new recovery codes"),
            ("setup", "Set up a new authenticator app" if app else "Add an authenticator app"),
        ]
        if app and key_choices:
            choices.append(("remove_app", "Remove the authenticator app"))
        choices += [(f"remove_key:{pk}", f"Remove {name}") for pk, name in key_choices]
        if not required:
            choices.append(("disable", "Turn off two-factor sign-in"))
        self.fields["action"].choices = choices
        self.order_fields(["current_password", "otp_code", "action"])


class SecurityKeyNameForm(StyledForm):
    name = forms.CharField(
        label="Name of the key",
        max_length=60,
        help_text="So that you can tell your keys apart, for example where you keep it.",
    )
    security_key_response = forms.CharField(
        required=False, widget=forms.HiddenInput, max_length=64 * 1024
    )

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Enter a name for the key.")
        return name

    def clean(self):
        values = super().clean()
        if not self.errors and not values.get("security_key_response"):
            raise forms.ValidationError(
                "Your browser did not return the new key. Choose Register the key and follow "
                "your browser's prompts."
            )
        return values


class TwoFactorConfirmForm(StyledForm):
    otp_code = _code_field(
        "Code from the app", "The 6-digit code the app shows for this account now."
    )

    def clean_otp_code(self):
        from .two_factor import code_kind

        code = self.cleaned_data["otp_code"]
        if code_kind(code)[0] != "totp":
            raise forms.ValidationError("Enter the 6-digit code the app shows.")
        return code
