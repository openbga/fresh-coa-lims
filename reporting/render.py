"""Issued-PDF rendering with WeasyPrint from the frozen snapshot only.

The same certificate partial serves the screen preview and the PDF, so the two cannot drift.
No live record is read, and the renderer may not fetch any URL.
"""

import logging

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class RenderError(Exception):
    """The certificate could not be rendered; issuance must roll back."""


def _deny_fetcher():
    """A WeasyPrint URL fetcher that refuses every URL (network, file and data alike).

    WeasyPrint 70 requires a `URLFetcher` instance; a refusal raised from `fetch` is caught by
    the renderer, which logs it and omits the resource instead of loading it.
    """
    from weasyprint.urls import URLFetcher

    class DenyFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            raise ValueError(f"Certificates may not load external resources: {url}")

    return DenyFetcher(allowed_protocols=())


def render_certificate(snapshot, *, synthetic_notice=False):
    try:
        from weasyprint import HTML

        html = render_to_string(
            "reporting/pdf/certificate.html",
            {"snapshot": snapshot, "synthetic_notice": synthetic_notice},
        )
        data = HTML(string=html, url_fetcher=_deny_fetcher()).write_pdf()
    except Exception as exc:  # renderer and font failures must roll the release back
        logger.exception("Certificate rendering failed")
        raise RenderError(str(exc) or exc.__class__.__name__) from exc
    if not data.startswith(b"%PDF-"):
        raise RenderError("The renderer did not produce a PDF.")
    return data
