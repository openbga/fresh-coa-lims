"""Account-access guidance; laboratory authority remains in the domain services."""

import secrets
import shlex

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET

from core.grids import Column

from .services import ROLES


def access_context(user):
    roles = sorted(user.groups.filter(name__in=ROLES).values_list("name", flat=True))
    return {
        "laboratory_roles": roles,
        "has_laboratory_role": bool(roles),
        "single_sign_on": settings.SINGLE_SIGN_ON,
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
SSO_PENDING = "single_sign_on_pending"
PASSKEY_CEREMONY = "passkey_sign_in"
PENDING_SETUP = "two_factor_setup"
PENDING_KEY = "security_key_registration"
CONFIRM_CEREMONY = "security_key_confirmation"


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
        from .security_keys import relying_party

        context = super().get_context_data(**kwargs)
        context["passkey_sign_in"] = (
            settings.PASSKEY_SIGN_IN and relying_party(self.request) is not None
        )
        if settings.SINGLE_SIGN_ON:
            context["single_sign_on"] = settings.OIDC_PROVIDER_NAME
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

    from . import security_keys, two_factor
    from .forms import SignInCodeForm
    from .signin_log import log_second_factor_failed

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    pending = request.session.get(PENDING_SIGN_IN)
    if not isinstance(pending, dict):
        return redirect("login")
    pending = dict(pending)
    # The account as the password found it; complete_sign_in rechecks it under the account lock.
    account = get_user_model().objects.filter(pk=pending.get("user")).first()
    if account is None:
        request.session.pop(PENDING_SIGN_IN, None)
        return redirect("login")
    rp = security_keys.relying_party(request)
    keys = rp is not None and security_keys.usable_keys(account, rp.id).exists()
    form = SignInCodeForm(
        request.POST if request.method == "POST" else None,
        keys=keys,
        app=two_factor.has_app(account),
    )
    if request.method == "POST":
        # Each challenge is answered once: a refused or repeated answer needs a new one.
        ceremony = pending.pop("key_ceremony", None)
        request.session[PENDING_SIGN_IN] = pending
    if request.method == "POST" and form.is_valid():
        answer = form.cleaned_data["security_key_response"]
        proof = (
            security_keys.KeyAssertion(answer, ceremony or {})
            if answer
            else form.cleaned_data["otp_code"]
        )
        try:
            user, factor = two_factor.complete_sign_in(pending, proof)
        except two_factor.SignInRestart:
            request.session.pop(PENDING_SIGN_IN, None)
            messages.info(request, _restart_message(pending))
            return redirect("login")
        except ValidationError as exc:
            log_second_factor_failed(pending, request)
            form.add_error(None, exc)
        else:
            request.session.pop(PENDING_SIGN_IN, None)
            user.sign_in_factors = [_first_factor(pending), factor]
            user.authenticated_epoch = user.session_epoch  # As checked under the account lock.
            login(request, user, backend=pending["backend"])
            if factor == "recovery_code":
                left = two_factor.status(user)["recovery_codes_left"]
                lost = (
                    "your authenticator app, set up a new one"
                    if two_factor.has_app(user)
                    else "your security key, remove it and add another"
                )
                messages.warning(
                    request,
                    f"You signed in with a recovery code. {left} unused "
                    f"recovery code{'' if left == 1 else 's'} left. If you no longer have "
                    f"{lost} on Two-factor sign-in.",
                )
            return redirect(pending.get("next") or "/")
    elif request.method == "GET" and (
        timezone.now().timestamp() - float(pending.get("started", 0)) > settings.MFA_PENDING_SECONDS
    ):
        request.session.pop(PENDING_SIGN_IN, None)
        messages.info(request, _restart_message(pending))
        return redirect("login")
    context = {
        "form": form,
        "pending_seconds": settings.MFA_PENDING_SECONDS,
        "first_factor": _first_factor(pending),
        "keys": keys,
        "app": two_factor.has_app(account),
        "keys_elsewhere": not keys and two_factor.has_keys(account),
    }
    if keys:
        ceremony = security_keys.begin(rp, "sign_in", account.pk)
        pending["key_ceremony"] = ceremony
        request.session[PENDING_SIGN_IN] = pending
        context["key_options"] = security_keys.request_options(account, ceremony)
    return render(
        request,
        "registration/login_verify.html",
        context,
        status=422 if request.method == "POST" else 200,
    )


def _first_factor(pending):
    """What the first sign-in step checked: the password, or the identity provider."""
    return "identity_provider" if pending.get("first") == "identity_provider" else "password"


def _restart_message(pending):
    if _first_factor(pending) == "identity_provider":
        return "Sign in again with your organization, then enter a new code."
    return "Sign in again: enter your password, then a new code."


def _safe_next(request, value):
    from django.utils.http import url_has_allowed_host_and_scheme

    if isinstance(value, str) and url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return ""


@sensitive_variables()
def login_passkey(request):
    """Sign in with a security key or passkey alone, without the password.

    Started by a POST from Sign in, which makes a new request for the browser; the answer comes
    back to the same address. Each request is answered once: a refused answer gets a new one.
    """
    from django.contrib.auth import login
    from django.core.exceptions import ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect

    from . import security_keys, two_factor
    from .forms import PasskeySignInForm
    from .signin_log import log_passkey_failed

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    rp = security_keys.relying_party(request)
    if request.method == "GET" or not settings.PASSKEY_SIGN_IN or rp is None:
        # Nothing is started by opening the address: Sign in offers the button.
        request.session.pop(PASSKEY_CEREMONY, None)
        return redirect("login")
    form = PasskeySignInForm(request.POST)
    ceremony = request.session.pop(PASSKEY_CEREMONY, None)
    next_url = _safe_next(request, request.POST.get("next"))
    status = 422
    if not form.is_valid():
        form.add_error(None, two_factor.KEY_REFUSED)  # Not an answer a browser gives.
    elif not form.cleaned_data["security_key_response"]:
        status = 200  # Started from Sign in, or sent without the page's script.
    elif not isinstance(ceremony, dict):
        # Sent twice, or the session ended: stale rather than wrong, and not counted.
        log_passkey_failed(
            security_keys.KeyAssertion(form.cleaned_data["security_key_response"], {}), request
        )
        form.add_error(None, two_factor.KEY_EXPIRED)
    else:
        assertion = security_keys.KeyAssertion(form.cleaned_data["security_key_response"], ceremony)
        try:
            user = two_factor.complete_passkey_sign_in(assertion)
        except ValidationError as exc:
            log_passkey_failed(assertion, request)
            form.add_error(None, exc)
        else:
            request.session.pop(PENDING_SIGN_IN, None)
            user.sign_in_factors = ["passkey"]
            user.authenticated_epoch = user.session_epoch  # As checked under the lock.
            login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
            return redirect(next_url or settings.LOGIN_REDIRECT_URL)
    # Each request is answered once: a new one for the next attempt.
    ceremony = security_keys.begin(rp, security_keys.PASSKEY, None)
    request.session[PASSKEY_CEREMONY] = ceremony
    context = {
        "form": form,
        "key_options": security_keys.passkey_options(ceremony),
        "pending_seconds": settings.MFA_PENDING_SECONDS,
        "next": next_url,
    }
    return render(request, "registration/login_passkey.html", context, status=status)


def _sso_callback_uri(request):
    from django.urls import reverse

    return request.build_absolute_uri(reverse("login_sso_callback"))


@require_GET
def login_sso(request):
    """Leave for the organization's identity provider to sign in (Sign in's button).

    Opening it only starts a request: the provider's answer must come back to this session with
    the state it was given, within single_sign_on.PENDING_SECONDS.
    """
    from django.contrib import messages
    from django.http import Http404
    from django.shortcuts import redirect

    from . import single_sign_on

    if not single_sign_on.configured():
        raise Http404
    next_url = _safe_next(request, request.GET.get("next"))
    try:
        url, pending = single_sign_on.begin("sign_in", _sso_callback_uri(request), next=next_url)
    except single_sign_on.ProviderUnavailable:
        messages.error(request, single_sign_on.UNAVAILABLE)
        return redirect("login")
    request.session[SSO_PENDING] = pending
    return redirect(url)


@require_GET
@sensitive_variables()
def login_sso_callback(request):
    """Where the identity provider sends the browser back, for a sign-in or a link."""
    from django.contrib import messages
    from django.contrib.auth import login
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import Http404
    from django.shortcuts import redirect

    from . import single_sign_on, two_factor
    from .signin_log import log_second_factor_requested, log_single_sign_on_failed

    if not single_sign_on.configured():
        raise Http404
    pending = request.session.pop(SSO_PENDING, None)  # Each request is answered once.
    purpose = pending.get("purpose") if isinstance(pending, dict) else None
    linking = purpose == "link" and request.user.is_authenticated
    back = "accounts:single_sign_on" if linking else "login"
    if purpose not in {"sign_in", "link"} or not single_sign_on.answered(pending, request.GET):
        log_single_sign_on_failed(None, request, "expired")
        messages.error(request, single_sign_on.EXPIRED)
        return redirect(back)
    try:
        found = single_sign_on.identity(pending, request.GET)
    except single_sign_on.ProviderUnavailable:
        messages.error(request, single_sign_on.UNAVAILABLE)
        return redirect(back)
    except single_sign_on.Refused as exc:
        log_single_sign_on_failed(None, request, "refused")
        messages.error(request, str(exc))
        return redirect(back)
    if purpose == "link":
        if not linking:
            messages.error(request, single_sign_on.NOT_YOURS)
            return redirect("login")
        try:
            user = single_sign_on.link(actor=request.user, pending=pending, found=found)
        except (ValidationError, PermissionDenied) as exc:
            messages.error(
                request, " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            )
            return redirect("accounts:single_sign_on")
        _keep_session(request, user)
        messages.success(
            request,
            f"Your account is linked to {found.label}. You can now sign in with "
            f"{settings.OIDC_PROVIDER_NAME}. Other sessions have been signed out.",
        )
        return redirect("accounts:single_sign_on")
    try:
        user = single_sign_on.sign_in(found)
    except ValidationError as exc:
        log_single_sign_on_failed(found, request, "account")
        messages.error(request, " ".join(exc.messages))
        return redirect("login")
    # The account generation read under the lock: a security change since ends this session.
    user.authenticated_epoch = user.session_epoch
    next_url = _safe_next(request, pending.get("next"))
    backend = settings.AUTHENTICATION_BACKENDS[0]
    if two_factor.enabled(user):
        user.backend = backend
        second = two_factor.begin_sign_in(user)
        second["next"] = next_url
        second["first"] = "identity_provider"
        request.session.cycle_key()
        request.session[PENDING_SIGN_IN] = second
        log_second_factor_requested(user, request)
        return redirect("login_verify")
    request.session.pop(PENDING_SIGN_IN, None)
    user.sign_in_factors = ["identity_provider"]
    login(request, user, backend=backend)
    return redirect(next_url or settings.LOGIN_REDIRECT_URL)


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

    from . import security_keys, two_factor
    from .administration import CREDENTIALS_LOCKED
    from .forms import TwoFactorChangeForm, TwoFactorStartForm

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    user = request.user
    state = two_factor.status(user)
    rp = security_keys.relying_party(request)
    keys = rp is not None and security_keys.usable_keys(user, rp.id).exists()
    context = {
        "page_title": "Two-factor sign-in",
        "state": state,
        "code_count": two_factor.RECOVERY_CODE_COUNT,
        "rp_id": rp.id if rp else None,
        "keys_available": rp is not None,
        "keys_here": keys,
        "unavailable_host": security_keys.UNAVAILABLE_HOST,
        "passkey_sign_in": settings.PASSKEY_SIGN_IN and rp is not None,
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
    form = form_class(
        request.POST or None,
        required=state["required"],
        keys=keys,
        app=state["app"],
        key_choices=[(k.pk, k.name) for k in state["keys"]],
    )
    ceremony = request.session.pop(CONFIRM_CEREMONY, None) if request.method == "POST" else None
    if request.method == "POST" and form.is_valid():
        action = form.cleaned_data["action"]
        data = {"actor": user, "current_password": form.cleaned_data["current_password"]}
        if state["enabled"]:
            answer = form.cleaned_data["security_key_response"]
            data["code"] = (
                security_keys.KeyAssertion(answer, ceremony or {})
                if answer
                else form.cleaned_data["otp_code"]
            )
        try:
            if action == "add_key":
                request.session[PENDING_KEY] = two_factor.begin_key_registration(rp=rp, **data)
                return redirect("accounts:security_key_add")
            if action == "remove_app":
                user = two_factor.remove_app(**data)
                _keep_session(request, user)
                messages.success(
                    request,
                    "The authenticator app is removed; your security keys remain. Other "
                    "sessions have been signed out.",
                )
                return redirect("accounts:two_factor")
            if action.startswith("remove_key:"):
                user, last = two_factor.remove_key(key_pk=int(action.split(":", 1)[1]), **data)
                _keep_session(request, user)
                messages.success(
                    request,
                    "The key is removed. It was your last second factor, so two-factor sign-in "
                    "is off and the recovery codes no longer work."
                    if last
                    else "The key is removed.",
                )
                return redirect("accounts:two_factor")
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
    if keys and state["enabled"]:
        ceremony = security_keys.begin(rp, "confirm", user.pk)
        request.session[CONFIRM_CEREMONY] = ceremony
        context["key_options"] = security_keys.request_options(user, ceremony)
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
            "replacing": two_factor.has_app(request.user),
            "setup_minutes": two_factor.SETUP_SECONDS // 60,
        },
        status=422 if request.method == "POST" else 200,
    )


@login_required
@sensitive_variables()
def security_key_add(request):
    """Register a security key or passkey: name it, then answer the browser's prompts."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect
    from webauthn.helpers import bytes_to_base64url

    from . import security_keys, two_factor
    from .forms import SecurityKeyNameForm

    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    ceremony = two_factor.pending_registration(request.user, request.session.get(PENDING_KEY))
    if ceremony is None:
        request.session.pop(PENDING_KEY, None)
        messages.info(request, "Registration was not started or has expired. Start again.")
        return redirect("accounts:two_factor")
    count = len(two_factor.status(request.user)["keys"])
    form = SecurityKeyNameForm(request.POST or None, initial={"name": f"Security key {count + 1}"})
    if request.method == "POST" and form.is_valid():
        try:
            user, key, codes = two_factor.register_key(
                actor=request.user,
                ceremony=ceremony,
                response=form.cleaned_data["security_key_response"],
                name=form.cleaned_data["name"],
            )
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else str(exc))
            # The answer was spent: a new challenge for the next try, same expiry.
            ceremony = dict(ceremony, challenge=bytes_to_base64url(secrets.token_bytes(32)))
            request.session[PENDING_KEY] = ceremony
        else:
            request.session.pop(PENDING_KEY, None)
            _keep_session(request, user)
            if codes is not None:
                return _show_recovery_codes(request, codes, replaced=False)
            messages.success(
                request, f"Security key “{key.name}” added. Other sessions have been signed out."
            )
            return redirect("accounts:two_factor")
    return render(
        request,
        "accounts/security_key_add.html",
        {
            "page_title": "Add a security key or passkey",
            "form": form,
            "key_options": security_keys.creation_options(request.user, ceremony),
            "first": not two_factor.enabled(request.user),
            "rp_id": ceremony["rp_id"],
            "setup_minutes": two_factor.SETUP_SECONDS // 60,
            "passkey_sign_in": settings.PASSKEY_SIGN_IN,
        },
        status=422 if request.method == "POST" else 200,
    )


@login_required
@sensitive_post_parameters("current_password", "otp_code")
@sensitive_variables()
def single_sign_on_page(request):
    """The owner's link to an account at the organization's identity provider."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import Http404, HttpResponseNotAllowed
    from django.shortcuts import redirect
    from django.urls import reverse

    from . import security_keys, single_sign_on, two_factor
    from .administration import CREDENTIALS_LOCKED
    from .forms import SingleSignOnChangeForm, SingleSignOnStartForm

    if not single_sign_on.configured():
        raise Http404
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    user = request.user
    state = single_sign_on.status(user)
    on = two_factor.enabled(user)
    rp = security_keys.relying_party(request)
    keys = on and rp is not None and security_keys.usable_keys(user, rp.id).exists()
    context = {
        "page_title": "Organization sign-in",
        "provider": settings.OIDC_PROVIDER_NAME,
        "issuer": settings.OIDC_ISSUER,
        "state": state,
        "two_factor": on,
        "keys_here": keys,
    }
    if user.credentials_locked:
        context["unavailable"] = CREDENTIALS_LOCKED
        return render(
            request,
            "accounts/single_sign_on.html",
            context,
            status=403 if request.method == "POST" else 200,
        )
    action = "unlink" if state["link"] else "link"
    pending = request.session.get(SSO_PENDING)
    if (
        request.method == "GET"
        and "continue" in request.GET
        and isinstance(pending, dict)
        and pending.get("purpose") == "link"
        and pending.get("user") == user.pk
        and pending.get("epoch") == user.session_epoch
        and isinstance(pending.get("url"), str)
        and 0
        <= timezone.now().timestamp() - float(pending.get("started", 0))
        <= single_sign_on.PENDING_SECONDS
    ):
        context["continue_url"] = pending["url"]
        context["pending_minutes"] = single_sign_on.PENDING_SECONDS // 60
        return render(request, "accounts/single_sign_on.html", context)
    if on:
        form = SingleSignOnChangeForm(
            request.POST or None, action=action, keys=keys, app=two_factor.has_app(user)
        )
    else:
        form = SingleSignOnStartForm(request.POST or None, action=action)
    ceremony = request.session.pop(CONFIRM_CEREMONY, None) if request.method == "POST" else None
    if request.method == "POST" and form.is_valid():
        data = {"actor": user, "current_password": form.cleaned_data["current_password"]}
        if on:
            answer = form.cleaned_data["security_key_response"]
            data["code"] = (
                security_keys.KeyAssertion(answer, ceremony or {})
                if answer
                else form.cleaned_data["otp_code"]
            )
        try:
            if action == "link":
                single_sign_on.client()  # Unreachable: refused before a code is spent.
                confirmed = single_sign_on.begin_link(**data)
                url, pending = single_sign_on.begin("link", _sso_callback_uri(request), **confirmed)
                request.session[SSO_PENDING] = {**pending, "url": url}
                # The page then shows an ordinary link to the provider: the site's form-action
                # policy, which also governs the redirects after a form's submission, stays
                # 'self', and reloading it sends no password or code again.
                return redirect(reverse("accounts:single_sign_on") + "?continue")
            user = single_sign_on.unlink(**data)
            _keep_session(request, user)
            messages.success(
                request,
                f"Your account is no longer linked; {settings.OIDC_PROVIDER_NAME} no longer "
                "signs you in. Other sessions have been signed out.",
            )
            return redirect("accounts:single_sign_on")
        except single_sign_on.ProviderUnavailable:
            form.add_error(None, single_sign_on.UNAVAILABLE)
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else str(exc))
    context["form"] = form
    if keys:
        ceremony = security_keys.begin(rp, "confirm", user.pk)
        request.session[CONFIRM_CEREMONY] = ceremony
        context["key_options"] = security_keys.request_options(user, ceremony)
    return render(
        request,
        "accounts/single_sign_on.html",
        context,
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


# The users list's columns (core.grids.Column; keys are saved in users' layouts).
USER_COLUMNS = (
    Column("account", "Account", locked=True),
    Column("roles", "Roles"),
    Column("status", "Status"),
    Column("two-factor", "Two-factor sign-in", priority="medium"),
    Column("last-sign-in", "Last sign-in", priority="low"),
)


@login_required
@require_GET
def user_list(request):
    from django import forms
    from django.contrib.auth import get_user_model
    from django.core.paginator import Paginator
    from django.db.models import Exists, OuterRef, Q
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from core.models import PINCredential
    from core.services import require_role

    from .models import LoginThrottle, SecurityKey
    from .two_factor import CODE_FAILURE_LIMIT

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
            has_app=Exists(TOTPDevice.objects.filter(user=OuterRef("pk"), confirmed=True)),
            has_key=Exists(SecurityKey.objects.filter(user=OuterRef("pk"))),
            # The states the account page shows: a PIN lock and a stopped second factor.
            pin_locked=Exists(
                PINCredential.objects.filter(user=OuterRef("pk"), locked_until__gt=timezone.now())
            ),
            factor_stopped=Exists(
                LoginThrottle.objects.filter(
                    user_id=OuterRef("pk"), code_failures__gte=CODE_FAILURE_LIMIT
                )
            ),
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
        if data["two_factor"] == "on":
            users = users.filter(Q(has_app=True) | Q(has_key=True))
        elif data["two_factor"] == "off":
            users = users.filter(has_app=False, has_key=False)
    else:
        users = users.none()
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "accounts/users.html",
        {
            "page_title": "Users and roles",
            "columns": USER_COLUMNS,
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
    from .models import SingleSignOnLink

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
    if evidence["single_sign_on"] and target.pk != request.user.pk:
        actions.append("remove_single_sign_on")
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
            "single_sign_on": SingleSignOnLink.objects.filter(user_id=target.pk).first(),
            "single_sign_on_configured": settings.SINGLE_SIGN_ON,
            "single_sign_on_issuer": settings.OIDC_ISSUER,
            "actions": [
                (ACTIONS[a], reverse("accounts:user_action", args=[pk, a])) for a in actions
            ],
            "history": Paginator(history, 30).get_page(request.GET.get("page")),
        },
    )


def _account_form(request, form, title, cancel, target=None, unavailable="", submit=""):
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
            "submit_label": submit or f"Sign and {title[:1].lower()}{title[1:]}",
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
    return _account_form(
        request,
        form,
        "New account",
        reverse("accounts:user_list"),
        submit="Sign and create account",
    )


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
    elif action == "remove_single_sign_on":
        from .models import SingleSignOnLink

        if target.pk == request.user.pk:
            unavailable = "Unlink your own organization account on the Organization sign-in page."
        elif not SingleSignOnLink.objects.filter(user_id=target.pk).exists():
            unavailable = "This account is not linked to an organization account."
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
            from .models import SingleSignOnLink

            found = SingleSignOnLink.objects.filter(user_id=user.pk).first()
            if found is not None:
                messages.warning(
                    request,
                    f"Your account is still linked to the organization account {found} "
                    f"(subject {found.subject}, linked "
                    f"{timezone.localtime(found.created_at):%Y-%m-%d}) for sign-in. "
                    "If you do not recognize it, unlink it on Organization sign-in.",
                )
            return redirect("quality:dashboard")
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
