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


class LaboratoryBench:
    """Bench checks for result entry, evaluated by the laboratory module.

    Testing calls this inside the transaction that records an observation or a batch QC result:
    the analyst needs a current approved qualification for the method, and every instrument and
    reagent or standard lot selected must be fit for use. Success records the resource uses and
    returns the evidence relied on; a refusal is audited after the entry has rolled back.
    """

    def choices(self):
        from laboratory.services import bench_choices

        return bench_choices()

    def lock_actor(self, actor):
        from django.db import connection

        from laboratory.services import lock_account

        if not connection.in_atomic_block:
            raise RuntimeError("Bench checks must run inside the result-entry transaction.")
        # The same first lock as signing and every laboratory write, so one person's result
        # entry and signature serialize before either holds a record.
        lock_account(actor)

    def authorize(
        self,
        *,
        actor,
        method_code,
        test_code,
        context_type,
        context_id,
        equipment_ids,
        reagent_ids,
        reason,
    ):
        from analytical.contracts import WorkRefused
        from laboratory.services import UseBlocked, use_in_work

        try:
            return use_in_work(
                actor=actor,
                activity=method_code,
                context_type=context_type,
                context_id=context_id,
                test_code=test_code,
                equipment_ids=equipment_ids,
                reagent_ids=reagent_ids,
                reason=reason,
            )
        except UseBlocked as exc:
            raise WorkRefused(
                [
                    {"subject": finding.subject, "reasons": list(finding.reasons)}
                    for finding in exc.findings
                    if not finding.ok
                ]
            ) from exc

    def record_refusal(
        self, *, actor, method_code, test_code, context_type, context_id, refusals, reason
    ):
        from laboratory.services import record_blocked_use

        record_blocked_use(
            actor=actor,
            activity=method_code,
            context_type=context_type,
            context_id=context_id,
            refusals=refusals,
            reason=reason,
        )


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
