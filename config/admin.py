from django.contrib.admin import AdminSite
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters


class AuditedAdminSite(AdminSite):
    def login(self, request, extra_context=None):
        """Sign in through the application only, so two-factor sign-in and its checks apply.

        Django admin's own sign-in form would start a session with the password alone.
        """
        from django.contrib.auth.views import redirect_to_login
        from django.urls import reverse
        from django.utils.http import url_has_allowed_host_and_scheme

        target = request.GET.get("next", "")
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            target = reverse("admin:index", current_app=self.name)
        return redirect_to_login(target, login_url=reverse("login"))

    @method_decorator(sensitive_post_parameters())
    def password_change(self, request, extra_context=None):
        """Use the same reason, audit and session revocation policy as the workspace."""
        return redirect("accounts:password_change")
