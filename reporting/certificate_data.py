"""The certificate's data in a machine-readable form (``oq.certificate-data/1``).

Built once, at issue, from the frozen snapshot the version is signed over, and stored as the
exact bytes that are embedded in the issued PDF and offered for download beside it. It states
what the printed certificate states and nothing more: a certificate for one scope of the lot
carries that scope's specification, results and signatures only, as
``reporting/_certificate.html`` prints them (``conformity.scope_view``). Values are the frozen
strings (exact decimals); moments are ISO 8601 in UTC to the second, as printed; internal record
numbers are left out except inside identifiers the certificate prints. Every field is read by
name, so the bytes do not depend on the key order of the stored snapshot. The format is
described in docs/certificate-data.md: removing or renaming a key or changing what a value
means is a new schema version; an added key is not, and readers ignore keys they do not know.
"""

import json
from datetime import UTC, datetime
from itertools import groupby

from . import conformity

SCHEMA = "oq.certificate-data/1"
FILENAME = "certificate-data.json"
MEDIA_TYPE = "application/json"
DESCRIPTION = "Certificate data (oq.certificate-data/1): the content of this certificate"
STATEMENT = (
    "This certificate reports the laboratory QC disposition and test results only. It is not "
    "the manufacturer's batch release or qualified-person certification."
)
SYNTHETIC_NOTICE = (
    "Synthetic demonstration data. This document has no regulatory or commercial standing."
)


def _moment(value):
    """A frozen moment as printed: ISO 8601 in UTC to the second (``2026-11-18T10:03:05Z``);
    the frozen records keep some with microseconds and an offset."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except TypeError, ValueError:
        return value
    if moment.tzinfo is None:
        return value
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value):
    """Development snapshots may give a section as any JSON value: text, independent of the
    key order of the stored copy."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _review(review):
    """A signature on a laboratory result: native (``signer``) or development (``signer_name``)."""
    if not review:
        return None
    return {
        "signer": review.get("signer") or review.get("signer_name"),
        "signed_at": _moment(review.get("signed_at")),
        "revision": review.get("revision"),
    }


def _statement(statement, *, scoped=False):
    """A result judged against one specification's statement of its test. On a certificate for
    one scope (``scoped``) whether the statement was the one applied to the lot is left out: the
    certificate does not print it, and it would say that another specification governed."""
    item = {
        "specification": statement.get("specification"),
        "scope": statement.get("scope"),
        "applied": statement.get("applied"),
        "requirement": statement.get("requirement") or None,
        "result": statement.get("result") or None,
        "outcome": statement.get("outcome"),
        "reason": statement.get("reason") or None,
    }
    if scoped:
        del item["applied"]
    return item


def _pick(item, *keys):
    """The printed fields of a frozen sub-record (its internal numbers stay out)."""
    if not item:
        return None
    return {key: item.get(key) for key in keys}


def _laboratory_result(result, statement=None):
    """A laboratory's result. On a certificate for one scope (``statement`` given) the result
    and the requirement are those of the scope's specification, in ``conformity``: the
    reportable value and limits the lot was released against may be another specification's,
    which that certificate does not name."""
    item = {
        "test": result.get("test_code"),
        "name": result.get("name") or result.get("test_code"),
        "sample": result.get("sample"),
        "method": _pick(result.get("method"), "code", "revision"),
        "contract_laboratory": _pick(
            result.get("contract_laboratory"), "name", "location", "report_number", "report_date"
        ),
        "replicates": [rep.get("value") for rep in result.get("replicates") or []],
        "reportable": None if statement is not None else result.get("reportable"),
        "unit": result.get("unit") or None,
        "limits": None
        if statement is not None
        else {
            "acceptance": result.get("acceptance") or None,
            "lower": result.get("lower_limit"),
            "lower_inclusive": result.get("lower_inclusive"),
            "upper": result.get("upper_limit"),
            "upper_inclusive": result.get("upper_inclusive"),
        },
        "review": _review(result.get("review")),
    }
    if statement is not None:
        item["conformity"] = _statement(statement, scoped=True)
    return item


def _supplier_result(result, statement=None):
    stated = result.get("stated") or {}
    signature = result.get("signature")
    item = {
        "test": result.get("test_code"),
        "name": result.get("name") or result.get("test_code"),
        "stated": {
            "result": stated.get("result"),
            "unit": result.get("unit") or None,
            "wording": stated.get("wording") or None,
            "method": stated.get("method"),
            "limits": stated.get("limits"),
        },
        # What the certificate prints in its Specification column: on a certificate for one
        # scope the scope's statement, never the criterion of another specification.
        "specification": (
            (statement.get("requirement") or None)
            if statement is not None
            else result.get("criterion")
        ),
        "supplier_certificate": _pick(
            result.get("certificate"), "number", "issued_on", "issued_by"
        ),
        "supplier": _pick(result.get("supplier"), "name", "location"),
        "qualification": _pick(result.get("qualification"), "label", "evidence_ref"),
        "acceptance": result.get("label"),
        "accepted": (
            {
                "signer": signature.get("signer"),
                "signed_at": _moment(signature.get("signed_at")),
                "revision": signature.get("revision"),
            }
            if signature
            else None
        ),
    }
    if statement is not None:
        item["conformity"] = _statement(statement, scoped=True)
    return item


def _sample_results(snapshot):
    """Results of the development-only manual journey, sample by sample."""
    return [
        {
            "sample": sample.get("reference"),
            "collected_at": _moment(sample.get("collected_at")),
            "results": [
                {
                    "test": r.get("test_code"),
                    "value": r.get("value"),
                    "unit": r.get("unit") or None,
                    "lower_limit": r.get("lower_limit"),
                    "upper_limit": r.get("upper_limit"),
                    "conforms": r.get("conforms"),
                    "analyst": r.get("analyst"),
                    "review": _review(r.get("review")),
                }
                for r in sample.get("results") or []
            ],
        }
        for sample in snapshot.get("samples") or []
    ]


def _methods(methods):
    found = []
    for method in methods:
        if not isinstance(method, dict):
            found.append({"text": _text(method)})
            continue
        found.append(
            {
                "code": method.get("code"),
                "version": method.get("version"),
                "document": method.get("document_ref") or None,
                "suitability": (
                    {
                        "kind": method.get("suitability_kind"),
                        "reference": method.get("suitability_ref"),
                    }
                    if method.get("suitability_ref")
                    else None
                ),
                "batch_qc_required": bool(method.get("requires_batch")),
                "batch_qc_checks": (
                    len(method.get("qc_checks") or []) if method.get("requires_batch") else None
                ),
                "sha256": method.get("approved_hash") or None,
            }
        )
    return found


def _specifications(snapshot, native, view):
    if view:
        specs = view["specifications"]
    elif native.get("specifications"):
        specs = native["specifications"]
    else:
        spec = snapshot.get("specification")
        if isinstance(spec, dict) and spec.get("code"):
            specs = [spec]
        elif spec:
            # A development snapshot gives its specification as sections of text.
            if isinstance(spec, dict):
                sections = {str(key): _text(value) for key, value in sorted(spec.items())}
            else:
                sections = {"": _text(spec)}
            return [{"sections": sections}]
        else:
            return []
    return [
        {
            "code": spec.get("code"),
            "version": spec.get("version"),
            "scope": spec.get("scope"),
            "sha256": spec.get("approved_hash") or None,
        }
        for spec in specs
    ]


def _investigation(item):
    conclusion = item.get("conclusion") or {}
    return {
        "investigation": item.get("investigation"),
        "trigger": item.get("trigger"),
        "outcome": item.get("outcome") or None,
        "concluded_by": conclusion.get("signer"),
        "concluded_at": _moment(conclusion.get("signed_at")),
    }


def _decision(item):
    decided = item.get("decided") or {}
    carried = decided.get("carried") or {}
    return {
        "test": item.get("code"),
        "stated_differently_in": list(item.get("differs") or []),
        "applies": _pick(item.get("applies"), "specification", "scopes", "requirement"),
        "not_applied": [
            _pick(alt, "specification", "scopes", "requirement")
            for alt in item.get("not_applied") or []
        ],
        "decided": (
            {
                "by": decided.get("by"),
                "at": _moment(decided.get("at")),
                "with": decided.get("with"),
                "reason": decided.get("reason"),
                "carried_by": carried.get("by"),
                "carried_at": _moment(carried.get("at")),
            }
            if decided
            else None
        ),
    }


def _signatures(snapshot, analytical, view):
    """The signature manifestations the certificate prints, in its order."""
    rows = []
    for sample in snapshot.get("samples") or []:
        for r in sample.get("results") or []:
            if r.get("review"):
                rows.append(
                    {
                        "meaning": (
                            f"Result {sample.get('reference')} {r.get('test_code')} reviewed"
                        ),
                        **_signed(_review(r["review"])),
                        "bound_to": f"Result revision {r['review'].get('revision')}",
                    }
                )
    for r in analytical.get("results") or []:
        if r.get("review") and (not view or r.get("test") in view["reviewed_tests"]):
            rows.append(
                {
                    "meaning": f"Test {r.get('sample')} {r.get('test_code')} reviewed",
                    **_signed(_review(r["review"])),
                    "bound_to": f"Test record revision {r['review'].get('revision')}",
                }
            )
    for s in analytical.get("supplier_results") or []:
        if s.get("signature") and (not view or s.get("acceptance") in view["accepted"]):
            rows.append(
                {
                    "meaning": f"Supplier result {s.get('test_code')} accepted in place of a test",
                    "signer": s["signature"].get("signer"),
                    "signed_at": _moment(s["signature"].get("signed_at")),
                    "bound_to": f"Acceptance {s.get('label')} revision "
                    f"{s['signature'].get('revision')}",
                }
            )
    disposition = snapshot.get("disposition")
    if disposition:
        rows.append(
            {
                "meaning": "QC disposition approved",
                "signer": disposition.get("signer_name"),
                "signed_at": _moment(disposition.get("signed_at")),
                "bound_to": f"Lot revision {disposition.get('revision')}",
            }
        )
    report = snapshot.get("report") or {}
    rows.append(
        {
            "meaning": "Certificate amended"
            if report.get("kind") == "amendment"
            else "Certificate issued",
            "signer": report.get("issued_by"),
            "signed_at": _moment(report.get("issued_at")),
            "bound_to": f"Certificate version {report.get('version')}",
        }
    )
    return rows


def _signed(review):
    return {"signer": review["signer"], "signed_at": review["signed_at"]}


def build(snapshot, *, synthetic=False):
    """The certificate data of one issued version, from its frozen snapshot only."""
    report = snapshot.get("report") or {}
    view = conformity.scope_view(snapshot, report.get("scope") or "")
    native = snapshot.get("native") or {}
    analytical = native.get("analytical") or {}
    lot = snapshot.get("lot") or {}
    dates = snapshot.get("dates") or {}
    rules = snapshot.get("rules") or {}
    disposition = snapshot.get("disposition")
    amendment = report.get("kind") == "amendment"
    data = {
        "schema": SCHEMA,
        "certificate": {
            "number": report.get("number"),
            "version": report.get("version"),
            "kind": report.get("kind"),
            "amends_version": report.get("amends_version"),
            "amendment_reason": report.get("reason") if amendment else None,
            "recipient": report.get("recipient") or None,
            "scope": view["scope"] if view else None,
            "issued_by": report.get("issued_by"),
            "issued_at": _moment(report.get("issued_at")),
            "remarks": report.get("remarks") or None,
            "statement": STATEMENT,
            "synthetic_data": bool(synthetic),
            "notice": SYNTHETIC_NOTICE if synthetic else None,
        },
        "lot": {
            "number": lot.get("number"),
            "material": lot.get("material"),
            "state": lot.get("state"),
            "received_at": _moment(lot.get("received_at")),
            "received_by": lot.get("received_by"),
            "expiry_on": dates.get("expiry_on"),
            "retest_on": dates.get("retest_on"),
            "reassessment": (
                {
                    "label": dates["reassessment"].get("label"),
                    "concluded_on": dates["reassessment"].get("concluded_on"),
                }
                if dates.get("reassessment")
                else None
            ),
        },
        "disposition": (
            {
                "decision": "approved",
                "signer": disposition.get("signer_name"),
                "signed_at": _moment(disposition.get("signed_at")),
                "lot_revision": disposition.get("revision"),
            }
            if disposition
            else None
        ),
        "rules": {
            "code": rules.get("code"),
            "version": rules.get("version"),
            "revision": rules.get("revision"),
            "segment": rules.get("segment"),
            "effective_from": _moment(rules.get("effective_from")),
            "effective_until": _moment(rules.get("effective_until")),
            "required_tests": None if view else list(rules.get("required_tests") or []),
        },
        "additional_rules": (
            []
            if view
            else [
                {
                    "code": extra.get("code"),
                    "version": extra.get("version"),
                    "segment": extra.get("segment"),
                    "required_tests": list(extra.get("required_tests") or []),
                }
                for extra in native.get("additional_rules") or []
            ]
        ),
        "specifications": _specifications(snapshot, native, view),
        "methods": _methods(view["methods"] if view else _distinct(snapshot.get("methods") or [])),
    }
    if view:
        data["requirement_decisions"] = []
        data["results"] = [_laboratory_result(r["result"], r["statement"]) for r in view["results"]]
        data["supplier_results"] = [
            _supplier_result(r["result"], r["statement"]) for r in view["supplier_results"]
        ]
        data["not_tested"] = [
            {"test": row["test_code"], "conformity": _statement(row["statement"], scoped=True)}
            for row in view["untested"]
        ]
        data["conformity"] = []
        data["decision_rule"] = conformity.DECISION_RULE
        investigations = view["investigations"]
    else:
        data["requirement_decisions"] = [_decision(item) for item in native.get("decisions") or []]
        data["results"] = [_laboratory_result(r) for r in analytical.get("results") or []]
        data["supplier_results"] = [
            _supplier_result(s) for s in analytical.get("supplier_results") or []
        ]
        data["not_tested"] = []
        data["conformity"] = [
            {
                "test": row.get("test_code"),
                "sample": row.get("sample") or None,
                "origin": row.get("origin"),
                "statements": [_statement(st) for st in row.get("statements") or []],
            }
            for row in native.get("conformity") or []
        ]
        data["decision_rule"] = conformity.DECISION_RULE if native.get("conformity") else None
        investigations = analytical.get("investigations") or []
    if not native:
        data["sample_results"] = _sample_results(snapshot)
    asserted = "holds" in (snapshot.get("sections_supplied") or [])
    data["holds"] = {
        "asserted": asserted,
        "items": (
            [
                # As printed: its description, or its identifier when it has none.
                {"hold": hold.get("description") or hold.get("id"), "status": hold.get("status")}
                for hold in snapshot.get("holds") or []
            ]
            if asserted
            else []
        ),
    }
    data["investigations"] = [_investigation(item) for item in investigations]
    data["corrections"] = [item.get("description") for item in snapshot.get("corrections") or []]
    data["signatures"] = _signatures(snapshot, analytical, view)
    data["identifiers"] = {
        "evidence_sha256": snapshot.get("evidence_hash"),
        "assignment_sha256": native.get("assignment_hash") or None,
        "requirement_sources": [] if view else _requirement_sources(analytical),
    }
    return data


def _distinct(methods):
    from .templatetags.reporting_tags import distinct_methods

    return distinct_methods(methods)


def _requirement_sources(analytical):
    """The requirement sources the certificate prints: those of the laboratory's results, or of
    the supplier's when the laboratory tested nothing, in order, a source repeated by the next
    result printed once (``{% ifchanged %}``)."""
    rows = analytical.get("results") or analytical.get("supplier_results") or []
    return [source for source, _ in groupby(row.get("requirement_source") for row in rows)]


def encode(data):
    """The stored bytes: UTF-8 JSON, indented for reading, keys in the documented order."""
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
