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
