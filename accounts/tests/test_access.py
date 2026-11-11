import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.services import ROLES, assign_roles
from core.models import AuditEvent
from quality.models import Lot

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("superuser", [False, True])
def test_roleless_login_lands_on_actionable_access_page(
    client, django_user_model, settings, superuser
):
    settings.DEBUG = False
    user = django_user_model.objects.create_user(
        "bootstrap" if superuser else "unassigned",
        password="Synthetic-access-2026!",
        is_superuser=superuser,
        is_staff=superuser,
    )
    user.groups.add(Group.objects.get_or_create(name="unrelated-group")[0])
    response = client.post(
        reverse("login"),
        {"username": user.username, "password": "Synthetic-access-2026!"},
        follow=True,
    )
    assert response.status_code == 200
    assert response.redirect_chain == [("/", 302), (reverse("accounts:access"), 302)]
    body = response.content.decode()
    assert "No laboratory role assigned" in body
    assert "Ask your organization" in body and "account administrator" in body
    assert "Open workspace" not in body
    assert "Sign out" in body
    assert ('href="/admin/accounts/user/"' in body) == superuser
    assert ("Bootstrap account administration" in body) == superuser
    if superuser:
        assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    assert list(user.groups.values_list("name", flat=True)) == ["unrelated-group"]
    assert not AuditEvent.objects.filter(action="account.roles_changed").exists()
    # A deep link remains denied; its recovery link ends at a successful information page.
    denied = client.get(reverse("core:rules"))
    assert denied.status_code == 403
    assert "No laboratory role assigned" in denied.content.decode()
    assert "Return to the workspace" not in denied.content.decode()
    assert f'href="{reverse("accounts:access")}"' in denied.content.decode()
    assert client.get(reverse("accounts:access")).status_code == 200
    assert client.post(reverse("quality:lot_new"), {"number": "FORBIDDEN"}).status_code == 403
    assert not Lot.objects.exists()
    # Neither the landing page nor a POST to it can grant roles.
    assert client.post(reverse("accounts:access"), {"roles": ["admin"]}).status_code == 405
    assert client.post(reverse("logout")).status_code == 302
    assert client.get(reverse("accounts:access")).status_code == 302


@pytest.mark.parametrize("role", sorted(ROLES))
def test_assigned_roles_keep_workspace_access(client, django_user_model, role):
    user = django_user_model.objects.create_user("assigned")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    client.force_login(user)
    assert client.get(reverse("quality:lot_list")).status_code == 200
    response = client.get(reverse("accounts:access"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Assigned laboratory roles" in body and "Open workspace" in body
    assert ("Account and role management" in body) == (role == "admin")
    assert 'href="/admin/accounts/user/"' not in body  # Role assignment never grants staff access.


def test_bootstrap_requires_explicit_audited_role_assignment(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        "bootstrap", password="Synthetic-access-2026!"
    )
    client.force_login(user)
    assert client.get("/").url == reverse("accounts:access")
    assign_roles(actor=user, user=user, roles=["admin"], reason="Bootstrap account administration")
    client.force_login(user)  # Explicit role changes revoke earlier sessions.
    assert client.get("/").status_code == 200
    assert client.get(reverse("accounts:access")).status_code == 200
    assert AuditEvent.objects.get(action="account.roles_changed").after["roles"] == ["admin"]
    # Explicit account administration still grants no analyst or scientific review authority.
    assert client.post(reverse("quality:lot_new"), {"number": "FORBIDDEN"}).status_code == 403
    assert client.get(reverse("core:audit")).status_code == 200
    replacement = django_user_model.objects.create_user("replacement")
    replacement.groups.add(Group.objects.get_or_create(name="admin")[0])
    assign_roles(actor=user, user=user, roles=[], reason="Revoke laboratory access")
    client.force_login(user)
    assert client.get("/", follow=True).status_code == 200
    assert client.get("/").url == reverse("accounts:access")


def test_access_page_requires_authentication(client):
    response = client.get(reverse("accounts:access"))
    assert response.status_code == 302 and response.url.startswith(reverse("login"))
