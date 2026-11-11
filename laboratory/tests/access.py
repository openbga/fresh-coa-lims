"""Shared helpers for the Admin role boundary tests (laboratory and stability).

Admin may read every read-only page but holds no scientific authority: an Admin-only account is
refused on every mutation or signing page and cannot POST, while Admin plus a laboratory role has
exactly that role's authority and the independence rules still apply.
"""

from django.contrib.auth.models import Group
from django.db.models import Model
from django.urls import reverse

from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin

from .helpers import PASSWORD, PIN


def make_user(django_user_model, name, roles):
    user = django_user_model.objects.create_user(name, password=PASSWORD)
    user.groups.add(*[Group.objects.get_or_create(name=role)[0] for role in roles])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def route_names(module):
    """Every named route of an app's URLconf, as namespace:name."""
    return {f"{module.app_name}:{pattern.name}" for pattern in module.urlpatterns}


def row_counts(models):
    tracked = [*models, AuditEvent, ElectronicSignature]
    return {model._meta.label: model.objects.count() for model in tracked}


def state_snapshot(models):
    """Every tracked row, so a refused POST is shown to change nothing."""
    snapshot = {}
    for model in [*models, AuditEvent, ElectronicSignature]:
        snapshot[model._meta.label] = sorted(
            tuple(sorted((k, str(v)) for k, v in row.items())) for row in model.objects.values()
        )
    return snapshot


# A non-empty body binds the form: an authorized POST is a validation error (422), not a redisplay.
PROBE = {"probe": "1"}


def _path(name, args):
    return reverse(name, args=args)


def check_boundary(client, *, reads, mutations, users, admin_only, tracked: list[type[Model]]):
    """`reads`/`mutations`: lists of (route, args, authorized user key). Raises AssertionError."""
    # Authorized users get every mutation page, so the fixtures are valid targets (a refusal for
    # a missing or wrong-state record cannot masquerade as the role denial).
    for name, args, who in mutations:
        client.force_login(users[who])
        response = client.get(_path(name, args))
        assert response.status_code == 200, (name, args, who, response.status_code)
        posted = client.post(_path(name, args), PROBE)
        assert posted.status_code == 422, (name, "authorized empty POST", posted.status_code)
    before = state_snapshot(tracked)
    client.force_login(admin_only)
    for name, args, _ in mutations:
        url = _path(name, args)
        assert client.get(url).status_code == 403, (name, "admin-only GET")
        assert client.post(url, PROBE).status_code == 403, (name, "admin-only POST")
        assert client.post(url, {"reason": "Admin attempt", "pin": PIN}).status_code == 403, name
    assert state_snapshot(tracked) == before
    # Read pages render for Admin and expose no mutation or signing link.
    mutation_paths = [_path(name, args) for name, args, _ in mutations]
    for name, args, _ in reads:
        response = client.get(_path(name, args))
        assert response.status_code == 200, (name, "admin read", response.status_code)
        html = response.content.decode()
        for path in mutation_paths:
            assert f'href="{path}' not in html, (name, "shows", path)
