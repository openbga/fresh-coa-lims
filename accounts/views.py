"""Account-access guidance; laboratory authority remains in the domain services."""

import shlex

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET

from .services import ROLES


def access_context(user):
    roles = sorted(user.groups.filter(name__in=ROLES).values_list("name", flat=True))
    return {
        "laboratory_roles": roles,
        "has_laboratory_role": bool(roles),
        "is_account_administrator": user.is_active and (user.is_superuser or "admin" in roles),
        "can_view_identity_admin": user.is_active
        and user.is_staff
        and (user.has_perm("accounts.view_user") or user.has_perm("accounts.change_user")),
        "bootstrap_command": shlex.join(
            [
                "python",
                "manage.py",
                "assign_roles",
                user.username,
                "admin",
                "--actor",
                user.username,
                "--reason",
                "Bootstrap account administration",
            ]
        ),
    }


PENDING_SIGN_IN = "two_factor_pending"
PENDING_SETUP = "two_factor_setup"


class SignIn(LoginView):
    """The standard sign-in view plus the published sign-in announcement, if any.

    For an account with a confirmed authenticator the accepted password only starts the sign-in;
    login_verify completes it once the second factor is accepted.
    """

    def get(self, request, *args, **kwargs):
        request.session.pop(PENDING_SIGN_IN, None)  # Opening sign-in again starts over.
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        from django.shortcuts import redirect

        from . import two_factor
        from .signin_log import log_second_factor_requested

        user = form.get_user()
        # The session keeps the account generation read with the password, so a second factor
        # set up in another session meanwhile ends this one at its next request.
        user.authenticated_epoch = user.session_epoch
        if not two_factor.enabled(user):
            return super().form_valid(form)
        pending = two_factor.begin_sign_in(user)
        pending["next"] = self.get_success_url()
        self.request.session.cycle_key()
        self.request.session[PENDING_SIGN_IN] = pending
        log_second_factor_requested(user, self.request)
        return redirect("login_verify")

    def get_context_data(self, **kwargs):
        from .announcements import announcement_html, published_announcement

        context = super().get_context_data(**kwargs)
        notice = published_announcement()
        if notice is not None:
            context["announcement"] = notice
            context["announcement_html"] = announcement_html(notice)
        return context


@sensitive_post_parameters("otp_code")
@sensitive_variables()
def login_verify(request):
    """Second sign-in step: the authenticator code, or a recovery code, after the password."""
    from django.contrib import messages
    from django.contrib.auth import login
    from django.core.exceptions import ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect

    from . import two_factor
    from .forms import SignInCodeForm
    from .signin_log import log_second_factor_failed

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    pending = request.session.get(PENDING_SIGN_IN)
    if not isinstance(pending, dict):
        return redirect("login")
    form = SignInCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user, factor = two_factor.complete_sign_in(pending, form.cleaned_data["otp_code"])
        except two_factor.SignInRestart:
            request.session.pop(PENDING_SIGN_IN, None)
            messages.info(request, "Sign in again: enter your password, then a new code.")
            return redirect("login")
        except ValidationError as exc:
            log_second_factor_failed(pending, request)
            form.add_error(None, exc)
        else:
            request.session.pop(PENDING_SIGN_IN, None)
            user.sign_in_factors = ["password", factor]
            user.authenticated_epoch = user.session_epoch  # As checked under the account lock.
            login(request, user, backend=pending["backend"])
            if factor == "recovery_code":
                left = two_factor.status(user)["recovery_codes_left"]
                messages.warning(
                    request,
                    f"You signed in with a recovery code. {left} unused "
                    f"recovery code{'' if left == 1 else 's'} left. If you no longer have your "
                    "authenticator app, set up a new one on Two-factor sign-in.",
                )
            return redirect(pending.get("next") or "/")
    elif request.method == "GET" and (
        timezone.now().timestamp() - float(pending.get("started", 0)) > settings.MFA_PENDING_SECONDS
    ):
        request.session.pop(PENDING_SIGN_IN, None)
        messages.info(request, "Sign in again: enter your password, then a new code.")
        return redirect("login")
    return render(
        request,
        "registration/login_verify.html",
        {"form": form, "pending_seconds": settings.MFA_PENDING_SECONDS},
        status=422 if request.method == "POST" else 200,
    )


def _keep_session(request, user):
    """After an owner's own security change: this session continues, the others end. What the
    session's sign-in proved (sign_in_factors) stays as it was."""
    request.session["account_epoch"] = user.session_epoch
    request.user = user


@login_required
@sensitive_post_parameters("current_password", "otp_code")
@sensitive_variables()
def two_factor_page(request):
    """The owner's two-factor sign-in: status, set up, new recovery codes, turn off."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect

    from . import two_factor
    from .administration import CREDENTIALS_LOCKED
    from .forms import TwoFactorChangeForm, TwoFactorStartForm

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    user = request.user
    state = two_factor.status(user)
    context = {
        "page_title": "Two-factor sign-in",
        "state": state,
        "code_count": two_factor.RECOVERY_CODE_COUNT,
    }
    if user.credentials_locked:
        context["unavailable"] = CREDENTIALS_LOCKED
        return render(
            request,
            "accounts/two_factor.html",
            context,
            status=403 if request.method == "POST" else 200,
        )
    form_class = TwoFactorChangeForm if state["enabled"] else TwoFactorStartForm
    form = form_class(request.POST or None, required=state["required"])
    if request.method == "POST" and form.is_valid():
        action = form.cleaned_data["action"]
        data = {"actor": user, "current_password": form.cleaned_data["current_password"]}
        if state["enabled"]:
            data["code"] = form.cleaned_data["otp_code"]
        try:
            if action == "setup":
                device = two_factor.begin_setup(**data)
                request.session[PENDING_SETUP] = device.pk
                return redirect("accounts:two_factor_setup")
            if action == "codes":
                user, codes = two_factor.replace_recovery_codes(**data)
                _keep_session(request, user)
                return _show_recovery_codes(request, codes, replaced=True)
            if action == "disable":
                user = two_factor.disable(**data)
                _keep_session(request, user)
                messages.success(
                    request, "Two-factor sign-in is off. Other sessions have been signed out."
                )
                return redirect("accounts:two_factor")
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else str(exc))
    context["form"] = form
    return render(
        request,
        "accounts/two_factor.html",
        context,
        status=422 if request.method == "POST" else 200,
    )


@sensitive_variables()
def _show_recovery_codes(request, codes, *, replaced):
    """The one display of a new set of recovery codes; they are not stored in readable form."""
    from django.contrib import messages
    from django.utils.html import format_html_join

    from .two_factor import Concealed

    messages.success(
        request,
        "New recovery codes made. The earlier codes no longer work."
        if replaced
        else "Two-factor sign-in is on. Other sessions have been signed out.",
    )
    return render(
        request,
        "accounts/two_factor_codes.html",
        {
            "page_title": "Recovery codes",
            "codes": Concealed(codes),
            # Rendered here, so no template loop frame holds a code in plain form.
            "code_list": Concealed(
                format_html_join("", "<li><code>{}</code></li>", ((code,) for code in codes)),
                html=True,
            ),
        },
    )


@login_required
@sensitive_post_parameters("otp_code")
@sensitive_variables()
def two_factor_setup(request):
    """Add the new key to an authenticator app, then confirm it with a code from the app."""
    import segno
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect
    from django.utils.safestring import mark_safe

    from . import two_factor
    from .forms import TwoFactorConfirmForm

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    device = two_factor.pending_setup(request.user, request.session.get(PENDING_SETUP))
    if device is None:
        request.session.pop(PENDING_SETUP, None)
        two_factor.discard_setup(request.user)
        messages.info(request, "Setup was not started or has expired. Start again.")
        return redirect("accounts:two_factor")
    form = TwoFactorConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user, codes = two_factor.confirm_setup(
                actor=request.user, device_pk=device.pk, code=form.cleaned_data["otp_code"]
            )
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else str(exc))
        else:
            request.session.pop(PENDING_SETUP, None)
            _keep_session(request, user)
            return _show_recovery_codes(request, codes, replaced=False)
    # Black on white in both themes so that every camera reads it.
    qr = segno.make(device.config_url, error="m").svg_inline(
        scale=5,
        dark="#000",
        light="#fff",
        border=4,
        svgclass="vr-qr",
        lineclass=None,
        omitsize=True,
    )
    return render(
        request,
        "accounts/two_factor_setup.html",
        {
            "page_title": "Set up two-factor sign-in",
            "form": form,
            # Generated markup: paths only, no supplied text.
            "qr_svg": two_factor.Concealed(mark_safe(qr), html=True),
            "secret_key": two_factor.Concealed(two_factor.secret_key(device)),
            "replacing": two_factor.enabled(request.user),
            "setup_minutes": two_factor.SETUP_SECONDS // 60,
        },
        status=422 if request.method == "POST" else 200,
    )


@login_required
@require_GET
def access(request):
    context = access_context(request.user)
    context["page_title"] = (
        "Account access" if context["has_laboratory_role"] else "No laboratory role assigned"
    )
    return render(request, "accounts/access.html", context)


def permission_denied(request, exception):
    context = access_context(request.user) if request.user.is_authenticated else {}
    context["page_title"] = (
        "No laboratory role assigned"
        if request.user.is_authenticated and not context["has_laboratory_role"]
        else "Access not permitted"
    )
    return render(request, "403.html", context, status=403)


@login_required
@require_GET
def user_list(request):
    from django import forms
    from django.contrib.auth import get_user_model
    from django.core.paginator import Paginator
    from django.db.models import Exists, OuterRef, Q
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from core.services import require_role

    require_role(request.user, "admin")

    class Filters(forms.Form):
        q = forms.CharField(required=False, max_length=150, label="Find account")
        role = forms.ChoiceField(
            required=False, choices=[("", "All roles")] + [(r, r.title()) for r in sorted(ROLES)]
        )
        status = forms.ChoiceField(
            required=False,
            choices=[("", "Any status"), ("active", "Active"), ("inactive", "Inactive")],
        )
        two_factor = forms.ChoiceField(
            required=False,
            label="Two-factor sign-in",
            choices=[("", "On or off"), ("on", "On"), ("off", "Off")],
        )

    filters = Filters(request.GET)
    for field in filters.fields.values():
        field.widget.attrs["class"] = (
            "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        )
    users = (
        get_user_model()
        .objects.prefetch_related("groups")
        .annotate(
            has_two_factor=Exists(TOTPDevice.objects.filter(user=OuterRef("pk"), confirmed=True))
        )
        .order_by("username")
    )
    valid = filters.is_valid()
    if valid:
        data = filters.cleaned_data
        if data["q"]:
            users = users.filter(
                Q(username__icontains=data["q"])
                | Q(first_name__icontains=data["q"])
                | Q(last_name__icontains=data["q"])
                | Q(email__icontains=data["q"])
            )
        if data["role"]:
            users = users.filter(groups__name=data["role"])
        if data["status"]:
            users = users.filter(is_active=data["status"] == "active")
        if data["two_factor"]:
            users = users.filter(has_two_factor=data["two_factor"] == "on")
    else:
        users = users.none()
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "accounts/users.html",
        {
            "page_title": "Users and roles",
            "filters": filters,
            "page": Paginator(users, 30).get_page(request.GET.get("page")),
            "query": params.urlencode(),
            "filtered": any(request.GET.get(k) for k in filters.fields),
        },
        status=200 if valid else 422,
    )


@login_required
@require_GET
def user_detail(request, pk):
    from django.contrib.auth import get_user_model
    from django.core.paginator import Paginator
    from django.shortcuts import get_object_or_404
    from django.urls import reverse

    from core.models import AuditEvent
    from core.services import require_role

    from . import two_factor
    from .administration import ACTIONS, safe_snapshot

    require_role(request.user, "admin")
    target = get_object_or_404(get_user_model(), pk=pk)
    evidence = safe_snapshot(target)
    actions = [
        "identity",
        "roles",
        "deactivate" if target.is_active else "reactivate",
        "reset_password",
    ]
    if evidence["pin_enrolled"]:
        actions.extend(["unlock_pin", "reenroll_pin"])
    if two_factor.set_up_anything(target) and target.pk != request.user.pk:
        actions.append("reset_two_factor")
    history = (
        AuditEvent.objects.filter(object_type="accounts.user", object_id=str(pk))
        .select_related("actor", "electronicsignature")
        .order_by("-occurred_at", "-id")
    )
    return render(
        request,
        "accounts/user.html",
        {
            "page_title": target.username,
            "target": target,
            "evidence": evidence,
            "two_factor": two_factor.status(target),
            "actions": [
                (ACTIONS[a], reverse("accounts:user_action", args=[pk, a])) for a in actions
            ],
            "history": Paginator(history, 30).get_page(request.GET.get("page")),
        },
    )


def _account_form(request, form, title, cancel, target=None, unavailable=""):
    from core.models import PINCredential

    if not PINCredential.objects.filter(user=request.user).exists():
        unavailable = "Enroll your signature PIN before authorizing account changes."
    return render(
        request,
        "accounts/form.html",
        {
            "page_title": title,
            "form": form,
            "target": target,
            "cancel_url": cancel,
            "signing": True,
            "unavailable": unavailable,
            "submit_label": f"Sign and {title.lower()}",
        },
        status=422 if request.method == "POST" else 200,
    )


@login_required
@sensitive_post_parameters("password", "password_confirmation", "pin")
def user_create(request):
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect
    from django.urls import reverse

    from core.services import require_role

    from .administration import create_account
    from .forms import CreateAccountForm

    require_role(request.user, "admin")
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    form = CreateAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = {
            k: v
            for k, v in form.cleaned_data.items()
            if k not in {"signature_username", "password_confirmation"}
        }
        try:
            target = create_account(actor=request.user, **data)
            messages.success(
                request,
                "Account created. Share the initial password privately; "
                "the user must change it at first sign-in.",
            )
            return redirect("accounts:user_detail", pk=target.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return _account_form(request, form, "Create account", reverse("accounts:user_list"))


@login_required
@sensitive_post_parameters("temporary_password", "password_confirmation", "pin")
def user_action(request, pk, action):
    from django.contrib import messages
    from django.contrib.auth import get_user_model, logout
    from django.core.exceptions import ValidationError
    from django.http import Http404, HttpResponseNotAllowed
    from django.shortcuts import get_object_or_404, redirect
    from django.urls import reverse

    from core.models import PINCredential
    from core.services import require_role

    from .administration import ACTIONS, change_account, last_admin
    from .forms import AccountChangeForm

    require_role(request.user, "admin")
    if action not in ACTIONS:
        raise Http404
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    target = get_object_or_404(get_user_model(), pk=pk)
    form = AccountChangeForm(
        request.POST or None,
        action=action,
        user=target,
        initial={"revision": target.management_revision},
    )
    if request.method == "POST" and form.is_valid():
        data = {
            k: v
            for k, v in form.cleaned_data.items()
            if k not in {"signature_username", "password_confirmation", "revision"}
        }
        try:
            change_account(
                actor=request.user,
                user=target,
                action=action,
                expected_revision=form.cleaned_data["revision"],
                **data,
            )
            if target.pk == request.user.pk:
                logout(request)
                messages.success(request, "Your account was updated. Sign in again.")
                return redirect("login")
            messages.success(request, "Account updated. Existing sessions must sign in again.")
            return redirect("accounts:user_detail", pk=target.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    unavailable = ""
    if action == "deactivate":
        if not target.is_active:
            unavailable = "This account is already inactive."
        elif last_admin(target):
            unavailable = "Keep at least one active account with the admin role."
    elif action == "reactivate" and target.is_active:
        unavailable = "This account is already active."
    elif (
        action in {"unlock_pin", "reenroll_pin"}
        and not PINCredential.objects.filter(user=target).exists()
    ):
        unavailable = "This account has no enrolled PIN."
    elif action == "reset_two_factor":
        from . import two_factor

        if target.pk == request.user.pk:
            unavailable = "Change your own two-factor sign-in on the Two-factor sign-in page."
        elif not two_factor.set_up_anything(target):
            unavailable = "This account has not set up two-factor sign-in."
    return _account_form(
        request,
        form,
        ACTIONS[action],
        reverse("accounts:user_detail", args=[pk]),
        target,
        unavailable=unavailable,
    )


@login_required
@sensitive_post_parameters("current_password", "password", "password_confirmation")
def password_change(request):
    from django.contrib import messages
    from django.contrib.auth import update_session_auth_hash
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect
    from django.urls import reverse

    from .administration import CREDENTIALS_LOCKED, change_own_password
    from .forms import OwnPasswordForm

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    if request.user.credentials_locked:
        return render(
            request,
            "accounts/form.html",
            {
                "page_title": "Change password",
                "unavailable": CREDENTIALS_LOCKED,
                "cancel_url": reverse("accounts:access"),
            },
            status=403 if request.method == "POST" else 200,
        )
    form = OwnPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = change_own_password(
                actor=request.user,
                **{k: v for k, v in form.cleaned_data.items() if k != "password_confirmation"},
            )
            update_session_auth_hash(request, user)
            request.session["account_epoch"] = user.session_epoch
            request.user = user
            messages.success(request, "Password changed. Other sessions have been signed out.")
            return redirect("quality:lot_list")
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else str(exc))
    return render(
        request,
        "accounts/form.html",
        {
            "page_title": "Change password",
            "form": form,
            "required_change": request.user.password_change_required,
            "cancel_url": reverse("accounts:access"),
            "submit_label": "Change password",
        },
        status=422 if request.method == "POST" else 200,
    )


def _announcement_summary(event):
    was, now = event.before.get("published"), event.after.get("published")
    if now and not was:
        return "Announcement published"
    if was and not now:
        return "Announcement withdrawn"
    return "Published announcement changed" if now else "Unpublished text changed"


@login_required
@sensitive_post_parameters("pin")
def announcement(request):
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.core.paginator import Paginator
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect

    from core.models import AuditEvent, PINCredential
    from core.services import require_role

    from .announcements import MEANING, announcement_html, change_announcement, current_announcement
    from .forms import AnnouncementForm

    require_role(request.user, "admin")
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    current = current_announcement()
    form = AnnouncementForm(
        request.POST or None,
        initial={
            "title": current.title,
            "body": current.body,
            "published": current.published,
            "revision": current.revision,
        },
    )
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if k != "signature_username"}
        try:
            saved = change_announcement(
                actor=request.user, expected_revision=data.pop("revision"), **data
            )
            messages.success(
                request,
                "Announcement saved. It is shown on the sign-in page."
                if saved.published
                else "Announcement saved. The sign-in page shows no notice.",
            )
            return redirect("accounts:announcement")
        except ValidationError as exc:
            form.add_error(None, exc)
    history = Paginator(
        AuditEvent.objects.filter(object_type=current._meta.label_lower, object_id=str(current.pk))
        .select_related("actor", "electronicsignature")
        .order_by("-occurred_at", "-id"),
        20,
    ).get_page(request.GET.get("page"))
    for event in history:
        event.summary = _announcement_summary(event)
    return render(
        request,
        "accounts/announcement.html",
        {
            "page_title": "Sign-in announcement",
            "form": form,
            "announcement": current,
            "announcement_html": announcement_html(current),
            "meaning": MEANING,
            "history": history,
            "unavailable": ""
            if PINCredential.objects.filter(user=request.user).exists()
            else "Enroll your signature PIN before changing the announcement.",
        },
        status=422 if request.method == "POST" else 200,
    )
