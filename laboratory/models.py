"""Laboratory operations evidence: equipment fitness, analyst qualification, reagents/standards.

Records are append-oriented. Controlled fields are frozen by PostgreSQL triggers (see migration
0002); only the lifecycle columns named there can change, and every change bumps `revision`.
Dates named `*_date`/`valid_*` are inclusive calendar days in the deployment time zone.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone

from core import device_formats

http_url = URLValidator(schemes=["http", "https"])


def evidence_url():
    """External controlled-document link. Untrusted text: only http(s) is accepted."""
    return models.URLField(blank=True, max_length=500, validators=[http_url])


class Equipment(models.Model):
    class State(models.TextChoices):
        IN_SERVICE = "in_service", "In service"
        OUT_OF_SERVICE = "out_of_service", "Out of service"

    asset_id = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=160)
    category = models.CharField(max_length=80, help_text="For example balance, HPLC, chamber.")
    location = models.CharField(max_length=120, blank=True)
    requires_qualification = models.BooleanField(
        default=True,
        help_text="Require approved installation/operational/performance qualification evidence.",
    )
    state = models.CharField(max_length=20, choices=State, default=State.IN_SERVICE)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["asset_id"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return self.asset_id

    @property
    def connection(self):
        """The current data connection, or None (from a prefetch of ``connections`` when made)."""
        return next((c for c in self.connections.all() if c.ended_at is None), None)


class DeviceConnection(models.Model):
    """How readings are taken from a balance or meter connected to the analyst's computer.

    The device's output format and serial settings, and the serial number the device reports when
    its format reports one. Recorded by quality; append-only. Setting a new connection ends the
    current one, and an ended connection stays in the record with the readings taken through it.
    Only ``ended_at``, ``ended_by`` and ``revision`` change, once (migration 0005).
    """

    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="connections")
    device_format = models.CharField(
        "Output format", max_length=20, choices=device_formats.FORMAT_CHOICES
    )
    baud_rate = models.PositiveIntegerField(
        choices=[(rate, str(rate)) for rate in device_formats.BAUD_RATES]
    )
    data_bits = models.PositiveSmallIntegerField(choices=[(7, "7"), (8, "8")])
    parity = models.CharField(
        max_length=4, choices=[(p, p.title()) for p in device_formats.PARITIES]
    )
    stop_bits = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2")])
    flow_control = models.CharField(
        max_length=8,
        choices=[("none", "None"), ("hardware", "Hardware (RTS/CTS)")],
        default="none",
    )
    serial_number = models.CharField(
        max_length=device_formats.MAX_SERIAL,
        blank=True,
        help_text="As the device reports it. Required for a format that reports one: a reading "
        "from a device with another serial number is refused.",
    )
    verification_ref = models.CharField(
        "Verification record",
        max_length=200,
        help_text="Where the check that readings arrive unchanged through this connection is "
        "recorded, with its revision.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["equipment"],
                condition=models.Q(ended_at__isnull=True),
                name="device_connection_one_current",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True, ended_by__isnull=True)
                | models.Q(ended_at__isnull=False, ended_by__isnull=False),
                name="device_connection_ended_by",
            ),
            models.CheckConstraint(
                condition=~models.Q(verification_ref__regex=r"^\s*$"),
                name="device_connection_verified",
            ),
        ]

    @property
    def format(self):
        return device_formats.get(self.device_format)

    @property
    def settings_text(self):
        """Serial settings in the usual short form, e.g. "9600 baud, 8N1, no flow control"."""
        flow = "hardware flow control" if self.flow_control == "hardware" else "no flow control"
        frame = f"{self.data_bits}{self.parity[0].upper()}{self.stop_bits}"
        return f"{self.baud_rate} baud, {frame}, {flow}"

    def clean(self):
        if not self.device_format:
            return
        identifies = self.format.identifies
        if identifies and not self.serial_number.strip():
            raise ValidationError(
                {
                    "serial_number": "Enter the serial number the device reports; this format "
                    "reports it with every reading."
                }
            )
        if not identifies and self.serial_number:
            raise ValidationError(
                {"serial_number": "This format does not report a serial number; leave it empty."}
            )
        if self.serial_number != self.serial_number.strip():
            raise ValidationError(
                {"serial_number": "Enter the serial number without spaces around it."}
            )

    def evidence(self):
        """What a reading keeps of the connection it was taken through."""
        return {
            "id": self.pk,
            "equipment": self.equipment_id,
            "asset_id": self.equipment.asset_id,
            "format": self.device_format,
            "settings": self.settings_text,
            "serial_number": self.serial_number,
            "verification_ref": self.verification_ref,
        }

    def browser(self):
        """What the analyst's browser needs to take a reading through this connection."""
        return {
            "equipment": self.equipment_id,
            "asset_id": self.equipment.asset_id,
            "description": self.equipment.description,
            "connection": self.pk,
            "format": self.device_format,
            "kind": self.format.kind,
            "open": {
                "baudRate": self.baud_rate,
                "dataBits": self.data_bits,
                "parity": self.parity,
                "stopBits": self.stop_bits,
                "flowControl": self.flow_control,
            },
            "steps": self.format.browser(),
        }

    def __str__(self):
        return f"{self.equipment.asset_id} · {self.format.label}"


class Calibration(models.Model):
    """One calibration/verification event. Failed events block use as soon as recorded;
    passing events count only after independent signed acceptance."""

    class Outcome(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting acceptance"
        ACCEPTED = "accepted", "Accepted"

    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="calibrations")
    performed_at = models.DateTimeField()
    due_date = models.DateField(help_text="Last day the calibration remains valid (inclusive).")
    outcome = models.CharField(max_length=8, choices=Outcome)
    standard_ref = models.CharField(
        max_length=200, help_text="Reference standard or certificate providing traceability."
    )
    certificate_ref = models.CharField(max_length=200, blank=True)
    certificate_url = evidence_url()
    tolerance_note = models.TextField(blank=True, help_text="As-found/as-left values and limits.")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-performed_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state="recorded", accepted_at__isnull=True)
                | models.Q(state="accepted", accepted_at__isnull=False),
                name="calibration_acceptance_time",
            )
        ]

    def clean(self):
        if self.performed_at and self.due_date:
            # Dates are calendar days in the deployment (laboratory) time zone, not UTC.
            performed_on = (
                timezone.localdate(self.performed_at)
                if timezone.is_aware(self.performed_at)
                else self.performed_at.date()
            )
            if self.due_date < performed_on:
                raise ValidationError("The due date cannot precede the calibration date.")

    def __str__(self):
        return f"{self.equipment} calibration {self.performed_at:%Y-%m-%d}"


class TrainingRecord(models.Model):
    """A person's training in a method, procedure or activity, as evidence for their
    qualifications. Someone else records it; the trainee acknowledges it with a signature. The
    record is immutable apart from that acknowledgement (database guard, migration 0006)."""

    class Kind(models.TextChoices):
        READ = "read", "Read and understood"
        INSTRUCTION = "instruction", "Instruction or demonstration"
        SUPERVISED = "supervised", "Supervised practice"
        ASSESSMENT = "assessment", "Assessment of competence"

    class Outcome(models.TextChoices):
        COMPLETED = "completed", "Completed"
        COMPETENT = "competent", "Competent"
        NOT_YET_COMPETENT = "not_yet_competent", "Not yet competent"

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting acknowledgement"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"

    trainee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    activity = models.CharField(
        max_length=120, help_text="Method or activity code, as qualifications name it."
    )
    document_ref = models.CharField(
        "Procedure or course",
        max_length=200,
        help_text="The controlled procedure, method or course trained on, with its revision.",
    )
    kind = models.CharField(max_length=16, choices=Kind)
    outcome = models.CharField(max_length=20, choices=Outcome)
    trainer = models.CharField(
        "Trainer or assessor",
        max_length=160,
        help_text="Who gave the training or assessed it, or the provider of an outside course.",
    )
    completed_on = models.DateField(help_text="The day the training or assessment was completed.")
    evidence_ref = models.CharField(
        "Evidence reference",
        max_length=200,
        blank=True,
        help_text="Where the signed training record, test or certificate is kept.",
    )
    evidence_url = evidence_url()
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=14, choices=State, default=State.RECORDED)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-completed_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind="assessment", outcome__in=["competent", "not_yet_competent"])
                    | (~models.Q(kind="assessment") & models.Q(outcome="completed"))
                ),
                name="training_outcome_of_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(state="recorded", acknowledged_at__isnull=True)
                | models.Q(state="acknowledged", acknowledged_at__isnull=False),
                name="training_acknowledged_when_signed",
            ),
        ]

    @property
    def identifier(self):
        return f"TRN-{self.pk}"

    @property
    def supports_qualification(self):
        """Acknowledged, and not an assessment that found the trainee not yet competent."""
        return (
            self.state == self.State.ACKNOWLEDGED and self.outcome != self.Outcome.NOT_YET_COMPETENT
        )

    def __str__(self):
        return f"{self.identifier} · {self.activity}"


class Qualification(models.Model):
    """Approved evidence that an analyst is qualified for an activity/method, or that an
    instrument is qualified for its intended use. Exactly one subject.

    A person's qualification is for performing the work or for reviewing its results (``work``);
    an instrument's is always for performing. It may cite the person's acknowledged training
    records (``training``, their ids), frozen with the record and bound by its approval."""

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REVOKED = "revoked", "Revoked"

    class Work(models.TextChoices):
        PERFORM = "perform", "Performing the work"
        REVIEW = "review", "Reviewing results"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    equipment = models.ForeignKey(
        Equipment, null=True, blank=True, on_delete=models.PROTECT, related_name="qualifications"
    )
    activity = models.CharField(
        max_length=120, help_text="Method, activity or qualification stage (e.g. IQ/OQ/PQ)."
    )
    work = models.CharField("Qualified for", max_length=8, choices=Work, default=Work.PERFORM)
    scope_note = models.TextField(blank=True)
    evidence_ref = models.CharField(
        max_length=200, help_text="Controlled training or qualification record and revision."
    )
    evidence_url = evidence_url()
    training = models.JSONField(
        default=list,
        blank=True,
        help_text="Ids of the person's acknowledged training records this evidence relies on.",
    )
    valid_from = models.DateField()
    valid_until = models.DateField(help_text="Last day of validity (inclusive).")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    approved_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False, equipment__isnull=True)
                | models.Q(user__isnull=True, equipment__isnull=False),
                name="qualification_one_subject",
            ),
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | models.Q(work="perform", training=[]),
                name="qualification_equipment_performs",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__gte=models.F("valid_from")),
                name="qualification_interval_ordered",
            ),
        ]

    @property
    def subject(self):
        return self.user or self.equipment

    def __str__(self):
        return f"{self.subject} · {self.activity}"


class ReagentLot(models.Model):
    """Reagent, reference standard or prepared solution with provenance and independent release."""

    class Kind(models.TextChoices):
        REAGENT = "reagent", "Reagent"
        STANDARD = "reference_standard", "Reference standard"
        PREPARED = "prepared_solution", "Prepared solution"

    class State(models.TextChoices):
        RECEIVED = "received", "Awaiting release"
        RELEASED = "released", "Released for use"
        REJECTED = "rejected", "Rejected"

    identifier = models.CharField(max_length=60, unique=True)
    kind = models.CharField(max_length=24, choices=Kind)
    name = models.CharField(max_length=160)
    supplier = models.CharField(max_length=160, blank=True)
    lot_number = models.CharField(max_length=80)
    received_on = models.DateField(help_text="Receipt or preparation date.")
    expiry_date = models.DateField(help_text="Last day of use (inclusive).")
    assigned_purity = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    purity_unit = models.CharField(max_length=20, blank=True, help_text="For example % w/w.")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="preparations",
        help_text="Source lot for a prepared solution.",
    )
    preparation_note = models.TextField(blank=True, help_text="Diluent, amounts and calculation.")
    certificate_ref = models.CharField(max_length=200, blank=True)
    certificate_url = evidence_url()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECEIVED)
    released_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expiry_date__gte=models.F("received_on")),
                name="reagent_expiry_after_receipt",
            ),
            models.CheckConstraint(
                condition=models.Q(assigned_purity__isnull=True, purity_unit="")
                | models.Q(assigned_purity__isnull=False) & ~models.Q(purity_unit=""),
                name="reagent_purity_has_unit",
            ),
        ]

    def __str__(self):
        return f"{self.identifier} {self.name}"


class ResourceUse(models.Model):
    """Append-only evidence that an eligible resource was used for a piece of work."""

    equipment = models.ForeignKey(
        Equipment, null=True, blank=True, on_delete=models.PROTECT, related_name="uses"
    )
    reagent_lot = models.ForeignKey(
        ReagentLot, null=True, blank=True, on_delete=models.PROTECT, related_name="uses"
    )
    context_type = models.CharField(max_length=60, help_text="For example quality.sample.")
    context_id = models.CharField(max_length=64)
    activity = models.CharField(max_length=120)
    test_code = models.CharField(max_length=80, blank=True)
    profile_ref = models.CharField(
        max_length=120, blank=True, help_text="Stable test-profile revision, when known."
    )
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    used_at = models.DateTimeField(auto_now_add=True)
    eligibility = models.JSONField(default=dict)

    class Meta:
        ordering = ["-used_at", "-id"]
        indexes = [models.Index(fields=["context_type", "context_id"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(equipment__isnull=False, reagent_lot__isnull=True)
                | models.Q(equipment__isnull=True, reagent_lot__isnull=False),
                name="resource_use_one_resource",
            )
        ]

    @property
    def resource(self):
        return self.equipment or self.reagent_lot


class ContractLaboratory(models.Model):
    """Identity of an outside laboratory that tests for this one. Immutable once created.

    The register says who the laboratory is. Whether its results may be relied on for a method
    is a separate approved record (`ContractApproval`), never a flag here.
    """

    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=160)
    location = models.CharField(
        max_length=160, help_text="Site that performs the testing: town and country."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "contract laboratories"

    def __str__(self):
        return f"{self.code} · {self.name}"


class ContractApproval(models.Model):
    """Approved evidence that a contract laboratory may perform one method for this laboratory.

    Recorded by one quality person and approved by another with a signature. A result reported
    by the laboratory is accepted only under an approval whose dates include the date of its
    report; a revoked approval is relied on no further.
    """

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REVOKED = "revoked", "Revoked"

    laboratory = models.ForeignKey(
        ContractLaboratory, on_delete=models.PROTECT, related_name="approvals"
    )
    method_code = models.CharField(
        max_length=80, help_text="Code of the test method the laboratory is approved to perform."
    )
    scope_note = models.TextField(blank=True)
    evidence_ref = models.CharField(
        max_length=200,
        help_text="Quality agreement, audit report or accreditation certificate, with its "
        "revision.",
    )
    evidence_url = evidence_url()
    valid_from = models.DateField()
    valid_until = models.DateField(help_text="Last day of validity (inclusive).")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    approved_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_until__gte=models.F("valid_from")),
                name="contract_approval_interval_ordered",
            ),
            models.CheckConstraint(
                condition=~models.Q(method_code__regex=r"^\s*$")
                & ~models.Q(evidence_ref__regex=r"^\s*$"),
                name="contract_approval_stated",
            ),
            # Each state carries exactly the timestamps of the signatures behind it.
            models.CheckConstraint(
                condition=models.Q(
                    state="recorded", approved_at__isnull=True, revoked_at__isnull=True
                )
                | models.Q(state="approved", approved_at__isnull=False, revoked_at__isnull=True)
                | models.Q(state="revoked", approved_at__isnull=False, revoked_at__isnull=False),
                name="contract_approval_signed",
            ),
        ]

    @property
    def label(self):
        return f"CLA-{self.pk}"

    def __str__(self):
        return f"{self.laboratory.code} · {self.method_code}"


class ContractUse(models.Model):
    """Append-only evidence that a contract laboratory's report was accepted for a piece of work,
    and under which approval."""

    approval = models.ForeignKey(ContractApproval, on_delete=models.PROTECT, related_name="uses")
    context_type = models.CharField(max_length=60, help_text="analytical.analyticaltest.")
    context_id = models.CharField(max_length=64)
    method_code = models.CharField(max_length=80)
    test_code = models.CharField(max_length=80, blank=True)
    report_number = models.CharField(max_length=120)
    report_date = models.DateField()
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-used_at", "-id"]
        indexes = [models.Index(fields=["context_type", "context_id"], name="contract_use_context")]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(report_number__regex=r"^\s*$"),
                name="contract_use_report_stated",
            ),
        ]
