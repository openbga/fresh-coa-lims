from django.conf import settings
from django.core.validators import URLValidator
from django.db import models

# An external link is untrusted text: only http(s) is accepted.
http_url = URLValidator(schemes=["http", "https"])


class Supplier(models.Model):
    """Identity of a company that supplies material. Immutable once created.

    The register says who a supplier is, not whether it is qualified: a lot's receipt names
    its supplier, and reliance on a supplier's results is a separate, later decision.
    """

    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=160)
    location = models.CharField(
        max_length=160, help_text="Site the material is supplied from: town and country."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class SupplierQualification(models.Model):
    """Approved evidence that a supplier's certificate results can be relied on for a material.

    Recorded by one quality person and approved by another with a signature. It names the tests
    it covers: a result the supplier's certificate states for one of them may stand in for the
    laboratory's own test of a lot received within its dates, when the lot's rule set allows
    it. A revoked qualification is relied on no further. The evidence is never edited; a renewal
    or a change of scope is a new qualification.
    """

    class State(models.TextChoices):
        RECORDED = "recorded", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REVOKED = "revoked", "Revoked"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="qualifications")
    material = models.ForeignKey("catalog.Material", on_delete=models.PROTECT, related_name="+")
    test_codes = models.JSONField(
        help_text="Codes of the specification tests whose certificate results may be relied on."
    )
    basis = models.TextField(
        help_text="How the reliability of the supplier's results was established, for example "
        "the lots tested in full and compared with the certificates."
    )
    evidence_ref = models.CharField(
        max_length=200,
        help_text="Qualification report, audit report or comparison record, with its revision.",
    )
    evidence_url = models.URLField(blank=True, max_length=500, validators=[http_url])
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
                name="supplier_qualification_interval_ordered",
            ),
            models.CheckConstraint(
                condition=~models.Q(basis__regex=r"^\s*$")
                & ~models.Q(evidence_ref__regex=r"^\s*$"),
                name="supplier_qualification_stated",
            ),
            # Each state carries exactly the timestamps of the signatures behind it.
            models.CheckConstraint(
                condition=models.Q(
                    state="recorded", approved_at__isnull=True, revoked_at__isnull=True
                )
                | models.Q(state="approved", approved_at__isnull=False, revoked_at__isnull=True)
                | models.Q(state="revoked", approved_at__isnull=False, revoked_at__isnull=False),
                name="supplier_qualification_signed",
            ),
        ]

    @property
    def label(self):
        return f"SQ-{self.pk}"

    def __str__(self):
        return f"{self.supplier.code} · {self.material.code}"
