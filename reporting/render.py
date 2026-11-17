"""PDF rendering with WeasyPrint: the issued certificate (from its frozen snapshot only) and,
through ``write_pdf``, the printed copy of a lot record export (reporting/lot_record.py).

The same certificate partial serves the screen preview and the PDF, so the two cannot drift.
No live record is read. The renderer loads exactly two kinds of resource, served from this
module under private URL schemes: the vendored Archivo font (``certfont:``) and the status
glyphs (``certicon:``), standalone SVGs cut from the Bootstrap Icons sprite. Every other URL
(network, file, data) is refused. A missing font fails the render instead of printing the
certificate in a fallback face. Issued PDFs are stored bytes: nothing here runs again for them.
"""

import logging
import re

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

FONT_FILE = "archivo-latin-wdth-wght.woff2"
FONT_URL = f"certfont:{FONT_FILE}"
ICON_URL = "certicon:"
# The tones the certificate prints, and their glyphs (the Line status icons).
TONE_ICONS = {
    "success": "check-circle-fill",
    "warning": "exclamation-triangle-fill",
    "danger": "x-circle-fill",
}


class RenderError(Exception):
    """The certificate could not be rendered; issuance must roll back."""


def _font_path():
    return settings.BASE_DIR / "static" / "vendor" / "archivo-2.001" / FONT_FILE


def _icon(sprite, name):
    """One sprite symbol as a standalone SVG drawn in black (print-safe)."""
    match = re.search(
        rf'<symbol id="i-{re.escape(name)}" viewBox="([^"]+)">(.*?)</symbol>', sprite, re.S
    )
    if not match:
        raise RenderError(f"The status glyph {name} is not in the icon sprite.")
    view_box, body = match.groups()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" fill="#000">{body}</svg>'
    ).encode()


def resources():
    """{url: (bytes, content type)}: the only resources a certificate may load."""
    try:
        font = _font_path().read_bytes()
        sprite = (settings.BASE_DIR / "static" / "img" / "icons.svg").read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError("The certificate font or status glyphs are not installed.") from exc
    served = {FONT_URL: (font, "font/woff2")}
    for name in TONE_ICONS.values():
        served[f"{ICON_URL}{name}"] = (_icon(sprite, name), "image/svg+xml")
    return served


def _fetcher(allowed, served):
    """A WeasyPrint URL fetcher that serves ``allowed`` by exact URL and refuses everything else.

    A refusal raised from ``fetch`` is caught by the renderer, which logs it and omits the
    resource instead of loading it.
    """
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    class CertificateFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if url not in allowed:
                raise ValueError(f"Certificates may not load external resources: {url}")
            data, content_type = allowed[url]
            served.add(url)
            return URLFetcherResponse(url, data, {"Content-Type": content_type})

    return CertificateFetcher(allowed_protocols=())


def write_pdf(html):
    """``(pdf bytes, URLs served)`` for certificate markup, with only the allowed resources."""
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    served = set()
    fonts = FontConfiguration()  # loads the @font-face rule of the inline stylesheet
    data = HTML(string=html, base_url=None, url_fetcher=_fetcher(resources(), served)).write_pdf(
        font_config=fonts
    )
    return data, served


def render_certificate(snapshot, *, synthetic_notice=False):
    try:
        html = render_to_string(
            "reporting/pdf/certificate.html",
            {"snapshot": snapshot, "synthetic_notice": synthetic_notice},
        )
        data, served = write_pdf(html)
        if FONT_URL not in served:
            raise RenderError("The certificate font was not loaded.")
    except Exception as exc:  # renderer and font failures must roll the release back
        logger.exception("Certificate rendering failed")
        raise RenderError(str(exc) or exc.__class__.__name__) from exc
    if not data.startswith(b"%PDF-"):
        raise RenderError("The renderer did not produce a PDF.")
    return data
