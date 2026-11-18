"""PDF rendering with WeasyPrint: the issued certificate (from its frozen snapshot only) and,
through ``write_pdf``, the printed copy of a lot record export (reporting/lot_record.py).

An issued certificate is written as tagged PDF/A-3a, identified as PDF/UA-1 too, with its
certificate data (reporting/certificate_data.py) embedded as an associated file whose
relationship is Data: the archival copy, its accessible structure and its machine-readable
content in one file. The identification is what the file declares; whether a given output
conforms is checked with a validator, not asserted here.

The same certificate partial serves the screen preview and the PDF, so the two cannot drift.
No live record is read. The renderer loads exactly two kinds of resource, served from this
module under private URL schemes: the vendored Archivo font (``certfont:``) and the status
glyphs (``certicon:``), standalone SVGs cut from the Bootstrap Icons sprite. Every other URL
(network, file, data) is refused. A missing font fails the render instead of printing the
certificate in a fallback face. Issued PDFs are stored bytes: nothing here runs again for them.
"""

import logging
import re
from datetime import datetime
from xml.etree import ElementTree

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


# The archival variant of an issued certificate and how its stored versions name it.
PDF_VARIANT = "pdf/a-3a"
PDF_FORMAT = "PDF/A-3a, PDF/UA-1"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
# PDF/UA-1 identification, and the PDF/A extension schema that declares its namespace (PDF/A-3
# accepts XMP properties outside its predefined schemas only when they are declared).
UA_XMP = (
    f'<rdf:Description xmlns:rdf="{RDF}" xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/" '
    'rdf:about="" pdfuaid:part="1"/>'
)
UA_EXTENSION_XMP = f"""<rdf:Description xmlns:rdf="{RDF}" rdf:about=""
 xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
 xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"
 xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
<pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">
<pdfaSchema:schema>PDF/UA Universal Accessibility Schema</pdfaSchema:schema>
<pdfaSchema:namespaceURI>http://www.aiim.org/pdfua/ns/id/</pdfaSchema:namespaceURI>
<pdfaSchema:prefix>pdfuaid</pdfaSchema:prefix>
<pdfaSchema:property><rdf:Seq><rdf:li rdf:parseType="Resource">
<pdfaProperty:name>part</pdfaProperty:name>
<pdfaProperty:valueType>Integer</pdfaProperty:valueType>
<pdfaProperty:category>internal</pdfaProperty:category>
<pdfaProperty:description>Part of ISO 14289 the file declares</pdfaProperty:description>
</rdf:li></rdf:Seq></pdfaSchema:property>
</rdf:li></rdf:Bag></pdfaExtension:schemas>
</rdf:Description>"""
for _prefix, _uri in (
    ("pdfaExtension", "http://www.aiim.org/pdfa/ns/extension/"),
    ("pdfaSchema", "http://www.aiim.org/pdfa/ns/schema#"),
    ("pdfaProperty", "http://www.aiim.org/pdfa/ns/property#"),
):
    ElementTree.register_namespace(_prefix, _uri)


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


def _declare_ua(metadata):
    """Add the PDF/UA-1 identification to the one XMP packet WeasyPrint writes for PDF/A-3a.

    WeasyPrint identifies one variant per file; its extra XMP fragments are appended after the
    packet's RDF, where readers do not look, so the two descriptions join the RDF itself.
    """
    generate = metadata.generate_rdf_metadata

    def generate_with_ua(variant, version, conformance):
        rdf = ElementTree.fromstring(generate(variant, version, conformance))
        rdf.append(ElementTree.fromstring(UA_XMP))
        rdf.append(ElementTree.fromstring(UA_EXTENSION_XMP))
        return ElementTree.tostring(rdf, encoding="utf-8")

    metadata.generate_rdf_metadata = generate_with_ua


def write_archival_pdf(html, *, data, issued_at):
    """``(pdf bytes, URLs served)``: tagged PDF/A-3a declaring PDF/UA-1, with ``data`` (the
    certificate data) embedded as its associated file, dated ``issued_at``."""
    from weasyprint import HTML, Attachment
    from weasyprint.text.fonts import FontConfiguration

    from . import certificate_data

    served = set()
    fonts = FontConfiguration()
    document = HTML(string=html, base_url=None, url_fetcher=_fetcher(resources(), served)).render(
        font_config=fonts, pdf_variant=PDF_VARIANT
    )
    _declare_ua(document.metadata)
    attachment = Attachment(
        string=data,
        name=certificate_data.FILENAME,
        description=certificate_data.DESCRIPTION,
        created=issued_at,
        modified=issued_at,
        relationship="Data",
    )
    pdf = document.write_pdf(pdf_variant=PDF_VARIANT, attachments=[attachment])
    return pdf, served


def render_certificate(snapshot, *, data, synthetic_notice=False):
    """The issued certificate: its frozen ``snapshot`` printed, and its certificate ``data``
    (the stored bytes) embedded."""
    try:
        html = render_to_string(
            "reporting/pdf/certificate.html",
            {"snapshot": snapshot, "synthetic_notice": synthetic_notice},
        )
        issued_at = datetime.fromisoformat(snapshot["report"]["issued_at"])
        pdf, served = write_archival_pdf(html, data=data, issued_at=issued_at)
        if FONT_URL not in served:
            raise RenderError("The certificate font was not loaded.")
    except Exception as exc:  # renderer and font failures must roll the release back
        logger.exception("Certificate rendering failed")
        raise RenderError(str(exc) or exc.__class__.__name__) from exc
    if not pdf.startswith(b"%PDF-"):
        raise RenderError("The renderer did not produce a PDF.")
    return pdf
