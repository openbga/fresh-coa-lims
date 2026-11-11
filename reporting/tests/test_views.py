"""HTTP behaviour: authorization, states, signing form, downloads."""

import re

import pytest
from django.urls import reverse

from core.models import AuditEvent, ElectronicSignature
from reporting import evidence as ev
from reporting import services
from reporting.models import Report, ReportVersion
from reporting.tests.conftest import PASSWORD, PIN, build_lot

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def login(client):
    def _login(name):
        assert client.login(username=name, password=PASSWORD)
        return client

    return _login


def sign_url(lot):
    digest = services.preview(lot)[1]
    return reverse("reporting:issue_sign", args=[lot.pk]) + f"?evidence={digest}", digest


def sign_payload(digest, **extra):
    data = {
        "evidence_hash": digest,
        "reason": "Customer shipment certificate",
        "remarks": "",
        "recipient": "Synthetic Customer A",
        "signature_username": "quality",
        "pin": PIN,
    }
    data.update(extra)
    return data


def issued(people, lot):
    return services.issue_report(
        actor=people["quality"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic Customer A",
        evidence_hash=services.preview(lot)[1],
        reason="Customer shipment certificate",
    )


def test_anonymous_users_are_sent_to_login(client, lot):
    for url in (reverse("reporting:list"), reverse("reporting:issue_preview", args=[lot.pk])):
        response = client.get(url)
        assert response.status_code == 302 and "/accounts/login/" in response["Location"]


def test_user_without_laboratory_role_is_denied_everywhere(login, people, lot):
    report = issued(people, lot)
    client = login("nobody")
    urls = [
        reverse("reporting:list"),
        reverse("reporting:new"),
        reverse("reporting:detail", args=[report.pk]),
        reverse("reporting:version", args=[report.pk, 1]),
        reverse("reporting:pdf", args=[report.pk, 1]),
        reverse("reporting:issue_preview", args=[lot.pk]),
        reverse("reporting:issue_sign", args=[lot.pk]),
        reverse("reporting:amend_preview", args=[report.pk]),
    ]
    assert [client.get(u).status_code for u in urls] == [403] * len(urls)
    assert not AuditEvent.objects.filter(action="report.downloaded").exists()


def test_empty_and_filtered_empty_states(login, people):
    client = login("quality")
    page = client.get(reverse("reporting:list")).content.decode()
    assert "No certificates of analysis yet." in page
    assert "New certificate of analysis" in page
    page = client.get(reverse("reporting:list") + "?q=zzz").content.decode()
    assert "No certificates match these filters." in page
    assert "Clear filters" in page


def test_read_only_roles_see_no_issue_action(login, people, lot):
    report = issued(people, lot)
    page = login("auditor").get(reverse("reporting:list")).content.decode()
    assert "CoA-SYN-100-1" in page
    assert "New certificate of analysis" not in page
    detail = login("auditor").get(reverse("reporting:detail", args=[report.pk])).content.decode()
    assert "Amend certificate" not in detail
    assert "Download PDF" in detail
    assert "History" in detail  # auditors may inspect the audit history


def test_list_filters_and_sorting(login, people, lot):
    issued(people, lot)
    other = build_lot(people, number="SYN-200")
    services.open_report(actor=people["quality"], lot=other, recipient="")
    client = login("quality")
    url = reverse("reporting:list")
    assert "SYN-200" not in client.get(url + "?status=issued").content.decode()
    assert "CoA-SYN-200-1" in client.get(url + "?status=draft").content.decode()
    assert "CoA-SYN-100-1" in client.get(url + "?q=customer a&sort=lot").content.decode()
    assert client.get(url + "?sort=%27%3B--").status_code == 200  # unknown sort is ignored


def test_new_lists_only_released_lots(login, people, lot):
    build_lot(people, number="SYN-QUAR", release=False)
    client = login("quality")
    page = client.get(reverse("reporting:new")).content.decode()
    assert "SYN-100" in page and "SYN-QUAR" not in page
    response = client.get(reverse("reporting:new"), {"lot": lot.pk})
    assert response.status_code == 302
    assert response["Location"] == reverse("reporting:issue_preview", args=[lot.pk])
    bad = client.get(reverse("reporting:new"), {"lot": 99999})
    assert bad.status_code == 422 and "Select a valid choice" in bad.content.decode()


def test_preview_shows_blockers_without_signing_action(login, people):
    lot = build_lot(people, number="SYN-QUAR", release=False)
    page = login("quality").get(reverse("reporting:issue_preview", args=[lot.pk])).content.decode()
    assert "cannot be issued until" in page
    assert "no signed QC disposition" in page
    assert "Continue to signing" not in page


def test_preview_for_author_explains_independence(login, people, lot):
    people["analyst"].groups.add(*people["quality"].groups.all())
    page = login("analyst").get(reverse("reporting:issue_preview", args=[lot.pk])).content.decode()
    assert "you cannot issue its certificate" in page
    assert "Continue to signing" not in page


def test_sign_page_requires_reviewed_evidence(login, people, lot):
    client = login("quality")
    response = client.get(reverse("reporting:issue_sign", args=[lot.pk]) + "?evidence=stale")
    assert response.status_code == 302
    assert response["Location"] == reverse("reporting:issue_preview", args=[lot.pk])


def test_analyst_cannot_open_signing(login, people, lot):
    url, _ = sign_url(lot)
    assert login("analyst").get(url).status_code == 403


def test_issue_flow_download_and_audit(login, people, lot):
    client = login("quality")
    preview = client.get(reverse("reporting:issue_preview", args=[lot.pk])).content.decode()
    assert "Continue to signing" in preview and "Preview, not issued" in preview
    url, digest = sign_url(lot)
    page = client.get(url).content.decode()
    assert "data-signature-dialog" in page
    assert "Signing username" in page and "Signature PIN" in page
    assert PIN not in page
    response = client.post(url, sign_payload(digest))
    report = Report.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("reporting:detail", args=[report.pk])
    detail = client.get(response["Location"]).content.decode()
    assert "version 1 issued" in detail
    assert "Amend certificate" in detail
    assert report.current_pdf_sha256 in detail
    pdf = client.get(reverse("reporting:pdf", args=[report.pk, 1]))
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert re.fullmatch(r'attachment; filename="CoA-SYN-100-1-v1\.pdf"', pdf["Content-Disposition"])
    assert "no-store" in pdf["Cache-Control"]
    assert pdf.content.startswith(b"%PDF-")
    assert AuditEvent.objects.filter(action="report.downloaded", actor=people["quality"]).exists()
    inline = client.get(reverse("reporting:pdf", args=[report.pk, 1]) + "?inline=1")
    assert inline["Content-Disposition"].startswith("inline;")
    version_page = client.get(reverse("reporting:version", args=[report.pk, 1])).content.decode()
    assert "Current version" in version_page and "frozen snapshot" in version_page


def test_failed_signing_keeps_input_clears_pin_and_records_denial(login, people, lot):
    client = login("quality")
    url, digest = sign_url(lot)
    response = client.post(
        url, sign_payload(digest, pin="11111111", reason="Reason to keep", remarks="Note")
    )
    page = response.content.decode()
    assert response.status_code == 422
    assert "Signature PIN was not accepted." in page
    assert "Reason to keep" in page and "Synthetic Customer A" in page
    assert "11111111" not in page
    assert not ReportVersion.objects.exists()
    assert AuditEvent.objects.filter(action="signature.denied").exists()


def test_wrong_signing_username_is_rejected(login, people, lot):
    client = login("quality")
    url, digest = sign_url(lot)
    response = client.post(url, sign_payload(digest, signature_username="quality2"))
    assert response.status_code == 422
    assert "Enter your own signing username" in response.content.decode()
    assert not ReportVersion.objects.exists()


def test_missing_fields_show_inline_errors(login, people, lot):
    client = login("quality")
    url, digest = sign_url(lot)
    response = client.post(url, {"evidence_hash": digest})
    page = response.content.decode()
    assert response.status_code == 422
    assert page.count("This field is required.") >= 3
    assert 'role="alert"' in page


def test_stale_post_is_rejected_not_retried(login, people, lot):
    client = login("quality")
    url, digest = sign_url(lot)
    ev.register_collector("holds", lambda lot: [])  # evidence changes after review
    response = client.post(url, sign_payload(digest))
    assert response.status_code == 422
    assert "evidence changed" in response.content.decode()
    assert not ReportVersion.objects.exists()


def test_author_post_is_forbidden_and_unsigned(login, people, lot):
    people["analyst"].groups.add(*people["quality"].groups.all())
    client = login("analyst")
    url, digest = sign_url(lot)
    response = client.post(url, sign_payload(digest, signature_username="analyst"))
    assert response.status_code == 403
    assert "authored" in response.content.decode()
    assert not ElectronicSignature.objects.filter(object_type="reporting.report").exists()


def test_amendment_flow(login, people, lot):
    report = issued(people, lot)
    client = login("quality2")
    preview = client.get(reverse("reporting:amend_preview", args=[report.pk])).content.decode()
    assert "Replaces version 1" in preview and "evidence is unchanged" in preview
    digest = services.preview(lot)[1]
    url = reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={digest}"
    assert 'name="expected_version" value="1"' in client.get(url).content.decode()
    response = client.post(
        url,
        {
            "evidence_hash": digest,
            "expected_version": 1,
            "reason": "Corrected recipient wording",
            "remarks": "",
            "signature_username": "quality2",
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    report.refresh_from_db()
    assert report.version_count == 2
    detail = client.get(reverse("reporting:detail", args=[report.pk])).content.decode()
    assert "Superseded" in detail and "Current" in detail and "Amended" in detail
    v1 = client.get(reverse("reporting:version", args=[report.pk, 1])).content.decode()
    assert "Superseded by" in v1
    # Stale amendment form (version 1 expected) is refused.
    stale = client.post(
        url,
        {
            "evidence_hash": digest,
            "expected_version": 1,
            "reason": "Again",
            "signature_username": "quality2",
            "pin": PIN,
        },
    )
    assert stale.status_code == 422 and "changed since you reviewed" in stale.content.decode()
    assert report.versions.count() == 2


def test_unknown_version_and_get_only_download(login, people, lot):
    report = issued(people, lot)
    client = login("quality")
    assert client.get(reverse("reporting:version", args=[report.pk, 9])).status_code == 404
    assert client.post(reverse("reporting:pdf", args=[report.pk, 1])).status_code == 405


def test_draft_report_detail_offers_issue(login, people, lot):
    draft = services.open_report(actor=people["quality"], lot=lot, recipient="Z")
    page = login("quality").get(reverse("reporting:detail", args=[draft.pk])).content.decode()
    assert "Not issued" in page and "Review and issue" in page
    assert (
        login("quality").get(reverse("reporting:amend_preview", args=[draft.pk])).status_code == 302
    )


def test_html_in_data_is_escaped(login, people):
    lot = build_lot(people, number="SYN-<b>X</b>")
    report = services.issue_report(
        actor=people["quality"],
        pin=PIN,
        lot=lot,
        recipient="<script>alert(1)</script>",
        evidence_hash=services.preview(lot)[1],
        reason="Escape check",
    )
    page = login("quality").get(reverse("reporting:detail", args=[report.pk])).content.decode()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "<b>X</b>" not in page


def test_sign_page_preflight_refuses_authors_before_the_pin_form(login, people, lot):
    people["analyst"].groups.add(*people["quality"].groups.all())
    client = login("analyst")
    url, _ = sign_url(lot)
    response = client.get(url, follow=True)
    page = response.content.decode()
    assert response.redirect_chain[-1][0] == reverse("reporting:issue_preview", args=[lot.pk])
    assert "you cannot sign this certificate as issued" in page
    assert "Signing username" not in page and "data-signature-dialog" not in page


def test_sign_page_preflight_explains_blockers_before_the_pin_form(login, people, lot):
    ev.register_collector(
        "holds", lambda lot: [{"id": "H1", "status": "open", "description": "Hold 5"}]
    )
    client = login("quality")
    url, _ = sign_url(lot)
    page = client.get(url, follow=True).content.decode()
    assert "cannot be issued: Open hold: Hold 5." in page
    assert "data-signature-dialog" not in page


def test_amend_preflight_refuses_authors_and_blockers(login, people, lot):
    report = issued(people, lot)
    digest = services.preview(lot)[1]
    url = reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={digest}"
    people["analyst"].groups.add(*people["quality"].groups.all())
    page = login("analyst").get(url, follow=True).content.decode()
    assert "you cannot sign this certificate as amended" in page
    assert "data-signature-dialog" not in page
    ev.register_collector("holds", lambda lot: [{"id": "H", "status": "open"}])
    blocked = services.preview(lot)[1]
    url = reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={blocked}"
    page = login("quality").get(url, follow=True).content.decode()
    assert "cannot be amended" in page and "data-signature-dialog" not in page
    # POST still revalidates independently of the preflight.
    posted = login("quality").post(
        url,
        {
            "evidence_hash": blocked,
            "expected_version": 1,
            "reason": "Try anyway",
            "signature_username": "quality",
            "pin": PIN,
        },
    )
    assert posted.status_code == 422 and "Open hold" in posted.content.decode()
    assert report.versions.count() == 1
