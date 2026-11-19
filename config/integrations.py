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


def method_resources(method_code, method_revision):
    """The suitable resources the approved method version lists (catalog), as plain lines for
    the laboratory checks; ``[]`` when it lists none or no version is named. The approved content
    never changes, so the answer is the same for the whole life of a test frozen to it. A
    version the catalog does not hold approved, of a method it knows, holds the entry rather
    than accept any resource; a method from another requirement source lists nothing here."""
    from catalog.models import Method, MethodRevision

    if method_revision is None:
        return []
    content = (
        MethodRevision.objects.filter(
            method__code=method_code,
            version=method_revision,
            approved_content__isnull=False,
        )
        .values_list("approved_content", flat=True)
        .first()
    )
    if content is None:
        if not Method.objects.filter(code=method_code).exists():
            return []
        raise ValidationError(
            f"Method {method_code} version {method_revision} is not approved here; results "
            "are held."
        )
    return list(content.get("resources") or [])


class LaboratoryBench:
    """Bench checks for result entry, evaluated by the laboratory module.

    Testing calls this inside the transaction that records an observation or a batch QC result:
    the analyst needs a current approved qualification for the method, and every instrument and
    reagent or standard lot selected must be fit for use. Where the method version the work is
    recorded under lists the instruments, reagents and standards suitable for it, each one
    selected must be one it lists and every required line must be answered. Success records the
    resource uses and returns the evidence relied on; a refusal is audited after the entry has
    rolled back.

    A result reported by a contract laboratory takes the other door: the laboratory needs a signed
    approval for the method that covers the date of its report.
    """

    def choices(self, method_code=None, method_revision=None):
        """What the analyst can select; only what the method version lists, when it lists any."""
        from laboratory.services import bench_choices

        return bench_choices(
            method_resources(method_code, method_revision), activity=method_code or ""
        )

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
        method_revision=None,
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
                suitable=method_resources(method_code, method_revision),
            )
        except UseBlocked as exc:
            raise WorkRefused(
                [
                    {"subject": finding.subject, "reasons": list(finding.reasons)}
                    for finding in exc.findings
                    if not finding.ok
                ]
            ) from exc

    # Readings from balances and meters are taken through the equipment's data connection.

    def connections(self):
        """What the analyst's browser needs to read each connected instrument, by equipment."""
        from laboratory.services import current_connections

        return {pk: c.browser() for pk, c in current_connections().items()}

    def connection(self, connection_id):
        """The evidence of the data connection ``connection_id`` while it is current, else None.
        Locks it, so ending it waits for the reading being taken."""
        from laboratory.models import DeviceConnection

        connection = (
            DeviceConnection.objects.select_for_update(of=("self",))
            .select_related("equipment")
            .filter(pk=connection_id, ended_at__isnull=True)
            .first()
        )
        return connection.evidence() if connection else None

    def current_connections(self, equipment_ids):
        """{equipment id: id of its current data connection}. Called once the result entry
        holds the equipment locks, so no connection changes before the entry commits."""
        from laboratory.services import current_connections

        return {pk: c.pk for pk, c in current_connections(equipment_ids).items()}

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


class StabilityPulls:
    """Stability pulls as the testing module sees them (settings.ANALYTICAL_STABILITY_PULLS).

    A test belongs to the testing of a lot or to a stability pull. For a pull's test the pull
    stands where the lot stands: ``requirements`` are the acceptance criteria of its protocol,
    ``refusal`` says why it takes no more testing, and ``lock`` locks the pulls a transition
    changes, refusing one that takes none (or, with ``refuse`` false, marking it ``closed``),
    so that the transition can advance their revision.
    """

    def requirements(self, pull):
        from stability import testing

        return testing.requirements(pull)

    def refusal(self, pull):
        from stability import testing

        return testing.refusal(pull)

    def lock(self, pull_ids, refuse=True):
        from stability import testing

        return testing.lock(pull_ids, refuse=refuse)


class Reassessments:
    """Reassessments of released lots as the testing module sees them
    (settings.ANALYTICAL_REASSESSMENTS). For a reassessment's test the reassessment stands where
    the lot stands, as a pull does: ``requirements`` are the required tests of the
    specifications in force for the lot, ``refusal`` says why it takes no more testing, and
    ``lock`` locks the reassessments a transition changes (with ``refuse`` false, marking each
    ``closed`` instead of refusing it)."""

    def requirements(self, reassessment):
        from quality import reassessment as module

        return module.requirements(reassessment)

    def refusal(self, reassessment):
        from quality import reassessment as module

        return module.refusal(reassessment)

    def lock(self, reassessment_ids, refuse=True):
        from quality import reassessment as module

        return module.lock(reassessment_ids, refuse=refuse)


class LaboratoryReviewers:
    """Who may review a test's results beyond the reviewer role (settings.ANALYTICAL_REVIEWERS).

    A method version approved with ``requires_review_qualification`` (catalog) asks that whoever
    reviews or returns a result of it holds an approved, current qualification to review that
    method (laboratory). The version is the one the test froze; its approved content never
    changes, so the answer is the same for the test's whole life. ``check`` returns the evidence
    to freeze on the test, ``{}`` where the version asks for nothing, or the reason for refusal.
    """

    def asks(self, *, method_code, method_revision):
        """Whether the approved method version asks for qualified reviewers."""
        from catalog.models import MethodRevision

        content = (
            MethodRevision.objects.filter(
                method__code=method_code,
                version=method_revision,
                approved_content__isnull=False,
            )
            .values_list("approved_content", flat=True)
            .first()
        )
        return bool((content or {}).get("requires_review_qualification"))

    def check(self, *, actor, method_code, method_revision, lock=False):
        from laboratory.services import review_finding

        if not self.asks(method_code=method_code, method_revision=method_revision):
            return {}, None
        finding = review_finding(actor=actor, activity=method_code, lock=lock)
        if not finding.ok:
            return None, " ".join(finding.reasons)
        return {
            "activity": method_code,
            "method_revision": method_revision,
            "qualification": finding.evidence["qualification"],
        }, None

    def describe(self, evidence):
        """The qualification frozen on a reviewed test, as a label and its page, or None."""
        from django.urls import reverse

        pk = (evidence or {}).get("qualification")
        if not isinstance(pk, int):
            return None
        return {
            "label": f"QUAL-{pk}",
            "href": reverse("laboratory:qualification_detail", args=[pk]),
        }


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
