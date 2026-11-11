import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from config.admin import AuditedAdminSite
from core.models import AuditEvent

pytestmark = pytest.mark.django_db
PASSWORD = "Synthetic-current-password-964!"
NEW_PASSWORD = "Synthetic-replacement-password-735!"


def test_admin_password_change_uses_audited_workspace_flow(client, django_user_model):
    user = django_user_model.objects.create_superuser("bootstrap", password=PASSWORD)
    client.force_login(user)
    other = Client()
    other.force_login(user)
    original_hash = user.password
    assert isinstance(admin.site, AuditedAdminSite)
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    old_url, new_url = reverse("admin:password_change"), reverse("accounts:password_change")
    for method, data in [
        ("get", {}),
        (
            "post",
            {
                "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        ),
    ]:
        response = getattr(client, method)(old_url, data)
        assert response.status_code == 302 and response.url == new_url
        user.refresh_from_db()
        assert user.password == original_hash and user.session_epoch == 1
        assert not AuditEvent.objects.filter(action="account.password_changed").exists()
    data = {
        "current_password": PASSWORD,
        "password": NEW_PASSWORD,
        "password_confirmation": NEW_PASSWORD,
    }
    assert client.post(new_url, data).status_code == 422  # reason cannot be bypassed
    response = client.post(new_url, {**data, "reason": "Scheduled synthetic password replacement"})
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD) and user.session_epoch == 2
    event = AuditEvent.objects.get(action="account.password_changed")
    assert event.actor == user and event.reason == "Scheduled synthetic password replacement"
    assert client.get(reverse("accounts:access")).status_code == 200
    assert other.get(reverse("accounts:access")).status_code == 302


def test_admin_password_redirect_keeps_staff_gate(client, django_user_model):
    url = reverse("admin:password_change")
    assert client.get(url).url.startswith(reverse("admin:login"))
    member = django_user_model.objects.create_user("member")
    client.force_login(member)
    assert client.get(url).url.startswith(reverse("admin:login"))
    assert client.get(reverse("accounts:password_change")).status_code == 200
