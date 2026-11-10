from django.conf import settings
from django.db import models


class Lot(models.Model):
    number = models.CharField(max_length=80, unique=True)
    material = models.CharField(max_length=160)
    rules = models.ForeignKey("core.RuleSet", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=24, default="quarantine")
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


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
