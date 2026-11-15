"""Sampling plans, lot requirement assignment and sampling provenance.

Published contract for other apps:
- ``current_requirements(lot)`` -> frozen requirement payload (tests, methods, limits, plan)
  for the lot's current assignment, or raises ``ApplicabilityHold``. Disposition must treat a hold
  as blocking.
- ``current_assignment(lot)`` -> latest LotAssignment or None.
- ``lot_blockers(lot)`` -> sampling reasons blocking QC disposition (call under the lot lock).
- ``lot_author_ids(lot)`` -> ids of everyone who sampled or recorded (including corrections)
  any sampling record of the lot; they must not sign its QC disposition.
- ``test_requirements(lot)`` -> {code: oq.test-requirement/1 or /2 payload} for analytical, or hold.
- ``catalog.services.batch_method_requirements()`` -> analytical method payloads for batches.

Before testing starts, requirements are assigned and assigned again without a signature. Once
testing has started only ``replace_requirements`` changes them: a quality person who authored
none of the lot's data signs the replacement by the versions now in force. The testing module
is reached through ``settings.REQUIREMENT_REPLACEMENT_TESTING`` and never imported here: it says
which tests carry over and which are superseded, refuses while a result would be set aside
unevaluated, and has its tests locked before the lot (``sign_transition(prepare=...)``).
"""

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from math import isqrt

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.decorators.debug import sensitive_variables

from catalog.models import RevisionStatus
from catalog.services import (
    AUTHOR_ROLE,
    ApplicabilityHold,
    _check_interval,
    _next_version,
    _require_reason,
    describe_limits,
    digest,
    effective_revision,
    register_check,
    resolve_requirements,
    test_requirement,
)
from core.audit import record_event, snapshot
from core.models import RuleSet
from core.services import applies_at, require_role, sign_transition
from quality.models import Lot, Sample
from quality.services import add_sample, disposition_authors

from .models import (
    AssignmentOrigin,
    AssignmentStatus,
    DeviationReview,
    DeviationStatus,
    LotAssignment,
    SamplingBasis,
    SamplingPlan,
    SamplingPlanRevision,
    SamplingPurpose,
    SamplingRecord,
)


def containers_required(basis, parameter, total):
    """Containers the approved plan requires for a lot of ``total`` containers (exact integers)."""
    if total < 1:
        raise ValidationError("A lot has at least one container.")
    if basis == SamplingBasis.ALL:
        needed = total
    elif basis == SamplingBasis.FIXED:
        needed = int(parameter)
    elif basis == SamplingBasis.SQRT_PLUS_ONE:
        root = isqrt(total)
        needed = 1 + (root if root * root == total else root + 1)
    elif basis == SamplingBasis.PERCENT:
        needed = int((Decimal(total) * Decimal(parameter) / 100).to_integral_value(ROUND_CEILING))
    else:
        raise ValidationError("Unknown sampling basis.")
    return max(1, min(total, needed))


def validate_plan_shape(basis, parameter):
    if basis in (SamplingBasis.FIXED, SamplingBasis.PERCENT):
        if parameter is None or parameter <= 0:
            raise ValidationError({"parameter": "Enter a positive count or percentage."})
        if basis == SamplingBasis.FIXED and parameter != parameter.to_integral_value():
            raise ValidationError({"parameter": "A fixed plan needs a whole number of containers."})
        if basis == SamplingBasis.PERCENT and parameter > 100:
            raise ValidationError({"parameter": "A percentage cannot exceed 100."})
    elif parameter is not None:
        raise ValidationError({"parameter": "This basis takes no parameter."})


def _check_plan_revision(revision):
    validate_plan_shape(revision.basis, revision.parameter)
    if not revision.rationale.strip() or not revision.instructions.strip():
        raise ValidationError("Sampling instructions and rationale are required.")


register_check(SamplingPlanRevision, _check_plan_revision)


@transaction.atomic
def create_plan(*, actor, code, title, material, stage, reason, **revision_fields):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    plan = SamplingPlan(code=code, title=title, material=material, stage=stage, created_by=actor)
    plan.full_clean()
    plan.save()
    record_event(
        actor=actor, action="sampling_plan.created", obj=plan, after=snapshot(plan), reason=reason
    )
    revision = new_plan_revision(actor=actor, plan=plan, reason=reason, **revision_fields)
    return plan, revision


@transaction.atomic
def new_plan_revision(
    *,
    actor,
    plan,
    basis,
    minimum_quantity,
    quantity_unit,
    instructions,
    rationale,
    effective_from,
    effective_until,
    reason,
    parameter=None,
    composite_allowed=False,
):
    require_role(actor, AUTHOR_ROLE)
    _require_reason(reason)
    _check_interval(effective_from, effective_until)
    validate_plan_shape(basis, parameter)
    SamplingPlan.objects.select_for_update().get(pk=plan.pk)
    revision = SamplingPlanRevision(
        plan=plan,
        version=_next_version(SamplingPlanRevision, "plan", plan),
        basis=basis,
        parameter=parameter,
        minimum_quantity=minimum_quantity,
        quantity_unit=quantity_unit,
        composite_allowed=composite_allowed,
        instructions=instructions,
        rationale=rationale,
        effective_from=effective_from,
        effective_until=effective_until,
        change_reason=reason,
        author=actor,
    )
    revision.full_clean()
    revision.save()
    record_event(
        actor=actor,
        action="sampling_plan_revision.created",
        obj=revision,
        after=snapshot(revision),
        reason=reason,
    )
    return revision


# Lot requirements ------------------------------------------------------------------------------


def current_assignment(lot):
    return LotAssignment.objects.filter(lot=lot).order_by("-assigned_at", "-id").first()


def current_requirements(lot):
    assignment = current_assignment(lot)
    if assignment is None:
        raise ApplicabilityHold(["No specification or sampling requirements are assigned."])
    if assignment.status != AssignmentStatus.READY:
        raise ApplicabilityHold(assignment.hold_reasons)
    return assignment.payload


def test_requirements(lot):
    """{test_code: oq.test-requirement/1 or /2 payload} for the lot's required tests, or hold.

    Information-only tests are not requirements. ``source`` names the frozen specification
    version and the lot's requirement payload hash, so it changes whenever requirements do.
    """
    payload = current_requirements(lot)
    assignment = current_assignment(lot)
    return _test_requirements(payload, assignment.payload_hash)


def _test_requirements(payload, payload_hash):
    spec = payload["specification"]
    source = (
        f"catalog:{spec['code']}@v{spec['version']}#rev{spec['revision_id']}"
        f"/lot-req:{payload_hash[:16]}"
    )
    return {t["code"]: test_requirement(t, source) for t in payload["tests"] if t["required"]}


def rules_in_force(rules, at):
    """The approved version of this rule set that applies at ``at``, or None."""
    return RuleSet.objects.filter(applies_at(at), code=rules.code).order_by("-version").first()


def _plan_fields(revision):
    """The approved sampling plan version as it is frozen into a lot's requirements."""
    return {
        "revision_id": revision.pk,
        "code": revision.plan.code,
        "version": revision.version,
        "approved_hash": revision.approved_hash,
        **{
            key: revision.approved_content[key]
            for key in (
                "basis",
                "parameter",
                "minimum_quantity",
                "quantity_unit",
                "composite_allowed",
                "instructions",
            )
        },
    }


def _sampled_plan(lot, material, stage):
    """The plan version the lot's samples were taken under, for requirements assigned again
    to the same material and stage, or None.

    Samples already taken stay valid under the plan they were taken under: a later version of
    the plan does not make them unusable, and nothing could make them usable again. None
    when nothing was sampled, when the lot's sampling records name several versions, or when
    the plan belongs to another material or stage; the sampling gate then says which samples
    do not fit the requirements.
    """
    revisions = {record.plan_revision for record in current_records(lot).values()}
    if len(revisions) != 1:
        return None
    (revision,) = revisions
    plan = revision.plan
    return revision if (plan.material_id, plan.stage) == (material.pk, stage) else None


def _plan_payload(lot, material, stage, at, reasons):
    if kept := _sampled_plan(lot, material, stage):
        return kept, _plan_fields(kept)
    plan = SamplingPlan.objects.filter(material=material, stage=stage).first()
    revision = effective_revision(SamplingPlanRevision, plan, at) if plan else None
    if plan is None:
        reasons.append(f"No sampling plan exists for {material.code} at stage {stage}.")
    elif revision is None:
        reasons.append(f"Sampling plan {plan.code} has no approved version effective now.")
    else:
        return revision, _plan_fields(revision)
    return None, None


REASSIGNMENT_REFUSED = (
    "Testing has started on this lot, so its requirements cannot be assigned again. Quality "
    "can replace them with a signature."
)


def testing_started(lot):
    """True when native analytical tests exist for the lot.

    Read through the app registry so sampling does not import the analytical app, which
    locks the same lot row when it creates tests, so this check serializes with test assignment.
    """
    if not apps.is_installed("analytical"):
        return False
    return apps.get_model("analytical", "AnalyticalTest").objects.filter(lot=lot).exists()


# Read-only preflights shared by pages (GET) and services (under the lot lock) --------------------


def assignment_blocker(lot):
    """Why requirements cannot be (re)assigned to this lot now, or None."""
    if lot.state != "quarantine":
        return "Only quarantined lots can receive requirements."
    if testing_started(lot):
        return REASSIGNMENT_REFUSED
    return None


def sampling_preflight(lot):
    """(assignment, blocker) from ONE read of the current assignment.

    Pages render from the returned assignment so a concurrent reassignment cannot swap in a
    different (e.g. held, plan-less) assignment between the check and the form; submission
    re-reads and re-checks everything under the lot lock.
    """
    assignment = current_assignment(lot)
    if lot.state != "quarantine":
        return assignment, "Only quarantined lots accept new samples."
    if assignment is None:
        return None, "Assign approved requirements before recording sampling."
    if assignment.status != AssignmentStatus.READY:
        return assignment, "Applicability hold: " + "; ".join(assignment.hold_reasons)
    if assignment.plan_revision.status != RevisionStatus.APPROVED:
        return assignment, "The assigned sampling plan is not approved."
    return assignment, None


def sampling_blocker(lot):
    """Why sampling cannot be recorded for this lot now, or None. Hold reasons are listed."""
    return sampling_preflight(lot)[1]


def correction_blocker(record):
    """Why this sampling record cannot be corrected now, or None."""
    if Lot.objects.get(pk=record.lot_id).state != "quarantine":
        return "Sampling for a dispositioned lot cannot be corrected here."
    if SamplingRecord.objects.filter(corrects_id=record.pk).exists():
        return "This record was already corrected. Correct the latest record."
    return None


def record_author_ids(record, records=None):
    """Samplers and recorders of ``record`` and of every earlier record it corrects.

    A correction starts from the values of the record it replaces, so everyone in the chain is an
    author of the current values. ``records`` optionally maps pk to already loaded records.
    """
    ids = set()
    while record is not None:
        ids |= {record.sampled_by_id, record.recorded_by_id}
        if record.corrects_id is None:
            break
        record = (records or {}).get(record.corrects_id) or SamplingRecord.objects.get(
            pk=record.corrects_id
        )
    return ids


def lot_author_ids(lot):
    """Users who sampled or recorded any sampling record of the lot, as a set of user ids.

    Every record counts, including corrected originals and intermediate corrections, so the set
    covers each correction chain in full. Disposition must not be signed by any of them.
    """
    ids = set()
    for sampled_by, recorded_by in SamplingRecord.objects.filter(lot_id=lot.pk).values_list(
        "sampled_by_id", "recorded_by_id"
    ):
        ids.update((sampled_by, recorded_by))
    ids.discard(None)
    return ids


def assessment_blocker(review, actor=None):
    """(reason, is_permission) why the deviation cannot be assessed now, or (None, False)."""
    record = SamplingRecord.objects.get(pk=review.record_id)
    if Lot.objects.get(pk=record.lot_id).state != "quarantine":
        return "Only deviations of quarantined lots can be assessed.", False
    if review.status != DeviationStatus.PENDING:
        return "This deviation has already been assessed.", False
    if SamplingRecord.objects.filter(corrects_id=record.pk).exists():
        return "This record was corrected; assess the latest record instead.", False
    if actor is not None and actor.pk in record_author_ids(record):
        return "You sampled, recorded or corrected this sample; another person must assess.", True
    return None, False


@transaction.atomic
def assign_requirements(*, actor, lot, material, stage, reason, scope="general"):
    """Freeze the effective specification, methods and sampling plan for a lot, or record a hold.

    A new assignment supersedes the previous one; earlier assignments and their payloads remain.
    The lot moves to the version in force of its own rule set when that is not the one it has,
    and once it has been sampled it keeps the plan version its samples were taken under.
    The lot revision increments so a disposition prepared against old requirements goes stale.
    Once testing has started this is refused: tests are bound to the frozen payload, and only
    a signed replacement (``replace_requirements``) changes the lot's requirements.
    """
    require_role(actor, "analyst", "quality")
    _require_reason(reason)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    if blocker := assignment_blocker(locked):
        raise ValidationError(blocker)
    previous = current_assignment(locked)
    at = timezone.now()
    reasons = []
    spec_payload = None
    # The lot follows its own rule set: the version in force is applied, as it is for the
    # specification and the methods. With none in force the lot's version is named in the hold.
    rules = rules_in_force(locked.rules, at) or locked.rules
    try:
        spec_payload = resolve_requirements(
            material=material, stage=stage, scope=scope, rules=rules, at=at
        )
    except ApplicabilityHold as hold:
        reasons.extend(hold.reasons)
    plan_revision, plan_payload = _plan_payload(locked, material, stage, at, reasons)
    assignment = LotAssignment(
        lot=locked,
        material=material,
        stage=stage,
        scope=scope,
        reason=reason,
        assigned_by=actor,
        supersedes=previous,
    )
    if reasons:
        assignment.status = AssignmentStatus.HOLD
        assignment.hold_reasons = reasons
    else:
        payload = {**spec_payload, "lot": {"id": locked.pk, "number": locked.number}}
        payload["sampling_plan"] = plan_payload
        assignment.status = AssignmentStatus.READY
        assignment.payload = payload
        assignment.payload_hash = digest(payload)
        assignment.specification_revision_id = spec_payload["specification"]["revision_id"]
        assignment.plan_revision = plan_revision
    assignment.full_clean()
    assignment.save()
    moved = not reasons and rules.pk != locked.rules_id
    changes = {"revision": F("revision") + 1, **({"rules": rules} if moved else {})}
    Lot.objects.filter(pk=locked.pk).update(**changes)
    record_event(
        actor=actor,
        action="lot.requirements_" + ("assigned" if not reasons else "held"),
        obj=assignment,
        before={
            **({"assignment": previous.pk} if previous else {}),
            **({"rules": locked.rules_id} if moved else {}),
        },
        after={
            "lot": locked.pk,
            "status": assignment.status,
            "hold_reasons": reasons,
            **({"rules": rules.pk} if moved else {}),
            "specification_revision": assignment.specification_revision_id,
            "plan_revision": assignment.plan_revision_id,
            "payload_hash": assignment.payload_hash,
        },
        reason=reason,
    )
    return assignment


# Replacement during testing -------------------------------------------------------------------

REPLACED_MEANING = "requirements_replaced"
REPLACEMENT_SCHEMA = "oq.requirement-replacement/1"
NOT_STARTED = (
    "Testing has not started on this lot. Assign its requirements again instead; that needs "
    "no signature before testing."
)
NOT_CONFIGURED = (
    "Requirement replacement is not configured for testing, so the lot keeps its requirements."
)
NOTHING_TO_REPLACE = (
    "The versions frozen for this lot are the ones in force now. There is nothing to replace."
)
SELF_REPLACEMENT = (
    "You recorded receipt, supplier certificate, sampling or test data of this lot, or proposed "
    "a supplier's result for it. Someone who authored none of it replaces its requirements."
)
REPLACEMENT_STALE = (
    "The versions in force or the lot's tests changed after this page was opened. Review the "
    "replacement again before signing."
)
# Keys a line frozen by an earlier release may lack; they read as that release meant them.
LINE_DEFAULTS = {
    "lower_inclusive": True,
    "upper_inclusive": True,
    "expected_result": "",
    "reporting_decimals": None,
    "replicates": 1,
}


def _testing():
    """The testing module's side of a replacement (settings.REQUIREMENT_REPLACEMENT_TESTING),
    or None when none is configured."""
    path = getattr(settings, "REQUIREMENT_REPLACEMENT_TESTING", "")
    return import_string(path)() if path else None


def replacement_blocker(lot, assignment=None):
    """Why this lot's requirements cannot be replaced at all, or None. Read-only."""
    if lot.state != "quarantine":
        return "Only quarantined lots can have their requirements replaced."
    if not testing_started(lot):
        return NOT_STARTED
    assignment = assignment or current_assignment(lot)
    if assignment is None or assignment.status != AssignmentStatus.READY:
        return "The lot has no assigned requirements to replace."
    if _testing() is None:
        return NOT_CONFIGURED
    return None


def replacement_denial(actor, lot):
    """Why this person cannot sign the replacement, or "". Shown before any PIN is requested."""
    return SELF_REPLACEMENT if actor.pk in disposition_authors(lot) else ""


def _line_text(line):
    """One requirement line as text: acceptance, rounding, replicates and method version."""
    line = {**LINE_DEFAULTS, **line}
    parts = [describe_limits(line)]
    if line["result_type"] != "qualitative" and line["reporting_decimals"] is not None:
        parts.append(f"rounded to {line['reporting_decimals']} decimals")
    if line["replicates"] != 1:
        parts.append(f"{line['replicates']} replicates")
    parts.append(f"method {line['method']['code']} v{line['method']['version']}")
    return " · ".join(parts)


def _same_line(before, after):
    """True when testing would freeze the same requirement for both lines (see
    ``test_requirement``); a line an earlier release froze without today's keys counts as
    changed."""
    if before["required"] != after["required"]:
        return False
    try:
        return test_requirement(before, "") == test_requirement(after, "")
    except KeyError:
        return False


def _line_changes(old, new):
    """Requirement lines of the new payload, then lines only the old one has, each marked
    unchanged, changed, added or removed."""
    before = {line["code"]: line for line in old["tests"]}
    after = {line["code"]: line for line in new["tests"]}
    rows = []
    for code in [*after, *(code for code in before if code not in after)]:
        was, now = before.get(code), after.get(code)
        if was is None:
            change = "added"
        elif now is None:
            change = "removed"
        else:
            change = "unchanged" if _same_line(was, now) else "changed"
        rows.append(
            {
                "code": code,
                "name": (now or was)["name"],
                "change": change,
                "before": _line_text(was) if was else "",
                "after": _line_text(now) if now else "",
                "required": bool(now and now["required"]),
                "was_required": bool(was and was["required"]),
            }
        )
    return rows


@dataclass
class Replacement:
    """What replacing a lot's requirements now would do. Built read-only for the page and again
    under the locks for the signature; ``basis`` identifies everything the signer was shown
    except the time of resolution."""

    lot: Lot
    current: LotAssignment | None
    blocker: str = ""
    reasons: list = field(default_factory=list)
    rules: RuleSet | None = None
    payload: dict | None = None
    payload_hash: str = ""
    requirements: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)
    tests: list = field(default_factory=list)
    supplier_results: list = field(default_factory=list)
    basis: str = ""

    @property
    def possible(self):
        return not self.blocker and not self.reasons

    @property
    def superseded(self):
        return [row for row in self.tests if row["effect"] == "superseded"]

    @property
    def carried(self):
        return [row for row in self.tests if row["effect"] == "carried"]


def replacement_preview(lot, at=None):
    """Resolve the versions in force for the lot's material, stage and scope and its rule set,
    and work out what replacing the lot's requirements with them would do.

    The sampling plan is kept: samples already taken were taken under it. A resolution that
    is incomplete (no effective specification, method or rule version, or a rule set the
    specification does not cover) is a reason for refusal, never a hold recorded on the lot.
    """
    current = current_assignment(lot)
    preview = Replacement(lot=lot, current=current)
    if blocker := replacement_blocker(lot, current):
        preview.blocker = blocker
        return preview
    at = at or timezone.now()
    rules = rules_in_force(lot.rules, at)
    preview.rules = rules
    reasons = []
    if rules is None:
        reasons.append(f"Rule set {lot.rules.code} has no approved version effective now.")
    resolved = None
    try:
        resolved = resolve_requirements(
            material=current.material, stage=current.stage, scope=current.scope, rules=rules, at=at
        )
    except ApplicabilityHold as hold:
        reasons.extend(hold.reasons)
    if reasons:
        preview.reasons = reasons
        return preview
    payload = {**resolved, "lot": {"id": lot.pk, "number": lot.number}}
    payload["sampling_plan"] = current.payload["sampling_plan"]
    preview.payload, preview.payload_hash = payload, digest(payload)
    preview.lines = _line_changes(current.payload, payload)
    if (
        rules.pk == lot.rules_id
        and payload["specification"]["revision_id"] == current.specification_revision_id
        and all(row["change"] == "unchanged" for row in preview.lines)
    ):
        preview.blocker = NOTHING_TO_REPLACE
        return preview
    preview.requirements = _test_requirements(payload, preview.payload_hash)
    testing = _testing().effects(lot, preview.requirements)
    preview.reasons = list(testing["refusals"])
    preview.tests = testing["tests"]
    preview.supplier_results = testing["supplier_results"]
    preview.basis = digest(
        {
            "previous": current.pk,
            "rules": rules.pk,
            "specification": payload["specification"]["approved_hash"],
            "tests": payload["tests"],
            "testing": [[row["test"], row["state"], row["effect"]] for row in preview.tests],
            "supplier_results": preview.supplier_results,
        }
    )
    return preview


def newer_versions(lot, current=None):
    """What differs between the versions in force and the ones frozen for a lot in testing, or
    None when nothing does (or the lot is not in quarantine and in testing).

    ``{"items": [...], "reasons": [...], "rules": bool}``: ``items`` names the rule set and
    specification versions in force and counts the requirements that changed; ``reasons`` is
    set instead when the versions in force cannot be applied to the lot; ``rules`` says that
    the lot's rule version is no longer the one in force, which the disposition requires. The
    lot keeps its frozen requirements either way, until quality replaces them.
    """
    if lot.state != "quarantine" or not testing_started(lot):
        return None
    preview = replacement_preview(lot)
    if preview.blocker:
        return None
    found = {
        "items": [],
        "reasons": preview.reasons if preview.payload is None else [],
        # The lot's rule version is no longer the one in force: that blocks the disposition.
        "rules": preview.rules is None or preview.rules.pk != lot.rules_id,
    }
    if preview.rules and preview.rules.pk != lot.rules_id:
        found["items"].append(f"rule set {preview.rules}")
    if preview.payload:
        spec = preview.payload["specification"]
        if spec["revision_id"] != preview.current.specification_revision_id:
            found["items"].append(f"specification {spec['code']} v{spec['version']}")
        changed = sum(1 for row in preview.lines if row["change"] != "unchanged")
        if changed:
            found["items"].append(f"{changed} requirement{'' if changed == 1 else 's'} changed")
    return found


def replacement_notices(lot):
    """What a disposition signer should know about the lot's requirements; never a blocker.

    First, when the versions in force are no longer the frozen ones, that the lot is judged
    against its frozen requirements. Then one line per signed replacement, oldest first."""
    notices = []
    newer = newer_versions(lot)
    if newer and newer["rules"]:
        notices.append(
            "The lot's rule set version is no longer in force"
            + (": " + ", ".join(newer["items"]) + " in force now" if newer["items"] else "")
            + ". The disposition is refused until quality replaces the lot's requirements."
        )
    elif newer and newer["items"]:
        notices.append(
            "The versions in force now are not the ones frozen for this lot: "
            + ", ".join(newer["items"])
            + ". The lot is dispositioned against its frozen requirements unless quality "
            "replaces them first. This does not block the disposition."
        )
    replaced = LotAssignment.objects.filter(lot=lot, origin=AssignmentOrigin.REPLACED)
    for assignment in replaced.select_related("assigned_by").order_by("assigned_at", "id"):
        superseded = [
            f"{row['label']} {row['test_code']}"
            for row in assignment.replacement.get("tests", [])
            if row["effect"] != "carried"
        ]
        signer = assignment.assigned_by.get_full_name() or assignment.assigned_by.get_username()
        notices.append(
            f"The lot's requirements were replaced during testing on "
            f"{timezone.localtime(assignment.assigned_at):%Y-%m-%d %H:%M %Z} by {signer}: "
            f"{assignment.reason} "
            + (
                "Superseded tests, kept in the record and not part of this evidence: "
                + ", ".join(superseded)
                + "."
                if superseded
                else "Every test carried over."
            )
        )
    return notices


@sensitive_variables("pin")
def replace_requirements(*, actor, pin, lot, expected_revision, reason, basis):
    """Replace a lot's frozen requirements, during testing, by the versions now in force.

    Signed by a quality person who authored none of the lot's data. ``basis`` is the preview
    the signer reviewed; anything that changed since refuses the signature. In one
    transaction: the tests whose requirement is no longer one of the lot's are superseded, a
    new assignment supersedes the current one and keeps the evidence of the replacement, the
    lot moves to the rule version in force, and the lot revision advances with the signature.
    """
    testing = _testing()
    held = {}

    def prepare():
        if testing is not None:
            held["tests"] = testing.lock(lot)  # tests before the lot, the order testing uses

    def apply(locked):
        preview = replacement_preview(locked, at=locked._signing_timestamp)
        if preview.blocker:
            raise ValidationError(preview.blocker)
        if denial := replacement_denial(actor, locked):
            raise PermissionDenied(denial)
        if preview.reasons:
            raise ValidationError(preview.reasons)
        if preview.basis != basis:
            raise ValidationError(REPLACEMENT_STALE)
        previous, payload, rules = preview.current, preview.payload, preview.rules
        tests = testing.apply(
            actor=actor,
            lot=locked,
            requirements=preview.requirements,
            reason=reason,
            locked=held["tests"],
        )
        evidence = {
            "schema": REPLACEMENT_SCHEMA,
            "replaces": {"assignment": previous.pk, "payload_hash": previous.payload_hash},
            "rules": {
                "before": {"id": locked.rules_id, "label": str(locked.rules)},
                "after": {"id": rules.pk, "label": str(rules)},
            },
            "specification": {
                "before": {
                    key: previous.payload["specification"][key]
                    for key in ("revision_id", "code", "version")
                },
                "after": {
                    key: payload["specification"][key] for key in ("revision_id", "code", "version")
                },
            },
            "lines": preview.lines,
            "tests": tests,
            "supplier_results": preview.supplier_results,
            # The lot revision this replacement's signature is bound to.
            "lot_revision": locked.revision + 1,
        }
        assignment = LotAssignment(
            lot=locked,
            material=previous.material,
            stage=previous.stage,
            scope=previous.scope,
            status=AssignmentStatus.READY,
            payload=payload,
            payload_hash=preview.payload_hash,
            specification_revision_id=payload["specification"]["revision_id"],
            plan_revision=previous.plan_revision,
            supersedes=previous,
            origin=AssignmentOrigin.REPLACED,
            replacement=evidence,
            reason=reason,
            assigned_by=actor,
        )
        assignment.full_clean()
        assignment.save()
        locked.rules = rules
        record_event(
            actor=actor,
            action="lot.requirements_replaced",
            obj=assignment,
            before={
                "assignment": previous.pk,
                "payload_hash": previous.payload_hash,
                "rules": evidence["rules"]["before"],
                "specification": evidence["specification"]["before"],
            },
            after={
                "lot": locked.pk,
                "payload_hash": assignment.payload_hash,
                "rules": evidence["rules"]["after"],
                "specification": evidence["specification"]["after"],
                "lines_changed": [
                    row["code"] for row in preview.lines if row["change"] != "unchanged"
                ],
                "tests_superseded": [row["label"] for row in tests if row["effect"] != "carried"],
                "tests_carried": [row["label"] for row in tests if row["effect"] == "carried"],
            },
            reason=reason,
        )

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=lot,
        expected_revision=expected_revision,
        meaning=REPLACED_MEANING,
        reason=reason,
        permission=AUTHOR_ROLE,
        apply=apply,
        prepare=prepare,
    )


# Sampling provenance ---------------------------------------------------------------------------


def _check_observation(
    *,
    plan_revision,
    containers_total,
    containers_sampled,
    quantity,
    quantity_unit,
    sampled_at,
    deviation,
):
    errors = {}
    if not plan_revision.effective_from <= sampled_at < plan_revision.effective_until:
        raise ValidationError(
            {
                "sampled_at": f"Sampling plan {plan_revision} is not effective at this sampling "
                "time. Assign current requirements to the lot first."
            }
        )
    required = containers_required(plan_revision.basis, plan_revision.parameter, containers_total)
    if containers_sampled > containers_total:
        errors["containers_sampled"] = "More containers sampled than the lot contains."
    if sampled_at > timezone.now():
        errors["sampled_at"] = "Sampling time cannot be in the future."
    if quantity is None or quantity <= 0:
        errors["quantity"] = "Enter the amount collected."
    if quantity_unit != plan_revision.quantity_unit:
        errors["quantity_unit"] = (
            f"The approved plan states amounts in {plan_revision.quantity_unit}."
        )
    if errors:
        raise ValidationError(errors)
    shortfalls = []
    if containers_sampled < required:
        shortfalls.append(f"plan requires {required} containers; {containers_sampled} sampled")
    if quantity < plan_revision.minimum_quantity:
        shortfalls.append(
            f"plan requires at least {plan_revision.minimum_quantity.normalize():f} "
            f"{plan_revision.quantity_unit}"
        )
    if shortfalls and not deviation.strip():
        raise ValidationError({"deviation": "Record a deviation: " + "; ".join(shortfalls) + "."})
    return required


@transaction.atomic
def record_sampling(
    *,
    actor,
    lot,
    reference,
    sampled_at,
    containers_total,
    containers_sampled,
    container_ids,
    quantity,
    quantity_unit,
    location,
    reason,
    deviation="",
    purpose=SamplingPurpose.ROUTINE,
    resample_of=None,
):
    """Record actual sampling against the lot's approved plan and create the foundation sample.

    A resample (``purpose="resample"``) names the original sample of the same lot it replaces
    for an investigation; the analytical app decides whether the resample is authorized.
    """
    require_role(actor, "analyst")
    _require_reason(reason)
    # The account, then the lot: the order of signing and of every other lot writer. Creating
    # the sample below locks the account, which must not be the second lock taken here.
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    assignment = current_assignment(locked)
    if locked.state == "quarantine" and (
        assignment is None or assignment.status != AssignmentStatus.READY
    ):
        current_requirements(locked)  # raises the hold with its reasons
    if blocker := sampling_blocker(locked):
        raise ValidationError(blocker)
    plan_revision = assignment.plan_revision
    if Sample.objects.filter(reference=reference).exists():
        raise ValidationError({"reference": "This sample reference already exists."})
    if purpose == SamplingPurpose.RESAMPLE:
        if (
            resample_of is None
            or resample_of.lot_id != locked.pk
            or not SamplingRecord.objects.filter(sample=resample_of).exists()
        ):
            raise ValidationError(
                {"resample_of": "Choose a sampled original sample of this lot to resample."}
            )
    elif purpose == SamplingPurpose.ROUTINE:
        if resample_of is not None:
            raise ValidationError({"resample_of": "Only a resample names an original sample."})
    else:
        raise ValidationError({"purpose": "Unknown sampling purpose."})
    required = _check_observation(
        plan_revision=plan_revision,
        containers_total=containers_total,
        containers_sampled=containers_sampled,
        quantity=quantity,
        quantity_unit=quantity_unit,
        sampled_at=sampled_at,
        deviation=deviation,
    )
    sample = add_sample(
        actor=actor, lot=locked, reference=reference, collected_at=sampled_at, reason=reason
    )
    record = SamplingRecord(
        lot=locked,
        sample=sample,
        assignment=assignment,
        plan_revision=plan_revision,
        containers_total=containers_total,
        containers_required=required,
        containers_sampled=containers_sampled,
        container_ids=container_ids,
        quantity=quantity,
        quantity_unit=quantity_unit,
        location=location,
        sampled_at=sampled_at,
        sampled_by=actor,
        recorded_by=actor,
        deviation=deviation,
        reason=reason,
        purpose=purpose,
        resample_of=resample_of,
    )
    record.full_clean()
    record.save()
    if record.deviation:
        DeviationReview.objects.create(record=record)
    record_event(
        actor=actor, action="sampling.recorded", obj=record, after=snapshot(record), reason=reason
    )
    return record


@transaction.atomic
def correct_sampling(
    *,
    actor,
    record,
    reason,
    sampled_at,
    containers_total,
    containers_sampled,
    container_ids,
    quantity,
    quantity_unit,
    location,
    deviation="",
):
    """Add a linked correction; the original sampling record is preserved unchanged."""
    require_role(actor, "analyst")
    _require_reason(reason)
    locked_lot = Lot.objects.select_for_update().get(pk=record.lot_id)
    original = SamplingRecord.objects.select_for_update().get(pk=record.pk)
    if blocker := correction_blocker(original):
        raise ValidationError(blocker)
    required = _check_observation(
        plan_revision=original.plan_revision,
        containers_total=containers_total,
        containers_sampled=containers_sampled,
        quantity=quantity,
        quantity_unit=quantity_unit,
        sampled_at=sampled_at,
        deviation=deviation,
    )
    correction = SamplingRecord(
        lot=locked_lot,
        sample=original.sample,
        assignment=original.assignment,
        plan_revision=original.plan_revision,
        containers_total=containers_total,
        containers_required=required,
        containers_sampled=containers_sampled,
        container_ids=container_ids,
        quantity=quantity,
        quantity_unit=quantity_unit,
        location=location,
        sampled_at=sampled_at,
        sampled_by=original.sampled_by,
        recorded_by=actor,
        deviation=deviation,
        reason=reason,
        corrects=original,
        purpose=original.purpose,
        resample_of=original.resample_of,
    )
    correction.full_clean()
    correction.save()
    if correction.deviation:
        DeviationReview.objects.create(record=correction)
    Lot.objects.filter(pk=locked_lot.pk).update(revision=F("revision") + 1)
    record_event(
        actor=actor,
        action="sampling.corrected",
        obj=correction,
        before=snapshot(original),
        after=snapshot(correction),
        reason=reason,
    )
    return correction


# Deviation assessment -------------------------------------------------------------------------


def assess_deviation(*, actor, pin, review, expected_revision, accept, reason):
    """Independent quality decision on a sampling deviation, signed with PIN re-entry."""

    def apply(locked):
        record = SamplingRecord.objects.get(pk=locked.record_id)
        lot = Lot.objects.select_for_update().get(pk=record.lot_id)
        reason, is_permission = assessment_blocker(locked, actor)
        if reason:
            raise (PermissionDenied if is_permission else ValidationError)(reason)
        locked.status = DeviationStatus.ACCEPTED if accept else DeviationStatus.REJECTED
        locked.decided_by = actor
        locked.decided_at = timezone.now()
        Lot.objects.filter(pk=lot.pk).update(revision=F("revision") + 1)

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=review,
        expected_revision=expected_revision,
        meaning="accepted" if accept else "rejected",
        reason=reason,
        permission=AUTHOR_ROLE,
        apply=apply,
    )


# Disposition gate ------------------------------------------------------------------------------


def current_records(lot):
    """{sample_id: latest SamplingRecord in its correction chain} for the lot."""
    records = list(
        SamplingRecord.objects.filter(lot=lot).select_related(
            "sample", "plan_revision", "deviation_review"
        )
    )
    corrected = {r.corrects_id for r in records if r.corrects_id}
    return {r.sample_id: r for r in records if r.pk not in corrected}


def lot_blockers(lot):
    """Reasons this lot's sampling cannot support QC disposition; empty when it can.

    Read-only; call under the caller's lock on the lot row. Every sample of the lot needs current
    sampling provenance against the plan of the current requirement assignment; deviations need
    an accepted independent assessment. An approved plan alone is not evidence of sampling.
    """
    assignment = current_assignment(lot)
    if assignment is None:
        return ["Applicability hold: no specification or sampling requirements are assigned."]
    if assignment.status != AssignmentStatus.READY:
        return [f"Applicability hold: {reason}" for reason in assignment.hold_reasons]
    samples = list(Sample.objects.filter(lot=lot).order_by("reference"))
    if not samples:
        return ["No sampling has been recorded against the approved sampling plan."]
    current = current_records(lot)
    reasons = []
    for sample in samples:
        record = current.get(sample.pk)
        if record is None:
            reasons.append(
                f"Sample {sample.reference} has no sampling record against the approved plan."
            )
            continue
        if record.plan_revision_id != assignment.plan_revision_id:
            reasons.append(
                f"Sample {sample.reference} was sampled under {record.plan_revision}; the current "
                f"requirements use {assignment.plan_revision}."
            )
        if record.deviation:
            review = getattr(record, "deviation_review", None)
            status = review.status if review else DeviationStatus.PENDING
            if status == DeviationStatus.PENDING:
                reasons.append(
                    f"Sampling deviation for sample {sample.reference} awaits quality assessment."
                )
            elif status == DeviationStatus.REJECTED:
                reasons.append(
                    f"Sampling deviation for sample {sample.reference} was rejected; correct the "
                    "record or resample."
                )
    return reasons
