"""Fixtures: one synthetic user per role, each with a signature PIN where signing applies."""

import pytest
from django.contrib.auth.models import Group

from core.services import set_pin

from .helpers import PASSWORD, PIN, ROLES


@pytest.fixture
def people(django_user_model):
    users = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(name, password=PASSWORD)
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        if name not in ("auditor", "admin"):
            set_pin(actor=user, pin=PIN, password=PASSWORD)
        users[name] = user
    return users
