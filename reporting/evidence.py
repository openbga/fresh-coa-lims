"""Frozen evidence for a certificate: collection, canonical hashing and release gates.

`collect_evidence` reads the foundation's signed QC disposition, reviewed results and review
signatures. Sibling packages publish further frozen sections (approved specification and method
snapshots, hold snapshots, corrections) through `register_collector`; until they are registered
those sections are absent and the certificate says so. Gates run on the collected payload, so a
fixture payload and a live one are judged identically.
"""

import hashlib
import json
from datetime import UTC

from django.apps import apps

from core.models import ElectronicSignature
from quality.models import Lot

SCHEMA = "oq.coa/1"
# Hold states that do not block. Any other state, including an unknown one, blocks.
CLEARED_HOLD_STATES = frozenset({"closed", "resolved", "cleared", "released"})
SECTION_KEYS = frozenset({"specification", "methods", "holds", "corrections"})

_collectors = {}


def register_collector(key, collector):
    """Publish a frozen section: `collector(lot)` returns JSON-serialisable data."""
    if key not in SECTION_KEYS:
        raise ValueError(f"Unknown evidence section {key!r}.")
    _collectors[key] = collector


def unregister_collector(key):
    _collectors.pop(key, None)


def iso(moment):
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def plain(value):
    """Exact Decimal text without trailing padding or exponent."""
    return format(value.normalize(), "f")


def canonical_hash(payload):
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode()).hexdigest()


def _person(user):
    return user.get_full_name() or user.get_username()


def _signature(signature):
    if signature is None:
        return None
    return {
        "signer_id": signature.signer_id,
        "signer_name": signature.signer_name,
        "signed_at": iso(signature.signed_at),
        "meaning": signature.meaning,
        "revision": signature.revision,
        "content_hash": signature.content_hash,
    }


def _latest_signatures(object_type, ids, meaning):
    found = {}
    rows = ElectronicSignature.objects.filter(
        object_type=object_type, object_id__in=[str(i) for i in ids], meaning=meaning
    ).order_by("signed_at", "id")
    for row in rows:
        found[row.object_id] = row
    return found


def _native(lot):
    """Frozen native-testing evidence stored with the QC disposition (None for foundation lots).

    The disposition stores the exact assignment hash and analytical evidence it was signed against;
    reading those, rather than recomputing, keeps the certificate faithful to the signed decision.
    """
    stored = lot.disposition_evidence or {}
    analytical = stored.get("analytical")
    if not analytical:
        return None
    spec = {}
    if stored.get("assignment_id"):
        # Append-only frozen payload; resolved by label so reporting has no import dependency.
        record = (
            apps.get_model("sampling", "LotAssignment")
            .objects.filter(
                pk=stored["assignment_id"], payload_hash=stored.get("assignment_hash", "")
            )
            .first()
        )
        if record is not None and record.payload:
            spec = record.payload.get("specification") or {}
    return {
        "assignment_id": stored.get("assignment_id"),
        "assignment_hash": stored.get("assignment_hash"),
        "specification": {
            k: spec[k] for k in ("code", "version", "revision_id", "approved_hash") if k in spec
        }
        or None,
        "analytical": analytical,
    }


def collect_evidence(lot):
    """Snapshot of everything a certificate asserts, for a lot as currently committed."""
    lot = Lot.objects.select_related("rules", "created_by").get(pk=lot.pk)
    samples = list(lot.samples.select_related("created_by").order_by("reference", "id"))
    results = []
    for sample in samples:
        results.extend(sample.results.select_related("analyst").order_by("test_code", "id"))
    review = _latest_signatures("quality.result", [r.pk for r in results], "reviewed")
    disposition = _latest_signatures("quality.lot", [lot.pk], "approved").get(str(lot.pk))
    rules = lot.rules
    native = _native(lot)
    authors = {lot.created_by_id}
    if native:
        authors.update(native["analytical"].get("author_ids", []))
    sample_blocks = []
    for sample in samples:
        authors.add(sample.created_by_id)
        rows = []
        for result in (r for r in results if r.sample_id == sample.pk):
            authors.add(result.analyst_id)
            rows.append(
                {
                    "id": result.pk,
                    "test_code": result.test_code,
                    "value": plain(result.value),
                    "unit": result.unit,
                    "lower_limit": plain(result.lower_limit),
                    "upper_limit": plain(result.upper_limit),
                    "conforms": result.conforms,
                    "state": result.state,
                    "revision": result.revision,
                    "analyst_id": result.analyst_id,
                    "analyst": _person(result.analyst),
                    "recorded_at": iso(result.recorded_at),
                    "review": _signature(review.get(str(result.pk))),
                }
            )
        sample_blocks.append(
            {
                "id": sample.pk,
                "reference": sample.reference,
                "collected_at": iso(sample.collected_at),
                "results": rows,
            }
        )
    evidence = {
        "schema": SCHEMA,
        "lot": {
            "id": lot.pk,
            "number": lot.number,
            "material": lot.material,
            "state": lot.state,
            "revision": lot.revision,
            "received_by": _person(lot.created_by),
            "received_at": iso(lot.created_at),
        },
        "rules": {
            "id": rules.pk,
            "code": rules.code,
            "version": rules.version,
            "revision": rules.revision,
            "segment": rules.segment,
            "status": rules.status,
            "effective_from": iso(rules.effective_from),
            "effective_until": iso(rules.effective_until) if rules.effective_until else None,
            "required_tests": list(rules.policy.get("required_tests", [])),
        },
        "samples": sample_blocks,
        "disposition": _signature(disposition),
        "authors": sorted(authors),
        "native": native,
        "specification": native["specification"] if native else None,
        "methods": None,
        "holds": [],
        "corrections": [],
    }
    for key, collector in _collectors.items():
        evidence[key] = collector(lot)
    # States which frozen sections a sibling package actually supplied (absence is not "none").
    evidence["sections_supplied"] = sorted(_collectors)
    return evidence


def blockers(evidence):
    """Reasons this evidence cannot support an issued certificate (empty when complete)."""
    problems = []
    lot = evidence["lot"]
    disposition = evidence.get("disposition")
    if lot["state"] != "released":
        problems.append("The lot has no signed QC disposition.")
    if disposition is None:
        problems.append("The signed QC disposition record is missing.")
    elif disposition["revision"] != lot["revision"] or disposition["meaning"] != "approved":
        problems.append("The QC disposition signature does not bind the current lot revision.")
    samples = evidence["samples"]
    analysts = set()
    native = evidence.get("native")
    if native:
        analytical = native["analytical"]
        if not analytical.get("complete") or analytical.get("blockers"):
            problems.append("The analytical evidence at disposition was not complete.")
        if not analytical.get("results"):
            problems.append("No reportable native results are recorded for this lot.")
        for result in analytical.get("results", []):
            label = f"{result['sample']} {result['test_code']}"
            if not result.get("review"):
                problems.append(f"{label} has no independent signed review.")
            if not result.get("replicates"):
                problems.append(f"{label} has no recorded replicates.")
        if disposition and disposition["signer_id"] in set(analytical.get("author_ids", [])):
            problems.append("The QC disposition was signed by an author of these results.")
    else:
        if not samples or not any(s["results"] for s in samples):
            problems.append("No sample results are recorded for this lot.")
        required = set(evidence["rules"]["required_tests"])
        for sample in samples:
            present = {r["test_code"] for r in sample["results"]}
            for missing in sorted(required - present):
                problems.append(f"Sample {sample['reference']} is missing required test {missing}.")
            for result in sample["results"]:
                label = f"{sample['reference']} {result['test_code']}"
                analysts.add(result["analyst_id"])
                review = result["review"]
                if result["state"] != "reviewed" or review is None:
                    problems.append(f"{label} has no independent signed review.")
                elif review["revision"] != result["revision"]:
                    problems.append(f"{label} review does not bind the current result revision.")
                elif review["signer_id"] == result["analyst_id"]:
                    problems.append(f"{label} was reviewed by its own analyst.")
                if not result["conforms"]:
                    problems.append(f"{label} is outside its limits.")
    if disposition and disposition["signer_id"] in analysts:
        problems.append("The QC disposition was signed by an analyst of these results.")
    for hold in evidence.get("holds") or []:
        if hold.get("status") not in CLEARED_HOLD_STATES:
            problems.append(f"Open hold: {hold.get('description') or hold.get('id')}.")
    return problems


def independence_conflict(evidence, actor):
    """True when the actor authored any record the certificate asserts."""
    return actor.pk in set(evidence["authors"])


def changed_sections(old, new):
    """Top-level evidence sections that differ between two evidence payloads."""
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
