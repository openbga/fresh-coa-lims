"""Planning pages (HTTP only; the rules are in ``planning.services``)."""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Max, Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from analytical.models import AnalyticalTest
from analytical.views import mark_supplier_results
from core import grids
from core.exports import csv_stream
from core.grids import Column
from core.people import person
from core.services import require_role
from laboratory.eligibility import equipment_queryset, equipment_status
from laboratory.models import Equipment
from laboratory.ui import cell, day, section_tabs, status

from . import figures as figure_rules
from . import reminders as reminder_list
from . import services
from .forms import (
    DEFAULT_WINDOW,
    FigureFilterForm,
    PeriodForm,
    PlanForm,
    ReminderFilterForm,
    ReviewedFilterForm,
    TakeForm,
    TargetForm,
    WorkFilterForm,
)
from .models import Plan, Target, Work

TITLE = "Planning"
WORK_LIST = "planning:work_list"


def access(user):
    require_role(user, *services.READ_ROLES)


def roles(user):
    return set(user.groups.values_list("name", flat=True))


def planning_tabs(request):
    """The section's tabs, without the figures for a reader who may not open them."""
    tabs = section_tabs(request)
    if can_read_figures(request.user):
        return tabs
    hidden = {reverse("planning:figures"), reverse("planning:reviewed")}
    return [tab for tab in tabs if tab["url"] not in hidden]


def crumbs(*pairs):
    return [(TITLE, reverse(WORK_LIST)), *pairs]


def plan_of(test):
    """The test's plan, or None when nobody has planned it yet."""
    try:
        return test.plan
    except Plan.DoesNotExist:
        return None


# --- Work list -------------------------------------------------------------------------------

SORTS = {
    "due": [F("due").asc(nulls_last=True), "created_at"],
    "-due": [F("due").desc(nulls_last=True), "-created_at"],
    "test": ["pk"],
    "-test": ["-pk"],
    "assigned": ["created_at"],
    "-assigned": ["-created_at"],
}


def work_columns(can_plan):
    columns = [
        Column("test", "Test", asc="test", desc="-test", locked=True),
        Column("due", "Due", asc="due", desc="-due"),
        Column("status", "Status"),
        Column("lot", "Lot"),
        Column("code", "Code", priority="low"),
        Column("analyst", "Analyst"),
        Column("instrument", "Instrument", priority="medium"),
        Column("assigned", "Assigned", asc="assigned", desc="-assigned", priority="low"),
    ]
    if can_plan:
        columns.insert(0, Column("select", "Select", locked=True, label_hidden=True))
    return columns


def planned_instruments():
    """Equipment some open test is planned on: the choices of the Instrument filter."""
    ids = Plan.objects.filter(test__state__in=services.PLANNABLE, equipment__isnull=False).values(
        "equipment"
    )
    return Equipment.objects.filter(pk__in=ids).order_by("asset_id")


def filter_work(tests, data, user, today):
    query = data.get("q", "").strip()
    if query:
        tests = tests.filter(
            Q(lot__number__icontains=query)
            | Q(sample__reference__icontains=query)
            | Q(pull__study__identifier__icontains=query)
            | Q(pull__study__lot__number__icontains=query)
            | Q(reassessment__lot__number__icontains=query)
            | Q(test_code__icontains=query)
        )
    if data.get("due"):
        tests = services.due_filter(tests, data["due"], today)
    match data.get("analyst"):
        case "me":
            tests = tests.filter(plan__analyst=user)
        case "none":
            tests = tests.filter(Q(plan__isnull=True) | Q(plan__analyst__isnull=True))
        case "" | None:
            pass
        case analyst:
            tests = tests.filter(plan__analyst_id=int(analyst))
    match data.get("equipment"):
        case "none":
            tests = tests.filter(Q(plan__isnull=True) | Q(plan__equipment__isnull=True))
        case "" | None:
            pass
        case equipment:
            tests = tests.filter(plan__equipment_id=int(equipment))
    if data.get("state"):
        tests = tests.filter(state=data["state"])
    if data.get("work"):
        tests = tests.filter(services.WORK_SUBJECT[data["work"]])
    return tests


@login_required
@require_http_methods(["GET"])
def work_list(request):
    access(request.user)
    today = timezone.localdate()
    user_roles = roles(request.user)
    can_plan = bool(user_roles & set(services.PLANNERS))
    can_take = bool(user_roles & set(services.TAKERS))
    filters = WorkFilterForm(
        request.GET if request.GET else None, instruments=planned_instruments()
    )
    data = filters.cleaned_data if filters.is_bound and filters.is_valid() else {}
    invalid = filters.is_bound and not filters.is_valid()
    tests = filter_work(services.open_work(), data, request.user, today)
    sort = request.GET.get("sort", "due")
    if sort not in SORTS:
        sort = "due"
    page = grids.paginate(request, tests.order_by(*SORTS[sort], "pk"))
    mark_supplier_results(page)
    rows = []
    for test in page:
        plan = plan_of(test)
        label, tone = services.due_status(test.due, today)
        take = None
        if can_take and test.state == "open" and (plan is None or plan.analyst_id is None):
            take = TakeForm(
                auto_id=False,
                initial={
                    "expected_revision": plan.revision if plan else 0,
                    "next": request.get_full_path(),
                },
            )
        rows.append(
            {
                "test": test,
                "due": test.due,
                "due_label": label,
                "due_tone": tone,
                "from_target": test.due is not None and (plan is None or plan.due_on is None),
                "analyst": plan.analyst if plan else None,
                "equipment": plan.equipment if plan else None,
                "take": take,
            }
        )
    filtered = bool(data) and any(data.values())
    return render(
        request,
        "planning/work_list.html",
        {
            "page_title": "Work list",
            "tabs": planning_tabs(request),
            "columns": work_columns(can_plan),
            "sort": sort,
            "page_obj": page,
            "rows": rows,
            "filters": filters,
            "query": data.get("q", "") if data else request.GET.get("q", ""),
            "filter_fields": [field for field in filters if field.name not in ("q",)],
            "inline_fields": [filters["due"], filters["analyst"], filters["state"]],
            "more_fields": [filters["equipment"], filters["work"]],
            "filtered": filtered or invalid,
            "invalid": filters.errors if invalid else None,
            "can_plan": can_plan,
            "today": today,
        },
    )


# --- Plan ------------------------------------------------------------------------------------


def _selected_ids(values):
    ids = []
    for value in values:
        try:
            ids.append(int(value))
        except TypeError, ValueError:
            continue
    return sorted(set(ids))


def _plan_rows(tests, today):
    """The selected tests as the plan page shows them: due, analyst and instrument now."""
    annotated = services.with_due(
        AnalyticalTest.objects.filter(pk__in=[t.pk for t in tests]).select_related(
            "lot",
            "sample",
            "pull__study__lot",
            "pull__timepoint__condition",
            "reassessment__lot",
            "plan__analyst",
            "plan__equipment",
        )
    ).order_by("pk")
    rows = []
    for test in annotated:
        plan = plan_of(test)
        label, tone = services.due_status(test.due, today)
        rows.append(
            {
                "test": test,
                "due": test.due,
                "due_label": label,
                "due_tone": tone,
                "analyst": plan.analyst if plan else None,
                "equipment": plan.equipment if plan else None,
            }
        )
    return rows


@login_required
@require_http_methods(["GET", "POST"])
def plan(request):
    access(request.user)
    require_role(request.user, *services.PLANNERS)
    today = timezone.localdate()
    cancel_url = reverse(WORK_LIST)
    tests, refusal = [], ""
    if request.method == "POST":
        form = PlanForm(request.POST)
        try:
            selected = services.parse_token(request.POST.get("token", ""))
            tests = list(AnalyticalTest.objects.filter(pk__in=selected).order_by("pk"))
        except ValidationError as exc:
            refusal = "; ".join(exc.messages)
        if form.is_valid() and not refusal:
            try:
                changed = services.plan_tests(
                    actor=request.user,
                    token=form.cleaned_data["token"],
                    reason=form.cleaned_data["reason"],
                    **form.changes(),
                )
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
            else:
                count = len(changed)
                messages.success(request, f"Planned {count} test{'s' if count != 1 else ''}.")
                return redirect(cancel_url)
    else:
        ids = _selected_ids(request.GET.getlist("test"))
        try:
            if not ids:
                raise ValidationError("Select the tests to plan on the work list first.")
            if len(ids) > services.MAX_SELECTED:
                raise ValidationError(f"Plan at most {services.MAX_SELECTED} tests at once.")
            tests = services.plannable(ids)
        except ValidationError as exc:
            refusal = "; ".join(exc.messages)
        form = PlanForm(initial={"token": services.selection_token(tests)} if tests else None)
    count = len(tests)
    return render(
        request,
        "planning/plan.html",
        {
            "page_title": "Plan selected tests",
            "crumbs": crumbs(("Plan selected tests", "")),
            "form": form,
            "rows": _plan_rows(tests, today) if tests and not refusal else [],
            "count": count,
            "refusal": refusal,
            "cancel_url": cancel_url,
        },
        status=422 if request.method == "POST" else (409 if refusal else 200),
    )


@login_required
@require_POST
def take(request, pk):
    access(request.user)
    require_role(request.user, *services.TAKERS)
    test = get_object_or_404(AnalyticalTest, pk=pk)
    form = TakeForm(request.POST)
    back = reverse(WORK_LIST)
    if form.is_valid():
        target = form.cleaned_data["next"]
        if target.startswith(back) and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            back = target
        try:
            services.take_test(
                actor=request.user,
                test=test,
                expected_revision=form.cleaned_data["expected_revision"],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, f"{test.label} is assigned to you.")
    else:
        messages.error(request, "The page was not readable. Open the work list again.")
    return redirect(back)


# --- Workload --------------------------------------------------------------------------------


def _work_url(**params):
    query = "&".join(f"{key}={value}" for key, value in params.items() if value != "")
    return reverse(WORK_LIST) + (f"?{query}" if query else "")


def _counts(today):
    """Aggregates matching the work list's due filters (services.due_filter)."""
    soon = today + timedelta(days=services.SOON_DAYS)
    return {
        "total": Count("pk"),
        "overdue": Count("pk", filter=Q(due__lt=today)),
        "today": Count("pk", filter=Q(due=today)),
        "soon": Count("pk", filter=Q(due__gt=today, due__lte=soon)),
        "none": Count("pk", filter=Q(due__isnull=True)),
    }


@login_required
@require_http_methods(["GET"])
def workload(request):
    access(request.user)
    today = timezone.localdate()
    work = services.open_work()
    open_tests = work.filter(state=AnalyticalTest.State.OPEN)
    # Each count is the count of the list it opens (the same filters as the work list).
    queues = [
        (label, services.due_filter(work, key, today).count(), tone, _work_url(due=key))
        for key, label, tone in (
            ("overdue", "Overdue", "danger"),
            ("today", "Due today", "warning"),
            ("week", f"Due in the next {services.SOON_DAYS} days", "warning"),
            ("none", "No due date", "info"),
        )
    ]
    queues += [
        (
            "Open, no analyst assigned",
            open_tests.filter(Q(plan__isnull=True) | Q(plan__analyst__isnull=True)).count(),
            "info",
            _work_url(analyst="none", state="open"),
        ),
        (
            "Awaiting review",
            work.filter(state=AnalyticalTest.State.SUBMITTED).count(),
            "info",
            _work_url(state="submitted"),
        ),
    ]
    by_analyst = {
        row["plan__analyst"]: row
        for row in open_tests.values("plan__analyst").annotate(**_counts(today))
    }
    analyst_rows = []
    for user in services.assignable(by_analyst):
        counts = by_analyst.get(user.pk, {})
        analyst_rows.append(_load_row(person(user), str(user.pk), counts))
    analyst_rows.append(_load_row("Not assigned", "none", by_analyst.get(None, {})))
    by_instrument = {
        row["plan__equipment"]: row
        for row in open_tests.filter(plan__equipment__isnull=False)
        .values("plan__equipment")
        .annotate(**_counts(today), latest=Max("due"))
    }
    instrument_rows = []
    equipment = equipment_queryset(today).filter(pk__in=by_instrument).order_by("asset_id")
    for item in equipment:
        counts = by_instrument[item.pk]
        label, tone, key = equipment_status(item, today)
        latest = counts["latest"]
        check = ""
        if key in ("out_of_service", "unfit", "overdue"):
            check = (label, "danger" if key != "unfit" else "warning")
        elif latest and item.last_due and item.last_due < latest:
            check = ("Calibration runs out before planned work", "warning")
        instrument_rows.append(
            {
                "asset": cell(
                    item.asset_id,
                    reverse("laboratory:equipment_detail", args=[item.pk]),
                    sub=item.description,
                ),
                "fitness": status(label, tone),
                "calibration_due": day(item.last_due),
                "latest": day(latest),
                "check": check,
                **_count_links(str(item.pk), counts, key="equipment"),
            }
        )
    return render(
        request,
        "planning/workload.html",
        {
            "page_title": "Workload",
            "tabs": planning_tabs(request),
            "queues": [
                {"label": label, "count": count, "tone": tone if count else "neutral", "href": href}
                for label, count, tone, href in queues
            ],
            "analyst_rows": analyst_rows,
            "instrument_rows": instrument_rows,
            "soon_days": services.SOON_DAYS,
        },
    )


def _count_links(value, counts, key="analyst"):
    def link(due=""):
        return _work_url(**{key: value, "state": "open", "due": due})

    return {
        "total": (counts.get("total", 0), link()),
        "overdue": (counts.get("overdue", 0), link("overdue")),
        "today": (counts.get("today", 0), link("today")),
        "soon": (counts.get("soon", 0), link("week")),
        "none": (counts.get("none", 0), link("none")),
    }


def _load_row(name, value, counts):
    return {"name": name, **_count_links(value, counts)}


# --- Reminders -------------------------------------------------------------------------------

REMINDER_COLUMNS = (
    Column("reminder", "Reminder", locked=True),
    Column("date", "Date"),
    Column("kind", "Kind"),
    Column("status", "Status"),
)


@login_required
@require_http_methods(["GET"])
def reminders(request):
    access(request.user)
    today = timezone.localdate()
    filters = ReminderFilterForm(request.GET if request.GET else None)
    data = filters.cleaned_data if filters.is_bound and filters.is_valid() else {}
    invalid = filters.is_bound and not filters.is_valid()
    within = data.get("within") or DEFAULT_WINDOW
    kind = data.get("kind", "")
    found = reminder_list.reminders(today, within, kind)
    page = grids.paginate(request, found)
    expired = reminder_list.expired_reagents(today).count() if kind in ("", "reagent") else 0
    return render(
        request,
        "planning/reminders.html",
        {
            "page_title": "Reminders",
            "tabs": planning_tabs(request),
            "columns": REMINDER_COLUMNS,
            "page_obj": page,
            "filters": filters,
            "filtered": bool(kind) or within != DEFAULT_WINDOW or invalid,
            "invalid": filters.errors if invalid else None,
            "within": within,
            "until": today + timedelta(days=within),
            "today": today,
            "expired": expired,
        },
    )


# --- Turnaround targets ----------------------------------------------------------------------

TARGET_COLUMNS = (
    Column("set", "Set", locked=True),
    Column("work", "Work"),
    Column("target", "Target"),
    Column("by", "Set by"),
    Column("reason", "Reason", priority="low"),
)


@login_required
@require_http_methods(["GET"])
def targets(request):
    access(request.user)
    current = services.current_targets()
    history = grids.paginate(
        request, Target.objects.select_related("set_by").order_by("-set_at", "-id")
    )
    return render(
        request,
        "planning/targets.html",
        {
            "page_title": "Turnaround targets",
            "tabs": planning_tabs(request),
            "current": [(label, current[work]) for work, label in Work.choices],
            "columns": TARGET_COLUMNS,
            "page_obj": history,
            "can_change": bool(roles(request.user) & set(services.TARGET_SETTERS)),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def targets_change(request):
    access(request.user)
    require_role(request.user, *services.TARGET_SETTERS)
    current = services.current_targets()
    form = TargetForm(request.POST or None, current=current)
    if request.method == "POST" and form.is_valid():
        try:
            services.set_targets(
                actor=request.user,
                days=form.days(),
                expected=form.expected_targets(),
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "The turnaround targets are changed.")
            return redirect("planning:targets")
    return render(
        request,
        "planning/targets_change.html",
        {
            "page_title": "Change targets",
            "crumbs": crumbs(
                ("Turnaround targets", reverse("planning:targets")), ("Change targets", "")
            ),
            "form": form,
            "cancel_url": reverse("planning:targets"),
        },
        status=422 if request.method == "POST" else 200,
    )


# --- Figures ---------------------------------------------------------------------------------

REVIEWED = "planning:reviewed"


def period_query(request, today):
    """The page's query with the default period filled in when it names none, so the From and
    To fields show the dates the figures cover."""
    data = request.GET.copy()
    if not data.get("start") and not data.get("end"):
        start, end = figure_rules.default_period(today)
        data["start"], data["end"] = start.isoformat(), end.isoformat()
    return data


def access_figures(user):
    require_role(user, *services.FIGURE_READERS)


def can_read_figures(user):
    return bool(roles(user) & set(services.FIGURE_READERS))


def _reviewed_url(**params):
    query = urlencode({key: value for key, value in params.items() if value not in ("", None)})
    return reverse(REVIEWED) + (f"?{query}" if query else "")


# Each figure that counts tests, with the Reviewed tests filter that lists exactly those tests.
COUNTS = {
    "reviewed": {},
    "on_time": {"timeliness": figure_rules.ON_TIME},
    "late": {"timeliness": figure_rules.LATE},
    "no_due": {"timeliness": figure_rules.NO_DUE},
    "first_time": {"first_time": figure_rules.FIRST_TIME},
    "returned": {"first_time": figure_rules.RETURNED_KEY},
    "corrected": {"first_time": figure_rules.CORRECTED_KEY},
    "repeat": {"first_time": figure_rules.REPEAT_KEY},
    "oos": {"result": "oos"},
    "invalidated": {"result": "invalidated"},
}


def _links(figures, params):
    """{figure: (count, URL of the Reviewed tests list showing those tests)}."""
    return {key: (figures[key], _reviewed_url(**params, **extra)) for key, extra in COUNTS.items()}


def _percent(part, whole):
    value = figure_rules.share(part, whole)
    return "" if value is None else f"{value}%"


def _summary(figures, params):
    """The rows of the In the period table: (label, count, link, share in words)."""
    links = _links(figures, params)
    reviewed, with_due, oos = figures["reviewed"], figures["with_due"], figures["oos"]

    def of(key, whole, noun):
        return f"{_percent(figures[key], whole)} of {whole} {noun}" if whole else ""

    rows = [
        ("reviewed", "Reviewed", ""),
        ("on_time", "Reviewed on time", of("on_time", with_due, "with a due date")),
        ("late", "Reviewed late", of("late", with_due, "with a due date")),
        ("no_due", "No due date", ""),
        ("first_time", "Right first time", of("first_time", reviewed, "reviewed")),
        ("returned", "Returned for correction", ""),
        ("corrected", "A reading corrected", ""),
        ("repeat", "A repeat, or repeated", ""),
        ("oos", "Out of specification", ""),
        (
            "invalidated",
            "Invalidated after investigation",
            of("invalidated", oos, "out of specification"),
        ),
    ]
    return [
        {"label": label, "count": links[key][0], "href": links[key][1], "share": share}
        for key, label, share in rows
    ]


def _group_rows(rows, group, start, end, params):
    people = {}
    if group == "analyst":
        ids = [row["key"] for row in rows if row["key"] is not None]
        people = {user.pk: user for user in get_user_model().objects.filter(pk__in=ids)}
    shown = []
    for row in rows:
        key = row["key"]
        scope = dict(params)
        match group:
            case "work":
                name = figure_rules.WORK_LABELS.get(key, key)
                scope["work"] = key
            case "material" | "method":
                name = key if key else "—"
                scope[group] = key or ""
            case "analyst":
                name = person(people[key]) if key in people else "No analyst recorded"
                scope["analyst"] = key if key is not None else "none"
            case "month":
                first = timezone.localtime(key).date() if hasattr(key, "tzinfo") else key
                first = first.replace(day=1)
                last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                name = first.strftime("%B %Y")
                scope["start"] = max(start, first).isoformat()
                scope["end"] = min(end, last).isoformat()
        links = _links(row, scope)
        shown.append(
            {
                "name": name,
                "median": row["median"],
                "ninth": row["ninth"],
                "on_time_share": _percent(row["on_time"], row["with_due"]),
                "first_time_share": _percent(row["first_time"], row["reviewed"]),
                **links,
            }
        )
    return shown


@login_required
@require_http_methods(["GET"])
def figures(request):
    access_figures(request.user)
    today = timezone.localdate()
    form = FigureFilterForm(period_query(request, today))
    invalid = not form.is_valid()
    data = form.cleaned_data if form.is_bound and not invalid else {}
    start, end = form.period(today)
    group = data.get("by") or "work"
    work = data.get("work") or ""
    params = {"start": start.isoformat(), "end": end.isoformat(), "work": work}
    totals, summary, group_rows = None, [], []
    if not invalid:
        tests = figure_rules.filter_reviewed(
            figure_rules.reviewed_tests(start, end), {"work": work}
        )
        rows = figure_rules.rows_of(tests, group)
        totals = figure_rules.measure(rows)
        if totals["reviewed"]:
            summary = _summary(totals, params)
            group_rows = _group_rows(figure_rules.grouped(rows, group), group, start, end, params)
    default_start, default_end = figure_rules.default_period(today)
    return render(
        request,
        "planning/figures.html",
        {
            "page_title": "Figures",
            "tabs": planning_tabs(request),
            "filters": form,
            "inline_fields": [form["start"], form["end"], form["by"]],
            "more_fields": [form["work"]],
            "active": bool(work) or group != "work" or (start, end) != (default_start, default_end),
            "invalid": form.errors if invalid else None,
            "start": start,
            "end": end,
            "totals": totals,
            "summary": summary,
            "on_time_share": _percent(totals["on_time"], totals["with_due"]) if summary else "",
            "first_time_share": _percent(totals["first_time"], totals["reviewed"])
            if summary
            else "",
            "group_label": dict(figure_rules.GROUPS)[group],
            "group_title": "By " + dict(figure_rules.GROUPS)[group].lower(),
            "group_rows": group_rows,
            "list_url": _reviewed_url(**params),
        },
    )


REVIEWED_SORTS = {
    "-reviewed": ["-reviewed_at"],
    "reviewed": ["reviewed_at"],
    "-turnaround": [F("turnaround").desc(nulls_last=True), "-reviewed_at"],
    "turnaround": [F("turnaround").asc(nulls_last=True), "reviewed_at"],
    "test": ["pk"],
    "-test": ["-pk"],
}

REVIEWED_COLUMNS = (
    Column("test", "Test", asc="test", desc="-test", locked=True),
    Column("reviewed", "Reviewed", asc="reviewed", desc="-reviewed"),
    Column("turnaround", "Turnaround", asc="turnaround", desc="-turnaround"),
    Column("due", "Due date"),
    Column("first_time", "First time"),
    Column("lot", "Lot"),
    Column("material", "Material", priority="low"),
    Column("method", "Method", priority="medium"),
    Column("analyst", "Analyst"),
    Column("result", "Result", priority="low"),
)


def search_reviewed(tests, query):
    if not query:
        return tests
    return tests.filter(
        Q(lot__number__icontains=query)
        | Q(sample__reference__icontains=query)
        | Q(pull__study__identifier__icontains=query)
        | Q(pull__study__lot__number__icontains=query)
        | Q(reassessment__lot__number__icontains=query)
        | Q(test_code__icontains=query)
        | Q(material__icontains=query)
    )


def _days(n):
    return f"{n} day{'s' if n != 1 else ''}"


def _timeliness(test):
    """(label, tone) of how a reviewed test kept its due date."""
    if test.due is None:
        return "No due date", "neutral"
    late = (test.reviewed_on - test.due).days
    if late > 0:
        return f"Late by {_days(late)}", "danger"
    return "On time", "success"


def _first_time(test, repeated_by):
    """What kept a reviewed test from being right first time, in words ([] when it was)."""
    reasons = []
    if test.returns:
        reasons.append("Returned" if test.returns == 1 else f"Returned {test.returns} times")
    if test.corrections:
        reasons.append(
            "1 reading corrected"
            if test.corrections == 1
            else f"{test.corrections} readings corrected"
        )
    if test.is_repeat:
        reasons.append(f"{test.get_kind_display()} of T-{test.parent_id}")
    if test.pk in repeated_by:
        reasons.append("Repeated by " + ", ".join(f"T-{pk}" for pk in repeated_by[test.pk]))
    elif test.repeated:
        reasons.append("Repeated")
    return reasons


def _repeated_by(tests):
    found = {}
    children = AnalyticalTest.objects.filter(
        parent_id__in=[t.pk for t in tests], kind__in=figure_rules.REPEAT_KINDS
    ).order_by("pk")
    for parent, child in children.values_list("parent_id", "pk"):
        found.setdefault(parent, []).append(child)
    return found


CSV_HEADER = [
    "Test",
    "Test code",
    "Kind",
    "Work",
    "Lot",
    "Material",
    "Method",
    "Method revision",
    "Analyst",
    "Assigned on",
    "Due on",
    "Due from",
    "Reviewed at",
    "Reviewed on",
    "Turnaround days",
    "Due date kept",
    "Returns",
    "Corrected readings",
    "Repeat of",
    "Repeated by",
    "Right first time",
    "Conforms",
    "Invalidated after investigation",
]


def _csv_lines(tests):
    """The CSV rows of ``tests``, read in chunks so a long period is never held at once."""
    yield CSV_HEADER
    timeliness = dict(figure_rules.TIMELINESS)
    for chunk in _chunks(tests, 500):
        repeated_by = _repeated_by(chunk)
        for test in chunk:
            plan = plan_of(test)
            due_from = "planner" if plan and plan.due_on else ("target" if test.due else "")
            yield [
                test.label,
                test.test_code,
                test.get_kind_display(),
                figure_rules.WORK_LABELS.get(test.work, test.work),
                test.source_lot.number,
                test.material,
                test.method,
                test.requirement.get("method", {}).get("revision", ""),
                test.submitted_by.get_username() if test.submitted_by else "",
                test.assigned_on.isoformat(),
                test.due.isoformat() if test.due else "",
                due_from,
                timezone.localtime(test.reviewed_at).isoformat(),
                test.reviewed_on.isoformat(),
                test.turnaround,
                timeliness[test.timeliness],
                test.returns,
                test.corrections,
                f"T-{test.parent_id}" if test.is_repeat else "",
                " ".join(f"T-{pk}" for pk in repeated_by.get(test.pk, [])),
                "yes" if test.first_time else "no",
                {True: "yes", False: "no"}.get(test.conforms, ""),
                "yes" if test.invalidated else "no",
            ]


def _csv(tests, start, end):
    response = StreamingHttpResponse(
        csv_stream(_csv_lines(tests)), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="reviewed-tests-{start.isoformat()}-{end.isoformat()}.csv"'
    )
    return response


def _chunks(queryset, size):
    chunk = []
    for item in queryset.iterator(chunk_size=size):
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


@login_required
@require_http_methods(["GET"])
def reviewed(request):
    access_figures(request.user)
    today = timezone.localdate()
    query = period_query(request, today)
    period = PeriodForm(query)
    start, end = period.period(today)
    in_period = figure_rules.reviewed_tests(start, end)
    options = figure_rules.filter_options(in_period) if period.is_valid() else None
    form = ReviewedFilterForm(query, options=options)
    invalid = not form.is_valid()
    data = form.cleaned_data if not invalid else {}
    if invalid:
        tests = in_period.none()
    else:
        tests = figure_rules.filter_reviewed(in_period, data)
        tests = search_reviewed(tests, data.get("q", "").strip())
    sort = request.GET.get("sort", "-reviewed")
    if sort not in REVIEWED_SORTS:
        sort = "-reviewed"
    tests = tests.order_by(*REVIEWED_SORTS[sort], "pk")
    if request.GET.get("export") == "csv" and not invalid:
        return _csv(tests, start, end)
    page = grids.paginate(request, tests)
    repeated_by = _repeated_by(list(page))
    rows = []
    for test in page:
        plan = plan_of(test)
        label, tone = _timeliness(test)
        rows.append(
            {
                "test": test,
                "timeliness": label,
                "tone": tone,
                "from_target": test.due is not None and (plan is None or plan.due_on is None),
                "reasons": _first_time(test, repeated_by),
                "turnaround": _days(test.turnaround),
            }
        )
    default_start, default_end = figure_rules.default_period(today)
    others = {key: value for key, value in data.items() if key not in ("start", "end")}
    filtered = any(others.values()) or (start, end) != (default_start, default_end)
    return render(
        request,
        "planning/reviewed.html",
        {
            "page_title": "Reviewed tests",
            "tabs": planning_tabs(request),
            "columns": REVIEWED_COLUMNS,
            "sort": sort,
            "page_obj": page,
            "rows": rows,
            "filters": form,
            "query": data.get("q", "") if data else request.GET.get("q", ""),
            "inline_fields": [form["start"], form["end"], form["first_time"]],
            "more_fields": [
                form["timeliness"],
                form["work"],
                form["material"],
                form["method"],
                form["analyst"],
                form["result"],
            ],
            "more_open": any(
                data.get(key)
                for key in ("timeliness", "work", "material", "method", "analyst", "result")
            ),
            "filtered": filtered or invalid,
            "invalid": form.errors if invalid else None,
            "start": start,
            "end": end,
            "figures_url": reverse("planning:figures")
            + "?"
            + urlencode({"start": start.isoformat(), "end": end.isoformat()}),
        },
    )
