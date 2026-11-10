from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import record_event
from core.services import require_role, sign_transition, validate_rules

from .models import Lot, Result, Sample


def effective_rules(rules):
    validate_rules(rules)
    required = rules.policy["required_tests"]
    return required


@transaction.atomic
def receive_lot(*, actor, number, material, rules, reason):
    require_role(actor, "analyst")
    effective_rules(rules)
    lot = Lot.objects.create(number=number, material=material, rules=rules, created_by=actor)
    record_event(
        actor=actor,
        action="lot.received",
        obj=lot,
        reason=reason,
        after={"number": number, "material": material, "rules": rules.pk},
    )
    return lot


@transaction.atomic
def add_sample(*, actor, lot, reference, collected_at, reason):
    require_role(actor, "analyst")
    lot = Lot.objects.select_for_update().get(pk=lot.pk)
    if lot.state != "quarantine":
        raise ValidationError("Only quarantined lots accept new samples.")
    sample = Sample.objects.create(
        lot=lot, reference=reference, collected_at=collected_at, created_by=actor
    )
    lot.revision += 1
    lot.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="sample.collected",
        obj=sample,
        reason=reason,
        after={"lot": lot.pk, "reference": reference, "collected_at": collected_at.isoformat()},
    )
    return sample


@transaction.atomic
def record_result(*, actor, sample, reason, **values):
    require_role(actor, "analyst")
    lot = Lot.objects.select_for_update().get(pk=sample.lot_id)
    if lot.state != "quarantine":
        raise ValidationError("Only quarantined lots accept results.")
    if values["test_code"] not in effective_rules(lot.rules):
        raise ValidationError("Test is not required by this lot's rule set.")
    result = Result(sample=sample, analyst=actor, **values)
    result.full_clean()
    result.save()
    lot.revision += 1
    lot.save(update_fields=["revision"])
    record_event(
        actor=actor,
        action="result.recorded",
        obj=result,
        reason=reason,
        after={"sample": sample.pk, **{k: str(v) for k, v in values.items()}},
    )
    return result


def review_result(*, actor, pin, result, expected_revision, reason):
    def apply(locked):
        lot = Lot.objects.select_for_update().get(pk=locked.sample.lot_id)
        if lot.state != "quarantine" or locked.state != "recorded":
            raise ValidationError("This result is not awaiting review.")
        if locked.analyst_id == actor.pk:
            raise ValidationError("You cannot review your own result.")
        if not locked.conforms:
            raise ValidationError("Out-of-specification result: investigation is required.")
        effective_rules(lot.rules)
        locked.state = "reviewed"
        lot.revision += 1
        lot.save(update_fields=["revision"])

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=result,
        expected_revision=expected_revision,
        meaning="reviewed",
        reason=reason,
        permission="reviewer",
        apply=apply,
    )


def dispose_lot(*, actor, pin, lot, expected_revision, reason):
    def apply(locked):
        if locked.state != "quarantine":
            raise ValidationError("This lot has already been dispositioned.")
        required = set(effective_rules(locked.rules))
        samples = list(locked.samples.all())
        if not samples:
            raise ValidationError("The lot requires a sample and reviewed results.")
        for sample in samples:
            results = list(sample.results.all())
            if not required.issubset({r.test_code for r in results}):
                raise ValidationError("Required tests are missing.")
            if any(r.analyst_id == actor.pk for r in results):
                raise ValidationError("You cannot disposition a lot containing your own results.")
            if any(r.state != "reviewed" or not r.conforms for r in results):
                raise ValidationError("All results must conform and have independent review.")
        locked.state = "released"

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=lot,
        expected_revision=expected_revision,
        meaning="approved",
        reason=reason,
        permission="quality",
        apply=apply,
    )
