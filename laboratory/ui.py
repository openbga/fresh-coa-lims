"""Shared view helpers for the laboratory and stability apps (HTTP only; policy lives in services).

Pages are described as plain data (facts, sections, rows of cells) and rendered by the generic
`ops/*.html` templates, which compose the shared design-system includes.
"""

import re

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from core import grids
from core.models import AuditEvent, ElectronicSignature
from core.services import require_role

READERS = ("analyst", "reviewer", "quality", "admin", "auditor")

# Sibling lists under one sidebar item, shown as tabs on the overview and every list.
SECTION_TABS = {
    "laboratory": [
        ("Overview", "overview"),
        ("Equipment", "equipment_list"),
        ("Calibrations", "calibration_list"),
        ("Qualifications", "qualification_list"),
        ("Reagents and standards", "reagent_list"),
        ("Contract laboratories", "contract_laboratory_list"),
        ("Resource use", "use_list"),
    ],
    "stability": [
        ("Overview", "overview"),
        ("Protocols", "protocol_list"),
        ("Studies", "study_list"),
        ("Pulls", "pull_list"),
        ("Reserves", "reserve_list"),
        ("Holds", "hold_list"),
    ],
    "validation": [
        ("Intended use", "use_list"),
        ("Rehearsals", "rehearsal_list"),
    ],
}


def section_tabs(request):
    match = request.resolver_match
    return [
        {
            "label": label,
            "url": reverse(f"{match.namespace}:{name}"),
            "current": match.url_name == name,
        }
        for label, name in SECTION_TABS.get(match.namespace, [])
    ]


def access(user):
    require_role(user, *READERS)


def roles_of(user):
    return set(user.groups.values_list("name", flat=True))


class FilterForm(forms.Form):
    """Search plus an optional status choice; GET-bound so the URL is the whole state."""

    q = forms.CharField(required=False, label="Search", max_length=100)

    def __init__(self, *args, choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if choices:
            self.fields["status"] = forms.ChoiceField(
                required=False, label="Status", choices=[("", "All"), *choices]
            )


def make_filter(request, choices=None):
    keys = {"q", "status"}
    bound = any(key in request.GET for key in keys)
    form = FilterForm(request.GET if bound else None, choices=choices)
    cleaned = form.cleaned_data if bound and form.is_valid() else {}
    return form, cleaned


# --- Cells -----------------------------------------------------------------------------------


def cell(text="", href=None, tone=None, numeric=False, link_rel=None, pill=None):
    """One table/fact value. `tone` renders `text` as a status label (text plus glyph); `pill`
    (label, tone) adds a status label after plain `text` (a clock fact: date, then its state)."""
    return {
        "text": text,
        "href": href,
        "tone": tone,
        "numeric": numeric,
        "rel": link_rel,
        "pill": pill,
    }


def wrap(value):
    return value if isinstance(value, dict) else cell(value)


# Only canonical record numbers are resolved (ASCII digits, no leading zero, fits a bigint); any
# other recorded identifier, such as "007" or a non-ASCII digit, keeps its raw fallback label.
CANONICAL_ID = re.compile(r"[1-9][0-9]{0,17}")


def _result_text(test):
    try:
        return test.reportable_with_unit
    except Exception:  # an unreadable frozen requirement must not break a laboratory page
        return test.reportable_display


def work_labels(pairs):
    """Readable labels for recorded work contexts, keyed by (context_type, context_id).

    Known contexts resolve to the sample reference, the test label with its lot number and sample
    reference (or its stability pull), or the QC batch number; anything unknown or no longer
    resolvable keeps its raw identifier as the fallback. Returns (labels, links, details):
    `details` holds, per resolved test or QC batch, the facts the impact lists show."""
    from django.apps import apps
    from django.db.models import Count

    # Only these recognized context types are resolved, each against one fixed model; any other
    # type keeps its raw identifier. There is no dynamic lookup of arbitrary models.
    pairs = [(kind, str(ident)) for kind, ident in pairs]
    wanted = {}
    for kind, ident in set(pairs):
        wanted.setdefault(kind, set()).add(ident)
    labels = {(kind, ident): f"{kind} {ident}" for kind, ident in set(pairs)}
    links, details = {}, {}

    def canonical(kind):
        return {int(i) for i in wanted.get(kind, ()) if CANONICAL_ID.fullmatch(i)}

    sample_ids = canonical("quality.sample")
    test_ids = canonical("analytical.analyticaltest")
    batch_ids = canonical("analytical.qcbatch")
    if test_ids and apps.is_installed("analytical"):
        tests = apps.get_model("analytical", "AnalyticalTest").objects.filter(pk__in=test_ids)
        related = ("sample", "lot", "pull__study__lot", "pull__timepoint__condition")
        for test in tests.select_related(*related):
            key = ("analytical.analyticaltest", str(test.pk))
            # A test of a stability pull names the pull where a lot's test names its sample.
            lot = test.source_lot.number
            sampled = "stability pull" if test.pull_id is not None else "sample"
            labels[key] = f"{test.label} · lot {lot} · {sampled} {test.sample_text}"
            links[key] = reverse("analytical:test_detail", args=[test.pk])
            details[key] = {
                "kind": "test",
                "lot": lot,
                "test_code": test.test_code,
                "state": test.get_state_display(),
                "result": _result_text(test),
            }
    if batch_ids and apps.is_installed("analytical"):
        batches = apps.get_model("analytical", "QCBatch").objects.filter(pk__in=batch_ids)
        for batch in batches.annotate(test_count=Count("tests")):
            key = ("analytical.qcbatch", str(batch.pk))
            labels[key] = f"QC batch {batch.number}"
            links[key] = reverse("analytical:batch_detail", args=[batch.pk])
            details[key] = {"kind": "batch", "tests": batch.test_count}
    if sample_ids:
        sample_model = apps.get_model("quality", "Sample")
        for sample in sample_model.objects.filter(pk__in=sample_ids):
            key = ("quality.sample", str(sample.pk))
            labels[key] = sample.reference
            links[key] = reverse("quality:lot_detail", args=[sample.lot_id])
    return labels, links, details


def work_cell(use, resolved):
    labels, links = resolved[:2]
    key = (use.context_type, str(use.context_id))
    return cell(labels.get(key, f"{use.context_type} {use.context_id}"), links.get(key))


def when(moment):
    """Unambiguous timestamp with zone, from the deployment's local time."""
    return timezone.localtime(moment).strftime("%Y-%m-%d %H:%M %Z") if moment else ""


def day(value):
    return value.isoformat() if value else ""


def status(label, tone="neutral"):
    return cell(label, tone=tone)


def external_link(url, label=None):
    """Untrusted external link: validated http(s) at input; never trusted for navigation."""
    if not url:
        return cell("")
    return cell(label or url, href=url, link_rel="noopener noreferrer")


# --- Lists -----------------------------------------------------------------------------------


def paginate(request, queryset, sorts, default):
    """Server-side sort and paging over the whole authorized queryset.

    `sorts` maps a public key to ORDER BY expressions; unknown keys fall back to `default`.
    """
    key = request.GET.get("sort", default)
    descending = key.startswith("-")
    base = key.lstrip("-")
    if base not in sorts:
        base, descending = default.lstrip("-"), default.startswith("-")
    expressions = sorts[base]
    expressions = [expressions] if isinstance(expressions, str) else list(expressions)
    ordering = (
        [e[1:] if e.startswith("-") else "-" + e for e in expressions]
        if descending
        else expressions
    )
    page = grids.paginate(request, queryset.order_by(*ordering, "pk"))
    return page, base, descending


def list_page(
    request,
    *,
    template="ops/list.html",
    title,
    intro,
    noun,
    columns,
    rows,
    page,
    sort,
    descending,
    filter_form,
    new=None,
    empty_body,
    extra=None,
):
    """`columns`: list of (label, sort_key|None, numeric). `rows`: list of lists of cells."""
    filtered = any(v for k, v in request.GET.items() if k not in ("page", "per_page", "sort"))
    context = {
        "page_title": title,
        "intro": intro,
        "noun": noun,
        "columns": [
            {"label": label, "sort": key, "desc": f"-{key}" if key else "", "numeric": numeric}
            for label, key, numeric in columns
        ],
        "rows": [[wrap(c) for c in row] for row in rows],
        "page_obj": page,
        "sort": f"-{sort}" if descending else sort,
        "filter_form": filter_form,
        # The toolbar's search box is the q field; the other fields sit beside it.
        "query": (filter_form["q"].value() or "") if "q" in filter_form.fields else "",
        "filter_fields": [field for field in filter_form if field.name != "q"],
        "filtered": filtered,
        "new": new,
        "empty_body": empty_body,
        "tabs": section_tabs(request),
        **(extra or {}),
    }
    return render(request, template, context)


# --- Records ---------------------------------------------------------------------------------


def history_for(*objs):
    query = Q()
    for obj in objs:
        query |= Q(object_type=obj._meta.label_lower, object_id=str(obj.pk))
    events = list(
        AuditEvent.objects.filter(query).select_related("actor").order_by("occurred_at", "id")
    )
    for event in events:
        # Show old/new only for changes to an existing record, never whole creation payloads.
        event.changes = (
            [
                (key, _brief(event.before.get(key)), _brief(event.after.get(key)))
                for key in sorted(set(event.before) | set(event.after))
                if event.before.get(key) != event.after.get(key)
            ]
            if event.before
            else []
        )
    return events


BRIEF_LIMIT = 240


def _brief(value):
    """A long structured value, such as the results frozen with a pull's acceptance, is named
    in the history instead of printed: the page shows it in its own section, the signature
    binds it and the audit trail keeps it in full."""
    if isinstance(value, (dict, list)) and len(str(value)) > BRIEF_LIMIT:
        return f"structured record with {len(value)} entries, kept in full in the audit trail"
    return value


def signatures_for(*objs):
    query = Q()
    for obj in objs:
        query |= Q(object_type=obj._meta.label_lower, object_id=str(obj.pk))
    return ElectronicSignature.objects.filter(query).order_by("signed_at", "id")


def record_page(
    request,
    *,
    identifier,
    title,
    crumbs,
    state,
    facts,
    actions=(),
    sections=(),
    related=(),
    notice=None,
    schedule=None,
    status_code=200,
):
    """`related` are objects whose signatures and audit history appear on the page. `schedule`
    (a stability study's pulls as a condition by time point grid) is shown before `sections`.

    The header shows at most one primary action (last) and three others; the rest go under
    More (docs/ui-standards.md)."""
    actions = [a for a in actions if a]
    primary = next((a for a in actions if a["primary"]), None)
    others = [a for a in actions if a is not primary]
    return render(
        request,
        "ops/record.html",
        {
            "page_title": title,
            "identifier": identifier,
            "crumbs": crumbs,
            "state": state,
            "facts": [(label, wrap(value)) for label, value in facts],
            "primary_action": primary,
            "actions": others[:3],
            "more_actions": others[3:],
            "sections": sections,
            "signatures": signatures_for(*related),
            "history": history_for(*related),
            "notice": notice,
            "schedule": schedule,
        },
        status=status_code,
    )


def section(title, columns, rows, empty, note=""):
    """`columns`: list of (label, numeric)."""
    return {
        "title": title,
        "columns": columns,
        "rows": [[wrap(c) for c in row] for row in rows],
        "empty": empty,
        "note": note,
    }


def action(label, href, primary=False):
    return {"label": label, "href": href, "primary": primary}


# --- Forms and signing -----------------------------------------------------------------------


def form_page(request, form, *, title, crumbs, submit, cancel_url, intro="", record=None):
    return render(
        request,
        "ops/form.html",
        {
            "page_title": title,
            "form": form,
            "crumbs": crumbs,
            "submit": submit,
            "cancel_url": cancel_url,
            "intro": intro,
            "record": record,
        },
        status=422 if request.method == "POST" and form.errors else 200,
    )


def run_form(request, form, action_fn):
    """Run a service call for a valid form; domain refusals become form errors, not 500s."""
    try:
        return action_fn(), None
    except ValidationError as exc:
        form.add_error(None, "; ".join(exc.messages))
    return None, form


def sign_page(
    request,
    form,
    *,
    title,
    identifier,
    meaning,
    meaning_text,
    button,
    facts,
    revision,
    cancel_url,
    run,
    success,
    success_url,
    denial="",
    crumbs=(),
):
    """Native signing page. `run(cleaned_data)` calls the signed service transition. A denied
    actor sees the reason and no PIN control; opening the page never signs."""
    context = {
        "page_title": title,
        "identifier": identifier,
        "meaning": meaning,
        "meaning_text": meaning_text,
        "button": button,
        "facts": [(label, wrap(value)) for label, value in facts],
        "revision": revision,
        "form": form,
        "cancel_url": cancel_url,
        "crumbs": crumbs,
        "denial": denial,
    }
    if denial:
        return render(request, "ops/sign.html", context, status=403)
    if request.method == "POST" and form.is_valid():
        try:
            run(form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        except PermissionDenied as exc:
            context["denial"] = str(exc) or "This action is not permitted for you."
            return render(request, "ops/sign.html", context, status=403)
        else:
            messages.success(request, success)
            return redirect(success_url)
    return render(
        request, "ops/sign.html", context, status=422 if request.method == "POST" else 200
    )


def impact_columns():
    return [
        ("Used", False),
        ("Work", False),
        ("Lot", False),
        ("Test", False),
        ("State", False),
        ("Reportable result", False),
        ("Tests in batch", True),
        ("By", False),
    ]


def impact_row(use, resolved):
    """One affected use: the work with its lot, test code, state and result, or batch size."""
    detail = resolved[2].get((use.context_type, str(use.context_id)), {})
    batch = detail.get("kind") == "batch"
    return [
        when(use.used_at),
        work_cell(use, resolved),
        detail.get("lot", ""),
        use.test_code if batch else detail.get("test_code", use.test_code),
        detail.get("state", ""),
        detail.get("result", ""),
        cell(str(detail["tests"]), numeric=True) if batch else "",
        str(use.used_by),
    ]


def impact_summary(use, resolved):
    """The same facts as one line of text with the work's link, for the signing page."""
    key = (use.context_type, str(use.context_id))
    detail = resolved[2].get(key, {})
    parts = [resolved[0].get(key, f"{use.context_type} {use.context_id}")]
    if detail.get("kind") == "test":
        parts += [detail["test_code"], detail["state"]]
        if detail["result"]:
            parts.append(f"result {detail['result']}")
    elif detail.get("kind") == "batch":
        parts.append(f"{detail['tests']} test(s)")
    elif use.test_code:
        parts.append(use.test_code)
    return cell(" · ".join(parts), resolved[1].get(key))
