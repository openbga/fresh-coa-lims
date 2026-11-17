"""Per-user presentation preferences, stored on the server (lab workstations are shared).

Keys and the values they accept:
  grid:<grid>:v<version>  {"order": [column id, …], "hidden": [column id, …]}, static/js/grid.js
  page:<view name>        {"per_page": 25 | 50 | 100, "sort": "<-column>"}, the middleware below
                          (config/settings.py MIDDLEWARE, after authentication)
  nav.collapsed           true | false, static/js/sidebar.js
  pagedocs.open           true | false, the page documentation panel (pagedocs.js)
  pagedocs.width          PAGEDOCS_WIDTH pixels, the panel's width (pagedocs.js)
  whatsnew.seen           id of the newest changelog entry shown to the user ("2026-11-17-slug"),
                          set by the server when What's new is opened (whatsnew/catalogue.py)

Every value is checked when written and again when read: a value that no longer fits (an old
format, a column that was removed) is ignored and the page falls back to its defaults.
Presentation only: a preference never widens what a user may see.
"""

import json
import re

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST

from core.grids import PAGE_SIZES
from core.models import UserPreference

MAX_PREFERENCES = 300  # per user: grids and pages are a bounded set
MAX_BODY = 8_000  # bytes of one request
GRID_KEY = re.compile(r"^grid:[a-z0-9_.-]{1,80}:v\d{1,3}$")
PAGE_KEY = re.compile(r"^page:[a-z0-9_:-]{1,100}$")
COLUMN_ID = re.compile(r"^[a-z0-9_-]{1,40}$")
SORT = re.compile(r"^-?[a-z0-9_]{1,40}$")
ENTRY_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")  # a changelog.d/ entry
CLIENT_KEYS = re.compile(r"^(grid:|nav\.|pagedocs\.)")  # what the page hands to its scripts
# Settings the browser may write besides grid layouts (page size and sort are server-set).
CLIENT_SETTINGS = {"nav.collapsed", "pagedocs.open", "pagedocs.width"}
PAGEDOCS_WIDTH = range(280, 961)  # pagedocs.js MIN..LIMIT


def _columns(value):
    return (
        isinstance(value, list)
        and len(value) <= 60
        and all(isinstance(item, str) and COLUMN_ID.match(item) for item in value)
    )


def clean(key, value):
    """The value if it is valid for the key, else None."""
    if GRID_KEY.match(key):
        if isinstance(value, dict) and set(value) == {"order", "hidden"}:
            if _columns(value["order"]) and _columns(value["hidden"]):
                return value
        return None
    if PAGE_KEY.match(key):
        if not isinstance(value, dict) or not set(value) <= {"per_page", "sort"}:
            return None
        cleaned = {}
        if value.get("per_page") in PAGE_SIZES and not isinstance(value["per_page"], bool):
            cleaned["per_page"] = value["per_page"]
        if isinstance(value.get("sort"), str) and SORT.match(value["sort"]):
            cleaned["sort"] = value["sort"]
        return cleaned or None
    if key in ("nav.collapsed", "pagedocs.open"):
        return value if isinstance(value, bool) else None
    if key == "whatsnew.seen":
        valid = isinstance(value, str) and len(value) <= 120 and ENTRY_ID.match(value)
        return value if valid else None
    if key == "pagedocs.width":
        valid = isinstance(value, int) and not isinstance(value, bool) and value in PAGEDOCS_WIDTH
        return value if valid else None
    return None


def for_request(request):
    """All valid preferences of the signed-in user, read once per request (one indexed query).

    Read from the database rather than a session copy: two settings saved at the same moment
    (the panel's open state and width) would otherwise race to overwrite each other's copy, and
    another session of the same user sees a change on its next page.
    """
    if hasattr(request, "_vr_preferences"):
        return request._vr_preferences
    prefs = {}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        stored = UserPreference.objects.filter(user=user).values_list("key", "value")
        for key, value in stored:
            if (valid := clean(key, value)) is not None:
                prefs[key] = valid
    request._vr_preferences = prefs
    return prefs


def save(request, key, value):
    """Store (or, for None, remove) one preference of the signed-in user. Raises ValueError."""
    prefs = for_request(request)
    if value is None:
        UserPreference.objects.filter(user=request.user, key=key).delete()
        prefs.pop(key, None)
        return
    if clean(key, value) != value:
        raise ValueError(f"Not a valid value for {key!r}.")
    if prefs.get(key) == value:
        return
    exists = UserPreference.objects.filter(user=request.user, key=key).exists()
    if not exists and UserPreference.objects.filter(user=request.user).count() >= MAX_PREFERENCES:
        raise ValueError("Too many saved preferences.")
    UserPreference.objects.update_or_create(user=request.user, key=key, defaults={"value": value})
    prefs[key] = value


@login_required
@require_POST
def preference(request):  # core:preference, /preferences/ (static/js/preferences.js)
    """POST {"key": …, "value": …} (value null removes it): the signed-in user's own setting."""
    if len(request.body) > MAX_BODY:
        return HttpResponseBadRequest("Too large.", content_type="text/plain")
    try:
        data = json.loads(request.body)
        key, value = data["key"], data["value"]
        if not isinstance(key, str) or not (GRID_KEY.match(key) or key in CLIENT_SETTINGS):
            raise ValueError("Unknown preference.")
        save(request, key, value)
    except (ValueError, KeyError, TypeError) as error:
        return HttpResponseBadRequest(str(error), content_type="text/plain")
    return HttpResponse(status=204)


class GridPreferenceMiddleware:
    """Remember each user's page size and sort per list, and apply them when the URL has none.

    Lists follow the shared grid contract (core.grids): `per_page` and `sort` in the query string.
    A valid value in the URL is saved for this page; without one, the saved value is added to the
    request, so the view, its pagination and its links all see it. The view still validates both.
    """

    PARAMS = ("per_page", "sort")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        match = request.resolver_match
        if request.method != "GET" or user is None or not user.is_authenticated or match is None:
            return None
        key = f"page:{match.view_name}"
        if not PAGE_KEY.match(key):
            return None
        stored = for_request(request).get(key, {})
        given = {}
        if request.GET.get("per_page", "").isdigit() and int(request.GET["per_page"]) in PAGE_SIZES:
            given["per_page"] = int(request.GET["per_page"])
        if SORT.match(request.GET.get("sort", "")):
            given["sort"] = request.GET["sort"]
        if given and {**stored, **given} != stored:
            save(request, key, {**stored, **given})
        missing = {
            name: stored[name] for name in self.PARAMS if name in stored and name not in request.GET
        }
        if missing:
            params = request.GET.copy()
            for name, value in missing.items():
                params[name] = str(value)
            request.GET = params
            request.vr_saved_params = set(missing)  # links may leave these out (core.grids)
        return None
