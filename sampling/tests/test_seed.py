"""Five synthetic segment profiles: drafts only, idempotent, and coherent once approved."""

import pytest
from django.core.management import call_command

from catalog.models import MethodRevision, SpecificationRevision
from catalog.services import resolve_requirements
from catalog.tests.factories import approve, approved_rules
from core.models import ElectronicSignature
from sampling.models import SamplingPlanRevision

pytestmark = pytest.mark.django_db(transaction=True)
MODELS = (MethodRevision, SpecificationRevision, SamplingPlanRevision)


def test_profiles_are_drafts_idempotent_and_resolve_after_independent_approval(people):
    call_command("seed_qc_profiles", actor=people["author"].username)
    call_command("seed_qc_profiles", actor=people["author"].username)
    specs = SpecificationRevision.objects.select_related("specification__material")
    assert specs.count() == 5
    assert SamplingPlanRevision.objects.count() == 5
    assert all(r.status == "draft" for model in MODELS for r in model.objects.all())
    assert not ElectronicSignature.objects.exists()
    for model in MODELS:
        for revision in model.objects.all():
            approve(revision, people["approver"])
    rules = approved_rules(people["author"])
    for revision in specs:
        spec = revision.specification
        payload = resolve_requirements(
            material=spec.material, stage=spec.stage, scope=spec.scope, rules=rules
        )
        assert {t["code"] for t in payload["tests"]} >= {"identity"}
        assert len(payload["tests"]) == 3


def test_seed_refuses_collisions_with_unrelated_records(people):
    from django.core.management.base import CommandError

    from catalog import services
    from catalog.models import Material
    from catalog.tests.factories import window

    start, end = window()
    services.create_method(
        actor=people["author"],
        code="hplc-assay",
        title="Unrelated real method",
        technique="HPLC",
        document_ref="SOP-X",
        suitability_kind="validation",
        suitability_ref="VAL-X",
        effective_from=start,
        effective_until=end,
        reason="Lab method",
    )
    services.create_material(
        actor=people["author"], code="syn-solvent", name="Other", kind="raw_material", reason="x"
    )
    with pytest.raises(CommandError) as caught:
        call_command("seed_qc_profiles", actor=people["author"].username)
    assert "method hplc-assay" in str(caught.value) and "material syn-solvent" in str(caught.value)
    assert "Nothing was created" in str(caught.value)
    assert Material.objects.count() == 1
    assert not SpecificationRevision.objects.exists()
