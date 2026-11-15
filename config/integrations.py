"""Explicit adapters between approved catalog evidence and laboratory execution contracts."""

from django.core.exceptions import ValidationError

from analytical.contracts import RequirementHold, parse_method, parse_requirement
from catalog.services import ApplicabilityHold, batch_method_requirements
from sampling.services import require_additional_rules, test_requirements


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

    def require_additional_rules(self, lot):
        """Refuse while a rule set version that applies to the lot in addition to its own is
        no longer in force (testing checks the lot's own rule set itself)."""
        require_additional_rules(lot)

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

    A result reported by a contract laboratory takes the other door: the laboratory needs a signed
    approval for the method that covers the date of its report.
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

    # A result reported by a contract laboratory is checked against that laboratory's approval
    # for the method instead of the analyst and the selected resources.

    def contract_choices(self, method_code):
        from laboratory.contract import contract_choices

        return contract_choices(method_code)

    def authorize_contract(
        self,
        *,
        actor,
        laboratory_id,
        method_code,
        test_code,
        context_type,
        context_id,
        report_number,
        report_date,
    ):
        from analytical.contracts import WorkRefused
        from laboratory.contract import ContractBlocked, use_contract_report

        try:
            return use_contract_report(
                actor=actor,
                laboratory_id=laboratory_id,
                method_code=method_code,
                context_type=context_type,
                context_id=context_id,
                report_number=report_number,
                report_date=report_date,
                test_code=test_code,
            )
        except ContractBlocked as exc:
            raise WorkRefused(
                [{"subject": exc.finding.subject, "reasons": list(exc.finding.reasons)}]
            ) from exc

    def record_contract_refusal(
        self,
        *,
        actor,
        laboratory_id,
        method_code,
        test_code,
        context_type,
        context_id,
        report_number,
        report_date,
        refusals,
        reason,
    ):
        from laboratory.contract import record_blocked_contract

        record_blocked_contract(
            actor=actor,
            laboratory_id=laboratory_id,
            method_code=method_code,
            context_type=context_type,
            context_id=context_id,
            report_number=report_number,
            report_date=report_date,
            refusals=refusals,
            reason=reason,
        )

    def contract_notice(self, evidence):
        from laboratory.contract import reliance_notice

        return reliance_notice(evidence)


class AcceptedSupplierResults:
    """Supplier certificate results accepted in place of a test, read from the lot record.

    Testing never imports the lot's supplier records: the gate asks here which requirements a
    signed acceptance answers, and result entry asks which requirements a proposal or an
    acceptance currently stands for.
    """

    def lot(self, lot):
        from quality.reliance import lot_reliance

        return lot_reliance(lot)

    def standing(self, lot):
        from quality.reliance import standing_codes

        return standing_codes(lot)

    def standing_by_lot(self, lot_ids):
        from quality.reliance import standing_by_lot

        return standing_by_lot(lot_ids)


class TestingUnderReplacement:
    """What replacing a lot's requirements during testing does to the lot's tests.

    The sampling module owns the lot's requirements and never imports testing: it asks here
    which tests carry over and which are superseded, why testing refuses the replacement, and
    has the tests locked and superseded inside the signed transaction. ``requirements`` is
    ``{test_code: payload}`` as testing would receive it for the new requirements.
    """

    def effects(self, lot, requirements):
        """``{"refusals": [...], "tests": [...], "supplier_results": [...]}``, read-only."""
        from analytical import replacement
        from analytical.contracts import supplier_standing

        reasons = replacement.held(requirements)
        rows = replacement.effects(lot, requirements)
        standing = supplier_standing(lot)
        return {
            "refusals": reasons + replacement.refusals(lot, rows),
            "tests": rows,
            "supplier_results": [
                {"test_code": code, "label": standing[code]} for code in sorted(standing)
            ],
        }

    def lock(self, lot):
        from analytical import replacement

        return replacement.lock(lot)

    def apply(self, *, actor, lot, requirements, reason, locked):
        from analytical import replacement

        if reasons := replacement.held(requirements):
            raise ValidationError(reasons)
        return replacement.apply(
            actor=actor, lot=lot, requirements=requirements, reason=reason, locked=locked
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
