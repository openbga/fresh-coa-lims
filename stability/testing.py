"""Testing a stability pull in the system: what the testing module is told about a pull.

For a pull's tests the pull stands where the lot stands in release testing. The tests belong
to the pull and name no lot, so the record of the study's lot, often released long before,
is not touched: none of its revision, samples, tests, investigations or history changes.

The acceptance criteria are those of the protocol. The protocol names a specification, and
the version of it in force when a pull's tests are assigned is frozen on each test, as
release testing freezes a lot's requirements. A protocol that names no specification is not
tested here: its pulls link a sample of a lot still in quarantine, or external evidence.

`config.integrations.StabilityPulls` publishes `requirements`, `refusal` and `lock` to the
testing module (settings.ANALYTICAL_STABILITY_PULLS).
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from analytical.contracts import RequirementHold, parse_requirement
from catalog.services import Applicable, test_requirement

from .models import Pull, Study

NO_SPECIFICATION = (
    "The protocol names no specification, so its acceptance criteria are not in the system. "
    "Link a sample or external evidence instead; a new protocol version can name one."
)


def refusal(pull, study=None):
    """Why the tests of this pull take no work now, or None. ``study`` is the pull's study
    when the caller holds it locked."""
    study = study or pull.study
    if study.state != Study.State.ACTIVE:
        return f"Study {study.identifier} is closed; its pulls take no more testing."
    if pull.state == Pull.State.SCHEDULED:
        return "Record the pull before testing it."
    if pull.state != Pull.State.PULLED:
        return f"This pull is {pull.get_state_display().lower()}; its tests take no more work."
    return None


def lock(pull_ids):
    """Lock the pulls, then their studies, each in key order, and refuse a pull that takes no
    more testing. The caller advances each returned pull's revision with the evidence change,
    so an acceptance opened earlier goes stale."""
    pulls = list(Pull.objects.select_for_update().filter(pk__in=set(pull_ids)).order_by("pk"))
    studies = {
        study.pk: study
        for study in Study.objects.select_for_update()
        .filter(pk__in={pull.study_id for pull in pulls})
        .order_by("pk")
    }
    for pull in pulls:
        if reason := refusal(pull, studies[pull.study_id]):
            raise ValidationError(reason)
    return pulls


def linked_elsewhere(pull):
    """Why the pull cannot be tested here although it was pulled: its evidence is a sample
    tested with its lot or an external system's record. A pull keeps one kind of evidence."""
    if pull.sample_id:
        return (
            f"This pull's evidence is sample {pull.sample.reference}, tested with its lot. "
            "A pull is tested in the system or linked to other evidence, never both."
        )
    if pull.external_sample_ref or pull.evidence_ref:
        return (
            "This pull's evidence is kept in an external system. A pull is tested in the "
            "system or linked to other evidence, never both."
        )
    return None


def assignment_refusal(pull, study=None):
    """Why tests cannot be assigned to this pull, or None."""
    if reason := refusal(pull, study) or linked_elsewhere(pull):
        return reason
    if (study or pull.study).protocol.specification_id is None:
        return NO_SPECIFICATION
    return None


def _read(specification, at):
    """The specification's version in force with its methods, read once, or a hold."""
    read = Applicable(
        material=specification.material,
        stage=specification.stage,
        scopes=[specification.scope],
        at=at or timezone.now(),
    )
    if not read.specifications:
        raise RequirementHold(
            [f"Specification {specification.code} has no approved version effective now."]
        )
    return read, read.specifications[0][2]


def _line(read, revision, specification, code):
    """(the line the version in force states for the test with its method in force, None) or
    (None, why there is none)."""
    line = read.line(code, specification.scope)
    if line is not None:
        return line, None
    stated = {item["code"]: item for item in revision.approved_content["tests"]}
    if code in stated:
        return None, (
            f"Method {stated[code]['method']} of {code} has no approved version effective now."
        )
    return None, f"Specification {specification.code} v{revision.version} does not state {code}."


def requirements(pull, at=None):
    """{test_code: oq.test-requirement payload} for every test of the pull's time point, from
    the version in force of the protocol's specification, or ``RequirementHold``.

    All or nothing: the tests of a pull are assigned together under one specification
    version. A test of a line the specification marks as not required is still a test of the
    protocol; the time point decides what is tested. ``source`` names the specification
    version and the protocol version.
    """
    if reason := linked_elsewhere(pull):
        raise RequirementHold([reason])
    protocol = pull.study.protocol
    specification = protocol.specification
    if specification is None:
        raise RequirementHold([NO_SPECIFICATION])
    read, revision = _read(specification, at)
    source = (
        f"catalog:{specification.code}@v{revision.version}#rev{revision.pk}"
        f"/stability:{protocol.code}@v{protocol.version}"
    )
    payloads, reasons = {}, []
    for code in pull.timepoint.test_codes:
        line, reason = _line(read, revision, specification, code)
        if line is None:
            reasons.append(f"{reason} The protocol tests it at {pull.timepoint}.")
        else:
            payloads[code] = test_requirement(line, source)
    if reasons:
        raise RequirementHold(reasons)
    return payloads


def protocol_problems(protocol, at=None):
    """Why a protocol that names a specification cannot be approved now, one reason for each
    test the specification's version in force cannot answer; empty without a specification."""
    specification = protocol.specification
    if specification is None:
        return []
    try:
        read, revision = _read(specification, at)
    except RequirementHold as hold:
        return hold.reasons
    problems = {}
    for timepoint in protocol.timepoints.select_related("condition").order_by("pk"):
        for code in timepoint.test_codes:
            if code in problems:
                continue
            line, reason = _line(read, revision, specification, code)
            if line is None:
                problems[code] = f"{reason} The protocol tests it at {timepoint}."
    return list(problems.values())


def material_problem(protocol, lot):
    """Why a study of this lot cannot start on a protocol that names a specification, or None:
    the lot must be of the specification's material, as its assigned requirements state."""
    specification = protocol.specification
    if specification is None:
        return None
    assignment = lot.qc_assignments.order_by("-assigned_at", "-id").first()
    material = specification.material
    if assignment is None:
        return (
            f"Lot {lot.number} has no requirements assigned, so its material is not "
            f"established. {protocol.identifier} tests against specification "
            f"{specification.code} of {material.code}; assign the lot's requirements first."
        )
    if assignment.material_id != material.pk:
        return (
            f"Lot {lot.number} is {assignment.material.code}; {protocol.identifier} tests "
            f"against specification {specification.code} of {material.code}."
        )
    return None


def criteria_now(protocol, at=None):
    """What the version in force of the protocol's specification states now for each test
    the protocol names: (specification version or None, [{"code", "name", "acceptance",
    "method", "problem"}]). A page aid; testing freezes the criteria when tests are assigned.
    """
    specification = protocol.specification
    codes = []
    for timepoint in protocol.timepoints.order_by("pk"):
        codes += [code for code in timepoint.test_codes if code not in codes]
    if specification is None:
        return None, []
    try:
        read, revision = _read(specification, at)
    except RequirementHold as hold:
        return None, [
            {"code": code, "name": "", "acceptance": "", "method": "", "problem": reason}
            for code in codes
            for reason in hold.reasons
        ]
    rows = []
    for code in codes:
        line, reason = _line(read, revision, specification, code)
        row = {"code": code, "name": "", "acceptance": "", "method": "", "problem": reason or ""}
        if line is not None:
            try:
                spec = parse_requirement(test_requirement(line, "preview"))
            except ValidationError as exc:
                row["problem"] = " ".join(exc.messages)
            else:
                row.update(
                    name=spec.name,
                    acceptance=spec.acceptance,
                    method=f"{spec.method.code} revision {spec.method.revision}",
                )
        rows.append(row)
    return revision, rows
