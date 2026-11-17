from django.conf import settings
from django.db import models
from django.db.models import Q

from catalog.units import QUANTITY_UNITS, plain


class LotState(models.TextChoices):
    QUARANTINE = "quarantine", "Quarantine"
    RELEASED = "released", "Released"
    # Signed decisions that end a lot's quarantine without releasing it. A rejected lot failed
    # its requirements or cannot be used; a cancelled lot was received in error. Neither
    # changes again, and the evidence frozen with the signature names the decision.
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class Lot(models.Model):
    number = models.CharField(max_length=80, unique=True)
    material = models.CharField(max_length=160)
    rules = models.ForeignKey("core.RuleSet", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=24, choices=LotState, default=LotState.QUARANTINE)
    disposition_evidence = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(state__in=LotState.values), name="lot_state_known"),
        ]

    def __str__(self):
        return self.number

    @property
    def decision(self):
        """The signed rejection or cancellation frozen on the lot, or None."""
        if self.state in (LotState.REJECTED, LotState.CANCELLED):
            return self.disposition_evidence
        return None


class ReceiptSource(models.TextChoices):
    SUPPLIER = "supplier", "Received from a supplier"
    ON_SITE = "on_site", "Made on site"


class ReceiptCondition(models.TextChoices):
    ACCEPTABLE = "acceptable", "No discrepancy found"
    DISCREPANCY = "discrepancy", "Discrepancy found"


class LotReceipt(models.Model):
    """Where a lot came from and what arrived. Append-only; a correction adds a linked record.

    A lot has one original record and a single chain of corrections; the record that nothing
    corrects is the current one.
    """

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="receipts")
    source = models.CharField(max_length=12, choices=ReceiptSource.choices)
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="receipts",
    )
    supplier_lot = models.CharField("Supplier lot number", max_length=80, blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    manufacturer_location = models.CharField(max_length=160, blank=True)
    manufacturer_lot = models.CharField("Manufacturer lot number", max_length=80, blank=True)
    shipment_ref = models.CharField("Delivery or batch document", max_length=120)
    received_on = models.DateField("Date received")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    quantity_unit = models.CharField(max_length=8, choices=QUANTITY_UNITS)
    containers = models.PositiveIntegerField("Number of containers")
    container_description = models.CharField("Containers", max_length=160)
    condition = models.CharField(
        "Examination on receipt", max_length=12, choices=ReceiptCondition.choices
    )
    condition_notes = models.TextField("Examination notes", blank=True)
    reason = models.TextField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    corrects = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrected_by"
    )

    class Meta:
        ordering = ["recorded_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lot"], condition=Q(corrects__isnull=True), name="lot_receipt_one_original"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="lot_receipt_quantity"),
            models.CheckConstraint(condition=Q(containers__gte=1), name="lot_receipt_containers"),
            models.CheckConstraint(
                condition=(Q(source="supplier") & Q(supplier__isnull=False))
                | (
                    Q(source="on_site")
                    & Q(supplier__isnull=True)
                    & Q(supplier_lot="")
                    & Q(manufacturer="")
                    & Q(manufacturer_location="")
                    & Q(manufacturer_lot="")
                ),
                name="lot_receipt_source_shape",
            ),
            models.CheckConstraint(
                condition=~Q(manufacturer="")
                | (Q(manufacturer_location="") & Q(manufacturer_lot="")),
                name="lot_receipt_manufacturer_named",
            ),
            models.CheckConstraint(
                condition=Q(condition="acceptable")
                | (Q(condition="discrepancy") & ~Q(condition_notes="")),
                name="lot_receipt_examination",
            ),
            models.CheckConstraint(
                condition=~Q(shipment_ref="") & ~Q(container_description="") & ~Q(reason=""),
                name="lot_receipt_stated",
            ),
        ]

    def __str__(self):
        return f"Receipt of {self.lot}"

    @property
    def quantity_text(self):
        return plain(self.quantity)

    @property
    def has_discrepancy(self):
        return self.condition == ReceiptCondition.DISCREPANCY


class LotDates(models.Model):
    """The expiry date and the retest date of a lot's material. Append-only.

    A lot has at most one original record and a single chain of corrections; the record that
    nothing replaces is the one in force. Records are added only while the lot is in quarantine:
    the release freezes the one in force. The expiry date is the last day the material may be
    used; the retest date is the day it must be examined again before further use. A correction
    may state neither date, when the lot has none after all.
    """

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="dates")
    expiry_on = models.DateField("Expiry date", null=True, blank=True)
    retest_on = models.DateField("Retest date", null=True, blank=True)
    basis = models.TextField(
        "Basis",
        blank=True,
        help_text="Where the dates come from: the supplier's label or certificate, or the "
        "shelf life or retest period the laboratory assigned and its reference.",
    )
    reason = models.TextField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    replaces = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="replaced_by"
    )

    class Meta:
        ordering = ["recorded_at", "id"]
        verbose_name = "expiry and retest dates"
        verbose_name_plural = "expiry and retest dates"
        constraints = [
            models.UniqueConstraint(
                fields=["lot"], condition=Q(replaces__isnull=True), name="lot_dates_one_original"
            ),
            # A retest date after the expiry date would never be reached in use.
            models.CheckConstraint(
                condition=Q(expiry_on__isnull=True)
                | Q(retest_on__isnull=True)
                | Q(retest_on__lte=models.F("expiry_on")),
                name="lot_dates_retest_by_expiry",
            ),
            # Dates come with their basis; a record without dates is a correction to none.
            models.CheckConstraint(
                condition=(
                    (Q(expiry_on__isnull=False) | Q(retest_on__isnull=False))
                    & ~Q(basis__regex=r"^\s*$")
                )
                | Q(expiry_on__isnull=True, retest_on__isnull=True, replaces__isnull=False),
                name="lot_dates_stated",
            ),
            models.CheckConstraint(condition=~Q(reason__regex=r"^\s*$"), name="lot_dates_reason"),
        ]

    def __str__(self):
        return f"Dates of {self.lot}"

    @property
    def stated(self):
        return self.expiry_on is not None or self.retest_on is not None


class SupplierCertificate(models.Model):
    """What a supplier's certificate of analysis states for a lot. Append-only.

    These are the supplier's results, never the laboratory's own tests. A correction adds a
    linked record and a withdrawal adds a withdrawal record; the record that nothing corrects is
    the current one of its chain. A lot may hold several certificates.
    """

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="supplier_certificates")
    number = models.CharField("Certificate number", max_length=80)
    issued_by = models.CharField(max_length=160)
    issued_on = models.DateField("Date of the certificate")
    stated_lot = models.CharField("Lot number on the certificate", max_length=80)
    document_ref = models.CharField("Where the certificate is kept", max_length=200)
    notes = models.TextField(blank=True)
    result_count = models.PositiveSmallIntegerField(
        help_text="Number of results the record holds; the database accepts no more."
    )
    reason = models.TextField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    corrects = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrected_by"
    )

    class Meta:
        ordering = ["recorded_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(result_count__gte=1), name="supplier_certificate_has_results"
            ),
            models.CheckConstraint(
                condition=~Q(number="")
                & ~Q(issued_by="")
                & ~Q(stated_lot="")
                & ~Q(document_ref="")
                & ~Q(reason=""),
                name="supplier_certificate_stated",
            ),
        ]

    def __str__(self):
        return f"Supplier certificate {self.number} for {self.lot}"


class SupplierCertificateResult(models.Model):
    """One result stated on a supplier's certificate, against one requirement of the lot.

    ``requirement`` is the lot's approved requirement the result was compared with, frozen with
    its hash; ``conforms`` is that comparison and is never recalculated.
    """

    certificate = models.ForeignKey(
        SupplierCertificate, on_delete=models.PROTECT, related_name="results"
    )
    position = models.PositiveSmallIntegerField()
    test_code = models.CharField(max_length=80)
    value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    qualifier = models.CharField(max_length=1, blank=True)
    outcome = models.CharField(max_length=20, blank=True)
    value_text = models.CharField(max_length=40, help_text="Result exactly as recorded")
    stated_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Wording of a qualitative result on the certificate",
    )
    method = models.CharField(max_length=200, blank=True)
    limits = models.CharField(max_length=200, blank=True)
    requirement = models.JSONField()
    requirement_hash = models.CharField(max_length=64)
    conforms = models.BooleanField()

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["certificate", "test_code"], name="supplier_result_one_per_test"
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(outcome="")
                    & Q(value__isnull=True)
                    & Q(qualifier="")
                    & ~Q(stated_text__regex=r"^\s*$")
                )
                | (
                    Q(outcome="")
                    & Q(value__isnull=False)
                    & Q(qualifier__in=["", "<"])
                    & Q(stated_text="")
                ),
                name="supplier_result_shape",
            ),
            models.CheckConstraint(
                condition=~Q(test_code="") & ~Q(value_text="") & ~Q(requirement_hash=""),
                name="supplier_result_stated",
            ),
        ]

    def __str__(self):
        return f"{self.test_code} on {self.certificate}"


class SupplierCertificateWithdrawal(models.Model):
    """States that a supplier certificate record is void, for example recorded on the wrong lot.

    The certificate and its results are kept; a withdrawn certificate cannot be corrected.
    """

    certificate = models.OneToOneField(
        SupplierCertificate, on_delete=models.PROTECT, related_name="withdrawal"
    )
    reason = models.TextField()
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    withdrawn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(reason=""), name="supplier_certificate_withdrawal_reason"
            ),
        ]

    def __str__(self):
        return f"Withdrawal of {self.certificate}"


class SupplierResultAcceptance(models.Model):
    """A result stated on a supplier's certificate, accepted in place of the laboratory's own
    test of one requirement of the lot.

    An analyst proposes it and a reviewer who authored none of the certificate records signs
    it. ``evidence`` is what was relied on when it was proposed: the stated result, the
    certificate, the supplier, the receipt, the supplier qualification and the rule set. The
    record is never edited: it is accepted or withdrawn, and a withdrawn one is replaced by a
    new proposal. Only one proposal or acceptance stands for a requirement of a lot at a time.
    """

    class State(models.TextChoices):
        PROPOSED = "proposed", "Awaiting acceptance"
        ACCEPTED = "accepted", "Accepted"
        WITHDRAWN = "withdrawn", "Withdrawn"

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="supplier_acceptances")
    test_code = models.CharField(max_length=80)
    result = models.ForeignKey(
        SupplierCertificateResult, on_delete=models.PROTECT, related_name="acceptances"
    )
    qualification = models.ForeignKey(
        "suppliers.SupplierQualification", on_delete=models.PROTECT, related_name="acceptances"
    )
    requirement_hash = models.CharField(max_length=64)
    evidence = models.JSONField()
    state = models.CharField(max_length=12, choices=State, default=State.PROPOSED)
    reason = models.TextField()
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    proposed_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["proposed_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lot", "test_code"],
                condition=Q(state__in=["proposed", "accepted"]),
                name="supplier_acceptance_one_standing",
            ),
            models.CheckConstraint(
                condition=~Q(test_code="") & ~Q(requirement_hash="") & ~Q(reason__regex=r"^\s*$"),
                name="supplier_acceptance_stated",
            ),
            # Each state carries exactly the marks of the steps behind it.
            models.CheckConstraint(
                condition=Q(
                    state="proposed",
                    accepted_at__isnull=True,
                    withdrawn_at__isnull=True,
                    withdrawn_by__isnull=True,
                    withdrawal_reason="",
                )
                | Q(
                    state="accepted",
                    accepted_at__isnull=False,
                    withdrawn_at__isnull=True,
                    withdrawn_by__isnull=True,
                    withdrawal_reason="",
                )
                | (
                    Q(state="withdrawn", withdrawn_at__isnull=False, withdrawn_by__isnull=False)
                    & ~Q(withdrawal_reason__regex=r"^\s*$")
                ),
                name="supplier_acceptance_steps",
            ),
        ]

    @property
    def label(self):
        return f"SRA-{self.pk}"

    @property
    def stands(self):
        return self.state != self.State.WITHDRAWN

    def __str__(self):
        return f"{self.label} {self.test_code} of {self.lot}"


class Sample(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="samples")
    reference = models.CharField(max_length=80, unique=True)
    collected_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self):
        return self.reference


class Result(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="results")
    test_code = models.CharField(max_length=80)
    value = models.DecimalField(max_digits=20, decimal_places=8)
    unit = models.CharField(max_length=40)
    lower_limit = models.DecimalField(max_digits=20, decimal_places=8)
    upper_limit = models.DecimalField(max_digits=20, decimal_places=8)
    analyst = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=24, default="recorded")
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sample", "test_code"], name="sample_test_unique"),
            models.CheckConstraint(
                condition=models.Q(lower_limit__lte=models.F("upper_limit")),
                name="result_limits_ordered",
            ),
        ]

    @property
    def conforms(self):
        return self.lower_limit <= self.value <= self.upper_limit
