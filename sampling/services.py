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

- ``applied_rules(lot)`` -> the rule set versions the lot is under: its own, then the additional
  ones frozen with its current requirements. ``require_additional_rules(lot)`` raises unless
  the additional ones are in force (the caller checks the lot's own).

Before testing starts, requirements are assigned and assigned again without a signature. Once
testing has started only ``replace_requirements`` changes them: a quality person who authored
none of the lot's data signs the replacement by the versions now in force. The testing module
is reached through ``settings.REQUIREMENT_REPLACEMENT_TESTING`` and never imported here: it says
which tests carry over and which are superseded, refuses while a result would be set aside
unevaluated, and has its tests locked before the lot (``sign_transition(prepare=...)``).

A lot is assigned under one or more scopes (``general`` and named market or customer overlays).
Every specification of a named scope and every additional rule set in force that names the
lot's material, stage or scopes applies. Where the specifications state a test differently
nothing is merged or picked: the assignment is a hold until ``decide_conflicts`` (before
testing) or the replacement (during testing) records which statement applies, signed by a
quality person who authored none of the lot's data.
"""

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from math import isqrt

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_slug
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.decorators.debug import sensitive_variables

from catalog.models import RevisionStatus, Specification
from catalog.services import (
    AUTHOR_ROLE,
    GENERAL,
    ApplicabilityHold,
    Applicable,
    _check_interval,
    _next_version,
    _require_reason,
    digest,
    effective_revision,
    normalize_scopes,
    register_check,
    requirement_text,
    same_requirement,
    test_requirement,
)
from core.audit import record_event, snapshot
from core.models import RuleSet
from core.services import (
    APPLIES_TO,
    applies_at,
    require_role,
    sign_transition,
    validate_rules,
)
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


def payload_scopes(payload):
    """The scopes a frozen requirement payload was resolved under."""
    return list(payload.get("scopes") or [payload["scope"]])


def payload_specifications(payload):
    """The specification versions frozen in a requirement payload, each with its scope."""
    return list(
        payload.get("specifications") or [{"scope": payload["scope"], **payload["specification"]}]
    )


def payload_additional_rules(payload):
    """The additional rule set versions frozen in a requirement payload."""
    return list(payload.get("additional_rules") or [])


def _test_requirements(payload, payload_hash):
    """Each required line with its source: the specification version that states it (the
    first of them when several state it alike) and the lot's requirement payload hash."""
    by_scope = {spec["scope"]: spec for spec in payload_specifications(payload)}

    def source(line):
        spec = by_scope[line["sources"][0]] if "sources" in line else payload["specification"]
        return (
            f"catalog:{spec['code']}@v{spec['version']}#rev{spec['revision_id']}"
            f"/lot-req:{payload_hash[:16]}"
        )

    return {t["code"]: test_requirement(t, source(t)) for t in payload["tests"] if t["required"]}


def rules_in_force(rules, at):
    """The approved version of this rule set that applies at ``at``, or None."""
    return RuleSet.objects.filter(applies_at(at), code=rules.code).order_by("-version").first()


def applied_rules(lot, assignment=None):
    """The rule set versions the lot is under: its own, then the additional ones frozen with
    its current requirements (none while it has no requirements or is held)."""
    assignment = assignment or current_assignment(lot)
    ids = []
    if assignment is not None and assignment.status == AssignmentStatus.READY:
        ids = [rule["id"] for rule in payload_additional_rules(assignment.payload)]
    found = RuleSet.objects.in_bulk(ids)
    return [lot.rules, *(found[pk] for pk in ids)]


def additional_rule_problems(lot, at=None):
    """Why an additional rule set version frozen for the lot can no longer be relied on, one
    reason each; empty when all are approved and in force."""
    problems = []
    for rule in applied_rules(lot)[1:]:
        try:
            validate_rules(rule, at)
        except ValidationError:
            problems.append(
                f"Rule set {rule}, which applies to this lot in addition to its own, is no "
                "longer in force. Assign the lot's requirements again, or have quality replace "
                "them once testing has started."
            )
    return problems


def require_additional_rules(lot, at=None):
    """Assigning tests and the disposition need every rule set version the lot is under in
    force. The caller checks the lot's own; this refuses a retired or expired additional one."""
    if problems := additional_rule_problems(lot, at):
        raise ValidationError(problems)


MAX_SCOPES = 12


def clean_scopes(scopes):
    """The scopes named for a lot, each once, ``general`` first. A scope is a slug of at most
    60 characters; at least one and at most ``MAX_SCOPES`` are named."""
    names = [str(name).strip() for name in scopes or []]
    if not names:
        raise ValidationError({"scopes": "Name at least one scope, for example general."})
    for name in names:
        try:
            validate_slug(name)
        except ValidationError as exc:
            raise ValidationError(
                {"scopes": f"“{name}” is not a scope name: use letters, digits, - and _."}
            ) from exc
        if len(name) > 60:
            raise ValidationError({"scopes": "A scope name has at most 60 characters."})
    names = normalize_scopes(names)
    if len(names) > MAX_SCOPES:
        raise ValidationError({"scopes": f"A lot is assigned under at most {MAX_SCOPES} scopes."})
    return names


def configured_scopes():
    """The scopes the configuration names: those of the specifications and those an approved
    additional rule set applies to. Shown where a lot's scopes are entered."""
    names = set(Specification.objects.values_list("scope", flat=True))
    additional = RuleSet.objects.filter(status="approved", policy__has_key=APPLIES_TO)
    for policy in additional.values_list("policy", flat=True):
        names.update(policy[APPLIES_TO].get("scopes", []))
    return normalize_scopes(names)


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


@dataclass
class Resolution:
    """The versions in force for a lot's material, stage and scopes, read at one moment.

    ``reasons`` is everything that holds the lot; ``conflicts`` the part of it a quality
    decision settles and ``blocking`` the part it cannot. ``applicable`` is what was read:
    it is frozen again, without another read, once a choice is made.
    """

    rules: RuleSet
    applicable: Applicable
    payload: dict | None = None
    plan_revision: SamplingPlanRevision | None = None
    plan_payload: dict | None = None
    reasons: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    blocking: list = field(default_factory=list)


def _resolve(lot, *, material, stage, scopes, at, decisions=None):
    """Read what applies to the lot now, once. The lot follows its own rule set: the version
    in force is applied, as it is for the specifications and the methods; with none in force
    the lot's version is named in the hold. A sampled lot keeps its sampling plan version."""
    rules = rules_in_force(lot.rules, at) or lot.rules
    read = Applicable(material=material, stage=stage, scopes=scopes, rules=rules, at=at)
    found = Resolution(rules=rules, applicable=read)
    try:
        found.payload = read.freeze(decisions)
    except ApplicabilityHold as hold:
        found.blocking.extend(hold.blocking)
        found.conflicts = hold.conflicts
    found.plan_revision, found.plan_payload = _plan_payload(
        lot, material, stage, at, found.blocking
    )
    found.reasons = found.blocking + [conflict["reason"] for conflict in found.conflicts]
    if found.reasons:
        found.payload = None
    return found


def _frozen(lot, resolution, payload=None):
    """The requirement payload as it is frozen for the lot."""
    payload = {**(payload or resolution.payload), "lot": {"id": lot.pk, "number": lot.number}}
    payload["sampling_plan"] = resolution.plan_payload
    return payload


DECIDED_BY_QUALITY = (
    "Quality decided which requirement applies to this lot where its specifications differ. "
    "Only quality assigns its requirements again; the decision is then made again."
)


def decision_records(assignment):
    """The choices between differing statements behind an assignment's requirements, each
    with who decided it, when, why and how (``decided``): made with a signed decision before
    testing, or made or carried with a signed replacement during testing."""
    if assignment is None:
        return []
    if assignment.origin == AssignmentOrigin.DECIDED:
        return list(assignment.decision.get("choices") or [])
    if assignment.origin == AssignmentOrigin.REPLACED:
        return list(assignment.replacement.get("decisions") or [])
    return []


def reassignment_denial(actor, lot, assignment=None):
    """Why this person cannot assign the lot's requirements again, or "": a signed decision
    is not set aside by someone without the quality role."""
    assignment = assignment or current_assignment(lot)
    if decision_records(assignment) and not actor.groups.filter(name=AUTHOR_ROLE).exists():
        return DECIDED_BY_QUALITY
    return ""


@transaction.atomic
def assign_requirements(*, actor, lot, material, stage, reason, scope=GENERAL, scopes=None):
    """Freeze the effective specifications, methods and sampling plan for a lot, or record a hold.

    The lot is assigned under one or more scopes (``scopes``; ``scope`` names a single one).
    Every specification of a named scope applies, and every additional rule set in force that
    names the lot's material, stage or scopes. Where they state a test differently, or
    something is missing, the assignment is a hold: nothing is merged or picked here.

    A new assignment supersedes the previous one; earlier assignments and their payloads remain.
    The lot moves to the version in force of its own rule set when that is not the one it has,
    and once it has been sampled it keeps the plan version its samples were taken under.
    The lot revision increments so a disposition prepared against old requirements goes stale.
    Once testing has started this is refused: tests are bound to the frozen payload, and only
    a signed replacement (``replace_requirements``) changes the lot's requirements.
    """
    require_role(actor, "analyst", "quality")
    _require_reason(reason)
    scopes = clean_scopes(scopes if scopes is not None else [scope])
    # The account, then the lot: the order of signing and of every other lot writer. The new
    # assignment names the account, and that reference must not be the last lock taken here.
    get_user_model().objects.select_for_update(no_key=True).get(pk=actor.pk)
    locked = Lot.objects.select_for_update().get(pk=lot.pk)
    if blocker := assignment_blocker(locked):
        raise ValidationError(blocker)
    previous = current_assignment(locked)
    if denial := reassignment_denial(actor, locked, previous):
        raise PermissionDenied(denial)
    resolution = _resolve(locked, material=material, stage=stage, scopes=scopes, at=timezone.now())
    reasons, rules = resolution.reasons, resolution.rules
    assignment = LotAssignment(
        lot=locked,
        material=material,
        stage=stage,
        scope=scopes[0],
        scopes=scopes,
        reason=reason,
        assigned_by=actor,
        supersedes=previous,
    )
    payload = None if reasons else _frozen(locked, resolution)
    if reasons:
        assignment.status = AssignmentStatus.HOLD
        assignment.hold_reasons = reasons
    else:
        assignment.status = AssignmentStatus.READY
        assignment.payload = payload
        assignment.payload_hash = digest(payload)
        assignment.specification_revision_id = payload["specification"]["revision_id"]
        assignment.plan_revision = resolution.plan_revision
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
            **({"scopes": scopes} if scopes != [GENERAL] else {}),
            **(
                {"conflicts": [c["code"] for c in resolution.conflicts]}
                if resolution.conflicts
                else {}
            ),
            **({"rules": rules.pk} if moved else {}),
            **(
                {"additional_rules": [r["id"] for r in payload_additional_rules(payload)]}
                if payload and payload_additional_rules(payload)
                else {}
            ),
            "specification_revision": assignment.specification_revision_id,
            "plan_revision": assignment.plan_revision_id,
            "payload_hash": assignment.payload_hash,
        },
        reason=reason,
    )
    return assignment


# Conflicting requirements: the signed quality decision ------------------------------------------

DECIDED_MEANING = "requirements_decided"
DECISION_SCHEMA = "oq.requirement-decision/1"
NO_DECISION = "This lot is not held for a decision on conflicting requirements."
DECISION_IN_TESTING = (
    "Testing has started on this lot. Quality decides conflicting requirements when it "
    "replaces the lot's requirements."
)
NO_CONFLICT = (
    "The specifications that apply to this lot no longer state a test differently. Assign "
    "the lot's requirements again."
)
SELF_DECISION = (
    "You recorded receipt, supplier certificate, sampling or test data of this lot, or proposed "
    "a supplier's result for it. Someone who authored none of it decides which requirement "
    "applies."
)
DECISION_STALE = (
    "The specifications or rule sets in force changed after this page was opened. Review the "
    "conflicting requirements again before signing."
)
CHOICE_REQUIRED = (
    "Choose which requirement applies for each test the specifications state differently."
)


@dataclass
class Decision:
    """What deciding a lot's conflicting requirements now would settle. Built read-only for
    the page and again under the lock for the signature; ``basis`` identifies everything the
    signer was shown except the time of resolution: the tests stated differently with their
    statements, the tests stated one way (``agreed``), and every version that was read."""

    lot: Lot
    current: LotAssignment | None
    blocker: str = ""
    conflicts: list = field(default_factory=list)
    agreed: list = field(default_factory=list)
    specifications: list = field(default_factory=list)
    additional_rules: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    rules: RuleSet | None = None
    resolution: Resolution | None = None
    basis: str = ""

    @property
    def possible(self):
        return not self.blocker and not self.reasons


def decision_blocker(lot, assignment=None):
    """Why this lot's conflicting requirements cannot be decided here at all, or None."""
    if lot.state != "quarantine":
        return "Only quarantined lots can have conflicting requirements decided."
    if testing_started(lot):
        return DECISION_IN_TESTING
    assignment = assignment or current_assignment(lot)
    if assignment is None or assignment.status != AssignmentStatus.HOLD:
        return NO_DECISION
    return None


def decision_denial(actor, lot):
    """Why this person cannot sign the decision, or "". Shown before any PIN is requested."""
    return SELF_DECISION if actor.pk in disposition_authors(lot) else ""


def _conflict_basis(conflicts):
    """What a signer was shown of each conflict: the statements and who states them."""
    return [
        [
            conflict["code"],
            [
                [item["scopes"], item["specification"]["revision_id"], item["name"], item["text"]]
                + [item["required"]]
                for item in conflict["candidates"]
            ],
        ]
        for conflict in conflicts
    ]


def decision_preview(lot, at=None):
    """Read once the versions in force for the scopes of the lot's held assignment, and list
    the tests the specifications state differently, each with its statements, beside the
    tests stated one way and the specifications and rule sets that apply.

    ``reasons`` are the other reasons the lot is held; a decision cannot settle them, so it
    is refused until they are resolved in the configuration. ``resolution`` is what was
    read: the signature freezes it with the choices, without reading again.
    """
    current = current_assignment(lot)
    preview = Decision(lot=lot, current=current)
    if blocker := decision_blocker(lot, current):
        preview.blocker = blocker
        return preview
    resolution = _resolve(
        lot,
        material=current.material,
        stage=current.stage,
        scopes=current.scope_list,
        at=at or timezone.now(),
    )
    if not resolution.conflicts:
        preview.blocker = NO_CONFLICT
        return preview
    read = resolution.applicable
    preview.resolution = resolution
    preview.rules = resolution.rules
    preview.conflicts = resolution.conflicts
    preview.agreed = read.agreed
    preview.specifications = [
        {"scope": name, "code": spec.code, "version": revision.version, "revision_id": revision.pk}
        for name, spec, revision in read.specifications
    ]
    preview.additional_rules = [
        {
            "code": rule.code,
            "version": rule.version,
            "required_tests": rule.policy["required_tests"],
        }
        for rule in read.extra
    ]
    preview.reasons = resolution.blocking
    preview.basis = digest(
        {
            "previous": current.pk,
            "rules": resolution.rules.pk,
            # Every version that was read: a specification, method or additional rule set
            # approved since makes the page stale, whether or not it is part of a conflict.
            "applied": read.applied,
            "plan": resolution.plan_revision.pk if resolution.plan_revision else None,
            "conflicts": _conflict_basis(resolution.conflicts),
            "agreed": [[row["code"], row["text"], row["required"]] for row in preview.agreed],
            "reasons": resolution.blocking,
        }
    )
    return preview


def _check_choices(conflicts, choices):
    """``choices`` names, for exactly the conflicting tests, a scope that states the test."""
    choices = dict(choices or {})
    offered = {
        conflict["code"]: {scope for item in conflict["candidates"] for scope in item["scopes"]}
        for conflict in conflicts
    }
    if set(choices) != set(offered) or any(choices[code] not in offered[code] for code in offered):
        raise ValidationError(CHOICE_REQUIRED)
    return choices


def _stamped(decisions, *, actor, at, reason, how, earlier=None):
    """The decided statements with who decided each, when, why and how. ``earlier`` maps a
    test code to the record of a choice that still stands unchanged; it keeps its own."""
    made = {
        "by": actor.get_full_name() or actor.get_username(),
        "by_id": actor.pk,
        "at": at.isoformat(),
        "reason": reason,
        "with": how,
    }
    earlier = earlier or {}
    return [
        {**item, "decided": earlier[item["code"]]["decided"] if item["code"] in earlier else made}
        for item in decisions
    ]


@sensitive_variables("pin")
def decide_conflicts(*, actor, pin, lot, expected_revision, reason, choices, basis):
    """Decide, before testing, which statement applies where the specifications that apply to
    a lot state a test differently, and freeze the lot's requirements accordingly.

    Signed by a quality person who authored none of the lot's data. ``choices`` is {test
    code: scope whose statement applies} for every conflicting test and ``basis`` the preview
    the signer reviewed; anything that changed since refuses the signature. What applies is
    read once under the lock: the token is checked against that read and the same read is
    frozen with the choices. The statements not chosen stay in the record with the decision.
    Nothing else that holds the lot is settled here: an incomplete resolution refuses the
    decision.
    """

    def apply(locked):
        at = locked._signing_timestamp
        preview = decision_preview(locked, at=at)
        if preview.blocker:
            raise ValidationError(preview.blocker)
        if denial := decision_denial(actor, locked):
            raise PermissionDenied(denial)
        if preview.basis != basis:
            raise ValidationError(DECISION_STALE)
        if preview.reasons:
            raise ValidationError(preview.reasons)
        decided = _check_choices(preview.conflicts, choices)
        previous, resolution = preview.current, preview.resolution
        try:
            resolved = resolution.applicable.freeze(decided)
        except ApplicabilityHold as hold:
            # The choice itself can leave a rule set uncovered (an information-only line).
            raise ValidationError(hold.reasons) from hold
        payload, rules = _frozen(locked, resolution, resolved), resolution.rules
        evidence = {
            "schema": DECISION_SCHEMA,
            "decides": {"assignment": previous.pk},
            "choices": _stamped(
                payload["decisions"], actor=actor, at=at, reason=reason, how="decision"
            ),
            # The lot revision this decision's signature is bound to.
            "lot_revision": locked.revision + 1,
        }
        assignment = LotAssignment(
            lot=locked,
            material=previous.material,
            stage=previous.stage,
            scope=previous.scope,
            scopes=previous.scope_list,
            status=AssignmentStatus.READY,
            payload=payload,
            payload_hash=digest(payload),
            specification_revision_id=payload["specification"]["revision_id"],
            plan_revision=resolution.plan_revision,
            supersedes=previous,
            origin=AssignmentOrigin.DECIDED,
            decision=evidence,
            reason=reason,
            assigned_by=actor,
        )
        assignment.full_clean()
        assignment.save()
        moved = rules.pk != locked.rules_id
        before_rules = locked.rules_id
        locked.rules = rules
        record_event(
            actor=actor,
            action="lot.requirements_decided",
            obj=assignment,
            before={
                "assignment": previous.pk,
                "hold_reasons": previous.hold_reasons,
                **({"rules": before_rules} if moved else {}),
            },
            after={
                "lot": locked.pk,
                "scopes": assignment.scope_list,
                "decisions": [
                    {
                        "code": item["code"],
                        "scope": item["scope"],
                        "specification": item["specification"],
                        "differs": item["differs"],
                        "applies": item["text"],
                        "not_applied": [alt["text"] for alt in item["alternatives"]],
                    }
                    for item in payload["decisions"]
                ],
                **({"rules": rules.pk} if moved else {}),
                "additional_rules": [r["id"] for r in payload_additional_rules(payload)],
                "specification_revision": assignment.specification_revision_id,
                "plan_revision": assignment.plan_revision_id,
                "payload_hash": assignment.payload_hash,
            },
            reason=reason,
        )

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=lot,
        expected_revision=expected_revision,
        meaning=DECIDED_MEANING,
        reason=reason,
        permission=AUTHOR_ROLE,
        apply=apply,
    )


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
            change = "unchanged" if same_requirement(was, now) else "changed"
        rows.append(
            {
                "code": code,
                "name": (now or was)["name"],
                "change": change,
                "before": requirement_text(was) if was else "",
                "after": requirement_text(now) if now else "",
                "required": bool(now and now["required"]),
                "was_required": bool(was and was["required"]),
            }
        )
    return rows


@dataclass
class Replacement:
    """What replacing a lot's requirements now would do. Built read-only for the page and again
    under the locks for the signature; ``basis`` identifies everything the signer was shown
    except the time of resolution.

    ``conflicts`` are the tests the specifications in force state differently and no choice
    settles yet; ``standing`` the choices of the lot's current requirements that still stand,
    and ``choices`` those and the ones given, by test code."""

    lot: Lot
    current: LotAssignment | None
    blocker: str = ""
    reasons: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    standing: dict = field(default_factory=dict)
    choices: dict = field(default_factory=dict)
    rules: RuleSet | None = None
    payload: dict | None = None
    payload_hash: str = ""
    requirements: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    tests: list = field(default_factory=list)
    supplier_results: list = field(default_factory=list)
    basis: str = ""

    @property
    def possible(self):
        return not self.blocker and not self.reasons and not self.conflicts

    @property
    def superseded(self):
        return [row for row in self.tests if row["effect"] == "superseded"]

    @property
    def carried(self):
        return [row for row in self.tests if row["effect"] == "carried"]


def _version_labels(payload):
    """{key: label} of the rule set and specification versions frozen in a payload, the lot's
    own rule set excepted (the lot row holds it)."""
    labels = {
        ("rule set", rule["code"]): f"{rule['code']} v{rule['version']}"
        for rule in payload_additional_rules(payload)
    }
    for spec in payload_specifications(payload):
        labels[("specification", spec["code"])] = f"{spec['code']} v{spec['version']}"
    return labels


def _version_changes(old, new):
    """What differs between the additional rule sets and the specifications of two payloads:
    ``[{"kind", "code", "before", "after"}]``, a side empty when the document applies on the
    other side only."""
    before, after = _version_labels(old), _version_labels(new)
    return [
        {
            "kind": key[0],
            "code": key[1],
            "before": before.get(key, ""),
            "after": after.get(key, ""),
        }
        for key in [*before, *(key for key in after if key not in before)]
        if before.get(key) != after.get(key)
    ]


def _standing_choices(payload, read):
    """{test code: scope} of the choices in a frozen payload that still stand under what
    applies now (``read``): the scope that was named states the test exactly as it is frozen
    for the lot. A choice whose statement was revised is not carried; it is made again."""
    frozen = {line["code"]: line for line in payload["tests"]}
    standing = {}
    for item in payload.get("decisions") or []:
        stated = read.line(item["code"], item["scope"])
        if stated is not None and same_requirement(frozen[item["code"]], stated):
            standing[item["code"]] = item["scope"]
    return standing


def replacement_preview(lot, at=None, choices=None):
    """Resolve the versions in force for the lot's material, stage and scopes and its rule
    sets, and work out what replacing the lot's requirements with them would do.

    The sampling plan is kept: samples already taken were taken under it. A resolution that
    is incomplete (no effective specification, method or rule version, or a rule set the
    specifications do not cover) is a reason for refusal, never a hold recorded on the lot.
    Where the specifications in force state a test differently, the choice made for the lot's
    current requirements is carried while the scope that was named still states the test
    exactly as it is frozen for the lot, and ``choices`` ({test code: scope}) settles the
    rest; a conflict without a choice is listed and the replacement waits for one. What
    applies is read once; the payload and the token of the preview come from that read.
    """
    current = current_assignment(lot)
    preview = Replacement(lot=lot, current=current)
    if blocker := replacement_blocker(lot, current):
        preview.blocker = blocker
        return preview
    at = at or timezone.now()
    rules = rules_in_force(lot.rules, at)
    preview.rules = rules
    read = Applicable(
        material=current.material,
        stage=current.stage,
        scopes=current.scope_list,
        rules=rules,
        at=at,
    )
    preview.standing = _standing_choices(current.payload, read)
    preview.choices = {**preview.standing, **dict(choices or {})}
    reasons = []
    if rules is None:
        reasons.append(f"Rule set {lot.rules.code} has no approved version effective now.")
    resolved = None
    try:
        resolved = read.freeze(preview.choices)
    except ApplicabilityHold as hold:
        reasons.extend(hold.blocking)
        preview.conflicts = hold.conflicts
    if reasons or preview.conflicts:
        preview.reasons = reasons
        return preview
    payload = {**resolved, "lot": {"id": lot.pk, "number": lot.number}}
    payload["sampling_plan"] = current.payload["sampling_plan"]
    preview.payload, preview.payload_hash = payload, digest(payload)
    preview.lines = _line_changes(current.payload, payload)
    preview.versions = _version_changes(current.payload, payload)
    if (
        rules.pk == lot.rules_id
        and not preview.versions
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
            "additional_rules": [rule["id"] for rule in payload_additional_rules(payload)],
            "specifications": [
                [spec["scope"], spec["approved_hash"]] for spec in payload_specifications(payload)
            ],
            "decisions": payload.get("decisions") or [],
            "tests": payload["tests"],
            "testing": [[row["test"], row["state"], row["effect"]] for row in preview.tests],
            "supplier_results": preview.supplier_results,
        }
    )
    return preview


def newer_versions(lot, current=None):
    """What differs between the versions in force and the ones frozen for a lot in testing, or
    None when nothing does (or the lot is not in quarantine and in testing).

    ``{"items": [...], "reasons": [...], "rules": bool, "own_rules": bool}``: ``items`` names
    the rule set and specification versions in force and counts the requirements that
    changed; ``reasons`` is set instead when the versions in force cannot be applied to the
    lot; ``rules`` says that a rule set version the lot is under is no longer in force, which
    the disposition requires, and ``own_rules`` that it is the lot's own. The lot keeps its
    frozen requirements either way, until quality replaces them.
    """
    if lot.state != "quarantine" or not testing_started(lot):
        return None
    preview = replacement_preview(lot)
    if preview.blocker:
        return None
    own = preview.rules is None or preview.rules.pk != lot.rules_id
    found = {
        "items": [],
        "reasons": preview.reasons if preview.payload is None else [],
        # A rule set version the lot is under is no longer in force: that blocks the
        # disposition.
        "rules": own or bool(additional_rule_problems(lot)),
        "own_rules": own,
    }
    if preview.rules and preview.rules.pk != lot.rules_id:
        found["items"].append(f"rule set {preview.rules}")
    if preview.conflicts:
        codes = ", ".join(conflict["code"] for conflict in preview.conflicts)
        found["items"].append(
            f"the specifications in force state {codes} differently, which quality decides "
            "with the replacement"
        )
    if preview.payload:
        for change in preview.versions:
            found["items"].append(
                f"{change['kind']} {change['after']}"
                if change["after"]
                else f"{change['kind']} {change['before']} no longer applies"
            )
        changed = sum(1 for row in preview.lines if row["change"] != "unchanged")
        if changed:
            found["items"].append(f"{changed} requirement{'' if changed == 1 else 's'} changed")
    return found


def _when_by(assignment):
    signer = assignment.assigned_by.get_full_name() or assignment.assigned_by.get_username()
    return f"{timezone.localtime(assignment.assigned_at):%Y-%m-%d %H:%M %Z} by {signer}"


def applicability_notices(lot, current=None):
    """For a lot assigned under several scopes or rule sets: one line that names the scopes,
    the specifications and the additional rule sets its requirements were frozen from, so the
    disposition signer sees what the lot was judged under. Never a blocker."""
    current = current or current_assignment(lot)
    if current is None or current.status != AssignmentStatus.READY:
        return []
    payload = current.payload
    if "specifications" not in payload:
        return []
    specifications = ", ".join(
        f"{spec['code']} v{spec['version']} ({spec['scope']})"
        for spec in payload_specifications(payload)
    )
    additional = ", ".join(
        f"{rule['code']} v{rule['version']}" for rule in payload_additional_rules(payload)
    )
    return [
        f"The lot's requirements were assigned under the scope"
        f"{'' if len(payload_scopes(payload)) == 1 else 's'} "
        f"{', '.join(payload_scopes(payload))}: "
        f"specification{'' if len(payload_specifications(payload)) == 1 else 's'} "
        f"{specifications}"
        + (f"; additional rule sets applied: {additional}" if additional else "")
        + ". A market or customer the lot is for and that is not named here was not applied."
    ]


def _moment(iso):
    from datetime import datetime

    return f"{timezone.localtime(datetime.fromisoformat(iso)):%Y-%m-%d %H:%M %Z}"


def decision_notices(lot, current=None):
    """One line per conflict decided in the lot's current requirements: which specification's
    statement applies, what it was chosen over, who decided, when and why, and the
    replacement that carried the choice since. Then one line for a signed decision that was
    set aside when the lot's requirements were assigned again. Never a blocker."""
    current = current or current_assignment(lot)
    notices = []
    if current is not None and current.status == AssignmentStatus.READY:
        for item in decision_records(current):
            made = item["decided"]
            carried = current.is_replacement and made["at"] != current.replacement["signed_at"]
            notices.append(
                f"The specifications that apply to this lot state {item['code']} differently "
                f"({', '.join(item['differs'])}). Decided on {_moment(made['at'])} by "
                f"{made['by']}: {item['specification']['code']} "
                f"v{item['specification']['version']} ({', '.join(item['scopes'])}) applies, "
                f"{item['text']}; not applied: "
                + "; ".join(
                    f"{alt['specification']['code']} v{alt['specification']['version']} "
                    f"({', '.join(alt['scopes'])}), {alt['text']}"
                    for alt in item["alternatives"]
                )
                + f". Reason: {made['reason']}"
                + (
                    f" The choice was carried by the replacement of {_when_by(current)}."
                    if carried
                    else ""
                )
            )
    set_aside = LotAssignment.objects.filter(
        lot=lot, origin=AssignmentOrigin.DECIDED, superseded_by__origin=AssignmentOrigin.ASSIGNED
    ).select_related("assigned_by", "superseded_by__assigned_by")
    for decided in set_aside.order_by("assigned_at", "id"):
        after = decided.superseded_by
        codes = ", ".join(item["code"] for item in decision_records(decided))
        notices.append(
            f"The decision of {_when_by(decided)} on the requirements the specifications "
            f"state differently ({codes}) was set aside without a signature when the lot's "
            f"requirements were assigned again on {_when_by(after)} under the scope"
            f"{'' if len(after.scope_list) == 1 else 's'} {', '.join(after.scope_list)}."
        )
    return notices


def replacement_notices(lot):
    """What a disposition signer should know about the lot's requirements; never a blocker.

    First, when the versions in force are no longer the frozen ones, that the lot is judged
    against its frozen requirements. Then one line per signed replacement, oldest first; for
    a lot under several scopes or rule sets, what its requirements were frozen from; and one
    line per conflict between specifications that quality decided for the current
    requirements."""
    notices = []
    newer = newer_versions(lot)
    if newer and newer["rules"]:
        notices.append(
            (
                "The lot's rule set version is no longer in force"
                if newer["own_rules"]
                else "A rule set version that applies to this lot in addition to its own is no "
                "longer in force"
            )
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
        notices.append(
            f"The lot's requirements were replaced during testing on {_when_by(assignment)}: "
            f"{assignment.reason} "
            + (
                "Superseded tests, kept in the record and not part of this evidence: "
                + ", ".join(superseded)
                + "."
                if superseded
                else "Every test carried over."
            )
        )
    return notices + applicability_notices(lot) + decision_notices(lot)


@sensitive_variables("pin")
def replace_requirements(*, actor, pin, lot, expected_revision, reason, basis, choices=None):
    """Replace a lot's frozen requirements, during testing, by the versions now in force.

    Signed by a quality person who authored none of the lot's data. ``basis`` is the preview
    the signer reviewed; anything that changed since refuses the signature. ``choices``
    ({test code: scope}) says which statement applies where the specifications in force state
    a test differently; the replacement is refused while one is undecided. In one
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
        preview = replacement_preview(locked, at=locked._signing_timestamp, choices=choices)
        if preview.blocker:
            raise ValidationError(preview.blocker)
        if denial := replacement_denial(actor, locked):
            raise PermissionDenied(denial)
        if preview.reasons:
            raise ValidationError(preview.reasons)
        if preview.conflicts:
            raise ValidationError(CHOICE_REQUIRED)
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
        if preview.versions:
            # Every specification and additional rule set version that changed.
            evidence["versions"] = preview.versions
        if payload.get("decisions"):
            # Each choice between differing statements with who made it: this signer, or
            # whoever decided it before when the statement that applies is unchanged.
            records = {record["code"]: record for record in decision_records(previous)}
            before = {line["code"]: line for line in previous.payload["tests"]}
            after = {line["code"]: line for line in payload["tests"]}
            standing = {
                code: record
                for code, record in records.items()
                if code in after and same_requirement(before[code], after[code])
            }
            evidence["decisions"] = _stamped(
                payload["decisions"],
                actor=actor,
                at=locked._signing_timestamp,
                reason=reason,
                how="replacement",
                earlier=standing,
            )
            evidence["signed_at"] = locked._signing_timestamp.isoformat()
        assignment = LotAssignment(
            lot=locked,
            material=previous.material,
            stage=previous.stage,
            scope=previous.scope,
            scopes=previous.scope_list,
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
                **({"versions": preview.versions} if preview.versions else {}),
                **(
                    {
                        "decisions": [
                            {"code": item["code"], "scope": item["scope"]}
                            for item in payload["decisions"]
                        ]
                    }
                    if payload.get("decisions")
                    else {}
                ),
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
