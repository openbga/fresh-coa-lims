"""Planning of open tests: when each is due, who does it and on which instrument.

Planning decides nothing about a result: it never authorizes work, and the bench still checks
the analyst's qualification and every instrument and lot when a result is recorded. A test is
due by the date a planner set on its plan or, without one, by the turnaround target in force for
its kind of work when the test was assigned.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class Work(models.TextChoices):
    """What a test belongs to, as the subject of the test says (analytical.AnalyticalTest)."""

    LOT = "lot", "Lot testing"
    STABILITY = "stability", "Stability testing"
    REASSESSMENT = "reassessment", "Reassessment testing"


MAX_TARGET_DAYS = 365


class Target(models.Model):
    """A turnaround target for one kind of work, as quality set it. Append-only (trigger): the
    newest row of a kind is the target in force, and a test takes the target in force when it
    was assigned, so changing a target never moves the due date of a test already assigned.
    ``days`` empty: no target from then on."""

    work = models.CharField(max_length=16, choices=Work.choices)
    days = models.PositiveSmallIntegerField(
        "target", null=True, blank=True, help_text="Calendar days from the day a test is assigned"
    )
    reason = models.TextField(blank=True)
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    set_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work", "-set_at", "-id"]
        verbose_name = "turnaround target"
        constraints = [
            models.CheckConstraint(
                condition=Q(days__isnull=True) | Q(days__gte=1, days__lte=MAX_TARGET_DAYS),
                name="planning_target_days_range",
            ),
            models.CheckConstraint(
                condition=Q(work__in=Work.values), name="planning_target_work_known"
            ),
        ]

    def __str__(self):
        return f"{self.get_work_display()}: {self.days or 'no'} days"


class Plan(models.Model):
    """The plan of one test: a due date set by a planner (empty: the turnaround target applies),
    the analyst who is to do it and the instrument it is planned on. A test has no plan row until
    it is first selected for planning (the row stays empty, revision 0, when that change left it
    as it was). Changed only while the test is open or awaiting review; never deleted (trigger).
    Each change is audited with its before and after values."""

    test = models.OneToOneField(
        "analytical.AnalyticalTest", on_delete=models.PROTECT, related_name="plan"
    )
    due_on = models.DateField("due date", null=True, blank=True)
    analyst = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    equipment = models.ForeignKey(
        "laboratory.Equipment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="instrument",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    changed_at = models.DateTimeField(null=True, blank=True)
    # 0 until the first change: a page that showed a test without a plan names revision 0.
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["test_id"]
        verbose_name = "test plan"

    def __str__(self):
        return f"Plan of T-{self.test_id}"

    @property
    def label(self):
        return f"plan of T-{self.test_id}"
