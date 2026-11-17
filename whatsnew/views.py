from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from accounts.context_processors import account_navigation

from . import catalogue


@login_required
@require_GET
def index(request):  # whatsnew:index, /whats-new/
    """Every change, newest month first and by impact; opening it clears the unread indicator."""
    entries, errors = catalogue.load()
    before = catalogue.mark_seen(request, entries)
    groups = catalogue.shown_groups(entries, account_navigation(request), before)
    toc = [(g["group"].anchor, f"{g['group'].label} ({g['group'].count})") for g in groups]
    return render(
        request,
        "whatsnew/index.html",
        {
            "page_title": "What's new",
            "groups": groups,
            "errors": errors,
            "toc": toc if len(toc) >= 4 else [],
            "new_count": sum(
                item["new"] for g in groups for s in g["sections"] for item in s["items"]
            ),
        },
    )
