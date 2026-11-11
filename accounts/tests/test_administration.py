"""Signed account lifecycle and revocation contracts on real PostgreSQL transactions."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts import administration as admin
from accounts.services import assign_roles
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-admin-pass-764!"
REPLACEMENT = "Synthetic-replacement-pass-891!"
PIN = "82519374"


@pytest.fixture
def users():
    result = {}
    for name, roles in [("manager", ["admin"]), ("member", ["analyst"]), ("root", [])]:
        user = get_user_model().objects.create_user(
            username=name,
            password=PASSWORD,
            first_name="Synthetic",
            last_name=name,
            is_superuser=name == "root",
            is_staff=name == "root",
        )
        user.groups.set([Group.objects.get_or_create(name=role)[0] for role in roles])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        result[name] = user
    return result


def fresh(user):
    return get_user_model().objects.get(pk=user.pk)


def change(users, action, **kwargs):
    target = kwargs.pop("user", users["member"])
    return admin.change_account(
        actor=kwargs.pop("actor", users["manager"]),
        user=target,
        expected_revision=kwargs.pop("expected_revision", fresh(target).management_revision),
        action=action,
        pin=kwargs.pop("pin", PIN),
        reason="Synthetic independent account decision",
        **kwargs,
    )


def create(users, **kwargs):
    values = {
        "actor": users["manager"],
        "pin": PIN,
        "username": "new-member",
        "first_name": "Synthetic",
        "last_name": "New",
        "email": "new@example.invalid",
        "password": PASSWORD,
        "roles": ["analyst"],
        "reason": "Synthetic verified identity",
    }
    values.update(kwargs)
    return admin.create_account(**values)


def assert_secret_free(users, extra_secrets=()):
    secrets = [PIN, PASSWORD, REPLACEMENT, *extra_secrets]
    secrets += list(get_user_model().objects.values_list("password", flat=True))
    secrets += list(PINCredential.objects.values_list("encoded", flat=True))
    payloads = []
    for event in AuditEvent.objects.all():
        payloads.extend([event.before, event.after, event.reason])
    for signature in ElectronicSignature.objects.all():
        payloads.extend([signature.content, signature.authentication_context])
    serialized = json.dumps(payloads)
    for secret in secrets:
        assert secret not in serialized
    forbidden = {"password", "pin", "encoded", "temporary_password", "password_hash", "pin_hash"}

    def check_keys(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)

    check_keys(payloads)


def assert_signed(user, action):
    signature = ElectronicSignature.objects.get(
        object_type="accounts.user", object_id=str(user.pk), revision=user.management_revision
    )
    assert signature.meaning == "account_authorized"
    assert signature.content["action"] == action
    assert signature.content["account"] == signature.audit_event.after
    assert signature.audit_event.action == action
    assert signature.content["account"]["revision"] == user.management_revision
    assert (
        signature.content_hash
        == hashlib.sha256(
            json.dumps(signature.content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return signature


def test_admin_web_authority_is_explicit_and_precedes_target_lookup(users):
    client = Client()
    routes = [
        reverse("accounts:user_list"),
        reverse("accounts:user_create"),
        reverse("accounts:user_detail", args=[users["member"].pk]),
        reverse("accounts:user_detail", args=[987654]),
        reverse("accounts:user_action", args=[users["member"].pk, "roles"]),
        reverse("accounts:user_action", args=[987654, "roles"]),
    ]
    for actor in (users["root"], users["member"]):
        client.force_login(actor)
        for url in routes:
            assert client.get(url).status_code == 403
        assert client.post(reverse("accounts:user_create"), {}).status_code == 403
    client.force_login(users["manager"])
    assert client.get(reverse("accounts:user_list")).status_code == 200
    assert client.get(reverse("accounts:user_detail", args=[987654])).status_code == 404
    with pytest.raises(PermissionDenied):
        create(users, actor=users["root"])


def test_create_account_is_signed_forced_to_change_password_and_secret_free(users):
    user = create(users)
    assert user.check_password(PASSWORD)
    assert user.password_change_required and user.is_active
    assert set(user.groups.values_list("name", flat=True)) == {"analyst"}
    assert not PINCredential.objects.filter(user=user).exists()
    signature = assert_signed(user, "account.created")
    assert signature.signer == users["manager"]
    assert signature.audit_event.before == {}
    assert_secret_free(users)


def test_pin_failure_counter_and_audit_survive_rejected_admin_action(users):
    for _ in range(5):
        with pytest.raises(ValidationError, match="PIN was not accepted"):
            change(users, "roles", roles=["reviewer"], pin="00000000")
    credential = PINCredential.objects.get(user=users["manager"])
    assert credential.locked_until > timezone.now()
    with pytest.raises(ValidationError, match="temporarily locked"):
        change(users, "roles", roles=["reviewer"])
    assert fresh(users["member"]).management_revision == 1
    assert set(users["member"].groups.values_list("name", flat=True)) == {"analyst"}
    assert not ElectronicSignature.objects.exists()
    assert AuditEvent.objects.filter(action="signature.denied").count() == 6
    assert_secret_free(users)


def test_http_account_signature_binds_entered_username(users):
    client = Client()
    client.force_login(users["manager"])
    url = reverse("accounts:user_action", args=[users["member"].pk, "roles"])
    payload = {"revision": 1, "pin": PIN, "reason": "Independent review", "roles": ["reviewer"]}
    for username in ("", users["root"].username):
        response = client.post(url, {**payload, "signature_username": username})
        assert response.status_code == 422
        assert not ElectronicSignature.objects.exists()
    response = client.post(url, {**payload, "signature_username": users["manager"].username})
    assert response.status_code == 302
    signature = assert_signed(fresh(users["member"]), "account.roles")
    assert signature.authentication_context["channel"] == "web"
    assert signature.authentication_context["components"] == ["username", "pin"]
    assert PINCredential.objects.get(user=users["manager"]).failures == 0


def test_stale_revision_refuses_without_changing_target_or_creating_signature(users):
    changed = change(users, "identity", first_name="Updated", last_name="Member", email="")
    before = admin.safe_snapshot(changed)
    with pytest.raises(ValidationError, match="Account changed"):
        change(users, "roles", expected_revision=1, roles=["quality"])
    assert admin.safe_snapshot(fresh(changed)) == before
    assert ElectronicSignature.objects.count() == 1


@pytest.mark.parametrize("action", ["roles", "deactivate", "reenroll_pin", "reset_password"])
def test_signature_failure_rolls_back_account_credentials_roles_and_audit(
    users, monkeypatch, action
):
    before = admin.safe_snapshot(users["member"])
    old_password = users["member"].password
    old_pin = PINCredential.objects.get(user=users["member"]).encoded

    def fail(**kwargs):
        raise RuntimeError("Synthetic signature storage failure")

    monkeypatch.setattr(ElectronicSignature.objects, "create", fail)
    options = {"roles": ["quality"]} if action == "roles" else {}
    if action == "reset_password":
        options["temporary_password"] = REPLACEMENT
    with pytest.raises(RuntimeError, match="Synthetic signature storage failure"):
        change(users, action, **options)
    target = fresh(users["member"])
    assert admin.safe_snapshot(target) == before
    assert target.password == old_password
    assert PINCredential.objects.get(user=target).encoded == old_pin
    assert not AuditEvent.objects.filter(action=f"account.{action}").exists()
    assert not ElectronicSignature.objects.exists()


def test_signature_failure_rolls_back_new_account(users, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("Synthetic signature storage failure")

    monkeypatch.setattr(ElectronicSignature.objects, "create", fail)
    with pytest.raises(RuntimeError):
        create(users)
    assert not get_user_model().objects.filter(username="new-member").exists()
    assert not AuditEvent.objects.filter(action="account.created").exists()


@pytest.mark.parametrize("api", ["signed", "cli"])
def test_self_role_addition_forbidden_even_for_existing_admin(users, api):
    actor = users["manager"]
    with pytest.raises(PermissionDenied, match="yourself additional roles"):
        if api == "signed":
            change(users, "roles", actor=actor, user=actor, roles=["admin", "quality"])
        else:
            assign_roles(actor=actor, user=actor, roles=["admin", "quality"], reason="Escalate")
    assert set(actor.groups.values_list("name", flat=True)) == {"admin"}
    assert fresh(actor).management_revision == 1


@pytest.mark.parametrize("action", ["roles", "deactivate", "cli_roles"])
def test_last_active_admin_cannot_be_removed(users, action):
    actor = users["manager"]
    # An inactive administrator does not satisfy the safety predicate.
    users["member"].groups.add(Group.objects.get(name="admin"))
    get_user_model().objects.filter(pk=users["member"].pk).update(is_active=False)
    with pytest.raises(ValidationError, match="at least one active"):
        if action == "cli_roles":
            assign_roles(actor=users["root"], user=actor, roles=[], reason="Remove last admin")
        else:
            change(
                users,
                action,
                actor=actor,
                user=actor,
                **({"roles": []} if action == "roles" else {}),
            )
    assert fresh(actor).is_active
    assert actor.groups.filter(name="admin").exists()


def test_cli_bootstrap_exception_is_narrow(users):
    root = users["root"]
    with pytest.raises(PermissionDenied):
        assign_roles(actor=root, user=root, roles=["admin"], reason="Admin already exists")
    get_user_model().objects.filter(pk=users["manager"].pk).update(is_active=False)
    with pytest.raises(PermissionDenied):
        assign_roles(actor=root, user=root, roles=["admin", "quality"], reason="Too broad")
    bootstrapped = assign_roles(actor=root, user=root, roles=["admin"], reason="Initial bootstrap")
    assert set(bootstrapped.groups.values_list("name", flat=True)) == {"admin"}
    with pytest.raises(PermissionDenied):
        assign_roles(
            actor=bootstrapped, user=bootstrapped, roles=["admin", "quality"], reason="Escalate"
        )


@pytest.mark.parametrize("action", ["roles", "deactivate"])
def test_concurrent_different_target_removals_preserve_one_active_admin(users, action):
    """Both requests start with two admins; serializing only each target row is insufficient."""
    second = users["member"]
    second.groups.set([Group.objects.get(name="admin")])
    barrier = Barrier(2)

    def worker(pk):
        close_old_connections()
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
            actor = get_user_model().objects.get(pk=pk)
            barrier.wait(timeout=10)
            try:
                admin.change_account(
                    actor=actor,
                    user=actor,
                    expected_revision=1,
                    action=action,
                    pin=PIN,
                    reason="Concurrent removal",
                    **({"roles": []} if action == "roles" else {}),
                )
                return "changed"
            except ValidationError as exc:
                assert "at least one active" in str(exc)
                return "last-admin-refused"
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, user.pk) for user in (users["manager"], second)]
        outcomes = [future.result(timeout=20) for future in futures]
    assert sorted(outcomes) == ["changed", "last-admin-refused"]
    assert get_user_model().objects.filter(is_active=True, groups__name="admin").count() == 1
    assert ElectronicSignature.objects.count() == 1


def test_all_lifecycle_actions_preserve_signed_safe_evidence(users):
    target = change(
        users, "identity", first_name="Renamed", last_name="Member", email="m@example.invalid"
    )
    assert target.first_name == "Renamed"
    assert_signed(target, "account.identity")
    target = change(users, "roles", roles=["reviewer", "auditor"])
    assert set(target.groups.values_list("name", flat=True)) == {"reviewer", "auditor"}
    assert_signed(target, "account.roles")
    target = change(users, "deactivate")
    assert not target.is_active
    assert_signed(target, "account.deactivate")
    target = change(users, "reactivate")
    assert target.is_active
    assert_signed(target, "account.reactivate")
    credential = PINCredential.objects.get(user=target)
    original_pin_hash = credential.encoded
    credential.failures = 3
    credential.locked_until = timezone.now() + timedelta(minutes=15)
    credential.save()
    target = change(users, "unlock_pin")
    credential.refresh_from_db()
    assert credential.failures == 0 and credential.locked_until is None
    assert credential.encoded == original_pin_hash
    assert_signed(target, "account.unlock_pin")
    target = change(users, "reenroll_pin")
    assert not PINCredential.objects.filter(user=target).exists()
    assert_signed(target, "account.reenroll_pin")
    target = change(users, "reset_password", temporary_password=REPLACEMENT)
    assert target.password_change_required and target.check_password(REPLACEMENT)
    assert not target.check_password(PASSWORD)
    assert_signed(target, "account.reset_password")
    assert target.management_revision == 8 and target.session_epoch == 8
    assert_secret_free(users, extra_secrets=[original_pin_hash])


@pytest.mark.parametrize(
    "action", ["roles", "identity", "unlock_pin", "reenroll_pin", "deactivate_reactivate"]
)
def test_account_security_changes_invalidate_existing_sessions(users, action):
    client = Client()
    client.force_login(users["member"])
    assert client.get(reverse("quality:lot_list")).status_code == 200
    if action == "deactivate_reactivate":
        change(users, "deactivate")
        change(users, "reactivate")  # no request while inactive; old session must not revive
    else:
        options = {"roles": ["analyst"]} if action == "roles" else {}
        if action == "identity":
            options = {"first_name": "Changed", "last_name": "Member", "email": ""}
        change(users, action, **options)
    response = client.get(reverse("quality:lot_list"))
    assert response.status_code == 302 and reverse("login") in response.url
    assert "_auth_user_id" not in client.session


def test_forced_password_change_blocks_lab_and_retains_only_current_session(users):
    old = Client()
    old.force_login(users["member"])
    change(users, "reset_password", temporary_password=REPLACEMENT)
    assert reverse("login") in old.get(reverse("quality:lot_list")).url
    current, other = Client(), Client()
    for client in (current, other):
        assert client.login(username="member", password=REPLACEMENT)
        response = client.get(reverse("quality:lot_list"))
        assert response.status_code == 302
        assert response.url == reverse("accounts:password_change")
        assert client.get(reverse("accounts:password_change")).status_code == 200
    target = fresh(users["member"])
    before = target.management_revision
    new_password = "Synthetic-owner-selected-password-382!"
    payload = {
        "current_password": "wrong",
        "password": new_password,
        "password_confirmation": new_password,
        "reason": "Replace initial credential",
    }
    url = reverse("accounts:password_change")
    assert current.post(url, payload).status_code == 422
    assert fresh(target).management_revision == before
    response = current.post(url, {**payload, "current_password": REPLACEMENT})
    assert response.status_code == 302 and response.url == reverse("quality:lot_list")
    target = fresh(target)
    assert not target.password_change_required and target.check_password(new_password)
    assert current.get(reverse("quality:lot_list")).status_code == 200
    assert int(current.session["_auth_user_id"]) == target.pk
    assert current.session["account_epoch"] == target.session_epoch
    assert reverse("login") in other.get(reverse("quality:lot_list")).url
    assert "_auth_user_id" not in other.session
    assert (
        AuditEvent.objects.filter(
            action="account.password_changed", object_id=str(target.pk)
        ).count()
        == 1
    )
    assert_secret_free(users, extra_secrets=[new_password])


@pytest.mark.parametrize("security_change", ["epoch", "forced_change"])
def test_http_signing_rechecks_midflight_security_change(users, monkeypatch, security_change):
    """Middleware admission cannot authorize a later signature after signer security changes."""
    client = Client()
    client.force_login(users["manager"])
    verify = admin.verify_pin

    def revoke_after_pin(actor, pin):
        encoded = verify(actor, pin)
        fields = (
            {"session_epoch": fresh(actor).session_epoch + 1}
            if security_change == "epoch"
            else {"password_change_required": True}
        )
        get_user_model().objects.filter(pk=actor.pk).update(**fields)
        return encoded

    monkeypatch.setattr(admin, "verify_pin", revoke_after_pin)
    response = client.post(
        reverse("accounts:user_action", args=[users["member"].pk, "roles"]),
        {
            "revision": 1,
            "pin": PIN,
            "signature_username": "manager",
            "roles": ["quality"],
            "reason": "Decision interrupted by signer security change",
        },
    )
    assert response.status_code == 422
    assert fresh(users["member"]).management_revision == 1
    assert set(users["member"].groups.values_list("name", flat=True)) == {"analyst"}
    assert not ElectronicSignature.objects.exists()
    assert not AuditEvent.objects.filter(action="account.roles").exists()
    assert PINCredential.objects.get(user=users["manager"]).failures == 0


@pytest.mark.parametrize("action", ["identity", "roles", "reset_password", "reenroll_pin"])
def test_signed_self_security_change_commits_then_logs_out(users, action):
    """The signature authorizes its own revocation using the locked pre-change signer state."""
    users["member"].groups.add(Group.objects.get(name="admin"))
    client = Client()
    client.force_login(users["manager"])
    payload = {
        "revision": 1,
        "pin": PIN,
        "signature_username": "manager",
        "reason": "Authorized self security change",
    }
    if action == "identity":
        payload.update(first_name="Changed", last_name="Manager", email="self@example.invalid")
    elif action == "roles":
        payload["roles"] = []  # another active admin remains
    elif action == "reset_password":
        payload.update(temporary_password=REPLACEMENT, password_confirmation=REPLACEMENT)
    response = client.post(
        reverse("accounts:user_action", args=[users["manager"].pk, action]), payload
    )
    assert response.status_code == 302 and response.url == reverse("login")
    assert "_auth_user_id" not in client.session
    target = fresh(users["manager"])
    assert target.management_revision == 2 and target.session_epoch == 2
    signature = assert_signed(target, f"account.{action}")
    assert signature.signer_id == target.pk
    assert signature.authentication_context["channel"] == "web"
    if action == "identity":
        assert target.first_name == "Changed"
        assert target.email == "self@example.invalid"
    elif action == "roles":
        assert not target.groups.exists()
        assert users["member"].groups.filter(name="admin").exists()
    elif action == "reset_password":
        assert target.password_change_required and target.check_password(REPLACEMENT)
    elif action == "reenroll_pin":
        assert not PINCredential.objects.filter(user=target).exists()
    assert_secret_free(users)
