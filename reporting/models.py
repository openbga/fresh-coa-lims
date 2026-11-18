from django.conf import settings
from django.db import models
from django.db.models import Q


class Report(models.Model):
    """Identity and mutable head of one certificate of analysis (CoA) series.

    The head only advances through signed transitions (`revision` is the signed record revision).
    All issued content lives in immutable `ReportVersion` rows. A signed withdrawal ends the
    series for good: its versions and their PDF bytes stay as issued, and a later certificate
    for the same lot and recipient is a new series with its own number.
    """

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="reports")
    recipient = models.CharField(max_length=160, blank=True)
    # The scope (a customer or a market) whose specification the certificate reports, or ""
    # for all of the lot's requirements. Set when the series is opened and never changed (the
    # head guard keeps every identity column).
    scope = models.CharField(
        "certificate for",
        max_length=60,
        blank=True,
        help_text="The scope of the lot whose specification the certificate reports; blank for "
        "all of the lot's requirements.",
    )
    sequence = models.PositiveIntegerField()
    number = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=16, default="draft")
    # Number of issued versions; the stale-check counter shown to the signer.
    version_count = models.PositiveIntegerField(default=0)
    current_snapshot_hash = models.CharField(max_length=64, blank=True)
    current_pdf_sha256 = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)
    # Set once, by the signed withdrawal (database-guarded, migrations/0003).
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField("reason for withdrawal", blank=True)
    withdrawal_reference = models.CharField(
        "withdrawal reference",
        max_length=200,
        blank=True,
        help_text="The impact assessment, deviation or other quality-system record behind the "
        'withdrawal, e.g. "IA-3".',
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # One current series per lot and recipient; a withdrawn one leaves room for a new one.
            models.UniqueConstraint(
                fields=["lot", "recipient"],
                condition=~Q(state="withdrawn"),
                name="report_lot_recipient_current",
            ),
            models.UniqueConstraint(fields=["lot", "sequence"], name="report_lot_sequence"),
            models.CheckConstraint(
                condition=Q(state__in=["draft", "issued", "withdrawn"]), name="report_state"
            ),
            # The withdrawal details exist exactly when the certificate is withdrawn.
            models.CheckConstraint(
                condition=(
                    Q(state="withdrawn", withdrawn_at__isnull=False) & ~Q(withdrawal_reason="")
                )
                | (
                    ~Q(state="withdrawn")
                    & Q(withdrawn_at__isnull=True, withdrawal_reason="", withdrawal_reference="")
                ),
                name="report_withdrawal_details",
            ),
        ]

    def __str__(self):
        return self.number

    @property
    def tone(self):
        if self.state == "withdrawn":
            return "danger"
        return "success" if self.state == "issued" else "neutral"

    @property
    def status_label(self):
        if self.state == "withdrawn":
            return "Withdrawn"
        if self.state != "issued":
            return "Not issued"
        return "Issued" if self.version_count == 1 else "Amended"

    @property
    def awaiting_notification(self):
        """Withdrawn, and no recipient notification is recorded yet. A list that annotates
        ``notified`` (an Exists over the notifications) is answered without a query per row."""
        if self.state != "withdrawn":
            return False
        notified = getattr(self, "notified", None)
        return not (self.notifications.exists() if notified is None else notified)


class ReportVersion(models.Model):
    """One issued certificate: frozen evidence snapshot, issued bytes and checksums."""

    report = models.ForeignKey(Report, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    kind = models.CharField(max_length=16)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by"
    )
    reason = models.TextField()
    remarks = models.TextField(blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField()
    lot_revision = models.PositiveIntegerField()
    # Signed `Report.revision` that carries this version's electronic signature.
    report_revision = models.PositiveIntegerField()
    evidence_hash = models.CharField(max_length=64)
    snapshot = models.JSONField()
    snapshot_hash = models.CharField(max_length=64)
    pdf = models.BinaryField()
    pdf_sha256 = models.CharField(max_length=64)
    pdf_size = models.PositiveIntegerField()

    class Meta:
        ordering = ["report_id", "number"]
        constraints = [
            models.UniqueConstraint(fields=["report", "number"], name="reportversion_number"),
            models.UniqueConstraint(
                fields=["report", "report_revision"], name="reportversion_revision"
            ),
        ]

    def __str__(self):
        return f"{self.report.number} v{self.number}"

    @property
    def is_current(self):
        return self.number == self.report.version_count


class RecipientNotification(models.Model):
    """Evidence that a recipient was told that a certificate is withdrawn: who, when, how, and
    where the notice and any acknowledgement are kept. Append-only (database-guarded,
    migrations/0003); it never changes the certificate's head or its signed revision."""

    class Means(models.TextChoices):
        EMAIL = "email", "Email"
        LETTER = "letter", "Letter"
        TELEPHONE = "telephone", "Telephone"
        IN_PERSON = "in_person", "In person"
        OTHER = "other", "Other"

    report = models.ForeignKey(Report, on_delete=models.PROTECT, related_name="notifications")
    recipient = models.CharField("recipient notified", max_length=160)
    notified_on = models.DateField("date notified")
    means = models.CharField(max_length=16, choices=Means.choices)
    evidence_ref = models.CharField(
        "evidence reference",
        max_length=200,
        help_text="Where the notice and any acknowledgement are kept.",
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["notified_on", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(means__in=["email", "letter", "telephone", "in_person", "other"]),
                name="recipientnotification_means",
            ),
            models.CheckConstraint(
                condition=~Q(means="other") | ~Q(note=""), name="recipientnotification_other_note"
            ),
        ]

    def __str__(self):
        return f"Notification of {self.recipient} on {self.notified_on.isoformat()}"
