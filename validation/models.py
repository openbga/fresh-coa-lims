"""The laboratory's validation records: its acceptance of the system for its intended use, and
its rehearsals of recovery, downtime and upgrades.

Both are recorded by one person and accepted by a different quality person with a signature.
What was recorded is never edited: a correction is a withdrawal and a new record.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from suppliers.models import http_url


def _stated(*names):
    condition = Q()
    for name in names:
        condition &= ~Q(**{f"{name}__regex": r"^\s*$"})
    return condition


class UseAcceptance(models.Model):
    """The laboratory's signed acceptance of the system for its defined use.

    It states what the system is used for, the supported assays (methods), who owns the
    process and the system, and the laboratory's validation report. The signature freezes the
    approved configuration in force and the running release, so later changes can be shown
    against what was accepted. Accepting a newer record supersedes the one before; at most one
    is accepted at a time.
    """

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting acceptance"
        ACCEPTED = "accepted", "Accepted"
        SUPERSEDED = "superseded", "Superseded"
        WITHDRAWN = "withdrawn", "Withdrawn"

    title = models.CharField(
        max_length=160, help_text="Short name of the use, e.g. QC release testing at Site A."
    )
    intended_use = models.TextField(
        help_text="What the laboratory uses the system for: the materials, stages, records and "
        "decisions it supports."
    )
    exclusions = models.TextField(
        "Outside the intended use",
        blank=True,
        help_text="Functions the laboratory does not use, and records it keeps elsewhere.",
    )
    method_codes = models.JSONField(help_text="Codes of the methods that are supported assays.")
    process_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    system_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    other_responsibilities = models.TextField(blank=True)
    validation_ref = models.CharField(
        "Validation report",
        max_length=200,
        help_text="The laboratory's validation report for this use, with its revision.",
    )
    validation_url = models.URLField(blank=True, max_length=500, validators=[http_url])
    open_issues = models.TextField(
        "Known issues and conditions",
        blank=True,
        help_text="Issues found in validation and how each is resolved or restricted.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    # Frozen by the acceptance signature: the approved configuration in force and the release
    # that was running at that moment.
    configuration = models.JSONField(null=True, blank=True)
    configuration_hash = models.CharField(max_length=64, blank=True)
    accepted_release = models.CharField(max_length=80, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=_stated("title", "intended_use", "validation_ref"),
                name="use_acceptance_stated",
            ),
            # Each state carries exactly what its signature or withdrawal wrote.
            models.CheckConstraint(
                condition=Q(
                    state="recorded",
                    configuration__isnull=True,
                    accepted_at__isnull=True,
                    superseded_at__isnull=True,
                    withdrawn_at__isnull=True,
                )
                | Q(
                    state="accepted",
                    configuration__isnull=False,
                    accepted_at__isnull=False,
                    superseded_at__isnull=True,
                    superseded_by__isnull=True,
                    withdrawn_at__isnull=True,
                )
                | Q(
                    state="superseded",
                    configuration__isnull=False,
                    accepted_at__isnull=False,
                    superseded_at__isnull=False,
                    superseded_by__isnull=False,
                    withdrawn_at__isnull=True,
                )
                | Q(
                    state="withdrawn",
                    configuration__isnull=True,
                    accepted_at__isnull=True,
                    superseded_at__isnull=True,
                    superseded_by__isnull=True,
                    withdrawn_at__isnull=False,
                ),
                name="use_acceptance_states",
            ),
            models.UniqueConstraint(
                fields=["state"],
                condition=Q(state="accepted"),
                name="use_acceptance_one_accepted",
            ),
        ]

    @property
    def label(self):
        return f"UA-{self.pk}"

    def __str__(self):
        return f"{self.label} · {self.title}"


class Rehearsal(models.Model):
    """A recorded rehearsal of recovery, downtime with reconciliation, or an upgrade.

    The person who performed or coordinated it records the procedure followed, the acceptance
    criteria, what happened and the outcome, and attaches the evidence. A different quality
    person accepts the record with a signature, whether its criteria were met or not.
    """

    class Kind(models.TextChoices):
        RECOVERY = "recovery", "Recovery from backup"
        DOWNTIME = "downtime", "Downtime and reconciliation"
        UPGRADE = "upgrade", "Upgrade"

    class Outcome(models.TextChoices):
        MET = "met", "Criteria met"
        NOT_MET = "not_met", "Criteria not met"

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting acceptance"
        ACCEPTED = "accepted", "Accepted"
        WITHDRAWN = "withdrawn", "Withdrawn"

    kind = models.CharField(max_length=12, choices=Kind)
    title = models.CharField(max_length=160)
    performed_on = models.DateField()
    release = models.CharField(
        max_length=80, help_text="Release or source revision rehearsed (for an upgrade: after)."
    )
    previous_release = models.CharField(
        max_length=80, blank=True, help_text="For an upgrade: the release before it."
    )
    environment = models.CharField(
        max_length=200,
        help_text="Where it was performed, e.g. an isolated copy on the validation server.",
    )
    procedure_ref = models.CharField(
        "Procedure", max_length=200, help_text="Procedure followed, with its revision."
    )
    acceptance_criteria = models.TextField(
        help_text="What had to be shown, e.g. restore check passes and recovery within 4 hours."
    )
    outcome = models.CharField(max_length=8, choices=Outcome)
    observations = models.TextField(
        help_text="What was done and found: steps, measured times, records reconciled."
    )
    issues_and_actions = models.TextField(
        "Issues and actions",
        blank=True,
        help_text="Deviations found and how each was or will be corrected.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=12, choices=State, default=State.RECORDED)
    accepted_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-performed_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=_stated(
                    "title",
                    "release",
                    "environment",
                    "procedure_ref",
                    "acceptance_criteria",
                    "observations",
                ),
                name="rehearsal_stated",
            ),
            # An upgrade names the release before it; a rehearsal that failed states its issues.
            models.CheckConstraint(
                condition=~Q(kind="upgrade") | _stated("previous_release"),
                name="rehearsal_upgrade_from",
            ),
            models.CheckConstraint(
                condition=~Q(outcome="not_met") | _stated("issues_and_actions"),
                name="rehearsal_issues_stated",
            ),
            models.CheckConstraint(
                condition=Q(state="recorded", accepted_at__isnull=True, withdrawn_at__isnull=True)
                | Q(state="accepted", accepted_at__isnull=False, withdrawn_at__isnull=True)
                | Q(state="withdrawn", accepted_at__isnull=True, withdrawn_at__isnull=False),
                name="rehearsal_states",
            ),
        ]

    @property
    def label(self):
        return f"RH-{self.pk}"

    def __str__(self):
        return f"{self.label} · {self.title}"


class RehearsalFile(models.Model):
    """Evidence of a rehearsal, kept exactly as received. Rows are append-only."""

    rehearsal = models.ForeignKey(Rehearsal, on_delete=models.PROTECT, related_name="files")
    filename = models.CharField(max_length=200, help_text="Base name of the uploaded file")
    content_type = models.CharField(
        max_length=100, blank=True, help_text="Type declared by the browser; informational only"
    )
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    content = models.BinaryField()
    description = models.CharField(max_length=200, help_text="What the file is")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["rehearsal", "sha256"], name="validation_rehearsalfile_unique"
            ),
            models.CheckConstraint(
                condition=Q(size__gt=0), name="validation_rehearsalfile_not_empty"
            ),
        ]

    def __str__(self):
        return self.filename
