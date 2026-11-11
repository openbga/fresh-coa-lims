from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.debug import sensitive_variables

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
    # Signing locks the actor before the lot; serialize here before taking any record lock.
    # NO KEY UPDATE stays compatible with deferred foreign-key checks on this account.
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)
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
    if not settings.DEBUG or lot.qc_assignments.exists():
        raise ValidationError("Record observations through approved native testing requirements.")
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


@sensitive_variables("pin")
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


SELF_DISPOSITION = "You cannot disposition a lot containing your own sampling or test data."


def disposition_authors(lot):
    """Everyone who authored the lot's sampling or test data; none may sign its disposition.

    Analytical authors (observations including corrected originals, submitters, batch QC,
    investigations), samplers and recorders of every sampling record including corrected
    originals and intermediate corrections, and foundation result analysts. Holding several
    roles never waives this.
    """
    from analytical.gates import lot_author_ids as analytical_author_ids
    from sampling.services import lot_author_ids as sampling_author_ids

    return (
        analytical_author_ids(lot)
        | sampling_author_ids(lot)
        | set(Result.objects.filter(sample__lot=lot).values_list("analyst_id", flat=True))
    )


def disposition_denial(actor, lot):
    """Read-only preflight shown before any PIN is requested; signing repeats it under lock."""
    return SELF_DISPOSITION if actor.pk in disposition_authors(lot) else ""


@sensitive_variables("pin")
def dispose_lot(*, actor, pin, lot, expected_revision, reason):
    def apply(locked):
        if locked.state != "quarantine":
            raise ValidationError("This lot has already been dispositioned.")
        from stability.gates import lot_blockers as hold_blockers

        if problems := hold_blockers(locked):
            raise ValidationError(problems)
        required = set(effective_rules(locked.rules))
        from analytical.gates import lot_blockers, lot_evidence
        from analytical.models import AnalyticalTest
        from sampling.services import current_assignment, current_requirements
        from sampling.services import lot_blockers as sampling_blockers

        assignment = current_assignment(locked)
        native = assignment is not None or AnalyticalTest.objects.filter(lot=locked).exists()
        if native or not settings.DEBUG:
            current_requirements(locked)  # missing or held applicability is a hard stop
            if not locked.samples.exists():
                raise ValidationError("The lot requires a sampled and tested record.")
            problems = sampling_blockers(locked) + lot_blockers(locked)
            if problems:
                raise ValidationError(problems)
            if actor.pk in disposition_authors(locked):
                raise ValidationError(SELF_DISPOSITION)
            if Result.objects.filter(sample__lot=locked).exists():
                raise ValidationError(
                    "Mixed foundation and native evidence requires reconciliation."
                )
            locked.disposition_evidence = {
                "assignment_id": assignment.pk,
                "assignment_hash": assignment.payload_hash,
                "analytical": lot_evidence(locked),
            }
            locked.state = "released"
            return
        samples = list(locked.samples.all())
        if not samples:
            raise ValidationError("The lot requires a sample and reviewed results.")
        for sample in samples:
            results = list(sample.results.all())
            if not required.issubset({r.test_code for r in results}):
                raise ValidationError("Required tests are missing.")
            if any(r.analyst_id == actor.pk for r in results):
                raise ValidationError(SELF_DISPOSITION)
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
