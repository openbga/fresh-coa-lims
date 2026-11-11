"""Explicit adapters between approved catalog evidence and laboratory execution contracts."""

from django.core.exceptions import ValidationError

from analytical.contracts import RequirementHold, parse_method, parse_requirement
from catalog.services import ApplicabilityHold, batch_method_requirements
from sampling.services import test_requirements


class CatalogRequirementProvider:
    """Validate the public catalog/sampling translation; never supply execution defaults."""

    def requirements(self, lot):
        try:
            payloads = test_requirements(lot)
        except ApplicabilityHold as exc:
            raise RequirementHold(exc.reasons) from exc
        except (KeyError, TypeError) as exc:
            raise RequirementHold(
                ["Approved requirements lack supported execution policy."]
            ) from exc
        errors = []
        for code, payload in payloads.items():
            try:
                parse_requirement(payload)
            except ValidationError as exc:
                errors.extend(f"{code}: {message}" for message in exc.messages)
        if not payloads:
            errors.append("No required tests in the approved assignment.")
        if errors:
            raise RequirementHold(errors)
        return payloads

    def methods(self):
        result = []
        for payload in batch_method_requirements():
            try:
                parse_method(payload)
            except ValidationError:
                continue
            result.append(payload)
        return result


def require_qualified_analyst(*, actor, test):
    """Native observations require current method-specific authorization evidence."""
    from django.db import connection

    from laboratory.eligibility import analyst_eligibility
    from laboratory.models import Qualification

    if not connection.in_atomic_block:
        raise RuntimeError("Eligibility must be evaluated inside the observation transaction.")
    # Revoke/approve serializes on the same qualification rows; preserve authorization at use.
    list(
        Qualification.objects.select_for_update()
        .filter(user=actor, activity__iexact=test.spec.method.code)
        .order_by("pk")
    )
    finding = analyst_eligibility(actor, test.spec.method.code)
    if not finding.ok:
        raise ValidationError(list(finding.reasons))
    return finding.evidence


def report_holds(lot):
    from stability.gates import lot_hold_evidence

    return [
        {"id": item["hold"], "status": item["state"], "description": item["reason"]}
        for item in lot_hold_evidence(lot)["holds"]
    ]


def report_methods(lot):
    if not lot.disposition_evidence:
        return None
    from reporting.evidence import frozen_assignment_payload

    source = frozen_assignment_payload(lot)
    if source is None:
        return None  # Reporting holds native evidence with a missing/mismatched signed assignment.
    return [test["method"] for test in source["tests"] if test["required"]]
