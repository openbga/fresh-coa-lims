"""The withdrawal of a certificate of analysis through its pages: the record's actions per role,
the signing page and its refusals, the recipient notification form, the version page, the
amendment pages of a withdrawn certificate and the list's status filters (synthetic data
only)."""

import html
from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from core.models import AuditEvent, ElectronicSignature, PINCredential
from reporting.models import RecipientNotification, Report
from tests.test_certificate_withdrawal import REASON, RECIPIENT, fresh, notify, withdraw
from tests.test_certificate_withdrawal import world as world  # noqa: F401
from tests.test_integrated_journey import PIN
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def text(response):
    """The page as text, tags and whitespace runs removed."""
    return " ".join(html.unescape(strip_tags(response.content.decode())).split())


def url(name, report):
    return reverse(f"reporting:{name}", args=[report.pk])


def signed(user, report, **values):
    return {
        "signature_username": user.username,
        "reason": REASON,
        "reference": "IA-3",
        "expected_revision": fresh(report).revision,
        "pin": PIN,
        **values,
    }


def told(**values):
    return {
        "recipient": RECIPIENT,
        "notified_on": timezone.localdate().isoformat(),
        "means": "letter",
        "evidence_ref": "SYN-LETTER-0001 in the complaint file",
        "note": "",
        **values,
    }


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def test_withdraw_is_a_quality_action_under_more_on_an_issued_certificate(client, world):
    people, report = world["people"], world["report"]
    withdraw_url = url("withdraw", report)
    client.force_login(people["approver"])
    page = client.get(url("detail", report)).content.decode()
    item = f'class="dropdown-item vr-menu-danger" href="{withdraw_url}">Withdraw certificate'
    assert item in page
    assert "Amend certificate" in page and "Record notification" not in page
    for who in ("reviewer", "auditor", "admin", "receiver"):
        client.force_login(people[who])
        page = client.get(url("detail", report)).content.decode()
        assert withdraw_url not in page and "Withdraw certificate" not in page, who
        assert client.get(withdraw_url).status_code == 403, who


def test_signing_the_withdrawal_from_its_page(client, world):
    people, report = world["people"], world["report"]
    approver = people["approver"]
    client.force_login(approver)
    page = client.get(url("withdraw", report))
    assert page.status_code == 200
    body = text(page)
    assert "Withdraw certificate · " + report.number in body
    assert "stops being valid when you sign" in body
    assert "Every issued version and its PDF stay on record exactly as issued" in body
    assert "record the notification" in body
    assert "Sign and withdraw" in body and "Signature PIN" in body
    assert "Current version" in body and "Version 1, issued" in body

    stale = client.post(url("withdraw", report), signed(approver, report, expected_revision=1))
    assert stale.status_code == 422 and "Record changed" in text(stale)
    wrong = client.post(url("withdraw", report), signed(approver, report, pin="00000000"))
    assert wrong.status_code == 422
    assert PINCredential.objects.get(user=approver).failures == 1
    assert AuditEvent.objects.filter(action="signature.denied", actor=approver).exists()
    blank = client.post(url("withdraw", report), signed(approver, report, reason=""))
    assert blank.status_code == 422 and fresh(report).state == "issued"

    done = client.post(url("withdraw", report), signed(approver, report))
    assert done.status_code == 302 and done["Location"] == url("detail", report)
    assert any("withdrawn; every issued version is kept" in m for m in messages_of(done))
    report = fresh(report)
    assert (report.state, report.withdrawal_reference) == ("withdrawn", "IA-3")
    assert ElectronicSignature.objects.filter(meaning="withdrawn", signer=approver).count() == 1

    again = client.get(url("withdraw", report))
    assert again.status_code == 403
    assert "This certificate is already withdrawn." in text(again)
    assert 'name="pin"' not in again.content.decode()


def test_a_draft_cannot_be_withdrawn(client, world):
    from reporting import services as reporting

    draft = reporting.open_report(
        actor=world["people"]["approver"], lot=world["lot"], recipient="Synthetic Customer B"
    )
    client.force_login(world["people"]["approver"])
    page = client.get(url("withdraw", draft))
    assert page.status_code == 403
    assert "Only an issued certificate can be withdrawn." in text(page)
    assert 'name="pin"' not in page.content.decode()
    posted = client.post(url("withdraw", draft), signed(world["people"]["approver"], draft))
    assert posted.status_code == 403 and fresh(draft).state == "draft"


def test_a_withdrawn_record_says_so_and_asks_for_the_notification(client, world):
    people, report = world["people"], world["report"]
    withdraw(world)
    client.force_login(people["approver"])
    response = client.get(url("detail", report))
    page, body = response.content.decode(), text(response)
    assert "Withdrawn This certificate was withdrawn on" in body
    assert "It is no longer valid and cannot be amended" in body
    assert f"Reason: {REASON} · Reference: IA-3" in body
    assert "Recipient notification not recorded." in body
    assert "<dt>Reason for withdrawal</dt>" in page and "<dt>Withdrawal reference</dt>" in page
    assert "No notification recorded yet" in body
    assert f'class="btn btn-primary" href="{url("notify", report)}">Record notification' in page
    assert "Amend certificate" not in page and url("withdraw", report) not in page
    assert 'data-signature-meaning="withdrawn"' in page
    assert 'data-signature-meaning="issued"' in page
    assert "Download PDF" in page  # the issued bytes stay available
    # The readers see the withdrawal and no quality action.
    client.force_login(people["reviewer"])
    response = client.get(url("detail", report))
    assert "This certificate was withdrawn on" in text(response)
    assert url("notify", report) not in response.content.decode()


def test_recording_a_notification_from_its_page(client, world):
    people, report = world["people"], world["report"]
    notify_url = url("notify", report)
    client.force_login(people["approver"])
    early = client.get(notify_url)
    assert early.status_code == 302 and early["Location"] == url("detail", report)
    assert any("only for a withdrawn certificate" in m for m in messages_of(early))
    refused = client.post(notify_url, told())
    assert refused.status_code == 422 and "only for a withdrawn certificate" in text(refused)
    withdraw(world)

    page = client.get(notify_url)
    assert page.status_code == 200
    assert f'value="{RECIPIENT}"' in page.content.decode()  # defaults to the named recipient
    body = text(page)
    assert "Record notification" in body and "Evidence reference" in body
    for who in ("reviewer", "auditor", "admin"):
        client.force_login(people[who])
        assert client.get(notify_url).status_code == 403, who
        assert client.post(notify_url, told()).status_code == 403, who
    client.force_login(people["approver"])

    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    invalid = client.post(notify_url, told(notified_on=future, means="other"))
    assert invalid.status_code == 422
    body = text(invalid)
    assert "The date notified cannot be in the future." in body
    assert "Describe how the recipient was notified." in body
    assert 'aria-invalid="true"' in invalid.content.decode()
    assert "SYN-LETTER-0001 in the complaint file" in invalid.content.decode()  # input kept
    assert not RecipientNotification.objects.exists()

    saved = client.post(notify_url, told())
    assert saved.status_code == 302 and saved["Location"] == url("detail", report)
    assert RecipientNotification.objects.get().means == "letter"
    response = client.get(url("detail", report))
    page, body = response.content.decode(), text(response)
    assert "Recipient notification not recorded." not in body
    assert "SYN-LETTER-0001 in the complaint file" in body and "Letter" in body
    # A further notification stays possible, from the panel; no primary action is left.
    assert f'class="btn btn-sm btn-outline-secondary" href="{notify_url}"' in page
    assert "btn btn-primary" not in page.split("vr-page-actions", 1)[-1].split("</div>", 1)[0]


def test_versions_of_a_withdrawn_certificate_stay_downloadable(client, world):
    people, report = world["people"], world["report"]
    version = report.versions.get(number=1)
    withdraw(world)
    client.force_login(people["auditor"])
    page = client.get(reverse("reporting:version", args=[report.pk, 1]))
    body = text(page)
    assert f"Certificate {report.number} was withdrawn on" in body
    assert "this version is no longer valid" in body and "PDF stays downloadable" in body
    pdf = client.get(reverse("reporting:pdf", args=[report.pk, 1]))
    assert pdf.status_code == 200 and pdf.content == bytes(version.pdf)


def test_the_amendment_pages_refuse_a_withdrawn_certificate(client, world):
    report = world["report"]
    withdraw(world)
    client.force_login(world["people"]["approver"])
    for name in ("amend_preview", "amend_sign"):
        response = client.get(url(name, report))
        assert response.status_code == 302 and response["Location"] == url("detail", report)
        assert any("withdrawn; it is not amended" in m for m in messages_of(response)), name


def test_the_list_filters_withdrawn_and_awaiting_notification(client, world):
    from reporting import services as reporting

    people, withdrawn = world["people"], world["report"]
    current = reporting.open_report(
        actor=people["approver"], lot=world["lot"], recipient="Synthetic Customer B"
    )
    withdraw(world)
    listing = reverse("reporting:list")
    client.force_login(people["reviewer"])

    def numbers(query):
        page = client.get(listing + query).content.decode()
        return {r.number for r in Report.objects.all() if f">{r.number}</a>" in page}

    assert numbers("?status=withdrawn") == {withdrawn.number}
    assert numbers("?status=awaiting_notification") == {withdrawn.number}
    assert numbers("?status=issued") == set()
    assert numbers("?status=draft") == {current.number}
    page = client.get(listing + "?status=withdrawn").content.decode()
    assert '<span class="vr-sub">Notification not recorded</span>' in page
    page = client.get(listing + "?sort=status").content.decode()
    assert page.index(current.number) < page.index(withdrawn.number)  # withdrawn sorts last
    notify(world)
    assert numbers("?status=awaiting_notification") == set()
    assert numbers("?status=withdrawn") == {withdrawn.number}
    assert "Notification not recorded" not in text(client.get(listing + "?status=withdrawn"))
