from functools import cached_property

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.device_formats import visible

from .contracts import (
    LESS_THAN,
    OUTCOMES,
    Reading,
    bench_resources,
    contract_source,
    parse_method,
    parse_requirement,
    reported_source,
)

DECIMAL = {"max_digits": 20, "decimal_places": 8}


class QCBatch(models.Model):
    class State(models.TextChoices):
        OPEN = "open", "Open"
        REJECTED = "rejected", "Rejected"

    number = models.CharField(max_length=80, unique=True)
    method_code = models.CharField(max_length=80)
    method = models.JSONField()
    method_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "QC batch"
        verbose_name_plural = "QC batches"

    def __str__(self):
        return self.number

    @cached_property
    def method_spec(self):
        return parse_method(self.method)

    def current_qc(self):
        return self.qc_results.filter(correction__isnull=True).select_related("recorded_by")

    def qc_status(self):
        """Return (status, checks) where status is incomplete, failed or passed."""
        current = {r.check_code: r for r in self.current_qc()}
        checks, status = [], "passed"
        for check in self.method_spec.qc_checks:
            result = current.get(check.code)
            conforms = None if result is None else check.conforms(result.value)
            checks.append({"check": check, "result": result, "conforms": conforms})
            if conforms is False:
                status = "failed"
            elif conforms is None and status != "failed":
                status = "incomplete"
        return status, checks


class QCResult(models.Model):
    batch = models.ForeignKey(QCBatch, on_delete=models.PROTECT, related_name="qc_results")
    check_code = models.CharField(max_length=40)
    value = models.DecimalField(**DECIMAL)
    value_text = models.CharField(max_length=40, help_text="Value exactly as entered")
    unit = models.CharField(max_length=40)
    raw_reference = models.CharField(max_length=200)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="correction"
    )
    reason = models.TextField(blank=True)
    eligibility = models.JSONField(
        default=dict,
        blank=True,
        help_text="Analyst qualification and equipment and reagent evidence at acceptance",
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["check_code", "recorded_at", "pk"]

    @property
    def equipment_used(self):
        return bench_resources(self.eligibility)[0]

    @property
    def reagents_used(self):
        return bench_resources(self.eligibility)[1]


class AnalyticalTest(models.Model):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "Original"
        RETEST = "retest", "Retest"
        RESAMPLE = "resample", "Resample"
        RERUN = "rerun", "Rerun after QC failure"
        REVISED = "revised", "Repeat under replaced requirements"
        # Follows a test that a signed record says cannot be completed, on the same sample or
        # on a new sample of the lot (``record_not_completed``); needs no investigation.
        REPEAT = "repeat", "Repeat of a test not completed"

    class State(models.TextChoices):
        OPEN = "open", "Open"
        SUBMITTED = "submitted", "Awaiting review"
        REVIEWED = "reviewed", "Reviewed"
        INVALIDATED = "invalidated", "Invalidated"
        # The lot's requirements were replaced and this test's requirement is no longer one of
        # them. The test and everything recorded on it are kept; it takes no more work and
        # never answers a requirement.
        SUPERSEDED = "superseded", "Superseded"
        # A quality person signed that the test cannot be completed (its sample was lost, an
        # instrument failed...). Everything recorded on it is kept, with what the signature
        # froze in ``not_completed_record``; it takes no more work and answers nothing.
        NOT_COMPLETED = "not_completed", "Not completed"

    class NotCompletedCause(models.TextChoices):
        SAMPLE = "sample", "The sample was lost, damaged or used up"
        HANDLING = "handling", "An error in preparing or running the test"
        EQUIPMENT = "equipment", "Equipment, reagent or standard failure"
        OTHER = "other", "Another cause, stated in the reason"

    # A test belongs to the testing of a lot (``lot`` and ``sample``), to a stability pull
    # (``pull``) or to a reassessment (below), never to two. A stability test names no lot:
    # nothing that reads a lot's tests can count it, so the record of a released lot is not
    # changed by its stability studies.
    lot = models.ForeignKey(
        "quality.Lot", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sample = models.ForeignKey(
        "quality.Sample", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    pull = models.ForeignKey(
        "stability.Pull", null=True, blank=True, on_delete=models.PROTECT, related_name="tests"
    )
    # Or to the reassessment of a released lot (``reassessment``): like a pull's test it names
    # no lot, so the record of the lot it examines again is not changed.
    reassessment = models.ForeignKey(
        "quality.Reassessment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tests",
    )
    test_code = models.CharField(max_length=80)
    requirement = models.JSONField()
    requirement_hash = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ORIGINAL)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    investigation = models.ForeignKey(
        "Investigation", null=True, blank=True, on_delete=models.PROTECT, related_name="tests"
    )
    batch = models.ForeignKey(
        QCBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="tests"
    )
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    mean_value = models.DecimalField(null=True, blank=True, **DECIMAL)
    reportable_value = models.DecimalField(null=True, blank=True, **DECIMAL)
    reportable_text = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Reportable result as frozen at submission, e.g. 99.8, <10 or Absent",
    )
    conforms = models.BooleanField(null=True, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    not_completed_record = models.JSONField(
        default=dict,
        blank=True,
        help_text="What the signed record that the test cannot be completed froze; empty "
        "for every other test",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["lot_id", "sample_id", "test_code", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "test_code"],
                condition=Q(kind="original"),
                name="analytical_one_original_test",
            ),
            models.CheckConstraint(
                condition=(Q(kind="original") & Q(parent__isnull=True))
                | (~Q(kind="original") & Q(parent__isnull=False)),
                name="analytical_test_lineage",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["original", "rerun", "revised", "repeat"])
                | Q(investigation__isnull=False),
                name="analytical_retest_has_investigation",
            ),
            models.CheckConstraint(
                condition=Q(
                    lot__isnull=False,
                    sample__isnull=False,
                    pull__isnull=True,
                    reassessment__isnull=True,
                )
                | Q(
                    lot__isnull=True,
                    sample__isnull=True,
                    pull__isnull=False,
                    reassessment__isnull=True,
                )
                | Q(
                    lot__isnull=True,
                    sample__isnull=True,
                    pull__isnull=True,
                    reassessment__isnull=False,
                ),
                name="analytical_test_subject_of_three",
            ),
            models.UniqueConstraint(
                fields=["pull", "test_code"],
                condition=Q(kind="original"),
                name="analytical_one_original_pull_test",
            ),
            models.UniqueConstraint(
                fields=["reassessment", "test_code"],
                condition=Q(kind="original"),
                name="analytical_one_original_reassessment_test",
            ),
            # A pull is retested on the material that was pulled: it has no other sample, and
            # its requirements are not replaced.
            models.CheckConstraint(
                condition=Q(pull__isnull=True)
                | Q(kind__in=["original", "retest", "rerun", "repeat"]),
                name="analytical_pull_test_kind",
            ),
            # So is a reassessment, on the sample taken for it.
            models.CheckConstraint(
                condition=Q(reassessment__isnull=True)
                | Q(kind__in=["original", "retest", "rerun", "repeat"]),
                name="analytical_reassessment_test_kind",
            ),
            # The record exists exactly when the test was recorded as not completed.
            models.CheckConstraint(
                condition=(Q(state="not_completed") & ~Q(not_completed_record={}))
                | (~Q(state="not_completed") & Q(not_completed_record={})),
                name="analytical_test_not_completed_record",
            ),
        ]

    def __str__(self):
        return f"T-{self.pk} {self.test_code}"

    @property
    def label(self):
        return f"T-{self.pk}"

    @property
    def is_stability(self):
        return self.pull_id is not None

    @property
    def is_reassessment(self):
        return self.reassessment_id is not None

    @property
    def detached(self):
        """A test of a stability pull or of a reassessment: it names no lot."""
        return self.lot_id is None

    @property
    def source_lot(self):
        """The lot the tested material comes from, for display: the lot under test or, for a
        stability test or a reassessment, the lot of the pull's study or the lot reassessed.
        Neither is part of that lot's record."""
        if self.pull_id is not None:
            return self.pull.study.lot
        if self.reassessment_id is not None:
            return self.reassessment.lot
        return self.lot

    @property
    def sample_text(self):
        """What was tested: the sample's reference, the stability pull or the reassessment."""
        if self.pull_id is not None:
            return self.pull.label
        if self.reassessment_id is not None:
            return self.reassessment.label
        return self.sample.reference

    @property
    def material_text(self):
        """What was tested, named: "sample S-1", "stability pull ..." or "reassessment RA-1"."""
        if self.pull_id is not None:
            return f"stability pull {self.pull.label}"
        if self.reassessment_id is not None:
            return f"reassessment {self.reassessment.label}"
        return f"sample {self.sample.reference}"

    @property
    def subject_heading(self):
        """The label of ``subject_text``."""
        if self.pull_id is not None:
            return "Lot and stability pull"
        if self.reassessment_id is not None:
            return "Lot and reassessment"
        return "Lot and sample"

    @property
    def subject_text(self):
        """Lot and sample, lot and stability pull, or lot and reassessment, on one line."""
        if self.lot_id is None:
            return f"{self.source_lot.number} / {self.material_text}"
        return f"{self.lot.number} / {self.sample.reference}"

    @property
    def material_taken(self):
        """The material a test of a stability pull or a reassessment is retested or repeated
        on, in words."""
        if self.reassessment_id is not None:
            return "the sample taken for the reassessment"
        return "the material that was pulled"

    @property
    def holder_word(self):
        """What an open investigation of this test holds: "lot", "pull" or "reassessment"."""
        if self.pull_id is not None:
            return "pull"
        if self.reassessment_id is not None:
            return "reassessment"
        return "lot"

    @property
    def subject_url(self):
        from django.urls import reverse

        _, name, args = self.subject_page
        return reverse(name, args=args)

    @property
    def subject_page(self):
        """(label, URL name, args) of the page the test is reached from: its lot's testing
        page, its stability pull or its reassessment."""
        if self.pull_id is not None:
            return self.pull.label, "stability:pull_detail", [self.pull_id]
        if self.reassessment_id is not None:
            return self.reassessment.label, "quality:reassessment_detail", [self.reassessment_id]
        return self.lot.number, "analytical:lot_testing", [self.lot_id]

    @cached_property
    def spec(self):
        return parse_requirement(self.requirement)

    @property
    def reportable_display(self):
        """Reportable result as frozen at submission, e.g. 99.8, <10 or Absent ("" if none).

        Tests submitted before the text was frozen fall back to formatting the numeric value at
        the approved reporting precision.
        """
        if self.reportable_text:
            return self.reportable_text
        if self.reportable_value is None:
            return ""
        return self.spec.format_value(self.reportable_value)

    @property
    def reportable_with_unit(self):
        text = self.reportable_display
        unit = self.spec.unit
        return f"{text} {unit}" if text and unit else text

    def current_observations(self):
        return self.observations.filter(correction__isnull=True).select_related("recorded_by")

    def contract_source(self):
        """The contract laboratory evidence when every current observation was reported by a
        contract laboratory, otherwise None. A test never mixes the two origins."""
        return reported_source(self.current_observations())

    def raw_file_list(self):
        """Raw-data files for display, oldest first, without loading their stored bytes."""
        return self.raw_files.defer("content").select_related("uploaded_by")


class Observation(models.Model):
    """One replicate observation. Rows are append-only; a correction is a new linked row.

    ``eligibility`` is the evidence relied on when the row was accepted: the analyst's
    qualification and the resources used at this bench, or, under ``contract``, the approval and
    the report of the contract laboratory that reported the replicate.
    """

    test = models.ForeignKey(AnalyticalTest, on_delete=models.PROTECT, related_name="observations")

    class Qualifier(models.TextChoices):
        NONE = "", "As recorded"
        LESS_THAN = LESS_THAN, "Less than"

    replicate = models.PositiveSmallIntegerField()
    value = models.DecimalField(
        null=True, blank=True, help_text="Numeric value; empty for a qualitative result", **DECIMAL
    )
    qualifier = models.CharField(
        max_length=1, choices=Qualifier.choices, blank=True, default=Qualifier.NONE
    )
    outcome = models.CharField(
        max_length=20,
        choices=list(OUTCOMES.items()),
        blank=True,
        default="",
        help_text="Qualitative outcome; blank for a numeric or count result",
    )
    value_text = models.CharField(max_length=40, help_text="Result exactly as recorded")
    observed_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="What was observed; required for a qualitative result",
    )
    unit = models.CharField(max_length=40, blank=True, help_text="Blank for a qualitative result")
    raw_reference = models.CharField(max_length=200)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="correction"
    )
    reason = models.TextField(blank=True)
    eligibility = models.JSONField(
        default=dict, blank=True, help_text="Analyst qualification evidence at acceptance"
    )
    inputs = models.JSONField(
        default=list,
        blank=True,
        help_text="Calculation inputs as entered, in input order; empty for an entered result",
    )
    calculation = models.JSONField(
        default=dict,
        blank=True,
        help_text="Calculation applied (method, revision, formula, unit, decimals); empty for an "
        "entered result",
    )
    # An imported replicate: the raw-data file of the test it was read from, with the row and
    # the cells as read (``imports.import_observations``). Empty for a replicate entered by hand.
    source_file = models.ForeignKey(
        "RawDataFile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="imported_observations",
    )
    source = models.JSONField(
        default=dict,
        blank=True,
        help_text="Row of the instrument export and the cells read from it; empty when entered "
        "by hand",
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["replicate", "recorded_at", "pk"]
        constraints = [
            # An imported replicate names its file and the row it was read from; one entered by
            # hand names neither. A correction is always entered by hand.
            models.CheckConstraint(
                condition=(Q(source_file__isnull=True) & Q(source={}))
                | (Q(source_file__isnull=False) & ~Q(source={}) & Q(supersedes__isnull=True)),
                name="analytical_observation_source",
            ),
            # A calculated value always keeps its inputs and the calculation applied, and is a
            # number as calculated (never reported as less than a value).
            models.CheckConstraint(
                condition=(Q(inputs=[]) & Q(calculation={}))
                | (
                    ~Q(inputs=[])
                    & ~Q(calculation={})
                    & Q(value__isnull=False)
                    & Q(qualifier="")
                    & Q(outcome="")
                ),
                name="analytical_observation_calculation",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(outcome="")
                    & Q(value__isnull=True)
                    & Q(qualifier="")
                    & ~Q(observed_text__regex=r"^\s*$")
                )
                | (Q(outcome="") & Q(value__isnull=False) & Q(qualifier__in=["", LESS_THAN])),
                name="analytical_observation_shape",
            ),
        ]

    @property
    def reading(self):
        return Reading(
            value=self.value, qualifier=self.qualifier, outcome=self.outcome, text=self.value_text
        )

    @property
    def is_calculated(self):
        return bool(self.calculation)

    @property
    def is_imported(self):
        return self.source_file_id is not None

    @property
    def contract(self):
        """Evidence that a contract laboratory reported this replicate, or None."""
        return contract_source(self.eligibility)

    @property
    def equipment_used(self):
        return bench_resources(self.eligibility)[0]

    @property
    def reagents_used(self):
        return bench_resources(self.eligibility)[1]


class Investigation(models.Model):
    class Phase(models.TextChoices):
        LABORATORY = "laboratory", "Phase I laboratory investigation"
        FULL = "full", "Phase II full investigation"
        CLOSED = "closed", "Closed"

    class Outcome(models.TextChoices):
        INVALIDATED = "invalidated", "Original result invalidated: assignable cause"
        CONFIRMED = "confirmed", "Out-of-specification result confirmed"

    # The lot whose record the investigation belongs to; none for a stability test, whose
    # investigation holds the pull and never the lot.
    lot = models.ForeignKey(
        "quality.Lot", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    test = models.OneToOneField(
        AnalyticalTest, on_delete=models.PROTECT, related_name="triggered_investigation"
    )
    trigger = models.CharField(max_length=200)
    phase = models.CharField(max_length=16, choices=Phase.choices, default=Phase.LABORATORY)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True)
    assignable_cause = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-opened_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(phase="closed") & ~Q(outcome="") & Q(closed_at__isnull=False))
                | (~Q(phase="closed") & Q(outcome="") & Q(closed_at__isnull=True)),
                name="analytical_investigation_closure",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return f"INV-{self.pk}"

    @property
    def is_open(self):
        return self.phase != self.Phase.CLOSED

    @property
    def is_stability(self):
        return self.test.pull_id is not None


class InvestigationEntry(models.Model):
    class Kind(models.TextChoices):
        ASSESSMENT = "assessment", "Laboratory assessment"
        HYPOTHESIS = "hypothesis", "Hypothesis or test plan"
        EVIDENCE = "evidence", "Evidence"
        ESCALATION = "escalation", "Escalation"
        PLAN = "plan", "Authorized retest or resample"
        IMPACT = "impact", "Impact on other lots or products"

    investigation = models.ForeignKey(
        Investigation, on_delete=models.PROTECT, related_name="entries"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    text = models.TextField()
    external_reference = models.CharField(max_length=200, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name_plural = "investigation entries"


class RawDataFile(models.Model):
    """A file of raw data attached to a test, kept exactly as received. Rows are append-only."""

    test = models.ForeignKey(AnalyticalTest, on_delete=models.PROTECT, related_name="raw_files")
    filename = models.CharField(max_length=200, help_text="Base name of the uploaded file")
    content_type = models.CharField(
        max_length=100, blank=True, help_text="Type declared by the browser; informational only"
    )
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    content = models.BinaryField()
    description = models.CharField(max_length=200, help_text="What the file is")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["test", "sha256"], name="analytical_rawfile_unique"),
            models.CheckConstraint(condition=Q(size__gt=0), name="analytical_rawfile_not_empty"),
        ]

    def __str__(self):
        return self.filename


class InstrumentReading(models.Model):
    """One reading taken for a test from a balance or meter connected to the analyst's computer,
    kept exactly as the device sent it.

    Every reading is kept, whether or not a replicate records it. ``connection`` is the data
    connection the reading was taken through, as it stood (laboratory ``DeviceConnection``
    evidence). ``target`` is what the reading was taken for: ``value`` for a result entered
    directly, otherwise the code of a calculation input. Rows are append-only; only
    ``observation`` is set, once, by the replicate that records the reading (migration 0012).
    """

    test = models.ForeignKey(
        AnalyticalTest, on_delete=models.PROTECT, related_name="instrument_readings"
    )
    target = models.CharField(max_length=40)
    label = models.CharField(max_length=160, help_text="What was read, as the form named it")
    connection = models.JSONField(help_text="Data connection relied on, as it stood")
    request = models.CharField(max_length=200, help_text="What the browser sent to the device")
    response = models.TextField(help_text="What the device sent, exactly as received")
    value = models.DecimalField(**DECIMAL)
    value_text = models.CharField(max_length=40, help_text="The number as the device wrote it")
    unit = models.CharField(max_length=40)
    serial_number = models.CharField(
        max_length=40, blank=True, help_text="Serial number the device reported, if its format does"
    )
    read_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    read_at = models.DateTimeField(auto_now_add=True)
    observation = models.ForeignKey(
        Observation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="instrument_readings",
    )

    class Meta:
        ordering = ["read_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(response="") & ~Q(request="") & ~Q(unit="") & ~Q(target=""),
                name="analytical_reading_stated",
            ),
            # A replicate records a reading once, for one of its values.
            models.UniqueConstraint(
                fields=["observation", "target"],
                condition=Q(observation__isnull=False),
                name="analytical_reading_once_per_value",
            ),
        ]

    @property
    def asset_id(self):
        return self.connection.get("asset_id", "")

    @property
    def response_text(self):
        """What the device sent, with its line endings shown."""
        return visible(self.response)

    def __str__(self):
        return f"{self.label} {self.value_text} {self.unit} from {self.asset_id}"
