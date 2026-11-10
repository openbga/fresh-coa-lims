from django.conf import settings
from django.db import models


class Report(models.Model):
    """Identity and mutable head of one certificate of analysis (CoA) series.

    The head only advances through signed transitions (`revision` is the signed record revision).
    All issued content lives in immutable `ReportVersion` rows.
    """

    lot = models.ForeignKey("quality.Lot", on_delete=models.PROTECT, related_name="reports")
    recipient = models.CharField(max_length=160, blank=True)
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

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["lot", "recipient"], name="report_lot_recipient"),
            models.UniqueConstraint(fields=["lot", "sequence"], name="report_lot_sequence"),
        ]

    def __str__(self):
        return self.number

    @property
    def tone(self):
        return "success" if self.state == "issued" else "neutral"

    @property
    def status_label(self):
        if self.state != "issued":
            return "Not issued"
        return "Issued" if self.version_count == 1 else "Amended"


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
