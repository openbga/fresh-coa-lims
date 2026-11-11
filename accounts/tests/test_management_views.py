"""Account list, validation and navigation behavior beyond signed lifecycle contracts."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.administration import ACTIONS
from core.models import AuditEvent, ElectronicSignature, PINCredential

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager(client):
    user = get_user_model().objects.create_user(username="manager")
    user.groups.add(Group.objects.get_or_create(name="admin")[0])
    PINCredential.objects.create(user=user, encoded="!unusable-test-only")
    client.force_login(user)
    return user


def test_list_filters_paging_and_empty_state(client, manager):
    users = get_user_model()
    users.objects.bulk_create(
        [users(username=f"member-{i:02}", first_name="Synthetic") for i in range(33)]
    )
    target = users.objects.get(username="member-32")
    target.email = "test@example.invalid"
    target.is_active = False
    target.save()
    target.groups.add(Group.objects.get_or_create(name="reviewer")[0])
    url = reverse("accounts:user_list")
    response = client.get(url)
    assert len(response.context["page"]) == 30
    assert response.context["page"].paginator.count == 34
    response = client.get(url, {"q": "EXAMPLE", "role": "reviewer", "status": "inactive"})
    assert list(response.context["page"]) == [target]
    assert b"Inactive" in response.content
    assert b"Never signed in" in response.content
    assert client.get(url, {"page": 2}).context["page"].number == 2
    response = client.get(url, {"q": "absent"})
    assert b"No accounts match these filters" in response.content
    response = client.get(url, {"role": "superuser"})
    assert response.status_code == 422
    assert response.context["page"].paginator.count == 0


def test_administrator_only_navigation_and_all_action_routes(client, manager):
    target = get_user_model().objects.create_user(username="target")
    management_link = f'href="{reverse("accounts:user_list")}"'.encode()
    assert management_link in client.get(reverse("accounts:access")).content
    for action in ACTIONS:
        response = client.get(reverse("accounts:user_action", args=[target.pk, action]))
        assert response.status_code == 200
        assert b"account_authorized" in response.content
        if action in {"reactivate", "unlock_pin", "reenroll_pin"}:
            assert b"Return without changes" in response.content
            assert b'name="pin"' not in response.content
        else:
            assert b'name="revision"' in response.content
    assert (
        client.get(reverse("accounts:user_action", args=[target.pk, "unknown"])).status_code == 404
    )
    client.force_login(target)
    assert management_link not in client.get(reverse("accounts:access")).content
    for action in ACTIONS:
        url = reverse("accounts:user_action", args=[target.pk, action])
        assert client.get(url).status_code == 403
        assert client.post(url, {}).status_code == 403


def test_invalid_create_keeps_safe_inputs_without_mutation_or_password_echo(client, manager):
    before = (
        get_user_model().objects.count(),
        AuditEvent.objects.count(),
        ElectronicSignature.objects.count(),
    )
    secret = "Private-synthetic-password-864!"
    response = client.post(
        reverse("accounts:user_create"),
        {
            "username": "candidate",
            "first_name": "Synthetic",
            "last_name": "Candidate",
            "password": secret,
            "password_confirmation": "Different-private-password-12!",
            "roles": ["analyst"],
            "reason": "",
            "signature_username": manager.username,
            "pin": "76543218",
        },
    )
    assert response.status_code == 422
    assert b"Passwords do not match" in response.content
    assert b'value="candidate"' in response.content
    assert secret.encode() not in response.content
    assert b'value="76543218"' not in response.content
    assert before == (
        get_user_model().objects.count(),
        AuditEvent.objects.count(),
        ElectronicSignature.objects.count(),
    )


def test_known_signing_blockers_are_explained_before_requesting_pin(client, manager):
    url = reverse("accounts:user_action", args=[manager.pk, "deactivate"])
    response = client.get(url)
    assert b"Keep at least one active account with the admin role" in response.content
    assert b'name="pin"' not in response.content
    PINCredential.objects.filter(user=manager).delete()
    response = client.get(reverse("accounts:user_create"))
    assert b"Enroll your signature PIN before authorizing account changes" in response.content
    assert b'name="pin"' not in response.content


def test_account_post_secrets_are_redacted_from_production_error_reports(client, manager, settings):
    from django.views.debug import SafeExceptionReporterFilter

    settings.DEBUG = False
    routes = [
        (reverse("accounts:user_create"), ["password", "password_confirmation", "pin"]),
        (
            reverse("accounts:user_action", args=[manager.pk, "reset_password"]),
            ["temporary_password", "password_confirmation", "pin"],
        ),
        (
            reverse("accounts:password_change"),
            ["current_password", "password", "password_confirmation"],
        ),
    ]
    for url, fields in routes:
        response = client.post(url, {field: "Synthetic-private-value-764!" for field in fields})
        filtered = SafeExceptionReporterFilter().get_post_parameters(response.wsgi_request)
        for field in fields:
            assert filtered[field] == "********************"
