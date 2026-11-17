"""A lot's complete record as one package to keep or hand over.

The package is a ZIP file holding a printed copy (``record.pdf``), an electronic copy
(``record.json``), the files the record holds (raw data and issued certificates, byte for byte),
a ``manifest.json`` and a ``SHA256SUMS`` list that standard tools can check.

Everything is read in one repeatable-read, read-only transaction, so every part describes the
same instant. Records are found by their links to the lot; the configuration they name (rule
sets, specifications, suppliers, instruments...) is added as it stands at the export. The
stored checksums and hashes are recomputed and each outcome is stated. Nothing is written
except the audit event that records the export, after the package is built.

Reporting reads sibling records by label, so it imports no sibling code.
"""

import hashlib
import json
import re
import tempfile
import tomllib
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, models, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from core.audit import record_event
from core.models import AuditEvent, AuditReview, ElectronicSignature
from core.services import AUDIT_READ_ROLES, require_role
from quality.models import Lot

from .evidence import canonical_hash
from .render import FONT_URL, RenderError, write_pdf

SCHEMA = "oq.lot-record/1"
MANIFEST_SCHEMA = "oq.lot-record-manifest/1"
EXPORT_ACTION = "lot.record_exported"
# The record includes the lot's audit trail, so exporting it needs the roles that read the trail.
EXPORT_ROLES = tuple(sorted(AUDIT_READ_ROLES))
PURPOSE_MAX = 500
# A structured value longer than this is printed as a pointer to the electronic copy, which
# keeps it in full. Shorter ones are printed in full.
PRINT_JSON_LIMIT = 2000
# An audit trail value longer than this is shortened in the printed copy only.
PRINT_CHANGE_LIMIT = 300
SPOOL_MEMORY = 8 * 1024 * 1024


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    label: str
    find: object  # callable(collection) -> Q


def _lot(c):
    return Q(lot=c.lot.pk)


def _in(name, key):
    return lambda c: Q(**{f"{name}__in": c.ids(key)})


def _tests(c):
    return Q(lot=c.lot.pk) | Q(sample__in=c.ids("samples"))


def _all_tests(c):
    return c.ids("tests") + c.ids("stability_tests")


def _of_tests(name):
    return lambda c: Q(**{f"{name}__in": _all_tests(c)})


def _investigations(c):
    return Q(lot=c.lot.pk) | Q(test__in=_all_tests(c))


def _batches(c):
    tests = c.records("tests") + c.records("stability_tests")
    return Q(pk__in={r.batch_id for r in tests if r.batch_id})


def _contexts(c):
    """Records that name one of the collected records as their context (label and id)."""
    query = Q(pk__in=[])
    for label, ids in c.refs_by_label().items():
        query |= Q(context_type=label, context_id__in=sorted(ids))
    return query


# The lot's own records, in the order they are collected and printed. A finder may use the ids of
# the sections before it.
LOT_SECTIONS = (
    Section("lot", "Lot", "quality.Lot", lambda c: Q(pk=c.lot.pk)),
    Section("receipts", "Receipt details", "quality.LotReceipt", _lot),
    Section("dates", "Expiry and retest dates", "quality.LotDates", _lot),
    Section("supplier_certificates", "Supplier certificates", "quality.SupplierCertificate", _lot),
    Section(
        "supplier_certificate_results",
        "Results stated on supplier certificates",
        "quality.SupplierCertificateResult",
        _in("certificate", "supplier_certificates"),
    ),
    Section(
        "supplier_certificate_withdrawals",
        "Supplier certificate withdrawals",
        "quality.SupplierCertificateWithdrawal",
        _in("certificate", "supplier_certificates"),
    ),
    Section(
        "supplier_result_acceptances",
        "Supplier results in place of tests",
        "quality.SupplierResultAcceptance",
        _lot,
    ),
    Section("assignments", "Requirement assignments", "sampling.LotAssignment", _lot),
    Section("samples", "Samples", "quality.Sample", _lot),
    Section("sampling_records", "Sampling records", "sampling.SamplingRecord", _lot),
    Section(
        "deviation_reviews",
        "Sampling deviation reviews",
        "sampling.DeviationReview",
        _in("record", "sampling_records"),
    ),
    Section("results", "Manual results", "quality.Result", _in("sample", "samples")),
    Section("studies", "Stability studies", "stability.Study", _lot),
    Section("pulls", "Stability pulls", "stability.Pull", _in("study", "studies")),
    Section("reserves", "Reserve samples", "stability.ReserveSample", _lot),
    Section("retention", "Retention obligations", "stability.RetentionObligation", _lot),
    Section("holds", "Holds", "stability.Hold", _lot),
    Section("tests", "Tests", "analytical.AnalyticalTest", _tests),
    # A stability pull's tests name no lot: they are not part of the lot's release testing, but
    # they are part of its record.
    Section(
        "stability_tests",
        "Tests of stability pulls",
        "analytical.AnalyticalTest",
        _in("pull", "pulls"),
    ),
    Section("observations", "Observations", "analytical.Observation", _of_tests("test")),
    Section("raw_files", "Raw-data files", "analytical.RawDataFile", _of_tests("test")),
    Section("investigations", "Investigations", "analytical.Investigation", _investigations),
    Section(
        "investigation_entries",
        "Investigation entries",
        "analytical.InvestigationEntry",
        _in("investigation", "investigations"),
    ),
    Section("qc_batches", "QC batches", "analytical.QCBatch", _batches),
    Section("qc_results", "QC batch checks", "analytical.QCResult", _in("batch", "qc_batches")),
    Section("reports", "Certificates of analysis", "reporting.Report", _lot),
    Section(
        "report_versions",
        "Certificate versions",
        "reporting.ReportVersion",
        _in("report", "reports"),
    ),
    # Last: they name any of the records above as their context.
    Section(
        "resource_uses",
        "Instruments and reagent lots used",
        "laboratory.ResourceUse",
        _contexts,
    ),
    Section(
        "contract_uses",
        "Contract laboratory reports relied on",
        "laboratory.ContractUse",
        _contexts,
    ),
)

# Configuration the lot's records name, added as it stands at the export. Its own history is on
# its pages; its signatures are listed with it.
REFERENCED = {
    "core.ruleset": "Rule sets",
    "catalog.material": "Materials",
    "catalog.specification": "Specifications",
    "catalog.specificationrevision": "Specification versions",
    "catalog.method": "Methods",
    "catalog.methodrevision": "Method versions",
    "sampling.samplingplan": "Sampling plans",
    "sampling.samplingplanrevision": "Sampling plan versions",
    "suppliers.supplier": "Suppliers",
    "suppliers.supplierqualification": "Supplier qualifications",
    "laboratory.equipment": "Equipment",
    "laboratory.reagentlot": "Reagent and standard lots",
    "laboratory.contractapproval": "Contract laboratory approvals",
    "laboratory.contractlaboratory": "Contract laboratories",
    "stability.protocol": "Stability protocols",
    "stability.protocolcondition": "Stability protocol conditions",
    "stability.protocoltimepoint": "Stability protocol time points",
}
USER_LABEL = "accounts.user"
# A link to the version that later replaced a record is not something the lot's records name.
NOT_FOLLOWED = frozenset({"superseded_by"})
# Approved versions whose stored hash is recomputed from their approved content.
APPROVED_VERSIONS = (
    "catalog.specificationrevision",
    "catalog.methodrevision",
    "sampling.samplingplanrevision",
)


class ExportError(Exception):
    """The package could not be built or recorded; nothing was recorded."""


def require_exporter(actor):
    require_role(actor, *EXPORT_ROLES)


def iso(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def label_of(model):
    return model._meta.label_lower


def ref(obj):
    return f"{label_of(type(obj))}:{obj.pk}"


def key_of(obj):
    return (label_of(type(obj)), str(obj.pk))


def safe_name(text, fallback, limit=80, uploaded=False):
    """A file or folder name that names no other folder and holds no control character.

    An uploaded file name keeps only its last part, as a browser may send a path; an identifier
    such as a lot number keeps every part, its separators replaced.
    """
    text = str(text)
    if uploaded:
        text = text.replace("\\", "/").rsplit("/", 1)[-1]
    text = re.sub(r"[^A-Za-z0-9._ -]+", "_", text).strip(" ._")[:limit].strip(" ._")
    return text or fallback


@cache
def application():
    found = {"name": "OpenBGA QM LIMS", "version": "unknown"}
    try:
        with open(Path(settings.BASE_DIR) / "pyproject.toml", "rb") as handle:
            found["version"] = str(tomllib.load(handle)["project"]["version"])
    except OSError, KeyError, TypeError, tomllib.TOMLDecodeError:
        pass
    return found


def _binary_fields(model):
    return [f for f in model._meta.concrete_fields if isinstance(f, models.BinaryField)]


def _is_reference(f):
    return f.is_relation and (f.many_to_one or f.one_to_one)


def _value(value):
    """A stored value in JSON: exact decimals as text, moments in UTC."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (memoryview, bytes)):
        raise TypeError("Binary values are kept as files.")
    return value


def type_description(model):
    """The meaning of each stored field: its label, kind, what it references and its choices."""
    described = []
    for f in model._meta.concrete_fields:
        item = {"name": f.name, "label": str(f.verbose_name), "kind": f.get_internal_type()}
        if _is_reference(f):
            item["references"] = label_of(f.related_model)
        if f.choices:
            item["choices"] = {str(k): str(v) for k, v in f.flatchoices}
        if f.help_text:
            item["help"] = str(f.help_text)
        described.append(item)
    return {"title": str(model._meta.verbose_name), "fields": described}


def _by_type(pairs):
    query = Q(pk__in=[])
    for label, ids in pairs.items():
        query |= Q(object_type=label, object_id__in=sorted(ids))
    return query


@dataclass
class Collection:
    lot: Lot
    by_section: dict = field(default_factory=dict)  # section key -> list of instances
    referenced: dict = field(default_factory=dict)  # label -> {pk: instance}
    files: list = field(default_factory=list)  # one entry per stored file in the package
    binary: dict = field(default_factory=dict)  # (ref, field name) -> file entry

    def records(self, key):
        return self.by_section.get(key, [])

    def ids(self, key):
        return [r.pk for r in self.records(key)]

    def lot_records(self):
        for section in LOT_SECTIONS:
            yield from self.records(section.key)

    def all_records(self):
        yield from self.lot_records()
        for rows in self.referenced.values():
            yield from rows.values()

    def refs_by_label(self, everything=False):
        grouped = {}
        for obj in self.all_records() if everything else self.lot_records():
            label, pk = key_of(obj)
            grouped.setdefault(label, set()).add(pk)
        return grouped


def _named_inside(c):
    """Configuration the lot's records name by id inside stored values: the rule sets,
    specification versions and method versions frozen in its requirement assignments, and every
    rule set the lot was under (its receipt and later assignments move ``Lot.rules``)."""
    wanted = {}

    def add(label, value):
        if isinstance(value, int) and not isinstance(value, bool):
            wanted.setdefault(label, set()).add(value)

    for assignment in c.records("assignments"):
        payload = assignment.payload if isinstance(assignment.payload, dict) else {}
        for rules in [payload.get("rules"), *(payload.get("additional_rules") or [])]:
            if isinstance(rules, dict):
                add("core.ruleset", rules.get("id"))
        for spec in [payload.get("specification"), *(payload.get("specifications") or [])]:
            if isinstance(spec, dict):
                add("catalog.specificationrevision", spec.get("revision_id"))
        for line in payload.get("tests") or []:
            method = line.get("method") if isinstance(line, dict) else None
            if isinstance(method, dict):
                add("catalog.methodrevision", method.get("revision_id"))
    for before, after in AuditEvent.objects.filter(
        object_type=label_of(Lot), object_id=str(c.lot.pk)
    ).values_list("before", "after"):
        for values in (before, after):
            if isinstance(values, dict):
                add("core.ruleset", values.get("rules"))
    return wanted


def collect(lot):
    """The lot's own records and the configuration they name, without file content."""
    c = Collection(lot=lot)
    for section in LOT_SECTIONS:
        model = apps.get_model(section.label)
        rows = model.objects.filter(section.find(c))
        binary = [f.name for f in _binary_fields(model)]
        if binary:
            rows = rows.defer(*binary)
        c.by_section[section.key] = list(rows.order_by("pk"))
    wanted, frontier = _named_inside(c), list(c.lot_records())
    while wanted or frontier:
        for obj in frontier:
            for f in type(obj)._meta.concrete_fields:
                if not _is_reference(f) or f.name in NOT_FOLLOWED:
                    continue
                label, value = label_of(f.related_model), getattr(obj, f.attname)
                if label in REFERENCED and value is not None:
                    wanted.setdefault(label, set()).add(value)
        frontier = []
        for label, ids in sorted(wanted.items()):
            found = c.referenced.setdefault(label, {})
            missing = [pk for pk in ids if pk not in found]
            for obj in apps.get_model(label).objects.filter(pk__in=missing).order_by("pk"):
                found[obj.pk] = obj
                frontier.append(obj)
        wanted = {}
    for label in list(c.referenced):
        c.referenced[label] = dict(sorted(c.referenced[label].items()))
    return c


def summarize(lot):
    """What an export of the lot would hold now, for the page that offers it."""
    with snapshot_read():
        c = collect(lot)
        return {
            "sections": [
                {"title": s.title, "count": len(c.records(s.key))}
                for s in LOT_SECTIONS
                if c.records(s.key)
            ],
            "referenced": sum(len(rows) for rows in c.referenced.values()),
            "events": AuditEvent.objects.filter(_by_type(c.refs_by_label())).count(),
            "signatures": ElectronicSignature.objects.filter(
                _by_type(c.refs_by_label(everything=True))
            ).count(),
            "files": len(c.records("raw_files")) + len(c.records("report_versions")),
        }


@contextmanager
def snapshot_read():
    """A read-only, repeatable-read transaction: one snapshot for every query inside it.

    Inside an outer transaction (tests that wrap each test in one) the outer snapshot is used.
    """
    outer = connection.in_atomic_block
    with transaction.atomic():
        if not outer:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield


def _people(c, events, signatures, reviews, actor):
    ids = {actor.pk}
    for obj in c.all_records():
        for f in type(obj)._meta.concrete_fields:
            if _is_reference(f) and label_of(f.related_model) == USER_LABEL:
                if getattr(obj, f.attname) is not None:
                    ids.add(getattr(obj, f.attname))
    ids.update(e.actor_id for e in events)
    ids.update(s.signer_id for s in signatures)
    ids.update(r.reviewer_id for r in reviews)
    return {
        user.pk: {
            "id": user.pk,
            "username": user.get_username(),
            "name": user.get_full_name() or user.get_username(),
        }
        for user in get_user_model().objects.filter(pk__in=ids).order_by("pk")
    }


def _serialize(obj, c):
    """Every stored field of a record. A stored file is named by its path in the package."""
    fields = {}
    for f in type(obj)._meta.concrete_fields:
        if isinstance(f, models.BinaryField):
            fields[f.name] = c.binary.get((ref(obj), f.name))
        else:
            fields[f.name] = _value(getattr(obj, f.attname))
    return {"id": _value(obj.pk), "fields": fields}


def _binary_path(obj, f, c):
    label = label_of(type(obj))
    if label == "analytical.rawdatafile":
        name = safe_name(obj.filename, "raw-data", limit=100, uploaded=True)
        return f"files/raw-data/test-{obj.test_id}/{obj.pk}-{name}"
    if label == "reporting.reportversion":
        number = next(
            (r.number for r in c.records("reports") if r.pk == obj.report_id), str(obj.report_id)
        )
        return f"files/certificates/{safe_name(number, 'certificate')}-v{obj.number}.pdf"
    return f"files/{label.replace('.', '-')}/{obj.pk}-{f.name}.bin"


def _entry(path, data):
    return {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _add(archive, name, data, stamp, compress=True):
    """Add one member. Stored files and PDFs are already compressed or are kept as they are, so
    they are stored without compressing them again, which keeps a large export fast."""
    info = zipfile.ZipInfo(name, date_time=stamp)
    info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def _write_files(c, archive, folder, stamp):
    """Copy each stored file into the package as it is read, one at a time."""
    for obj in list(c.all_records()):
        for f in _binary_fields(type(obj)):
            data = type(obj).objects.filter(pk=obj.pk).values_list(f.name, flat=True).get()
            data = bytes(data) if data is not None else b""
            entry = {**_entry(_binary_path(obj, f, c), data), "record": ref(obj)}
            c.binary[(ref(obj), f.name)] = entry
            c.files.append(entry)
            _add(archive, f"{folder}/{entry['path']}", data, stamp, compress=False)


def _check(kind, record, describes, stored, computed):
    return {
        "check": kind,
        "record": record,
        "describes": describes,
        "outcome": "intact" if stored == computed else "differs",
        "stored": stored,
        "computed": computed,
    }


def _file_text(entry):
    return f"{entry.get('sha256')} ({entry.get('size')} bytes)"


def _checks(c, signatures):
    """Recompute the SHA-256 of every stored file and the hash stored with each signature's
    content, certificate content, requirement assignment and approved version, and state each
    outcome. Other hashes the records hold are copied, not recomputed."""
    results = [
        _check(
            "signature content",
            ref(signature),
            f"{signature.signer_name}, {signature.meaning}, "
            f"{signature.object_type}:{signature.object_id} revision {signature.revision}",
            signature.content_hash,
            canonical_hash(signature.content),
        )
        for signature in signatures
    ]
    stored = {entry["record"]: entry for entry in c.files}
    for raw in c.records("raw_files"):
        results.append(
            _check(
                "raw-data file",
                ref(raw),
                f"{raw.filename}, test {raw.test_id}",
                f"{raw.sha256} ({raw.size} bytes)",
                _file_text(stored.get(ref(raw), {})),
            )
        )
    for version in c.records("report_versions"):
        results.append(
            _check(
                "certificate file",
                ref(version),
                str(version),
                f"{version.pdf_sha256} ({version.pdf_size} bytes)",
                _file_text(stored.get(ref(version), {})),
            )
        )
        results.append(
            _check(
                "certificate content",
                ref(version),
                str(version),
                version.snapshot_hash,
                canonical_hash(version.snapshot),
            )
        )
    for assignment in c.records("assignments"):
        if assignment.payload is None:  # a hold freezes no requirements and stores no hash
            continue
        results.append(
            _check(
                "requirement assignment",
                ref(assignment),
                f"Assignment {assignment.pk} ({assignment.status})",
                assignment.payload_hash,
                canonical_hash(assignment.payload),
            )
        )
    for label in APPROVED_VERSIONS:
        for revision in c.referenced.get(label, {}).values():
            if revision.approved_content is not None:
                results.append(
                    _check(
                        "approved content",
                        ref(revision),
                        str(revision),
                        revision.approved_hash,
                        canonical_hash(revision.approved_content),
                    )
                )
    return results


# Printed copy --------------------------------------------------------------------------------


def printed_moment(moment):
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _printed_value(obj, f, c, people, names):
    value = getattr(obj, f.attname)
    if isinstance(f, models.BinaryField):
        entry = c.binary.get((ref(obj), f.name))
        if not entry:
            return {"text": "No content."}
        return {"text": f"File {entry['path']}, {entry['size']} bytes, SHA-256 {entry['sha256']}"}
    if value is None or value == "" or (isinstance(f, models.JSONField) and value in ({}, [])):
        return {"text": "—"}  # blank, as "How to read this record" says; record.json keeps it
    if _is_reference(f):
        label = label_of(f.related_model)
        if label == USER_LABEL:
            person = people.get(value)
            return {"text": f"{person['name']} ({person['username']})" if person else f"#{value}"}
        return {"text": f"{names.get((label, str(value)), label)} (#{value})"}
    if f.choices:
        return {"text": str(getattr(obj, f"get_{f.name}_display")())}
    if isinstance(f, models.JSONField):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1)
        if len(text) > PRINT_JSON_LIMIT:
            return {
                "text": f"Structured data, {len(text)} characters: kept in full in record.json, "
                f"record {ref(obj)}, field {f.name}."
            }
        return {"text": text, "block": True}
    if isinstance(value, datetime):
        return {"text": printed_moment(value)}
    if isinstance(value, bool):
        return {"text": "Yes" if value else "No"}
    text = str(value)
    return {"text": text, "block": "\n" in text}


def _short(value):
    if value == "":
        return "(blank)"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) > PRINT_CHANGE_LIMIT:
        return f"{text[:PRINT_CHANGE_LIMIT]}… ({len(text)} characters, in full in record.json)"
    return text


def recorded(event):
    """What an event without earlier values recorded: each value it states."""
    after = event.after if isinstance(event.after, dict) else {}
    return [{"field": key, "value": _short(after[key])} for key in sorted(after)]


def changes(event):
    """What an audit event changed: each field whose value differs, before and after."""
    before, after = event.before, event.after
    if not before or not isinstance(before, dict) or not isinstance(after, dict):
        return []
    return [
        {
            "field": key,
            "before": _short(before[key]) if key in before else "(absent)",
            "after": _short(after[key]) if key in after else "(absent)",
        }
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key) or (key in before) != (key in after)
    ]


def _printed(c, sections, signatures, events, reviews, people, checks, meta):
    """The printed copy's content, prepared inside the read so that nothing is read later."""
    names = {key_of(obj): str(obj) for obj in c.all_records()}
    signed = {}
    for signature in signatures:
        signed.setdefault((signature.object_type, signature.object_id), []).append(signature)
    # A record's first event entered it when it states no earlier values; every later event
    # acted on the record after it was entered, whether or not it states earlier values.
    counted, trail = {}, []
    for event in events:
        key = (event.object_type, event.object_id)
        first = key not in counted
        total, entered = counted.get(key, (0, False))
        counted[key] = (total + 1, entered or (first and not event.before))
        trail.append((event, first and not event.before))
    outcome = {
        check["record"]: check["outcome"]
        for check in checks
        if check["check"] == "signature content"
    }

    def record_view(obj, part):
        total, entered = counted.get(key_of(obj), (0, False))
        return {
            "ref": ref(obj),
            "part": part,
            "title": str(obj),
            "rows": [
                {"label": str(f.verbose_name), **_printed_value(obj, f, c, people, names)}
                for f in type(obj)._meta.concrete_fields
            ],
            "events": total,
            "entered": entered,
            "later": total - 1 if entered else total,
            "signatures": [
                {
                    "name": s.signer_name,
                    "meaning": s.meaning,
                    "signed_at": printed_moment(s.signed_at),
                    "revision": s.revision,
                    "content_hash": s.content_hash,
                    "outcome": outcome[ref(s)],
                }
                for s in signed.get(key_of(obj), [])
            ],
        }

    def parts(part):
        return [
            {"title": s["title"], "records": [record_view(o, part) for o in s["objects"]]}
            for s in sections
            if s["part"] == part and s["objects"]
        ]

    def person(pk):
        return people.get(pk, {}).get("name", f"#{pk}")

    included = {str(e.pk) for e in events}
    return {
        "meta": meta,
        "exported": printed_moment(datetime.fromisoformat(meta["exported_at"])),
        "lot_parts": parts("lot"),
        "referenced_parts": parts("referenced"),
        "trail": [
            {
                "at": printed_moment(event.occurred_at),
                "person": person(event.actor_id),
                "action": event.action,
                "record": names.get((event.object_type, event.object_id), ""),
                "record_ref": f"{event.object_type}:{event.object_id}",
                "reason": event.reason,
                "entered": entered,
                "changes": changes(event),
                "recorded": [] if entered or event.before else recorded(event),
            }
            for event, entered in trail
        ],
        "reviews": [
            {
                "reviewer": person(review.reviewer_id),
                "at": printed_moment(review.reviewed_at),
                "conclusion": review.conclusion,
                "covered": len(included.intersection(review.event_ids)),
                "total": len(review.event_ids),
            }
            for review in reviews
        ],
        "files": c.files,
        "checks": checks,
        "differs": [check for check in checks if check["outcome"] != "intact"],
        "print_json_limit": PRINT_JSON_LIMIT,
        "print_change_limit": PRINT_CHANGE_LIMIT,
    }


def render_record_pdf(context, *, synthetic_notice=False):
    """The printed copy, in the shared print style; it loads only the certificate font."""
    try:
        html = render_to_string(
            "reporting/pdf/lot_record.html", {**context, "synthetic_notice": synthetic_notice}
        )
        data, served = write_pdf(html)
        if FONT_URL not in served:
            raise RenderError("The record font was not loaded.")
    except Exception as exc:  # renderer and font failures stop the export
        raise RenderError(str(exc) or exc.__class__.__name__) from exc
    if not data.startswith(b"%PDF-"):
        raise RenderError("The renderer did not produce a PDF.")
    return data


# Reading and packaging -----------------------------------------------------------------------


@dataclass
class Package:
    file: object  # an open binary file, positioned at its start
    filename: str
    size: int
    sha256: str
    export_id: str
    summary: dict


def build_package(*, actor, lot_pk, purpose):
    """Read the lot's record in one snapshot and write the package into a temporary file.

    Writes nothing to the database: ``export_lot_record`` records the audit event.
    """
    require_exporter(actor)
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY)
    try:
        with snapshot_read(), zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
            folder, export_id, summary = _build(actor, lot_pk, purpose, archive)
        spool.seek(0)
        digest, size = hashlib.sha256(), 0
        for chunk in iter(lambda: spool.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
        spool.seek(0)
    except BaseException:
        spool.close()
        raise
    return Package(
        file=spool,
        filename=f"{folder}.zip",
        size=size,
        sha256=digest.hexdigest(),
        export_id=export_id,
        summary=summary,
    )


def _build(actor, lot_pk, purpose, archive):
    """Read everything and write every member of the package; return its folder, export id and
    summary."""
    lot = Lot.objects.filter(pk=lot_pk).first()
    if lot is None:
        raise ExportError("The lot does not exist.")
    exported_at = timezone.now()
    export_id = str(uuid.uuid4())
    c = collect(lot)
    events = list(
        AuditEvent.objects.filter(_by_type(c.refs_by_label())).order_by("occurred_at", "id")
    )
    signatures = list(
        ElectronicSignature.objects.filter(_by_type(c.refs_by_label(everything=True))).order_by(
            "signed_at", "id"
        )
    )
    event_ids = {str(e.pk) for e in events}
    reviews = list(
        AuditReview.objects.filter(events__in=[e.pk for e in events])
        .distinct()
        .order_by("reviewed_at", "pk")
    )
    for review in reviews:
        review.event_ids = sorted(str(pk) for pk in review.events.values_list("pk", flat=True))
    people = _people(c, events, signatures, reviews, actor)

    slug = safe_name(lot.number, f"lot-{lot.pk}", limit=60).replace(" ", "-")
    folder = f"{slug}-record-{exported_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    stamp = exported_at.astimezone(UTC).timetuple()[:6]
    _write_files(c, archive, folder, stamp)
    checks = _checks(c, signatures)

    sections = [
        {
            "key": s.key,
            "title": s.title,
            "part": "lot",
            "type": s.label.lower(),
            "objects": c.records(s.key),
        }
        for s in LOT_SECTIONS
    ] + [
        {
            "key": label.replace(".", "_"),
            "title": title,
            "part": "referenced",
            "type": label,
            "objects": list(c.referenced.get(label, {}).values()),
        }
        for label, title in REFERENCED.items()
    ]
    meta = {
        "id": export_id,
        "exported_at": iso(exported_at),
        "exported_by": people[actor.pk],
        "purpose": purpose,
        "application": application(),
        "lot": {
            "id": lot.pk,
            "number": lot.number,
            "material": lot.material,
            "state": lot.state,
            "revision": lot.revision,
        },
    }
    types = {s["type"]: type_description(apps.get_model(s["type"])) for s in sections}
    for model in (AuditEvent, ElectronicSignature, AuditReview):
        types[label_of(model)] = type_description(model)
    record = {
        "schema": SCHEMA,
        "export": meta,
        "conventions": {
            "moments": "ISO 8601 in UTC.",
            "dates": "ISO 8601 calendar dates.",
            "decimals": "Text, exactly as stored, with every digit recorded.",
            "references": "A field that references another record holds that record's id; "
            "`types` names the type it references.",
            "people": "A field naming a person holds the id of an entry in `people`.",
            "files": "A field holding a file names its path in the package, its size and its "
            "SHA-256.",
            "referenced": "Sections of part `referenced` are configuration the lot's records "
            "name, as it stands at the export.",
        },
        "types": types,
        "sections": [
            {
                "key": s["key"],
                "title": s["title"],
                "part": s["part"],
                "type": s["type"],
                "records": [_serialize(o, c) for o in s["objects"]],
            }
            for s in sections
            if s["objects"]
        ],
        "signatures": [_serialize(s, c) for s in signatures],
        "audit_trail": [_serialize(e, c) for e in events],
        "audit_reviews": [
            {
                **_serialize(r, c),
                "events_in_this_record": [pk for pk in r.event_ids if pk in event_ids],
                "events_total": len(r.event_ids),
            }
            for r in reviews
        ],
        "people": list(people.values()),
        "files": c.files,
        "checks": checks,
    }
    printed = _printed(c, sections, signatures, events, reviews, people, checks, meta)
    pdf = render_record_pdf(
        printed, synthetic_notice=getattr(settings, "REPORT_SYNTHETIC_DATA_NOTICE", True)
    )
    record_bytes = json.dumps(record, ensure_ascii=False, indent=1).encode()

    listed = list(c.files)
    for name, data, compress in (("record.pdf", pdf, False), ("record.json", record_bytes, True)):
        _add(archive, f"{folder}/{name}", data, stamp, compress=compress)
        listed.append(_entry(name, data))
    summary = {
        "lot_revision": lot.revision,
        "records": sum(len(s["objects"]) for s in sections if s["part"] == "lot"),
        "referenced": sum(len(s["objects"]) for s in sections if s["part"] == "referenced"),
        "audit_events": len(events),
        "signatures": len(signatures),
        "audit_reviews": len(reviews),
        "files": len(c.files),
        "checks": len(checks),
        "checks_differ": len(printed["differs"]),
    }
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "export": meta,
        "summary": summary,
        "files": sorted(listed, key=lambda e: e["path"]),
        "verify": "In this folder, run `sha256sum -c SHA256SUMS`: every line must end in OK.",
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=1).encode()
    _add(archive, f"{folder}/manifest.json", manifest_bytes, stamp)
    listed.append(_entry("manifest.json", manifest_bytes))
    sums = "".join(f"{e['sha256']}  {e['path']}\n" for e in sorted(listed, key=lambda e: e["path"]))
    _add(archive, f"{folder}/SHA256SUMS", sums.encode(), stamp)
    summary.update(
        {
            "record_pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "record_json_sha256": hashlib.sha256(record_bytes).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        }
    )
    return folder, export_id, summary


def clean_purpose(purpose):
    purpose = (purpose or "").strip()
    if not purpose:
        raise ExportError("State why the record is exported.")
    if len(purpose) > PURPOSE_MAX:
        raise ExportError(f"Keep the purpose to {PURPOSE_MAX} characters.")
    return purpose


def export_lot_record(*, actor, lot_pk, purpose):
    """Build the package, then record who exported it, when, why, and its checksum.

    The package is returned only once its audit event is committed.
    """
    purpose = clean_purpose(purpose)
    package = build_package(actor=actor, lot_pk=lot_pk, purpose=purpose)
    try:
        with transaction.atomic():
            require_exporter(actor)
            lot = Lot.objects.get(pk=lot_pk)
            record_event(
                actor=actor,
                action=EXPORT_ACTION,
                obj=lot,
                after={
                    "export_id": package.export_id,
                    "package": package.filename,
                    "package_sha256": package.sha256,
                    "package_size": package.size,
                    **package.summary,
                },
                reason=purpose,
            )
    except BaseException:
        package.file.close()
        raise
    return package
