from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import Resolver404, resolve
from django.views.decorators.http import require_GET

from .docs import doc_for


def site_path(value):
    """The path of a same-site URL (query dropped); ``""`` for anything else."""
    parts = urlsplit(value or "")
    path = parts.path
    if parts.scheme or parts.netloc or not path.startswith("/") or "\\" in path:
        return ""
    return "" if path.startswith("//") else path


def url_name_for(path):
    """Resolve a site path to ``namespace:name``; ``""`` when it is not a named route."""
    path = site_path(path)
    if not path:
        return ""
    try:
        match = resolve(path)
    except Resolver404:
        return ""
    return match.view_name if match.url_name else ""


@require_GET
def page_doc(request):
    """Documentation for the page at ``?path=``: a panel fragment, or a full page without JS."""
    fragment = request.headers.get("X-Pagedocs") == "fragment"
    if fragment and not request.user.is_authenticated:
        return render(request, "pagedocs/denied.html", status=403)
    return _page_doc(request, fragment)


@login_required
def _full_page(request, context):
    return render(request, "pagedocs/page.html", context, status=context["status"])


def _page_doc(request, fragment):
    target = site_path(request.GET.get("path", ""))
    url_name = url_name_for(target)
    doc = doc_for(url_name) if url_name else None
    context = {
        "doc": doc,
        "url_name": url_name,
        "target": target if url_name else "",
        "status": 200 if doc else 404,
    }
    if not fragment:
        return _full_page(request, context)
    response = render(request, "pagedocs/fragment.html", context, status=context["status"])
    response["Cache-Control"] = "private, no-cache"
    return response
