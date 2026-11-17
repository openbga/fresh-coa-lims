"""Acceptance journeys: the record paths a laboratory relies on, run end to end through the
application's services in the deployment's own environment, with the evidence kept.

Five journeys, each on its own synthetic lot: a lot that passes and is certified, a failure that
is investigated and ends in rejection, corrections that keep their originals, a lot rejected and
a lot cancelled as received in error, and an amended certificate. Each step states what is
expected and what was observed, and the product requirements it gives evidence for. Refusals
are steps too: self-review, a disposition by someone who made the lot's records, a wrong PIN,
a release while a failure is open, and the database guarding signed history.

The journeys need a database created for them (``acceptance_journeys`` refuses one that holds
any account): they create synthetic accounts and configuration and commit every record, as the
pages do. Signing verifies the PIN outside any enclosing transaction, so failed attempts count
and nothing can be rolled back around the run. Passwords and PINs are random and held in memory
for the run; they are never shown, and only their hashes are stored.

The run is evidence that the release behaves as these journeys expect in this environment. It
does not test the laboratory's own configuration or intended use, and it is no statement of
compliance.
"""

import hashlib
import html
import json
import platform
import re
import secrets
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, timedelta
from decimal import Decimal

import django
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from accounts.services import provision_account
from analytical import gates
from analytical import services as analytical
from analytical.models import AnalyticalTest, Investigation, Observation
from catalog import services as catalog
from catalog.units import plain
from config.security import mask_password_hashes
from core.audit import record_event
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import approve_rule, save_rule, set_pin
from laboratory import services as laboratory
from quality import rejection
from quality import services as quality
from quality.models import Lot, LotReceipt
from reporting import lot_record
from reporting import services as reporting
from reporting.models import ReportVersion
from sampling import services as sampling

from .services import running_release

SCHEMA = "oq.acceptance-journeys/1"
STATEMENT = (
    "Evidence that the journeys below ran as expected on the release and in the environment "
    "named here, with synthetic accounts, configuration and lots created for the run. It is "
    "evidence for the laboratory's own validation. It does not test the laboratory's "
    "configuration, procedures or intended use, and it is not a statement of compliance with "
    "any regulation."
)
MARKER = "Synthetic account created by acceptance_journeys; its credentials were never shown."
REASON = "Synthetic acceptance journey"
PURPOSE = "Acceptance journey evidence: the lot's record as the journey left it"
SEGMENT = "chemical"
RECIPIENT = "Synthetic acceptance recipient"

# Who does what. The receiver also holds the quality role and the analyst the reviewer role: a
# role never waives independence.
PEOPLE = {
    "admin": (("admin",), "Provisions the other accounts"),
    "author": (("quality",), "Drafts the configuration and records the analyst's qualification"),
    "approver": (("quality",), "Approves the configuration and authorizes a retest"),
    "receiver": (("analyst", "quality"), "Receives lots and corrects a receipt"),
    "analyst": (
        ("analyst", "reviewer"),
        "Samples, records, submits and corrects observations; also holds the reviewer role",
    ),
    "reviewer": (("reviewer",), "Reviews data, returns a test and assesses a failure"),
    "quality": (
        ("quality",),
        "Concludes the investigation and signs dispositions, rejections, cancellations, "
        "certificates and the amendment",
    ),
    "auditor": (("auditor",), "Exports each lot's record"),
}

JOURNEYS = (
    (
        "passing",
        "A lot that meets its specification is released and certified",
        "Receipt, sampling, a conforming result, independent review, QC disposition and a "
        "signed certificate whose stored file never changes.",
    ),
    (
        "failing",
        "A failing result is investigated, retested and confirmed, and the lot is rejected",
        "An out-of-specification result opens an investigation and blocks release; one "
        "authorized retest stays linked to the original; the failure is confirmed and the lot "
        "is rejected with its evidence.",
    ),
    (
        "corrected",
        "Corrections add records and keep the originals",
        "A receipt and an observation are corrected with reasons; the originals stay in the "
        "record and in the database; the reviewed, released record carries the corrected value.",
    ),
    (
        "rejected",
        "A lot that cannot be used is rejected; a lot recorded in error is cancelled",
        "A lot with a discrepancy on receipt is rejected before testing and takes no further "
        "records; a duplicate receipt is cancelled and stays in the record.",
    ),
    (
        "amended",
        "An amended certificate keeps the original unchanged",
        "A released lot's certificate is amended with a reason; the new version links to the "
        "original, whose stored file is unchanged.",
    ),
)

# A run stops a journey at its first failed step; the others still run.
OUTCOMES = ("passed", "failed")


class Mismatch(Exception):
    """What was observed is not what the step expects."""


class JourneyStopped(Exception):
    """A step failed; the journey's later steps depend on it and are not run."""


def expect(condition, message):
    if not condition:
        raise Mismatch(message)


def message_of(error):
    """The error as people read it, with any stored password or PIN hash masked."""
    if isinstance(error, ValidationError):
        text = " ".join(error.messages)
    else:
        text = str(error)
    return mask_password_hashes(text)


# The SQLSTATE of RAISE EXCEPTION, which the history guards' triggers use. Any other database
# error (a lock timeout, a constraint) does not show that a guard refused the change.
GUARD_SQLSTATE = "P0001"


@dataclass
class Step:
    number: str
    action: str
    expected: str
    requirements: tuple
    outcome: str = "not run"
    observed: str = ""

    def as_dict(self):
        return {
            "number": self.number,
            "action": self.action,
            "expected": self.expected,
            "observed": self.observed,
            "outcome": self.outcome,
            "requirements": list(self.requirements),
        }


@dataclass
class Journey:
    key: str
    title: str
    purpose: str
    steps: list = field(default_factory=list)
    lots: list = field(default_factory=list)
    files: list = field(default_factory=list)
    outcome: str = "not run"

    def as_dict(self):
        return {
            "key": self.key,
            "title": self.title,
            "purpose": self.purpose,
            "outcome": self.outcome,
            "lots": self.lots,
            "files": self.files,
            "steps": [step.as_dict() for step in self.steps],
        }


class Evidence:
    """Where the run writes the files it keeps: lot record exports and certificates."""

    def __init__(self, root):
        self.root = root

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {
            "path": relative,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }


class AcceptanceRun:
    """Create the synthetic configuration, then run each journey and record its steps."""

    def __init__(self, *, evidence, operator, stamp=None, log=None):
        self.evidence = evidence
        self.operator = operator
        self.started = timezone.now()
        self.stamp = stamp or self.started.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.log = log or (lambda text: None)
        self.people = {}
        self._secrets = {}
        self.setup = Journey(
            "configuration",
            "Synthetic accounts and approved configuration",
            "The accounts and the approved rule set, method, specification, sampling plan and "
            "analyst qualification that the journeys use, each approved by someone other than "
            "its author.",
        )
        self.journeys = [Journey(key, title, purpose) for key, title, purpose in JOURNEYS]
        self.current = None
        self.counter = 0

    # --- Steps ---------------------------------------------------------------------------

    @contextmanager
    def step(self, action, *, expected, requirements):
        self.counter += 1
        index = self.journeys.index(self.current) + 1 if self.current in self.journeys else 0
        record = Step(f"{index}.{self.counter}", action, expected, tuple(requirements))
        self.current.steps.append(record)
        try:
            yield record
        except Exception as error:
            record.outcome = "failed"
            kind = "" if isinstance(error, Mismatch) else f"{type(error).__name__}: "
            record.observed = f"{kind}{message_of(error)}"
            self.log(f"  FAILED {record.number} {action}: {record.observed}")
            if not isinstance(error, Mismatch | ValidationError | PermissionDenied):
                self.log(mask_password_hashes(traceback.format_exc()))
            raise JourneyStopped from error
        record.outcome = "passed"
        self.log(f"  ok {record.number} {action}")

    def refused(self, action, *, expected, requirements, match, call):
        """A step whose expected outcome is that the application refuses the action."""
        with self.step(action, expected=expected, requirements=requirements) as record:
            try:
                call()
            except (ValidationError, PermissionDenied) as error:
                text = message_of(error)
                expect(re.search(match, text, re.IGNORECASE), f"Refused, but because: {text}")
                record.observed = f"Refused: {text}"
            else:
                raise Mismatch("The action was accepted.")

    def database_refuses(self, queryset, **changes):
        """Try to change a stored row directly; the database must refuse. The change is undone
        in any case, so a database without its guards is reported and never altered."""

        class Undo(Exception):
            pass

        try:
            with transaction.atomic():
                queryset.update(**changes)
                raise Undo
        except DatabaseError as error:
            text = message_of(error).strip().splitlines()[0]
            state = getattr(error.__cause__, "sqlstate", None)
            expect(state == GUARD_SQLSTATE, f"Refused by the database, not by a guard: {text}")
            return text
        except Undo:
            raise Mismatch("The database accepted the change (it was undone).") from None

    def run(self):
        """Run everything; return True when every step passed."""
        self.where = self.environment()  # Where the run ran, read before anything can fail.
        self.current = self.setup
        self.counter = 0
        self.log("Synthetic configuration")
        if not self._attempt(self.setup, self.configure):
            return False  # The journeys need the configuration: none of them is run.
        for journey in self.journeys:
            self.current = journey
            self.counter = 0
            self.log(journey.title)
            work = getattr(self, f"journey_{journey.key}")
            self._attempt(journey, lambda work=work, journey=journey: work(journey))
        return self.passed

    def _attempt(self, journey, work):
        """Run a journey (or the configuration); a failed step, or an error outside any step,
        fails it and is reported as a step."""
        try:
            work()
        except JourneyStopped:
            journey.outcome = "failed"
        except Exception as error:
            index = self.journeys.index(journey) + 1 if journey in self.journeys else 0
            self.log(f"  FAILED {index}.{self.counter + 1} outside a step: {message_of(error)}")
            self.log(mask_password_hashes(traceback.format_exc()))
            journey.steps.append(
                Step(
                    f"{index}.{self.counter + 1}",
                    "Continue the journey",
                    "No error",
                    (),
                    "failed",
                    f"{type(error).__name__}: {message_of(error)}",
                )
            )
            journey.outcome = "failed"
        else:
            journey.outcome = "passed"
        return journey.outcome == "passed"

    @property
    def passed(self):
        return all(j.outcome == "passed" for j in [self.setup, *self.journeys])

    # --- People and configuration -----------------------------------------------------------

    @sensitive_variables()
    def _credentials(self):
        password = secrets.token_urlsafe(24)
        pin = "".join(secrets.choice("0123456789") for _ in range(12))
        return password, pin

    def pin(self, who):
        return self._secrets[who][1]

    def wrong_pin(self, who):
        pin = self.pin(who)
        return pin[:-1] + str((int(pin[-1]) + 1) % 10)

    @sensitive_variables()
    def _bootstrap_admin(self):
        """No account exists to provision the first one, so it is created directly, as the
        operator's bootstrap does, and recorded in the audit trail."""
        password, pin = self._credentials()
        user = get_user_model()(
            username="acceptance-admin", first_name="Acceptance", last_name="Admin"
        )
        validate_password(password, user)
        user.full_clean(exclude=["password"])
        user.set_password(password)
        with transaction.atomic():
            user.save()
            user.groups.set([Group.objects.get_or_create(name="admin")[0]])
            record_event(
                actor=user,
                action="account.created",
                obj=user,
                after={
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "roles": ["admin"],
                },
                reason=MARKER,
            )
        set_pin(actor=user, pin=pin, password=password)
        self._secrets["admin"] = (password, pin)
        return user

    def _approve(self, revision, who="approver"):
        revision.refresh_from_db()
        return catalog.approve_revision(
            actor=self.people[who],
            pin=self.pin(who),
            revision=revision,
            expected_revision=revision.revision,
            reason=f"{REASON}: independent configuration review",
        )

    @sensitive_variables()
    def configure(self):
        with self.step(
            "Create the synthetic accounts with their roles",
            expected="Each account is created with its roles and a signature PIN, and recorded "
            "in the audit trail",
            requirements=("OQ-004", "OQ-002"),
        ) as record:
            admin = self._bootstrap_admin()
            self.people["admin"] = admin
            for who, (roles, _use) in PEOPLE.items():
                if who == "admin":
                    continue
                password, pin = self._credentials()
                user = provision_account(
                    actor=admin,
                    username=f"acceptance-{who}",
                    password=password,
                    first_name="Acceptance",
                    last_name=who.title(),
                    roles=list(roles),
                    reason=MARKER,
                )
                set_pin(actor=user, pin=pin, password=password)
                self._secrets[who] = (password, pin)
                self.people[who] = user
            created = AuditEvent.objects.filter(action="account.created").count()
            expect(created == len(PEOPLE), f"{created} account.created events")
            record.observed = (
                f"{len(PEOPLE)} accounts created, each with an account.created audit event: "
                + ", ".join(
                    f"{user.username} ({', '.join(PEOPLE[who][0])})"
                    for who, user in self.people.items()
                )
            )

        author = self.people["author"]
        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=365)
        with self.step(
            "Draft the rule set",
            expected="A draft rule set that requires the assay",
            requirements=("OQ-001",),
        ) as record:
            rules = save_rule(
                actor=author,
                code="acceptance-rules",
                segment=SEGMENT,
                policy={
                    "required_tests": ["assay"],
                    "review_meaning": "reviewed",
                    "disposition_meaning": "approved",
                },
                effective_from=start,
                effective_until=end,
                reason=f"{REASON}: rule set",
            )
            record.observed = f"Rule set {rules.code} v{rules.version} drafted by {author}"
        self.refused(
            "The author approves the rule set they drafted",
            expected="Refused: approval needs someone other than the author",
            requirements=("OQ-001", "OQ-004"),
            match=r"cannot approve their own",
            call=lambda: approve_rule(
                actor=author,
                pin=self.pin("author"),
                rule=rules,
                expected_revision=rules.revision,
                reason=f"{REASON}: self-approval",
            ),
        )
        with self.step(
            "Approve the rule set, method, specification and sampling plan, and the analyst's "
            "qualification for the method",
            expected="Each is approved with a signature by someone other than its author",
            requirements=("OQ-001", "OQ-005", "OQ-011", "OQ-003"),
        ) as record:
            approver = self.people["approver"]
            rules.refresh_from_db()
            self.rules = approve_rule(
                actor=approver,
                pin=self.pin("approver"),
                rule=rules,
                expected_revision=rules.revision,
                reason=f"{REASON}: independent rule set review",
            )
            self.material = catalog.create_material(
                actor=author,
                code="acceptance-powder",
                name="Synthetic acceptance powder",
                kind="raw_material",
                reason=f"{REASON}: material",
            )
            self.method, method_revision = catalog.create_method(
                actor=author,
                code="acceptance-assay",
                title="Synthetic acceptance assay",
                technique="Gravimetry",
                document_ref="SOP-ACC-001 rev 1",
                suitability_kind="validation",
                suitability_ref="VAL-ACC-001 rev 1",
                requires_batch=False,
                effective_from=start,
                effective_until=end,
                reason=f"{REASON}: method",
            )
            method_revision = self._approve(method_revision)
            _, spec_revision = catalog.create_specification(
                actor=author,
                code="acceptance-spec",
                title="Synthetic acceptance specification",
                material=self.material,
                stage="incoming",
                scope="general",
                basis="Synthetic limits for the acceptance journeys",
                effective_from=start,
                effective_until=end,
                reason=f"{REASON}: specification",
            )
            catalog.add_test_line(
                actor=author,
                revision=spec_revision,
                reason=f"{REASON}: assay limits",
                code="assay",
                name="Assay",
                method=self.method,
                result_type="numeric",
                unit="%",
                lower_limit=Decimal("98.00"),
                upper_limit=Decimal("102.00"),
                lower_inclusive=True,
                upper_inclusive=True,
                reporting_decimals=2,
                replicates=1,
                replicate_limits=True,
                max_retests=1,
                required=True,
            )
            spec_revision = self._approve(spec_revision)
            _, plan_revision = sampling.create_plan(
                actor=author,
                code="acceptance-plan",
                title="Synthetic acceptance sampling plan",
                material=self.material,
                stage="incoming",
                basis="all",
                minimum_quantity=Decimal("10"),
                quantity_unit="g",
                instructions="Take one identified sample from each container.",
                rationale="Synthetic single-container lots only",
                effective_from=start,
                effective_until=end,
                reason=f"{REASON}: sampling plan",
            )
            plan_revision = self._approve(plan_revision)
            qualification = laboratory.record_qualification(
                actor=author,
                user=self.people["analyst"],
                activity=self.method.code,
                evidence_ref="QUAL-ACC-001 rev 1",
                valid_from=start.date(),
                valid_until=end.date(),
                reason=f"{REASON}: analyst training evidence",
            )
            laboratory.approve_qualification(
                actor=approver,
                pin=self.pin("approver"),
                qualification=qualification,
                expected_revision=qualification.revision,
                reason=f"{REASON}: independent training evidence review",
            )
            approved = [
                f"rule set {self.rules.code} v{self.rules.version}",
                f"method {self.method.code} v{method_revision.version}",
                f"specification acceptance-spec v{spec_revision.version} "
                "(assay 98.00-102.00 %, one retest allowed)",
                f"sampling plan acceptance-plan v{plan_revision.version}",
                f"qualification of acceptance-analyst for {self.method.code}",
            ]
            signed = list(
                ElectronicSignature.objects.values_list("object_type", "object_id", "signer_id")
            )
            expect(len(signed) == 5, f"{len(signed)} signatures for the five approvals.")
            expect(len(set(signed)) == 5, "An approval was signed twice.")
            expect(
                {signer for _, _, signer in signed} == {approver.pk},
                "The approvals were not all signed by the approver.",
            )
            record.observed = "Approved with a signature by acceptance-approver: " + "; ".join(
                approved
            )

    # --- Building blocks of the journeys ------------------------------------------------------

    def lot_number(self, suffix):
        return f"ACC-{self.stamp}-{suffix}"

    def receipt(self, **changes):
        return {
            "source": "on_site",
            "supplier": None,
            "supplier_lot": "",
            "manufacturer": "",
            "manufacturer_location": "",
            "manufacturer_lot": "",
            "shipment_ref": f"BR-ACC-{self.stamp}",
            "received_on": timezone.localdate(),
            "quantity": Decimal("25"),
            "quantity_unit": "kg",
            "containers": 1,
            "container_description": "Synthetic 25 kg drum",
            "condition": "acceptable",
            "condition_notes": "",
        } | changes

    def receive(self, journey, suffix, **receipt):
        lot = quality.receive_lot(
            actor=self.people["receiver"],
            number=self.lot_number(suffix),
            material=self.material.name,
            rules=self.rules,
            reason=f"{REASON}: receipt",
            receipt=self.receipt(**receipt),
        )
        journey.lots.append(lot.number)
        return lot

    def sample(self, lot):
        assignment = sampling.assign_requirements(
            actor=self.people["analyst"],
            lot=lot,
            material=self.material,
            stage="incoming",
            reason=f"{REASON}: assign the approved requirements",
        )
        expect(assignment.status == "ready", f"Requirements {assignment.status}.")
        record = sampling.record_sampling(
            actor=self.people["analyst"],
            lot=lot,
            reference=f"{lot.number}-S1",
            sampled_at=timezone.now(),
            containers_total=1,
            containers_sampled=1,
            container_ids=f"{lot.number}-C1",
            quantity=Decimal("10"),
            quantity_unit="g",
            location="Synthetic sampling booth",
            reason=f"{REASON}: sampling",
        )
        return record.sample

    def received_and_sampled(self, journey, suffix):
        with self.step(
            "Receive the lot, assign its approved requirements and record its sampling",
            expected="The lot is in quarantine with its receipt, the requirements of the "
            "approved specification are assigned and the sampling record names the containers",
            requirements=("OQ-005", "OQ-006"),
        ) as record:
            lot = self.receive(journey, suffix)
            sample = self.sample(lot)
            lot.refresh_from_db()
            expect(lot.state == "quarantine", f"Lot state {lot.state}.")
            record.observed = (
                f"Lot {lot.number} in quarantine; requirements ready; sample {sample.reference} "
                "from 1 of 1 containers"
            )
        return lot, sample

    def assign_test(self, sample):
        tests, holds = analytical.assign_tests(
            actor=self.people["analyst"], sample=sample, reason=f"{REASON}: assign tests"
        )
        expect(holds == [] and len(tests) == 1, f"Tests {len(tests)}, holds {holds}.")
        return tests[0]

    def observe(self, test, value):
        analytical.record_observation(
            actor=self.people["analyst"],
            test=test,
            value=Decimal(value),
            raw_reference=f"RAW-ACC-{test.pk} p1",
            reason=f"{REASON}: original observation",
        )

    def submit(self, test):
        test.refresh_from_db()
        return analytical.submit_test(
            actor=self.people["analyst"],
            test=test,
            expected_revision=test.revision,
            reason=f"{REASON}: submit",
        )

    def review(self, test, who="reviewer", pin=None):
        test.refresh_from_db()
        return analytical.review_test(
            actor=self.people[who],
            pin=pin or self.pin(who),
            test=test,
            expected_revision=test.revision,
            reason=f"{REASON}: independent review of the original data",
        )

    def dispose(self, lot, who="quality"):
        lot = Lot.objects.get(pk=lot.pk)
        return quality.dispose_lot(
            actor=self.people[who],
            pin=self.pin(who),
            lot=lot,
            expected_revision=lot.revision,
            reason=f"{REASON}: QC disposition",
        )

    def issue(self, lot, *, check=True):
        lot = Lot.objects.get(pk=lot.pk)
        _evidence, evidence_hash, blockers = reporting.preview(lot)
        if check:
            expect(blockers == [], f"Certificate blockers: {blockers}")
        report = reporting.issue_report(
            actor=self.people["quality"],
            pin=self.pin("quality"),
            lot=lot,
            recipient=RECIPIENT,
            evidence_hash=evidence_hash,
            reason=f"{REASON}: issue the certificate",
        )
        return report, report.versions.get(number=1)

    def keep_certificate(self, journey, version):
        pdf = reporting.read_pdf(actor=self.people["quality"], version=version)
        expect(pdf.startswith(b"%PDF-"), "The stored certificate is not a PDF.")
        expect(
            hashlib.sha256(pdf).hexdigest() == version.pdf_sha256,
            "The certificate read back differs from its stored checksum.",
        )
        name = lot_record.safe_name(version.report.number, "certificate")
        entry = self.evidence.write(f"{journey.key}/{name}-v{version.number}.pdf", pdf)
        journey.files.append({**entry, "kind": "certificate"})
        return pdf

    def released_with_certificate(self, journey, suffix, value):
        lot, sample = self.received_and_sampled(journey, suffix)
        with self.step(
            f"Record and submit a conforming result ({value} %), review it, sign the QC "
            "disposition and issue the certificate",
            expected="The lot is released and certificate version 1 is issued with a signature",
            requirements=("OQ-007", "OQ-009", "OQ-010", "OQ-003"),
        ) as record:
            test = self.assign_test(sample)
            self.observe(test, value)
            test, investigation = self.submit(test)
            expect(investigation is None and test.conforms, "The result did not conform.")
            self.review(test)
            lot = self.dispose(lot)
            expect(lot.state == "released", f"Lot state {lot.state}.")
            report, version = self.issue(lot)
            pdf = self.keep_certificate(journey, version)
            record.observed = (
                f"Lot {lot.number} released; certificate {report.number} version 1 issued, "
                f"PDF SHA-256 {version.pdf_sha256[:16]}…"
            )
        return lot, report, version, pdf

    def export(self, journey, lot):
        with self.step(
            f"Export the record of lot {lot.number}",
            expected="One package with the printed and electronic copy, the stored files and a "
            "checksum of each; every stored checksum checks out; the export is in the audit "
            "trail",
            requirements=("OQ-016", "OQ-002"),
        ) as record:
            package = lot_record.export_lot_record(
                actor=self.people["auditor"], lot_pk=lot.pk, purpose=PURPOSE
            )
            try:
                data = package.file.read()
            finally:
                package.file.close()
            expect(hashlib.sha256(data).hexdigest() == package.sha256, "Package checksum.")
            summary = package.summary
            expect(summary["checks_differ"] == 0, f"{summary['checks_differ']} checks differ.")
            expect(
                AuditEvent.objects.filter(
                    action=lot_record.EXPORT_ACTION,
                    object_id=str(lot.pk),
                    actor=self.people["auditor"],
                ).exists(),
                "No audit event of the export.",
            )
            entry = self.evidence.write(f"{journey.key}/{package.filename}", data)
            journey.files.append({**entry, "kind": "lot record", "lot": lot.number})
            record.observed = (
                f"{package.filename}: {summary['records']} records, {summary['signatures']} "
                f"signatures, {summary['audit_events']} audit events, {summary['files']} stored "
                f"files, {summary['checks']} checks all intact; SHA-256 {package.sha256[:16]}…"
            )

    # --- The journeys -------------------------------------------------------------------------

    def journey_passing(self, journey):
        lot, sample = self.received_and_sampled(journey, "PASS")
        with self.step(
            "Assign the tests the lot's frozen requirements call for",
            expected="One assay test against the approved specification, with no holds",
            requirements=("OQ-005", "OQ-007"),
        ) as record:
            test = self.assign_test(sample)
            record.observed = (
                f"{test.label}: {test.test_code}, {test.requirement['source']}; no holds"
            )

        def unread():
            analytical.record_observation(
                actor=self.people["analyst"],
                test=test,
                value=None,
                raw_reference=f"RAW-ACC-{test.pk} p1",
                reason=f"{REASON}: an entry without a value",
            )

        self.refused(
            "Record the assay without a value",
            expected="Refused: a numeric result needs a value",
            requirements=("OQ-007",),
            match=r"enter the observed value",
            call=unread,
        )
        with self.step(
            "Record 100.25 % with its raw-data reference and submit it",
            expected="The result conforms to 98.00-102.00 % and no investigation is opened",
            requirements=("OQ-007",),
        ) as record:
            self.observe(test, "100.25")
            test, investigation = self.submit(test)
            expect(test.conforms is True, "The result does not conform.")
            expect(investigation is None, "An investigation was opened.")
            record.observed = f"Reportable {test.reportable_display} %, conforms; no investigation"
        self.refused(
            "The analyst reviews their own result",
            expected="Refused: no one reviews their own data",
            requirements=("OQ-004", "OQ-007"),
            match=r"cannot review your own",
            call=lambda: analytical.review_test(
                actor=self.people["analyst"],
                pin=self.pin("analyst"),
                test=test,
                expected_revision=test.revision,
                reason=f"{REASON}: self-review",
            ),
        )
        with self.step(
            "The reviewer signs the review with a wrong PIN",
            expected="Refused; the failed attempt is counted and kept in the audit trail although "
            "the review is refused; the test is unchanged",
            requirements=("OQ-003", "OQ-002"),
        ) as record:
            before = AnalyticalTest.objects.get(pk=test.pk).revision
            try:
                self.review(test, pin=self.wrong_pin("reviewer"))
            except ValidationError as error:
                text = message_of(error)
            else:
                raise Mismatch("The review was signed with a wrong PIN.")
            failures = PINCredential.objects.get(user=self.people["reviewer"]).failures
            denied = AuditEvent.objects.filter(
                action="signature.denied", actor=self.people["reviewer"]
            ).count()
            expect(failures == 1, f"Failed attempts counted: {failures}.")
            expect(denied == 1, f"signature.denied events: {denied}.")
            expect(AnalyticalTest.objects.get(pk=test.pk).revision == before, "Test changed.")
            record.observed = (
                f"Refused: {text} Failed attempts on the credential: 1; signature.denied "
                "recorded; test revision unchanged"
            )
        with self.step(
            "The reviewer signs the review",
            expected="Signed with the meaning reviewed, bound to the test's new revision; the "
            "failed-attempt count is cleared",
            requirements=("OQ-003", "OQ-007"),
        ) as record:
            test = self.review(test)
            signature = ElectronicSignature.objects.get(
                object_type="analytical.analyticaltest", object_id=str(test.pk)
            )
            expect(signature.revision == test.revision, "Signature not bound to the revision.")
            expect(signature.signer == self.people["reviewer"], "Wrong signer.")
            failures = PINCredential.objects.get(user=self.people["reviewer"]).failures
            expect(failures == 0, f"Failed attempts left: {failures}.")
            record.observed = (
                f"Test {test.state}; signature by {signature.signer_name} meaning "
                f"{signature.meaning} at revision {signature.revision}; content hash "
                f"{signature.content_hash[:16]}…"
            )
        self.refused(
            "The receiver, who also holds the quality role, signs the QC disposition",
            expected="Refused: whoever made the lot's records cannot dispose of it",
            requirements=("OQ-004", "OQ-009"),
            match=r"cannot disposition a lot containing your own receipt",
            call=lambda: self.dispose(lot, who="receiver"),
        )
        with self.step(
            "Quality signs the QC disposition",
            expected="The lot is released; the disposition evidence lists no blockers",
            requirements=("OQ-009", "OQ-003"),
        ) as record:
            lot = self.dispose(lot)
            expect(lot.state == "released", f"Lot state {lot.state}.")
            expect(lot.disposition_evidence["analytical"]["blockers"] == [], "Blockers.")
            record.observed = f"Lot {lot.state}; disposition evidence holds no blockers"
        with self.step(
            "Issue the certificate of analysis",
            expected="Version 1 is signed; the stored PDF's checksum is the one signed",
            requirements=("OQ-010", "OQ-003"),
        ) as record:
            report, version = self.issue(lot)
            pdf = self.keep_certificate(journey, version)
            signature = reporting.signature_for(version)
            expect(
                signature.content["current_pdf_sha256"] == version.pdf_sha256,
                "The signature does not name the stored PDF.",
            )
            record.observed = (
                f"Certificate {report.number} version 1, {len(pdf)} bytes, SHA-256 "
                f"{version.pdf_sha256[:16]}…, signed by {signature.signer_name}"
            )
        with self.step(
            "Read the certificate again and try to change its stored file in the database",
            expected="The same bytes are returned; the database refuses the change",
            requirements=("OQ-010", "OQ-002"),
        ) as record:
            stored = ReportVersion.objects.get(pk=version.pk)
            again = reporting.read_pdf(actor=self.people["reviewer"], version=stored)
            expect(hashlib.sha256(again).hexdigest() == version.pdf_sha256, "Bytes differ.")
            refusal = self.database_refuses(
                ReportVersion.objects.filter(pk=version.pk), pdf=b"changed"
            )
            record.observed = f"Identical bytes; the database refused: {refusal}"
        with self.step(
            "Try to change the review's signature and an audit event of the lot in the database",
            expected="The database refuses both: signatures and the audit trail are append-only",
            requirements=("OQ-002", "OQ-003"),
        ) as record:
            signature = ElectronicSignature.objects.get(
                object_type="analytical.analyticaltest", object_id=str(test.pk)
            )
            event = AuditEvent.objects.filter(object_type="quality.lot", object_id=str(lot.pk))
            expect(event.exists(), "The lot has no audit event.")
            signed = self.database_refuses(
                ElectronicSignature.objects.filter(pk=signature.pk), meaning="approved"
            )
            audited = self.database_refuses(
                AuditEvent.objects.filter(pk=event.first().pk), reason="changed"
            )
            record.observed = f"Signature refused: {signed} Audit event refused: {audited}"
        self.export(journey, lot)

    def journey_failing(self, journey):
        lot, sample = self.received_and_sampled(journey, "FAIL")
        with self.step(
            "Record 96.40 % and submit it",
            expected="The result does not conform; an investigation is opened and holds the lot",
            requirements=("OQ-007", "OQ-008"),
        ) as record:
            test = self.assign_test(sample)
            self.observe(test, "96.40")
            test, investigation = self.submit(test)
            expect(test.conforms is False, "The result conforms.")
            expect(investigation is not None, "No investigation was opened.")
            blockers = gates.lot_blockers(lot)
            expect(blockers, "Nothing blocks the lot.")
            record.observed = (
                f"Reportable {test.reportable_display} %, does not conform; investigation "
                f"{investigation.label} opened; blocking: {'; '.join(blockers)}"
            )
        self.refused(
            "Quality signs the QC disposition while the investigation is open",
            expected="Refused: an open investigation blocks the disposition",
            requirements=("OQ-009", "OQ-008"),
            match=r"INV-\d+ is open",
            call=lambda: self.dispose(lot),
        )
        self.refused(
            "Quality rejects the lot while the investigation is open",
            expected="Refused: the failure is investigated and concluded first",
            requirements=("OQ-008", "OQ-009"),
            match=r"INV-\d+ is open\. Conclude it before the lot is rejected",
            call=lambda: self.reject(lot, grounds="results"),
        )
        with self.step(
            "The reviewer reviews the original result and records the laboratory assessment",
            expected="The original result is reviewed as it was recorded; the assessment is in "
            "the investigation",
            requirements=("OQ-008", "OQ-007"),
        ) as record:
            test = self.review(test)
            analytical.add_entry(
                actor=self.people["reviewer"],
                investigation=investigation,
                kind="assessment",
                text=f"{REASON}: no laboratory error found in the original analysis.",
            )
            record.observed = f"Original {test.label} {test.state} at {test.reportable_display} %"
        with self.step(
            "Quality authorizes one retest",
            expected="Signed; the retest is a new test linked to the original and to the "
            "investigation",
            requirements=("OQ-008", "OQ-003"),
        ) as record:
            investigation.refresh_from_db()
            analytical.authorize_retest(
                actor=self.people["approver"],
                pin=self.pin("approver"),
                investigation=investigation,
                expected_revision=investigation.revision,
                kind="retest",
                reason=f"{REASON}: one retest of the retained sample",
            )
            retest = AnalyticalTest.objects.get(parent=test)
            authorized = ElectronicSignature.objects.filter(
                object_type="analytical.investigation",
                object_id=str(investigation.pk),
                meaning="authorized",
                signer=self.people["approver"],
            )
            expect(authorized.count() == 1, "The retest authorization is not signed.")
            expect(retest.investigation_id == investigation.pk, "Retest not linked.")
            expect(retest.kind == "retest", f"Kind {retest.kind}.")
            record.observed = f"{retest.label} ({retest.kind}) linked to {test.label}"
        self.refused(
            "Quality authorizes a second retest",
            expected="Refused: the specification allows one retest",
            requirements=("OQ-008", "OQ-005"),
            match=r"no further retests",
            call=lambda: analytical.authorize_retest(
                actor=self.people["approver"],
                pin=self.pin("approver"),
                investigation=Investigation.objects.get(pk=investigation.pk),
                expected_revision=Investigation.objects.get(pk=investigation.pk).revision,
                kind="retest",
                reason=f"{REASON}: a second retest",
            ),
        )
        with self.step(
            "Record 96.10 % on the retest, submit it and review it",
            expected="The retest does not conform either; the original result is unchanged",
            requirements=("OQ-008", "OQ-007"),
        ) as record:
            self.observe(retest, "96.10")
            retest, _ = self.submit(retest)
            expect(retest.conforms is False, "The retest conforms.")
            retest = self.review(retest)
            original = AnalyticalTest.objects.get(pk=test.pk)
            values = [o.value for o in Observation.objects.filter(test=original)]
            expect(values == [Decimal("96.40")], f"Original observations {values}.")
            record.observed = (
                f"{retest.label} {retest.reportable_display} %, does not conform, reviewed; "
                f"original {original.label} still {original.reportable_display} %"
            )
        self.refused(
            "Quality concludes that the original result is invalid",
            expected="Refused: a failing retest cannot invalidate a failing result",
            requirements=("OQ-008",),
            match=r"also out of specification",
            call=lambda: self.conclude(investigation, "invalidated"),
        )
        with self.step(
            "Quality concludes the investigation: the failure is confirmed",
            expected="Signed and closed; the confirmed failure still blocks the disposition",
            requirements=("OQ-008", "OQ-009", "OQ-003"),
        ) as record:
            investigation = self.conclude(investigation, "confirmed")
            expect(investigation.phase == "closed", f"Phase {investigation.phase}.")
            blockers = gates.lot_blockers(lot)
            expect(
                any("confirmed" in b for b in blockers), f"Blockers after conclusion: {blockers}"
            )
            record.observed = f"{investigation.label} closed, confirmed; blocking: {blockers[0]}"
        with self.step(
            "Quality rejects the lot on its results with a reference to the quality system",
            expected="The lot is rejected with a signature that keeps the tests as they stood",
            requirements=("OQ-009", "OQ-003", "OQ-014"),
        ) as record:
            lot = self.reject(lot, grounds="results")
            expect(lot.state == "rejected", f"Lot state {lot.state}.")
            evidence = lot.disposition_evidence
            expect(evidence["grounds"] == "results", "Grounds not kept.")
            record.observed = (
                f"Lot {lot.state}; grounds {evidence['grounds']}, reference "
                f"{evidence['reference']}; {len(evidence['tests'])} tests frozen"
            )
        self.refused(
            "Assign requirements to the rejected lot to sample it again",
            expected="Refused: a rejected lot takes no more records",
            requirements=("OQ-009", "OQ-006"),
            match=r"only quarantined lots",
            call=lambda: self.sample(Lot.objects.get(pk=lot.pk)),
        )
        self.export(journey, lot)

    def journey_corrected(self, journey):
        with self.step(
            "Receive the lot as 25 kg and correct the quantity to 24.5 kg with a reason",
            expected="A correction is added and linked; the original receipt is kept",
            requirements=("OQ-006", "OQ-002"),
        ) as record:
            lot = self.receive(journey, "CORR")
            original = quality.current_receipt(lot)
            corrected = quality.correct_receipt(
                actor=self.people["receiver"],
                receipt=original,
                reason=f"{REASON}: the delivery note states 24.5 kg",
                **self.receipt(quantity=Decimal("24.5")),
            )
            receipts = list(LotReceipt.objects.filter(lot=lot).order_by("pk"))
            current = quality.current_receipt(lot)
            expect(len(receipts) == 2, f"{len(receipts)} receipt records.")
            expect(corrected.corrects_id == original.pk, "Correction not linked.")
            expect(current.pk == corrected.pk, "The correction is not current.")
            expect(current.quantity == Decimal("24.5"), f"Current {current.quantity}.")
            expect(receipts[0].quantity == Decimal("25"), f"Original {receipts[0].quantity}.")
            record.observed = (
                f"Receipt records: original {plain(receipts[0].quantity)} kg kept, correction "
                f"{plain(current.quantity)} kg current, linked to the original"
            )
        with self.step(
            "Assign the requirements, sample, record 100.25 % and submit it",
            expected="The result conforms and is submitted for review",
            requirements=("OQ-007",),
        ) as record:
            sample = self.sample(lot)
            test = self.assign_test(sample)
            self.observe(test, "100.25")
            test, _ = self.submit(test)
            record.observed = f"Submitted {test.reportable_display} %"
        with self.step(
            "The reviewer returns the test: the entry differs from the raw data (100.52 %)",
            expected="The test is open again for correction",
            requirements=("OQ-007",),
        ) as record:
            test.refresh_from_db()
            test = analytical.return_test(
                actor=self.people["reviewer"],
                test=test,
                expected_revision=test.revision,
                reason=f"{REASON}: the entry differs from the raw data (100.52 %)",
            )
            expect(test.state == "open", f"Test state {test.state}.")
            record.observed = f"Test {test.state}"
        with self.step(
            "The analyst corrects the observation to 100.52 % with a reason",
            expected="A correction is added and linked; the original 100.25 % is kept",
            requirements=("OQ-007", "OQ-002"),
        ) as record:
            first = Observation.objects.get(test=test)
            analytical.correct_observation(
                actor=self.people["analyst"],
                observation=first,
                value=Decimal("100.52"),
                raw_reference=f"RAW-ACC-{test.pk} p1",
                reason=f"{REASON}: transcription error; the raw data reads 100.52 %",
            )
            rows = list(Observation.objects.filter(test=test).order_by("pk"))
            current = list(AnalyticalTest.objects.get(pk=test.pk).current_observations())
            expect(len(rows) == 2 and rows[1].supersedes_id == rows[0].pk, "Not linked.")
            expect([o.value for o in current] == [Decimal("100.52")], "Current value.")
            expect(rows[0].value == Decimal("100.25"), "Original changed.")
            record.observed = (
                f"Observations: original {plain(rows[0].value)} % kept, correction "
                f"{plain(rows[1].value)} % current, linked, with its reason"
            )
        with self.step(
            "Try to change the original observation in the database",
            expected="The database refuses: observations are append-only",
            requirements=("OQ-002", "OQ-007"),
        ) as record:
            refusal = self.database_refuses(
                Observation.objects.filter(pk=first.pk), value=Decimal("100.52")
            )
            record.observed = f"Refused: {refusal}"
        with self.step(
            "Submit, review, sign the QC disposition and issue the certificate",
            expected="The lot is released; the certificate reports the corrected 100.52 %",
            requirements=("OQ-007", "OQ-009", "OQ-010"),
        ) as record:
            test, _ = self.submit(test)
            expect(test.reportable_display == "100.52", f"Reported {test.reportable_display}.")
            self.review(test)
            self.refused_inline(
                lambda: self.dispose(lot, who="receiver"), r"own receipt", "receipt corrector"
            )
            lot = self.dispose(lot)
            report, version = self.issue(lot)
            self.keep_certificate(journey, version)
            results = version.snapshot.get("native", {}).get("analytical", {}).get("results", [])
            reported = [row.get("reportable") for row in results]
            expect(reported == ["100.52"], f"The certificate reports {reported}.")
            record.observed = (
                f"Lot {lot.state}; the receipt corrector was refused the disposition; "
                f"certificate {report.number} v1 reports {test.reportable_display} %"
            )
        self.export(journey, lot)

    def journey_rejected(self, journey):
        with self.step(
            "Receive a lot whose examination on receipt found a discrepancy",
            expected="The lot is in quarantine; the receipt keeps what was found",
            requirements=("OQ-006",),
        ) as record:
            lot = self.receive(
                journey,
                "REJ",
                condition="discrepancy",
                condition_notes="Synthetic: the drum seal is broken and the label is unreadable.",
            )
            receipt = quality.current_receipt(lot)
            expect(receipt.condition == "discrepancy", "Condition not kept.")
            record.observed = f"Lot {lot.number} in quarantine; receipt: {receipt.condition_notes}"
        self.refused(
            "The receiver, who also holds the quality role, rejects the lot",
            expected="Refused: whoever made the lot's records cannot reject it",
            requirements=("OQ-004", "OQ-009"),
            match=r"cannot reject a lot containing your own receipt",
            call=lambda: self.reject(lot, grounds="receipt", who="receiver"),
        )
        with self.step(
            "Quality rejects the lot on its receipt, before any testing",
            expected="The lot is rejected with a signature that keeps what stood in the way of "
            "release",
            requirements=("OQ-009", "OQ-003", "OQ-014"),
        ) as record:
            lot = self.reject(lot, grounds="receipt")
            evidence = lot.disposition_evidence
            expect(lot.state == "rejected", f"Lot state {lot.state}.")
            expect(evidence["outstanding"], "Nothing outstanding was kept.")
            record.observed = (
                f"Lot {lot.state}; grounds {evidence['grounds']}; outstanding at rejection: "
                f"{'; '.join(evidence['outstanding'])}"
            )
        self.refused(
            "Assign requirements to the rejected lot",
            expected="Refused: a rejected lot takes no more records",
            requirements=("OQ-009",),
            match=r"only quarantined lots",
            call=lambda: self.sample(Lot.objects.get(pk=lot.pk)),
        )
        self.refused(
            "Sign a QC disposition of the rejected lot",
            expected="Refused: the lot already has its decision",
            requirements=("OQ-009",),
            match=r"already been dispositioned",
            call=lambda: self.dispose(lot),
        )
        self.refused(
            "Issue a certificate for the rejected lot",
            expected="Refused: only a released lot is certified",
            requirements=("OQ-010",),
            match=r"no signed QC disposition",
            call=lambda: self.issue(lot, check=False),
        )
        self.export(journey, lot)
        with self.step(
            "Receive the same delivery a second time by mistake and cancel that lot",
            expected="The lot is cancelled with a signature and stays in the record",
            requirements=("OQ-006", "OQ-003", "OQ-002"),
        ) as record:
            duplicate = self.receive(journey, "DUP")
            duplicate = Lot.objects.get(pk=duplicate.pk)
            cancelled = rejection.cancel_receipt(
                actor=self.people["quality"],
                pin=self.pin("quality"),
                lot=duplicate,
                expected_revision=duplicate.revision,
                reason=f"{REASON}: the delivery was recorded twice",
                basis=rejection.cancellation_preview(duplicate).basis,
            )
            expect(cancelled.state == "cancelled", f"Lot state {cancelled.state}.")
            expect(Lot.objects.filter(pk=duplicate.pk).exists(), "The lot is gone.")
            record.observed = f"Lot {cancelled.number} {cancelled.state}; kept in the record"
        self.export(journey, cancelled)

    def journey_amended(self, journey):
        lot, report, first, original = self.released_with_certificate(journey, "AMD", "99.80")
        self.refused(
            "Amend the certificate from a stale view (version 0)",
            expected="Refused: the certificate changed since it was reviewed",
            requirements=("OQ-010", "OQ-003"),
            match=r"certificate changed since you reviewed it",
            call=lambda: self.amend(report, expected_version=0),
        )
        with self.step(
            "Quality amends the certificate with a reason",
            expected="Version 2 is signed, states its reason and links to version 1",
            requirements=("OQ-010", "OQ-003"),
        ) as record:
            self.amend(report, expected_version=1)
            second = ReportVersion.objects.get(report=report, number=2)
            signature = reporting.signature_for(second)
            expect(signature is not None, "Version 2 has no signature.")
            expect(signature.meaning == "amended", f"Meaning {signature.meaning}.")
            expect(
                signature.content["current_pdf_sha256"] == second.pdf_sha256,
                "The signature does not name version 2's file.",
            )
            expect(second.kind == "amendment", f"Kind {second.kind}.")
            expect(second.supersedes_id == first.pk, "Version 2 does not link to version 1.")
            self.keep_certificate(journey, second)
            record.observed = (
                f"Version 2 ({second.kind}) supersedes version 1; reason: {second.reason}; "
                f"SHA-256 {second.pdf_sha256[:16]}…"
            )
        with self.step(
            "Read version 1 again",
            expected="Version 1 returns the bytes first issued",
            requirements=("OQ-010", "OQ-002"),
        ) as record:
            first = ReportVersion.objects.get(pk=first.pk)
            again = reporting.read_pdf(actor=self.people["auditor"], version=first)
            expect(again == original, "Version 1 changed.")
            expect(first.pdf_sha256 != second.pdf_sha256, "The versions are the same file.")
            record.observed = f"Version 1 unchanged, SHA-256 {first.pdf_sha256[:16]}…"
        self.export(journey, lot)

    # --- Transitions used by several journeys -------------------------------------------------

    def refused_inline(self, call, match, who):
        try:
            call()
        except (ValidationError, PermissionDenied) as error:
            text = message_of(error)
            expect(re.search(match, text, re.IGNORECASE), f"{who} refused because: {text}")
        else:
            raise Mismatch(f"The {who} was not refused.")

    def reject(self, lot, *, grounds, who="quality"):
        lot = Lot.objects.get(pk=lot.pk)
        return rejection.reject_lot(
            actor=self.people[who],
            pin=self.pin(who),
            lot=lot,
            expected_revision=lot.revision,
            grounds=grounds,
            reason=f"{REASON}: the lot cannot be used",
            reference=f"NCR-ACC-{self.stamp}",
            basis=rejection.rejection_preview(lot).basis,
        )

    def conclude(self, investigation, outcome):
        investigation = Investigation.objects.get(pk=investigation.pk)
        return analytical.conclude(
            actor=self.people["quality"],
            pin=self.pin("quality"),
            investigation=investigation,
            expected_revision=investigation.revision,
            outcome=outcome,
            assignable_cause=(
                f"{REASON}: a cause stated to test the refusal" if outcome == "invalidated" else ""
            ),
            reason=f"{REASON}: conclusion ({outcome})",
        )

    def amend(self, report, *, expected_version):
        report.refresh_from_db()
        _evidence, evidence_hash, _ = reporting.preview(Lot.objects.get(pk=report.lot_id))
        return reporting.amend_report(
            actor=self.people["quality"],
            pin=self.pin("quality"),
            report=report,
            expected_version=expected_version,
            evidence_hash=evidence_hash,
            reason=f"{REASON}: the recipient's order number is added",
            remarks="Synthetic order number PO-ACC-0001",
        )

    # --- Report -----------------------------------------------------------------------------

    def environment(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('server_version'), current_database()")
            server, database = cursor.fetchone()
        release = running_release()
        return {
            "application": lot_record.application(),
            "release": release or "not stated (set SOURCE_REVISION to the deployed commit)",
            "database": {"engine": "PostgreSQL", "server_version": server, "name": database},
            "python": sys.version.split()[0],
            "django": django.get_version(),
            "platform": platform.platform(),
        }

    def _environment_or_unknown(self):
        try:
            return self.environment()
        except Exception as error:  # The database may be what failed.
            unknown = f"unavailable ({type(error).__name__})"
            return {
                "application": lot_record.application(),
                "release": running_release() or unknown,
                "database": {"engine": "PostgreSQL", "server_version": unknown, "name": unknown},
                "python": sys.version.split()[0],
                "django": django.get_version(),
                "platform": platform.platform(),
            }

    def report(self, finished):
        everything = [self.setup, *self.journeys]
        steps = [step for journey in everything for step in journey.steps]
        return {
            "schema": SCHEMA,
            "statement": STATEMENT,
            "run": {
                "operator": self.operator,
                "started_at": self.started.astimezone(UTC).isoformat(timespec="seconds"),
                "finished_at": finished.astimezone(UTC).isoformat(timespec="seconds"),
                "stamp": self.stamp,
            },
            "environment": getattr(self, "where", None) or self._environment_or_unknown(),
            "outcome": "passed" if self.passed else "failed",
            "summary": {
                "journeys": len(self.journeys),
                "journeys_passed": sum(j.outcome == "passed" for j in self.journeys),
                "steps": len(steps),
                "steps_passed": sum(s.outcome == "passed" for s in steps),
                "steps_failed": sum(s.outcome == "failed" for s in steps),
            },
            "people": [
                {
                    "username": user.username,
                    "roles": list(PEOPLE[who][0]),
                    "does": PEOPLE[who][1],
                }
                for who, user in self.people.items()
            ],
            "configuration": self.setup.as_dict(),
            "journeys": [journey.as_dict() for journey in self.journeys],
        }


def _cell(value):
    return html.escape(str(value))


def render_html(report):
    """A printable page of the report: the same content as report.json, for people."""
    run, env, summary = report["run"], report["environment"], report["summary"]
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>Acceptance journeys · OpenBGA QM LIMS</title>",
        "<style>body{font:14px/1.45 system-ui,sans-serif;margin:2rem;max-width:72rem}"
        "table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}"
        "th,td{border:1px solid #999;padding:.3rem .45rem;text-align:left;vertical-align:top}"
        "th{background:#eee}.failed{font-weight:700}code{font-size:.9em}"
        ".sign th{width:30%}.sign td{height:2.2rem}@media print{body{margin:0}}</style>",
        "</head><body>",
        "<h1>Acceptance journeys</h1>",
        f"<p><strong>Outcome: {_cell(report['outcome'])}</strong>. "
        f"{summary['journeys_passed']} of {summary['journeys']} journeys passed; "
        f"{summary['steps_passed']} of {summary['steps']} steps passed, "
        f"{summary['steps_failed']} failed.</p>",
        f"<p>{_cell(report['statement'])}</p>",
        "<h2>Run</h2><table>",
        f"<tr><th>Operator</th><td>{_cell(run['operator'])}</td></tr>",
        f"<tr><th>Started</th><td>{_cell(run['started_at'])}</td></tr>",
        f"<tr><th>Finished</th><td>{_cell(run['finished_at'])}</td></tr>",
        f"<tr><th>Application</th><td>{_cell(env['application']['name'])} "
        f"{_cell(env['application']['version'])}</td></tr>",
        f"<tr><th>Release</th><td><code>{_cell(env['release'])}</code></td></tr>",
        f"<tr><th>Database</th><td>{_cell(env['database']['engine'])} "
        f"{_cell(env['database']['server_version'])}, database "
        f"<code>{_cell(env['database']['name'])}</code></td></tr>",
        f"<tr><th>Python, Django</th><td>{_cell(env['python'])}, {_cell(env['django'])}</td></tr>",
        f"<tr><th>Platform</th><td>{_cell(env['platform'])}</td></tr>",
        "</table>",
        "<h2>Synthetic accounts</h2>",
        "<p>Created for the run. Their passwords and PINs were random and held in memory "
        "during the run; they were never shown, and only their hashes are stored.</p>",
        "<table><tr><th>Account</th><th>Roles</th><th>Does</th></tr>",
    ]
    for person in report["people"]:
        parts.append(
            f"<tr><td><code>{_cell(person['username'])}</code></td>"
            f"<td>{_cell(', '.join(person['roles']))}</td><td>{_cell(person['does'])}</td></tr>"
        )
    parts.append("</table>")
    for journey in [report["configuration"], *report["journeys"]]:
        parts.append(f"<h2>{_cell(journey['title'])}</h2>")
        parts.append(f"<p>{_cell(journey['purpose'])} Outcome: ")
        parts.append(f"<strong>{_cell(journey['outcome'])}</strong>.")
        if journey["lots"]:
            parts.append(f" Lots: {_cell(', '.join(journey['lots']))}.")
        parts.append("</p>")
        parts.append(
            "<table><tr><th>Step</th><th>Action</th><th>Expected</th><th>Observed</th>"
            "<th>Outcome</th><th>Requirements</th></tr>"
        )
        for step in journey["steps"]:
            mark = ' class="failed"' if step["outcome"] == "failed" else ""
            parts.append(
                f"<tr><td>{_cell(step['number'])}</td><td>{_cell(step['action'])}</td>"
                f"<td>{_cell(step['expected'])}</td><td>{_cell(step['observed'])}</td>"
                f"<td{mark}>{_cell(step['outcome'])}</td>"
                f"<td>{_cell(', '.join(step['requirements']))}</td></tr>"
            )
        parts.append("</table>")
        if journey["files"]:
            parts.append("<table><tr><th>Evidence file</th><th>Size</th><th>SHA-256</th></tr>")
            for entry in journey["files"]:
                parts.append(
                    f"<tr><td><code>{_cell(entry['path'])}</code></td>"
                    f"<td>{entry['size']}</td><td><code>{_cell(entry['sha256'])}</code></td></tr>"
                )
            parts.append("</table>")
    parts += [
        "<h2>The laboratory's review</h2>",
        "<p>For the laboratory to complete under its own procedures: whether the run is "
        "adequate evidence for its purpose, the issues found and their resolution, and the "
        "conclusion.</p>",
        '<table class="sign"><tr><th>Purpose of the run</th><td></td></tr>'
        "<tr><th>Issues and resolution</th><td></td></tr>"
        "<tr><th>Conclusion</th><td></td></tr>"
        "<tr><th>Reviewed by, date and signature</th><td></td></tr></table>",
        "<p>Check the files of this folder with <code>sha256sum -c SHA256SUMS</code>.</p>",
        "</body></html>",
    ]
    return "\n".join(parts) + "\n"


def write_report(run, output):
    """Write report.json, report.html and SHA256SUMS (of every file in the folder); return the
    report."""
    report = run.report(timezone.now())
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (output / "report.html").write_text(render_html(report), encoding="utf-8")
    lines = []
    sums = output / "SHA256SUMS"
    for path in sorted(p for p in output.rglob("*") if p.is_file() and p != sums):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(output).as_posix()}\n")
    sums.write_text("".join(lines), encoding="utf-8")
    return report
