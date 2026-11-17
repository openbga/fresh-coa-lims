"""Pages for the laboratory's validation records (HTTP only; the rules are in ``services``)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from catalog.web import form_status, run
from core.services import require_role
from core.uploads import size_text
from laboratory.forms import SigningForm
from laboratory.ui import (
    action,
    cell,
    day,
    external_link,
    form_page,
    list_page,
    make_filter,
    paginate,
    record_page,
    section,
    sign_page,
    status,
)
from laboratory.ui import when as stamp

from . import services
from .forms import AcceptUseForm, RehearsalForm, UseAcceptanceForm, WithdrawForm
from .models import Rehearsal, RehearsalFile, UseAcceptance

SECTION = "Validation"
WHAT_ACCEPTANCE_DOES = (
    "The acceptance records the laboratory's decision that the system is fit for the use "
    "described, with the approved configuration and release in force when it was signed. It "
    "holds no work: changes since then are shown here for the laboratory to assess under its "
    "own change control."
)
WHAT_REHEARSAL_DOES = (
    "A rehearsal record is the laboratory's evidence that a recovery, a period of downtime or "
    "an upgrade was tried out and how it went. The acceptance confirms the record; it does not "
    "make the criteria met."
)


def read_access(user):
    require_role(user, *services.READ_ROLES)


def _people(user):
    if user is None:
        return ""
    name = user.get_full_name()
    return f"{name} ({user.get_username()})" if name else user.get_username()


def _crumbs(*pairs):
    return [(SECTION, reverse("validation:use_list")), *pairs]


def _rehearsal_crumbs(*pairs):
    return _crumbs(("Rehearsals", reverse("validation:rehearsal_list")), *pairs)


def _release_text(release):
    return release or "Not stated by the deployment"


def _short(value, length=12):
    return value[:length] if value else ""


# --- Acceptance for intended use -----------------------------------------------------------


def use_url(acceptance):
    return reverse("validation:use_detail", args=[acceptance.pk])


def drift(acceptance, configuration=None, release=None):
    """What changed since an accepted record was signed: (configuration rows, release text)."""
    configuration = configuration or services.configuration_in_force()
    release = services.running_release() if release is None else release
    rows = services.configuration_changes(acceptance.configuration, configuration)
    moved = ""
    if release != acceptance.accepted_release:
        moved = (
            f"The running release ({_release_text(release)}) is not the accepted one "
            f"({_release_text(acceptance.accepted_release)})."
        )
    return rows, moved


def _drift_text(rows, moved):
    parts = []
    if rows:
        parts.append(f"{len(rows)} change{'s' if len(rows) != 1 else ''} to the configuration")
    if moved:
        parts.append("another release")
    return " and ".join(parts) if parts else "None"


USE_STATUS = [(value, label) for value, label in UseAcceptance.State.choices]


@login_required
def use_list(request):
    read_access(request.user)
    form, data = make_filter(request, USE_STATUS)
    queryset = UseAcceptance.objects.select_related("recorded_by")
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(Q(title__icontains=q) | Q(intended_use__icontains=q))
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {"recorded": ["recorded_at"], "title": ["title"], "accepted": ["accepted_at"]},
        "-recorded",
    )
    current = services.current_acceptance()
    rows_now, moved = drift(current) if current else ([], "")
    rows = []
    for item in page:
        label, tone = services.use_status(item)
        rows.append(
            [
                cell(item.label, use_url(item)),
                item.title,
                status(label, tone),
                str(item.recorded_by),
                day(timezone.localdate(item.recorded_at)),
                day(timezone.localdate(item.accepted_at)) if item.accepted_at else "",
                _drift_text(rows_now, moved) if current and item.pk == current.pk else "",
            ]
        )
    if current is None:
        notice = {
            "tone": "info",
            "label": "No accepted intended use",
            "text": "No record of the laboratory's intended use has been accepted yet.",
        }
    elif rows_now or moved:
        notice = {
            "tone": "warning",
            "label": "Changed since acceptance",
            "text": f"{current.label} was accepted on "
            f"{day(timezone.localdate(current.accepted_at))}. Since then: "
            f"{_drift_text(rows_now, moved).lower()}. Assess the changes under your change "
            "control; record and accept the intended use again when they change it.",
        }
    else:
        notice = {
            "tone": "success",
            "label": "Current acceptance",
            "text": f"{current.label} was accepted on "
            f"{day(timezone.localdate(current.accepted_at))}. The approved configuration and "
            "the release are those it froze.",
        }
    return list_page(
        request,
        template="validation/list.html",
        title="Intended use",
        intro="The laboratory's acceptance of the system for its defined use: the supported "
        "assays, the approved configuration and the people responsible. A different quality "
        "person accepts each record with a signature.",
        noun="records",
        columns=[
            ("Record", None, False),
            ("Title", "title", False),
            ("State", None, False),
            ("Recorded by", None, False),
            ("Recorded", "recorded", False),
            ("Accepted", "accepted", False),
            ("Changes since acceptance", None, False),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "intended use", "href": reverse("validation:use_new")}
        if services.has_role(request.user, services.KEEPER)
        else None,
        empty_body="Record the laboratory's intended use, its supported assays and owners, then "
        "have a different quality person accept it.",
        extra={"notice": notice},
    )


@login_required
@require_http_methods(["GET", "POST"])
def use_new(request):
    require_role(request.user, services.KEEPER)
    methods = services.method_choices()
    form = UseAcceptanceForm(request.POST or None, methods=methods)
    if request.method == "POST" and form.is_valid():
        done = run(
            form,
            lambda: services.record_use_acceptance(actor=request.user, **form.cleaned_data),
        )
        if done:
            messages.success(
                request, f"{done.label} recorded; a different quality person accepts it."
            )
            return redirect(use_url(done))
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": "Record intended use",
            "form": form,
            "crumbs": _crumbs(("Record intended use", None)),
            "cancel_url": reverse("validation:use_list"),
            "submit_label": "Record intended use",
            "intro": "Recording accepts nothing. A different quality person reviews the record "
            "and accepts it with a signature, which freezes the approved configuration in "
            "force and the running release.",
            "facts": []
            if methods
            else [
                (
                    "Supported assays",
                    "No method has an approved version in force. Approve the methods first.",
                )
            ],
        },
        status=form_status(request, form),
    )


def _acceptance(pk):
    return get_object_or_404(
        UseAcceptance.objects.select_related(
            "recorded_by", "process_owner", "system_owner", "superseded_by"
        ),
        pk=pk,
    )


def _method_titles(codes):
    from catalog.models import Method

    return dict(Method.objects.filter(code__in=codes).values_list("code", "title"))


def _assays_section(acceptance, configuration):
    titles = _method_titles(acceptance.method_codes)
    frozen = {e["code"]: e for e in (acceptance.configuration or {}).get("supported_assays", [])}
    now = {e["code"]: e for e in configuration["methods"]}
    rows = []
    for code in acceptance.method_codes:
        accepted = frozen.get(code)
        current = now.get(code)
        rows.append(
            [
                f"{titles[code]} ({code})" if titles.get(code) else code,
                f"v{accepted['version']}" if accepted else "",
                f"v{current['version']}" if current else status("None in force", "danger"),
            ]
        )
    return section(
        "Supported assays",
        [("Method", False), ("Accepted", False), ("In force now", False)],
        rows,
        "No supported assays.",
    )


def _configuration_section(title, configuration, note=""):
    rows = []
    for key, label in services.KINDS:
        for entry in configuration.get(key, []):
            rows.append([label, entry["code"], f"v{entry['version']}", _short(entry.get("hash"))])
    return section(
        title,
        [("Kind", False), ("Code", False), ("Version", False), ("Content hash", False)],
        rows,
        "No approved version was in force.",
        note=note,
    )


def _changes_section(rows):
    return section(
        "Changes since acceptance",
        [
            ("Kind", False),
            ("Code", False),
            ("Accepted", False),
            ("In force now", False),
            ("Change", False),
        ],
        [[r["kind"], r["code"], r["accepted"], r["now"], r["change"]] for r in rows],
        "None: every approved version in force is the one the acceptance froze.",
        note="Each row is a code whose approved version in force is not the one frozen at "
        "acceptance.",
    )


def _outside_text(acceptance, configuration):
    outside = services.outside_assays(acceptance.method_codes, configuration)
    return ", ".join(outside) if outside else "None"


@login_required
def use_detail(request, pk):
    read_access(request.user)
    acceptance = _acceptance(pk)
    label, tone = services.use_status(acceptance)
    configuration = services.configuration_in_force()
    release = services.running_release()
    sections = [_assays_section(acceptance, configuration)]
    notice = {"tone": "info", "label": "What an acceptance does", "text": WHAT_ACCEPTANCE_DOES}
    if acceptance.state == UseAcceptance.State.ACCEPTED:
        rows, moved = drift(acceptance, configuration, release)
        sections.append(_changes_section(rows))
        if rows or moved:
            notice = {
                "tone": "warning",
                "label": "Changed since acceptance",
                "text": " ".join(
                    part
                    for part in (
                        f"{len(rows)} approved version{'s' if len(rows) != 1 else ''} in "
                        "force differ from those frozen at acceptance."
                        if rows
                        else "",
                        moved,
                        "Assess them under your change control; record and accept the intended "
                        "use again when they change it. No work is held.",
                    )
                    if part
                ),
            }
    if acceptance.configuration:
        sections.append(
            _configuration_section(
                "Approved configuration frozen at acceptance",
                acceptance.configuration,
                note=f"In force at {stamp(acceptance.accepted_at)}; SHA-256 of the frozen "
                f"record {acceptance.configuration_hash}.",
            )
        )
    elif acceptance.state == UseAcceptance.State.RECORDED:
        sections.append(
            _configuration_section(
                "Approved configuration in force now",
                configuration,
                note="The acceptance signature freezes the versions in force when it is signed.",
            )
        )
    if acceptance.state == UseAcceptance.State.SUPERSEDED:
        notice = {
            "tone": "neutral",
            "label": "Superseded",
            "text": f"Superseded by {acceptance.superseded_by.label} on "
            f"{stamp(acceptance.superseded_at)}. It is kept as accepted.",
        }
    user = request.user
    facts = [
        ("Title", acceptance.title),
        ("Intended use", acceptance.intended_use),
        ("Outside the intended use", acceptance.exclusions),
        ("Methods in force that are not supported assays", _outside_text(acceptance, configuration))
        if acceptance.state in (UseAcceptance.State.RECORDED, UseAcceptance.State.ACCEPTED)
        else None,
        ("Process owner", _people(acceptance.process_owner)),
        ("System owner", _people(acceptance.system_owner)),
        ("Other responsibilities", acceptance.other_responsibilities),
        ("Validation report", acceptance.validation_ref),
        ("Validation report link", external_link(acceptance.validation_url)),
        ("Known issues and conditions", acceptance.open_issues),
        ("Recorded by", str(acceptance.recorded_by)),
        ("Recorded", stamp(acceptance.recorded_at)),
        ("Accepted", stamp(acceptance.accepted_at)),
        ("Accepted release", _release_text(acceptance.accepted_release))
        if acceptance.accepted_at
        else None,
        ("Running release", _release_text(release)),
        ("Superseded", stamp(acceptance.superseded_at)),
        ("Superseded by", cell(acceptance.superseded_by.label, use_url(acceptance.superseded_by)))
        if acceptance.superseded_by_id
        else None,
        ("Withdrawn", stamp(acceptance.withdrawn_at)),
        ("Revision", acceptance.revision),
    ]
    return record_page(
        request,
        identifier=acceptance.label,
        title=acceptance.title,
        crumbs=_crumbs((acceptance.label, None)),
        state=status(label, tone),
        facts=[fact for fact in facts if fact],
        actions=[
            action("Accept", reverse("validation:use_accept", args=[acceptance.pk]), True)
            if services.has_role(user, services.KEEPER)
            and not services.use_denial(user, acceptance, accept=True)
            else None,
            action("Withdraw", reverse("validation:use_withdraw", args=[acceptance.pk]))
            if not services.use_denial(user, acceptance, accept=False)
            else None,
        ],
        sections=sections,
        related=[acceptance],
        notice=notice,
    )


def _configuration_text(configuration):
    parts = []
    for key, label in services.KINDS:
        entries = configuration.get(key, [])
        listed = ", ".join(f"{e['code']} v{e['version']}" for e in entries) or "none"
        parts.append(f"{label}s: {listed}")
    return "; ".join(parts)


@login_required
@require_http_methods(["GET", "POST"])
def use_accept(request, pk):
    require_role(request.user, services.KEEPER)
    acceptance = _acceptance(pk)
    detail = use_url(acceptance)
    configuration = services.configuration_in_force()
    release = services.running_release()
    current = services.current_acceptance()
    supported, missing = services.supported_versions(acceptance.method_codes, configuration)
    token = services.acceptance_token(acceptance, configuration, release, current)
    form = AcceptUseForm(
        request.POST or None,
        initial={"expected_revision": acceptance.revision, "token": token},
    )
    denial = services.use_denial(request.user, acceptance, accept=True)
    if not denial and missing:
        denial = (
            f"{', '.join(missing)} has no approved version in force. Withdraw this record and "
            "record the intended use again."
        )
    titles = _method_titles(acceptance.method_codes)
    return sign_page(
        request,
        form,
        title="Accept intended use",
        identifier=acceptance.label,
        meaning="accepted",
        meaning_text="You accept the system for the intended use described, with the supported "
        "assays, the approved configuration in force and the running release listed here, on "
        "the evidence of the validation report named. Your signature freezes them.",
        button="Sign and accept",
        facts=[
            ("Title", acceptance.title),
            ("Intended use", acceptance.intended_use),
            ("Outside the intended use", acceptance.exclusions),
            (
                "Supported assays",
                ", ".join(
                    f"{titles.get(e['code'], e['code'])} ({e['code']} v{e['version']})"
                    for e in supported
                ),
            ),
            (
                "Methods in force that are not supported assays",
                _outside_text(acceptance, configuration),
            ),
            ("Process owner", _people(acceptance.process_owner)),
            ("System owner", _people(acceptance.system_owner)),
            ("Other responsibilities", acceptance.other_responsibilities),
            ("Validation report", acceptance.validation_ref),
            ("Validation report link", external_link(acceptance.validation_url)),
            ("Known issues and conditions", acceptance.open_issues),
            ("Approved configuration in force", _configuration_text(configuration)),
            ("Running release", _release_text(release)),
            (
                "Supersedes",
                f"{current.label}, accepted {stamp(current.accepted_at)}" if current else "None",
            ),
            ("Recorded by", str(acceptance.recorded_by)),
        ],
        revision=acceptance.revision,
        cancel_url=detail,
        run=lambda d: services.accept_use(
            actor=request.user,
            pin=d["pin"],
            acceptance=acceptance,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
            token=d["token"],
        ),
        success=f"{acceptance.label} accepted.",
        success_url=detail,
        denial=denial,
        crumbs=_crumbs((acceptance.label, detail), ("Accept", None)),
    )


def _withdraw_page(request, record, *, service, detail, crumbs, noun, state_refusal, refusal):
    if refusal:
        raise PermissionDenied(refusal)
    if state_refusal:
        messages.warning(request, state_refusal)
        return redirect(detail)
    form = WithdrawForm(request.POST or None, initial={"expected_revision": record.revision})
    if request.method == "POST" and form.is_valid():
        try:
            service(
                actor=request.user,
                expected_revision=form.cleaned_data["expected_revision"],
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        except PermissionDenied as exc:
            messages.warning(request, str(exc))
            return redirect(detail)
        else:
            messages.success(request, f"{record.label} withdrawn.")
            return redirect(detail)
    return form_page(
        request,
        form,
        title=f"Withdraw {record.label}",
        crumbs=crumbs,
        submit="Withdraw",
        cancel_url=detail,
        intro=f"A withdrawn {noun} is never accepted and keeps its content in the record. "
        f"Record a new {noun} to correct it.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def use_withdraw(request, pk):
    require_role(request.user, services.KEEPER)
    acceptance = _acceptance(pk)
    detail = use_url(acceptance)
    return _withdraw_page(
        request,
        acceptance,
        service=lambda **kw: services.withdraw_use(acceptance=acceptance, **kw),
        detail=detail,
        crumbs=_crumbs((acceptance.label, detail), ("Withdraw", None)),
        noun="record of the intended use",
        state_refusal=services.use_state_refusal(acceptance),
        refusal=services.use_person_refusal(request.user, acceptance, accept=False),
    )


# --- Rehearsals ------------------------------------------------------------------------------


def rehearsal_url(rehearsal):
    return reverse("validation:rehearsal_detail", args=[rehearsal.pk])


REHEARSAL_STATUS = [(value, label) for value, label in Rehearsal.State.choices]


@login_required
def rehearsal_list(request):
    read_access(request.user)
    form, data = make_filter(request, REHEARSAL_STATUS)
    queryset = Rehearsal.objects.select_related("recorded_by").annotate(file_count=Count("files"))
    if data.get("q"):
        q = data["q"]
        queryset = queryset.filter(
            Q(title__icontains=q) | Q(release__icontains=q) | Q(procedure_ref__icontains=q)
        )
    if data.get("status"):
        queryset = queryset.filter(state=data["status"])
    page, sort, descending = paginate(
        request,
        queryset,
        {"performed": ["performed_on"], "kind": ["kind", "-performed_on"], "title": ["title"]},
        "-performed",
    )
    rows = []
    for item in page:
        label, tone = services.rehearsal_status(item)
        rows.append(
            [
                cell(item.label, rehearsal_url(item)),
                item.get_kind_display(),
                item.title,
                day(item.performed_on),
                item.release,
                status(label, tone),
                cell(str(item.file_count), numeric=True),
            ]
        )
    return list_page(
        request,
        title="Rehearsals",
        intro="Recorded rehearsals of recovery from backup, downtime with reconciliation of the "
        "records made meanwhile, and upgrades, each with its evidence and the laboratory's "
        "acceptance.",
        noun="rehearsals",
        columns=[
            ("Record", None, False),
            ("Rehearsal of", "kind", False),
            ("Title", "title", False),
            ("Performed", "performed", False),
            ("Release", None, False),
            ("Status", None, False),
            ("Files", None, True),
        ],
        rows=rows,
        page=page,
        sort=sort,
        descending=descending,
        filter_form=form,
        new={"label": "rehearsal", "href": reverse("validation:rehearsal_new")}
        if services.has_role(request.user, *services.REHEARSAL_RECORDERS)
        else None,
        empty_body="Record a rehearsal after it took place, attach its evidence, then have a "
        "quality person accept it.",
    )


@login_required
@require_http_methods(["GET", "POST"])
def rehearsal_new(request):
    require_role(request.user, *services.REHEARSAL_RECORDERS)
    initial = {"release": services.running_release()} if request.method == "GET" else None
    form = RehearsalForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        done = run(form, lambda: services.record_rehearsal(actor=request.user, **form.cleaned_data))
        if done:
            messages.success(
                request, f"{done.label} recorded. Attach its evidence; a quality person accepts it."
            )
            return redirect(rehearsal_url(done))
    return render(
        request,
        "catalog/form.html",
        {
            "page_title": "Record rehearsal",
            "form": form,
            "crumbs": _rehearsal_crumbs(("Record rehearsal", None)),
            "cancel_url": reverse("validation:rehearsal_list"),
            "submit_label": "Record rehearsal",
            "intro": "Record a rehearsal after it took place, as it happened. You then attach "
            "its evidence, such as the restore check report, and a quality person who did not "
            "record it accepts the record.",
        },
        status=form_status(request, form),
    )


def _rehearsal(pk):
    return get_object_or_404(Rehearsal.objects.select_related("recorded_by"), pk=pk)


def _files(rehearsal):
    return list(rehearsal.files.select_related("uploaded_by").order_by("uploaded_at", "pk"))


def _files_section(files):
    rows = [
        [
            cell(item.filename, reverse("validation:rehearsal_file", args=[item.pk])),
            item.description,
            cell(size_text(item.size), numeric=True),
            item.sha256,
            str(item.uploaded_by),
            stamp(item.uploaded_at),
        ]
        for item in files
    ]
    return section(
        "Evidence files",
        [
            ("File", False),
            ("What it is", False),
            ("Size", True),
            ("SHA-256", False),
            ("Attached by", False),
            ("Attached", False),
        ],
        rows,
        "No evidence attached yet.",
        note="Each file is kept exactly as received; a download checks it against its SHA-256.",
    )


def _rehearsal_facts(rehearsal):
    facts = [
        ("Rehearsal of", rehearsal.get_kind_display()),
        ("Title", rehearsal.title),
        ("Performed", day(rehearsal.performed_on)),
        ("Release before", rehearsal.previous_release)
        if rehearsal.kind == Rehearsal.Kind.UPGRADE
        else None,
        ("Release", rehearsal.release),
        ("Environment", rehearsal.environment),
        ("Procedure", rehearsal.procedure_ref),
        ("Acceptance criteria", rehearsal.acceptance_criteria),
        ("Outcome", rehearsal.get_outcome_display()),
        ("Observations", rehearsal.observations),
        ("Issues and actions", rehearsal.issues_and_actions),
        ("Recorded by", str(rehearsal.recorded_by)),
    ]
    return [fact for fact in facts if fact]


@login_required
def rehearsal_detail(request, pk):
    read_access(request.user)
    rehearsal = _rehearsal(pk)
    label, tone = services.rehearsal_status(rehearsal)
    user = request.user
    files = _files(rehearsal)
    notice = {"tone": "info", "label": "What a rehearsal record does", "text": WHAT_REHEARSAL_DOES}
    if rehearsal.state == Rehearsal.State.RECORDED and not files:
        notice = {
            "tone": "warning",
            "label": "Evidence needed",
            "text": "Attach the evidence of the rehearsal, such as the restore check report or "
            "the reconciliation record. A rehearsal without evidence cannot be accepted.",
        }
    elif rehearsal.state == Rehearsal.State.ACCEPTED and (
        rehearsal.outcome == Rehearsal.Outcome.NOT_MET
    ):
        notice = {
            "tone": "danger",
            "label": "Criteria not met",
            "text": "The rehearsal did not meet its acceptance criteria. Follow the issues and "
            "actions under your procedure, and record a new rehearsal when they are done.",
        }
    return record_page(
        request,
        identifier=rehearsal.label,
        title=rehearsal.title,
        crumbs=_rehearsal_crumbs((rehearsal.label, None)),
        state=status(label, tone),
        facts=[
            *_rehearsal_facts(rehearsal),
            ("Recorded", stamp(rehearsal.recorded_at)),
            ("Accepted", stamp(rehearsal.accepted_at)),
            ("Withdrawn", stamp(rehearsal.withdrawn_at)),
            ("Revision", rehearsal.revision),
        ],
        actions=[
            action("Attach evidence", reverse("validation:rehearsal_file_new", args=[rehearsal.pk]))
            if services.has_role(user, *services.REHEARSAL_RECORDERS)
            and not services.file_denial(user, rehearsal)
            else None,
            action("Accept", reverse("validation:rehearsal_accept", args=[rehearsal.pk]), True)
            if not services.rehearsal_denial(user, rehearsal, accept=True)
            else None,
            action("Withdraw", reverse("validation:rehearsal_withdraw", args=[rehearsal.pk]))
            if services.has_role(user, *services.REHEARSAL_RECORDERS)
            and not services.rehearsal_denial(user, rehearsal, accept=False)
            else None,
        ],
        sections=[_files_section(files)],
        related=[rehearsal],
        notice=notice,
    )


@login_required
@require_http_methods(["GET", "POST"])
def rehearsal_file_new(request, pk):
    from analytical.rawdata import RawFileForm, max_bytes

    require_role(request.user, *services.REHEARSAL_RECORDERS)
    rehearsal = _rehearsal(pk)
    back = rehearsal_url(rehearsal)
    if refusal := services.file_denial(request.user, rehearsal):
        messages.warning(request, refusal)
        return redirect(back)
    # A request far above the size limit never reaches this view (core.uploads refuses it
    # unread); BoundedUploadHandler stops a file over the limit while it arrives.
    if (
        request.method == "POST"
        and request.FILES is not None
        and getattr(request, "upload_too_large", False)
    ):
        messages.error(
            request,
            f"The file is larger than the limit of {size_text(max_bytes())}. Nothing was stored.",
        )
        return redirect("validation:rehearsal_file_new", pk=rehearsal.pk)
    form = RawFileForm(request.POST or None, request.FILES or None)
    form.fields[
        "description"
    ].help_text = (
        "For example: restore check report, backup manifest, or the reconciliation record."
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.attach_rehearsal_file(
                actor=request.user,
                rehearsal=rehearsal,
                upload=form.cleaned_data["file"],
                description=form.cleaned_data["description"],
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, "Evidence attached.")
            return redirect(back)
    return render(
        request,
        "analytical/raw_file_form.html",
        {
            "page_title": f"Attach evidence · {rehearsal.label}",
            "form": form,
            "submit_label": "Attach file",
            "crumbs": _rehearsal_crumbs((rehearsal.label, back), ("Attach evidence", None)),
            "cancel_url": back,
            "summary": [
                ("Rehearsal", f"{rehearsal.label} · {rehearsal.title}"),
                ("Record revision", rehearsal.revision),
                ("Size limit", size_text(max_bytes())),
            ],
        },
        status=form_status(request, form),
    )


@login_required
@require_http_methods(["GET"])
def rehearsal_file(request, pk):
    from analytical.rawdata import verified_content

    read_access(request.user)  # before the lookup: a refusal must not reveal existence
    stored = get_object_or_404(RehearsalFile, pk=pk)
    try:
        data = verified_content(stored)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("validation:rehearsal_detail", pk=stored.rehearsal_id)
    name = "".join(
        c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in stored.filename
    )
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def rehearsal_accept(request, pk):
    require_role(request.user, services.KEEPER)
    rehearsal = _rehearsal(pk)
    detail = rehearsal_url(rehearsal)
    files = _files(rehearsal)
    form = SigningForm(request.POST or None, initial={"expected_revision": rehearsal.revision})
    return sign_page(
        request,
        form,
        title="Accept rehearsal",
        identifier=rehearsal.label,
        meaning="accepted",
        meaning_text="You accept this record as a true account of the rehearsal, with the "
        "outcome it states and the evidence attached.",
        button="Sign and accept",
        facts=[
            *_rehearsal_facts(rehearsal),
            (
                "Evidence files",
                "; ".join(f"{f.filename} ({f.description}, SHA-256 {f.sha256})" for f in files)
                or "None",
            ),
        ],
        revision=rehearsal.revision,
        cancel_url=detail,
        run=lambda d: services.accept_rehearsal(
            actor=request.user,
            pin=d["pin"],
            rehearsal=rehearsal,
            expected_revision=d["expected_revision"],
            reason=d["reason"],
        ),
        success=f"{rehearsal.label} accepted.",
        success_url=detail,
        denial=services.rehearsal_denial(request.user, rehearsal, accept=True),
        crumbs=_rehearsal_crumbs((rehearsal.label, detail), ("Accept", None)),
    )


@login_required
@require_http_methods(["GET", "POST"])
def rehearsal_withdraw(request, pk):
    require_role(request.user, *services.REHEARSAL_RECORDERS)
    rehearsal = _rehearsal(pk)
    detail = rehearsal_url(rehearsal)
    return _withdraw_page(
        request,
        rehearsal,
        service=lambda **kw: services.withdraw_rehearsal(rehearsal=rehearsal, **kw),
        detail=detail,
        crumbs=_rehearsal_crumbs((rehearsal.label, detail), ("Withdraw", None)),
        noun="rehearsal",
        state_refusal=services.rehearsal_state_refusal(rehearsal, accept=False),
        refusal=services.rehearsal_person_refusal(request.user, rehearsal, accept=False),
    )
