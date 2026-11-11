from django.contrib.admin import AdminSite
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters


class AuditedAdminSite(AdminSite):
    @method_decorator(sensitive_post_parameters())
    def password_change(self, request, extra_context=None):
        """Use the same reason, audit and session revocation policy as the workspace."""
        return redirect("accounts:password_change")
