import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.services import assign_roles, provision_account
from core.models import AuditEvent


@pytest.mark.django_db
def test_role_changes_require_authority_and_are_audited():
    users = get_user_model()
    admin = users.objects.create_user(username="provisioner", is_superuser=True)
    member = users.objects.create_user(username="analyst")
    with pytest.raises(PermissionDenied):
        assign_roles(actor=member, user=member, roles=["quality"], reason="Escalation")
    with pytest.raises(ValidationError):
        assign_roles(actor=admin, user=member, roles=["unknown"], reason="Mistake")
    assign_roles(actor=admin, user=member, roles=["analyst"], reason="Training verified")
    assert list(member.groups.values_list("name", flat=True)) == ["analyst"]
    event = AuditEvent.objects.get(action="account.roles_changed")
    assert event.actor == admin
    assert event.before["roles"] == []
    assert event.after["roles"] == ["analyst"]
    assign_roles(actor=admin, user=member, roles=[], reason="Authorization revoked")
    assert not member.groups.exists()


@pytest.mark.django_db
def test_provision_account_is_audited_and_unauthorized_creation_rolls_back():
    admin = get_user_model().objects.create_user(username="bootstrap", is_superuser=True)
    user = provision_account(
        actor=admin,
        username="new_analyst",
        password="Synthetic-Lab-123!",
        first_name="Synthetic",
        last_name="Analyst",
        roles=["analyst"],
        reason="Identity and qualification verified",
    )
    assert user.check_password("Synthetic-Lab-123!")
    assert AuditEvent.objects.filter(action="account.created", object_id=str(user.pk)).exists()
    with pytest.raises(PermissionDenied):
        provision_account(
            actor=user,
            username="unauthorized",
            password="Synthetic-Lab-123!",
            first_name="Synthetic",
            last_name="Other",
            roles=["admin"],
            reason="Not authorized",
        )
    assert not get_user_model().objects.filter(username="unauthorized").exists()
