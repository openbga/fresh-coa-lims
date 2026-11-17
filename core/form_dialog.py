"""Transport for the shared form dialog. Views keep every check: authorization, validation, CSRF.

A request from static/js/form-dialog.js carries X-VR-Form: 1. The browser would follow a redirect
before HTMX can see it, so a redirect answering such a request becomes a 204 that tells HTMX what
to do instead: load the next form into the dialog (HX-Location) when the destination is another
dialog form, else navigate the whole page there (HX-Redirect), which is what the full page does.
That includes the sign-in page after a session ends. Messages and cookies set by the view are
kept. Every other response passes unchanged.
"""

import json
from urllib.parse import urlsplit

from django.http import HttpResponse
from django.urls import Resolver404, resolve
from django.utils.cache import patch_vary_headers

from .form_surfaces import FORM_HEADER, FORM_SURFACES, is_dialog_request


def is_dialog_form(destination):
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return False
    try:
        return resolve(parsed.path).view_name in FORM_SURFACES
    except Resolver404:
        return False


class FormDialogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        patch_vary_headers(response, (FORM_HEADER,))
        if not is_dialog_request(request) or response.status_code not in (301, 302, 303):
            return response
        destination = response["Location"]
        result = HttpResponse(status=204, headers=dict(response.headers))
        result.cookies = response.cookies
        del result["Location"]
        if is_dialog_form(destination):
            result["HX-Location"] = json.dumps(
                {
                    "path": destination,
                    "target": "#vr-form-content",
                    "push": "false",
                    "headers": {FORM_HEADER: "1"},
                }
            )
        else:
            result["HX-Redirect"] = destination
        return result
