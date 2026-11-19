"""The instruments, reagents, reference standards and prepared solutions that a method version
lists as suitable, matched against the laboratory register.

A line comes from the method version's approved content (catalog ``MethodResource.content``):
``{"kind", "name", "required", "method_qualified"}``. An instrument line names an equipment
category; any other kind names a reagent lot's kind and name. Names match without regard to case
or repeated spaces. A reagent lot answers a line when the lot itself, or a lot it was prepared
from, has the line's kind and name, so a working solution answers the line of its standard.

Each kind is constrained on its own: a lot is checked only when the version lists a line of its
kind or of the kind of a lot it was prepared from. A version that lists its reference standard
therefore also checks the solutions prepared from standards, and leaves solvents and buffers
open until it lists a reagent.

This module never imports the catalog: the lines reach it as plain data from the integration
(``config.integrations.LaboratoryBench``), and the catalog asks it for the register's names.
"""

from django.db.models import Min
from django.utils import timezone

from .eligibility import (
    Finding,
    equipment_queryset,
    equipment_status,
    qualification_valid,
    reagent_lineage,
    reagent_status,
)
from .models import Equipment, Qualification, ReagentLot

INSTRUMENT = "instrument"
NOUNS = {
    INSTRUMENT: "instrument",
    ReagentLot.Kind.REAGENT: "reagent",
    ReagentLot.Kind.STANDARD: "reference standard",
    ReagentLot.Kind.PREPARED: "prepared solution",
}
SHOWN = 8  # register entries shown for one line on the method page


def name_key(name):
    """A register name as it is compared: surrounding and repeated spaces ignored, any case."""
    return " ".join((name or "").split()).casefold()


def tidy(name):
    return " ".join((name or "").split())


def register_names():
    """``{kind: [name, ...]}``: every equipment category and every reagent lot name by kind, as
    first recorded (spaces tidied), sorted. Rejected and expired lots count: a name is a name."""
    found = {kind: {} for kind in NOUNS}
    categories = Equipment.objects.values("category").annotate(first=Min("pk")).order_by("first")
    for row in categories:
        found[INSTRUMENT].setdefault(name_key(row["category"]), tidy(row["category"]))
    names = ReagentLot.objects.values("kind", "name").annotate(first=Min("pk")).order_by("first")
    for row in names:
        found[row["kind"]].setdefault(name_key(row["name"]), tidy(row["name"]))
    return {kind: sorted(names.values(), key=str.casefold) for kind, names in found.items()}


def _instrument_lines(lines):
    return {name_key(line["name"]): line for line in lines if line["kind"] == INSTRUMENT}


def _lot_matches(lines, chain):
    """``[(line, lot)]``: each non-instrument line answered by a lot of ``chain`` (the lot, then
    the lots it was prepared from, nearest first), with the nearest lot that answers it."""
    matches = []
    for line in lines:
        if line["kind"] == INSTRUMENT:
            continue
        key = name_key(line["name"])
        lot = next((n for n in chain if n.kind == line["kind"] and name_key(n.name) == key), None)
        if lot is not None:
            matches.append((line, lot))
    return matches


def _same(text, activity):
    return name_key(text) == name_key(activity)


def method_qualification(equipment, activity, at):
    """The approved, current qualification of ``equipment`` for the method ``activity``, or
    None (reads the prefetched or locked ``qualifications``)."""
    valid = [
        q
        for q in equipment.qualifications.all()
        if _same(q.activity, activity) and qualification_valid(q, at)
    ]
    return max(valid, key=lambda q: q.pk, default=None)


def _required_reason(line, activity):
    noun = NOUNS.get(line["kind"], line["kind"])
    if line["kind"] == INSTRUMENT:
        what = f"an instrument of the category “{line['name']}”"
    elif line["kind"] == ReagentLot.Kind.PREPARED:
        what = f"a prepared solution “{line['name']}”"
    else:
        what = f"a {noun} “{line['name']}” or a solution prepared from it"
    return f"Select {what}; method {activity} requires one."


def apply(findings, lines, *, activity, equipment, reagents, at=None):
    """The findings of ``eligibility.check_use`` with the method version's suitable resources
    applied. Without lines they are returned unchanged.

    Where the version lists instruments, an instrument whose category it does not list is
    refused, and so is one without the qualification for the method its line asks for. A lot
    whose kind, or the kind of a lot it was prepared from, the version lists is refused unless
    it answers one of the version's lines; lots of other kinds stay open. A required line that
    no selected resource answers is refused under the method. Each resource's evidence names
    the line it answered (``suitable_as``) and any qualification for the method relied on
    (``method_qualification``).
    """
    lines = [dict(line) for line in lines or ()]
    if not lines:
        return findings
    at = at or timezone.now()
    activity = (activity or "").strip()
    count = len(equipment)
    if len(findings) != 1 + count + len(reagents):
        raise ValueError("Findings do not match the selected resources.")
    instruments = _instrument_lines(lines)
    listed = [line for line in lines if line["kind"] != INSTRUMENT]
    listed_kinds = {line["kind"] for line in listed}
    answered = set()
    result = [findings[0]]
    for item, finding in zip(equipment, findings[1 : 1 + count], strict=True):
        reasons, evidence = list(finding.reasons), dict(finding.evidence)
        if instruments:
            line = instruments.get(name_key(item.category))
            if line is None:
                kinds = ", ".join(f"“{line['name']}”" for line in instruments.values())
                reasons.append(
                    f"Its category “{tidy(item.category)}” is not one that method {activity} "
                    f"lists as suitable ({kinds})."
                )
            else:
                answered.add(id(line))
                evidence["suitable_as"] = line["name"]
                if line.get("method_qualified"):
                    qualification = method_qualification(item, activity, at)
                    if qualification is None:
                        reasons.append(
                            "No approved, current qualification of this instrument for method "
                            f"{activity}."
                        )
                    else:
                        evidence["method_qualification"] = qualification.pk
        result.append(Finding(finding.subject, not reasons, tuple(reasons), evidence))
    for item, finding in zip(reagents, findings[1 + count :], strict=True):
        reasons, evidence = list(finding.reasons), dict(finding.evidence)
        if listed:
            chain = [item, *reagent_lineage(item)]
            matches = _lot_matches(listed, chain)
            if matches:
                answered.update(id(line) for line, _ in matches)
                evidence["suitable_as"] = [
                    {"kind": line["kind"], "name": line["name"], "lot": lot.identifier}
                    for line, lot in matches
                ]
            elif listed_kinds & {lot.kind for lot in chain}:
                reasons.append(
                    f"Method {activity} does not list the {NOUNS[item.kind]} “{tidy(item.name)}” "
                    "as suitable, nor a lot it was prepared from."
                )
        result.append(Finding(finding.subject, not reasons, tuple(reasons), evidence))
    missing = [
        _required_reason(line, activity)
        for line in lines
        if line.get("required") and id(line) not in answered
    ]
    if missing:
        result.append(Finding(f"Method {activity}", False, tuple(missing), {}))
    return result


# --- Choices offered at the bench, and the register beside each line ------------------------


def _parents():
    """``{lot id: (kind, name, parent id)}`` of every reagent lot, for lineage without queries."""
    return {
        pk: (kind, name, parent)
        for pk, kind, name, parent in ReagentLot.objects.values_list(
            "pk", "kind", "name", "parent_id"
        )
    }


def _chain_keys(pk, parents):
    """``[(kind, name key)]`` of a lot and the lots it was prepared from, nearest first."""
    keys, seen = [], set()
    while pk is not None and pk not in seen and pk in parents:
        seen.add(pk)
        kind, name, parent = parents[pk]
        keys.append((kind, name_key(name)))
        pk = parent
    return keys


def _method_qualified_ids(activity, at):
    """Ids of equipment with an approved, current qualification for the method ``activity``,
    matched as ``apply`` matches it (``name_key``)."""
    candidates = Qualification.objects.filter(
        equipment__isnull=False,
        state__in=[Qualification.State.APPROVED, Qualification.State.REVOKED],
    )
    return {
        q.equipment_id
        for q in candidates
        if _same(q.activity, activity) and qualification_valid(q, at)
    }


def narrow(choices, lines, *, activity, at=None):
    """The bench's ``{"equipment": [(pk, label)], "reagents": [(pk, label)]}`` narrowed to what
    the method version lists: instruments of a listed category (marked when the qualification
    for the method its line asks for is missing), and of the lots whose kind (or the kind of a
    lot they were prepared from) the version lists, those that answer one of its lines; other
    lots stay. ``required`` says which of the two the version requires through a line recorded
    with every result, so the entry form can ask for one."""
    lines = [dict(line) for line in lines or ()]
    if not lines:
        return choices
    at = at or timezone.now()
    activity = (activity or "").strip()
    narrowed = dict(choices)
    instruments = _instrument_lines(lines)
    if instruments:
        categories = dict(
            Equipment.objects.filter(
                pk__in=[pk for pk, _ in choices.get("equipment", [])]
            ).values_list("pk", "category")
        )
        qualified = (
            _method_qualified_ids(activity, at)
            if any(line.get("method_qualified") for line in instruments.values())
            else set()
        )
        offered = []
        for pk, label in choices.get("equipment", []):
            line = instruments.get(name_key(categories.get(pk)))
            if line is None:
                continue
            if line.get("method_qualified") and pk not in qualified:
                label = f"{label} · Not qualified for {activity}"
            offered.append((pk, label))
        narrowed["equipment"] = offered
    listed = {
        (line["kind"], name_key(line["name"])) for line in lines if line["kind"] != INSTRUMENT
    }
    if listed:
        kinds = {kind for kind, _ in listed}
        parents = _parents()
        offered = []
        for pk, label in choices.get("reagents", []):
            chain = _chain_keys(pk, parents)
            if listed.intersection(chain) or not kinds.intersection(k for k, _ in chain):
                offered.append((pk, label))
        narrowed["reagents"] = offered
    narrowed["required"] = {
        "equipment": any(line.get("required") for line in instruments.values()),
        "reagents": any(line.get("required") for line in lines if line["kind"] != INSTRUMENT),
    }
    return narrowed


def register(lines, *, activity, today=None):
    """What the register holds for each line, for the method page: ``[{"line", "entries",
    "more"}]``. Instruments of the category with their status (and, where the line asks for it,
    whether each is qualified for the method); lots not rejected or expired that answer the line,
    with their status. At most ``SHOWN`` items per line, the rest counted in ``more``."""
    today = today or timezone.localdate()
    now = timezone.now()
    activity = (activity or "").strip()
    lines = [dict(line) for line in lines or ()]
    if not lines:
        return []
    equipment = list(equipment_queryset(today).order_by("asset_id", "pk"))
    qualified = (
        _method_qualified_ids(activity, now)
        if any(line.get("method_qualified") for line in lines)
        else set()
    )
    lots = list(
        ReagentLot.objects.exclude(state=ReagentLot.State.REJECTED)
        .filter(expiry_date__gte=today)
        .order_by("identifier", "pk")
    )
    parents = _parents() if lots else {}
    rows = []
    for line in lines:
        key = name_key(line["name"])
        items = []
        if line["kind"] == INSTRUMENT:
            for item in equipment:
                if name_key(item.category) != key:
                    continue
                label, tone, _ = equipment_status(item, today)
                if line.get("method_qualified") and item.pk not in qualified:
                    label = f"{label} · Not qualified for the method"
                    tone = "danger" if tone == "danger" else "warning"
                items.append(
                    {
                        "id": item.asset_id,
                        "name": item.description,
                        "label": label,
                        "tone": tone,
                        "pk": item.pk,
                        "instrument": True,
                    }
                )
        else:
            for lot in lots:
                if (line["kind"], key) not in _chain_keys(lot.pk, parents):
                    continue
                label, tone = reagent_status(lot, today)
                items.append(
                    {
                        "id": lot.identifier,
                        "name": lot.name,
                        "label": label,
                        "tone": tone,
                        "pk": lot.pk,
                        "instrument": False,
                    }
                )
        rows.append({"line": line, "entries": items[:SHOWN], "more": max(len(items) - SHOWN, 0)})
    return rows
