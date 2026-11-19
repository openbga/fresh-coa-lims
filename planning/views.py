"""Planning pages (HTTP only; the rules are in ``planning.services``)."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from analytical.models import AnalyticalTest
from analytical.views import mark_supplier_results
from core import grids
from core.grids import Column
from core.people import person
from core.services import require_role
from laboratory.eligibility import equipment_queryset, equipment_status
from laboratory.models import Equipment
from laboratory.ui import cell, day, section_tabs, status

from . import reminders as reminder_list
from . import services
from .forms import (
    DEFAULT_WINDOW,
    PlanForm,
    ReminderFilterForm,
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
            "tabs": section_tabs(request),
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
            "tabs": section_tabs(request),
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
            "tabs": section_tabs(request),
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
            "tabs": section_tabs(request),
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
