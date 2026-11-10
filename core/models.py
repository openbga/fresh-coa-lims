import uuid

from django.conf import settings
from django.db import models


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

    class Meta:
        constraints = [models.UniqueConstraint(fields=["code", "version"], name="rule_version")]

    def __str__(self):
        return f"{self.code} v{self.version}"


class ElectronicSignature(models.Model):
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    signer_name = models.CharField(max_length=256)
    signed_at = models.DateTimeField(auto_now_add=True)
    meaning = models.CharField(max_length=80)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    revision = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    content = models.JSONField()
    audit_event = models.OneToOneField(AuditEvent, on_delete=models.PROTECT)


class AuditReview(models.Model):
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    events = models.ManyToManyField(AuditEvent)
    conclusion = models.TextField()
