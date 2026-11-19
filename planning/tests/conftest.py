import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from analytical import fixtures
from analytical import services as analytical
from analytical.models import AnalyticalTest
from core.models import RuleSet
from core.services import set_pin
from laboratory.tests.helpers import PASSWORD, PIN
from quality.services import add_sample, receive_lot
from tests.receipts import on_site_receipt

ROLES = {
    "analyst": ["analyst"],
    "analyst2": ["analyst"],
    "reviewer": ["reviewer"],
    "reviewer2": ["reviewer"],
    "quality": ["quality"],
    "quality2": ["quality"],
    "auditor": ["auditor"],
    "admin": ["admin"],
    "planner_analyst": ["analyst", "reviewer"],
}


@pytest.fixture(autouse=True)
def synthetic_testing(settings):
    """Synthetic requirements and bench are explicit test overrides, never deployment defaults."""
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.fixtures.FixtureProvider"
    settings.ANALYTICAL_BENCH = "analytical.fixtures.SyntheticBench"
    fixtures.BENCH_LOG.clear()
    fixtures.UNQUALIFIED.clear()


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def people(django_user_model):
    users = {}
    for name, roles in ROLES.items():
        user = django_user_model.objects.create_user(
            name, password=PASSWORD, first_name="Synthetic", last_name=name.capitalize()
        )
        user.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        if name not in ("auditor", "admin"):
            set_pin(actor=user, pin=PIN, password=PASSWORD)
        users[name] = user
    return users


def lot_tests(
    people,
    number="SYN-PLAN-1",
    codes=("identity", "water"),
    assigned_at=None,
    material="Synthetic powder",
):
    """A lot with one sample and its tests assigned (at ``assigned_at`` when given): {test code:
    test}."""
    rules = RuleSet.objects.create(
        code=f"rules-{number.lower()}",
        segment="chemical",
        author=people["quality"],
        status="approved",
        effective_from=(assigned_at or timezone.now()) - timedelta(days=1),
        effective_until=timezone.now() + timedelta(days=365),
        policy={
            "required_tests": list(codes),
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
    )
    lot = receive_lot(
        actor=people["analyst"],
        number=number,
        material=material,
        rules=rules,
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    sample = add_sample(
        actor=people["analyst"],
        lot=lot,
        reference=f"{number}-S1",
        collected_at=lot.created_at,
        reason="Synthetic sample",
    )
    with mock.patch("django.utils.timezone.now", return_value=assigned_at or timezone.now()):
        created, holds = analytical.assign_tests(
            actor=people["analyst"], sample=sample, reason="Required tests"
        )
    assert holds == []
    return {t.test_code: t for t in created}


@pytest.fixture
def tests_of_lot(people):
    return lot_tests(people)


def fresh(obj):
    return type(obj).objects.get(pk=obj.pk)


def review_identity(people, test):
    """Record, submit and review the identity test: it takes no more work."""
    analytical.record_observation(
        actor=people["analyst"], test=test, value=Decimal("1.00"), raw_reference="NB-PLAN p1"
    )
    test = fresh(test)
    analytical.submit_test(
        actor=people["analyst"], test=test, expected_revision=test.revision, reason="Complete"
    )
    test = fresh(test)
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Raw data checked",
    )
    test = fresh(test)
    assert test.state == AnalyticalTest.State.REVIEWED
    return test


def login(client, user):
    client.force_login(user)
    session = client.session
    session["authenticated_at"] = session["last_activity_at"] = time.time()
    session.save()
    return client
