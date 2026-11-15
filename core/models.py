import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.TextField()

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["object_type", "object_id", "occurred_at"])]


class PINCredential(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    encoded = models.CharField(max_length=256)
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    changed_at = models.DateTimeField(auto_now=True)


class RuleSet(models.Model):
    code = models.SlugField()
    version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
    segment = models.SlugField()
    policy = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="draft")
    effective_from = models.DateTimeField()
    effective_until = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    # Set when a later approved version of the same rule set takes over: the moment this version
    # stops applying and the version that replaced it. The approved content is not touched.
    superseded_from = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="rule_version"),
            models.CheckConstraint(
                condition=models.Q(superseded_from__isnull=True, superseded_by__isnull=True)
                | models.Q(
                    status="approved",
                    superseded_from__isnull=False,
                    superseded_by__isnull=False,
                    superseded_from__gte=models.F("effective_from"),
                ),
                name="rule_superseded",
            ),
        ]

    @property
    def applies_until(self):
        """The moment this version stops applying: its own end, or an earlier supersession."""
        return self.superseded_from or self.effective_until

    def __str__(self):
        return f"{self.code} v{self.version}"


class ElectronicSignature(models.Model):
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    signer_name = models.CharField(max_length=256)
    signed_at = models.DateTimeField(default=timezone.now, editable=False)
    meaning = models.CharField(max_length=80)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    revision = models.PositiveIntegerField()
    authentication_context = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64)
    content = models.JSONField()
    audit_event = models.OneToOneField(AuditEvent, on_delete=models.PROTECT)


class AuditReview(models.Model):
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    events = models.ManyToManyField(AuditEvent)
    conclusion = models.TextField()
