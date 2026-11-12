"""Account-access guidance; laboratory authority remains in the domain services."""

import shlex

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.views.decorators.debug import sensitive_post_parameters
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


class SignIn(LoginView):
    """The standard sign-in view plus the published sign-in announcement, if any."""

    def get_context_data(self, **kwargs):
        from .announcements import announcement_html, published_announcement

        context = super().get_context_data(**kwargs)
        notice = published_announcement()
        if notice is not None:
            context["announcement"] = notice
            context["announcement_html"] = announcement_html(notice)
        return context


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
    from django.db.models import Q

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

    filters = Filters(request.GET)
    for field in filters.fields.values():
        field.widget.attrs["class"] = (
            "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        )
    users = get_user_model().objects.prefetch_related("groups").order_by("username")
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
