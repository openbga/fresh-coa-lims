from io import StringIO

import pytest
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError

from catalog.models import Material, MethodRevision, SpecificationRevision
from catalog.services import create_material
from core.models import AuditEvent, ElectronicSignature, PINCredential, RuleSet
from quality.models import Lot, Result, Sample
from sampling.models import SamplingPlanRevision

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-seed-password-2026!"
PIN = "84621357"


@pytest.fixture
def demo_env(settings, monkeypatch, django_user_model):
    settings.DEBUG = True
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    monkeypatch.setenv("DEMO_PIN", PIN)
    return django_user_model.objects.create_user("bootstrap", is_superuser=True)


def test_demo_uses_services_and_is_idempotent(demo_env, django_user_model, monkeypatch):
    output = StringIO()
    warnings = StringIO()
    call_command("seed_demo", actor=demo_env.username, journey=True, stdout=output, stderr=warnings)
    assert "no admin laboratory role" in warnings.getvalue()
    assert "assign_roles bootstrap admin --actor bootstrap --reason" in warnings.getvalue()
    assert "replaces the complete role set" in warnings.getvalue()
    assert not demo_env.groups.exists()  # Seeding never grants its actor implicit authority.
    assert PASSWORD not in warnings.getvalue() and PIN not in warnings.getvalue()
    assert PASSWORD not in output.getvalue() and PIN not in output.getvalue()
    assert django_user_model.objects.filter(username__startswith="demo_").count() == 6
    hashes = {}
    for user in django_user_model.objects.filter(username__startswith="demo_"):
        credential = PINCredential.objects.get(user=user)
        assert user.check_password(PASSWORD)
        assert credential.encoded != PIN and check_password(PIN, credential.encoded)
        hashes[user.pk] = (user.password, credential.encoded)
    assert RuleSet.objects.filter(status="draft").count() == 4
    assert set(RuleSet.objects.values_list("author__username", flat=True)) == {"demo_config_author"}
    assert list(
        django_user_model.objects.get(username="demo_admin").groups.values_list("name", flat=True)
    ) == ["admin"]
    assert RuleSet.objects.get(code="chemical").status == "approved"
    signature = ElectronicSignature.objects.get()
    assert signature.signer.username == "demo_quality"
    assert signature.meaning == "approved" and signature.audit_event_id
    assert Result.objects.get().state == "recorded"
    assert Lot.objects.get().state == "quarantine"
    quality_user = django_user_model.objects.get(username="demo_quality")
    unrelated = create_material(
        actor=quality_user,
        code="unrelated-existing",
        name="Unrelated synthetic material",
        kind="raw_material",
        reason="Existing unrelated configuration",
    )
    unrelated_before = Material.objects.filter(pk=unrelated.pk).values().get()
    profile_counts = (
        MethodRevision.objects.count(),
        SpecificationRevision.objects.count(),
        SamplingPlanRevision.objects.count(),
    )
    before = AuditEvent.objects.count()
    monkeypatch.setenv("DEMO_PASSWORD", "Changed-input-must-not-reset-2026!")
    monkeypatch.setenv("DEMO_PIN", "99999999")
    call_command("seed_demo", actor=demo_env.username, journey=True, stdout=StringIO())
    assert AuditEvent.objects.count() == before
    assert Material.objects.filter(pk=unrelated.pk).values().get() == unrelated_before
    assert profile_counts == (
        MethodRevision.objects.count(),
        SpecificationRevision.objects.count(),
        SamplingPlanRevision.objects.count(),
    )
    assert (Lot.objects.count(), Sample.objects.count(), Result.objects.count()) == (1, 1, 1)
    for user in django_user_model.objects.filter(username__startswith="demo_"):
        assert hashes[user.pk] == (user.password, PINCredential.objects.get(user=user).encoded)


def test_demo_refuses_production_and_non_demo_accounts(demo_env, settings, django_user_model):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo", actor=demo_env.username)
    settings.DEBUG = True
    collision = django_user_model.objects.create_user("demo_quality", password=PASSWORD)
    with pytest.raises(CommandError, match="non-demo account"):
        call_command("seed_demo", actor=demo_env.username)
    assert django_user_model.objects.count() == 2
    collision.refresh_from_db()
    assert collision.check_password(PASSWORD)
    assert not AuditEvent.objects.exists()


def test_demo_default_keeps_all_presets_draft_and_rejects_bad_pin(demo_env, monkeypatch):
    monkeypatch.setenv("DEMO_PIN", "123")
    with pytest.raises(CommandError, match="8–32"):
        call_command("seed_demo", actor=demo_env.username)
    assert not AuditEvent.objects.exists()
    monkeypatch.setenv("DEMO_PIN", PIN)
    from django.contrib.auth.models import Group

    demo_env.groups.add(Group.objects.get_or_create(name="admin")[0])
    warnings = StringIO()
    call_command("seed_demo", actor=demo_env.username, stdout=StringIO(), stderr=warnings)
    assert not warnings.getvalue()
    assert RuleSet.objects.filter(status="draft").count() == 5
    assert not ElectronicSignature.objects.exists()
    assert not Lot.objects.exists()
    assert Material.objects.count() == SpecificationRevision.objects.count() == 5
    assert SamplingPlanRevision.objects.count() == 5
    assert MethodRevision.objects.count() > 0
    for model in (MethodRevision, SpecificationRevision, SamplingPlanRevision):
        assert not model.objects.exclude(status="draft").exists()
        assert set(model.objects.values_list("author__username", flat=True)) == {
            "demo_config_author"
        }


def test_legacy_demo_rule_author_is_preserved_without_admin_role_escalation(
    demo_env, django_user_model
):
    """Keep historical seeded revisions while new rule creation requires quality."""
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from accounts.services import provision_account
    from core.audit import record_event, snapshot
    from core.management.commands.seed_demo import MARKER
    from core.management.commands.seed_rules import SEED_REASON
    from core.services import set_pin

    admin = provision_account(
        actor=demo_env,
        username="demo_admin",
        password=PASSWORD,
        first_name="Synthetic",
        last_name="Admin",
        roles=["admin"],
        reason=MARKER,
    )
    set_pin(actor=admin, password=PASSWORD, pin=PIN)
    # Simulate the persisted older seed format; current services correctly prohibit its creation.
    with transaction.atomic():
        old = RuleSet.objects.create(
            code="chemical",
            segment="chemical",
            author=admin,
            effective_from=timezone.now(),
            effective_until=timezone.now() + timedelta(days=365),
            policy={
                "required_tests": ["identity"],
                "review_meaning": "reviewed",
                "disposition_meaning": "approved",
            },
        )
        event = record_event(
            actor=admin, action="rule.created", obj=old, after=snapshot(old), reason=SEED_REASON
        )
    previous = snapshot(old)
    credential = admin.password
    call_command("seed_demo", actor=demo_env.username, stdout=StringIO(), stderr=StringIO())
    old.refresh_from_db()
    admin.refresh_from_db()
    assert snapshot(old) == previous
    assert AuditEvent.objects.get(pk=event.pk).after == previous
    assert list(admin.groups.values_list("name", flat=True)) == ["admin"]
    assert admin.password == credential
    assert set(RuleSet.objects.exclude(pk=old.pk).values_list("author__username", flat=True)) == {
        "demo_config_author"
    }
    before = AuditEvent.objects.count()
    call_command("seed_demo", actor=demo_env.username, stdout=StringIO(), stderr=StringIO())
    assert AuditEvent.objects.count() == before
