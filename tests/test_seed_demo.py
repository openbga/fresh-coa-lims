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
    call_command("seed_demo", actor=demo_env.username, journey=True, stdout=output)
    assert PASSWORD not in output.getvalue() and PIN not in output.getvalue()
    assert django_user_model.objects.filter(username__startswith="demo_").count() == 5
    hashes = {}
    for user in django_user_model.objects.filter(username__startswith="demo_"):
        credential = PINCredential.objects.get(user=user)
        assert user.check_password(PASSWORD)
        assert credential.encoded != PIN and check_password(PIN, credential.encoded)
        hashes[user.pk] = (user.password, credential.encoded)
    assert RuleSet.objects.filter(status="draft").count() == 4
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
    call_command("seed_demo", actor=demo_env.username, stdout=StringIO())
    assert RuleSet.objects.filter(status="draft").count() == 5
    assert not ElectronicSignature.objects.exists()
    assert not Lot.objects.exists()
    assert Material.objects.count() == SpecificationRevision.objects.count() == 5
    assert SamplingPlanRevision.objects.count() == 5
    assert MethodRevision.objects.count() > 0
    for model in (MethodRevision, SpecificationRevision, SamplingPlanRevision):
        assert not model.objects.exclude(status="draft").exists()
        assert set(model.objects.values_list("author__username", flat=True)) == {"demo_quality"}
