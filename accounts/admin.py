from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import User


@admin.register(User)
class ReadOnlyUserAdmin(UserAdmin):
    """Identity maintenance must pass through the audited provisioning service."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(Group)
# Authenticator keys are secrets; their state is shown on the account page in the workspace.
admin.site.unregister(TOTPDevice)
