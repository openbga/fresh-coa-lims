"""The sign-in announcement: signed administrator changes and what visitors are shown."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.announcements import (
    MEANING,
    change_announcement,
    current_announcement,
    published_announcement,
)
from accounts.models import LoginAnnouncement
from core.models import AuditEvent, ElectronicSignature, PINCredential
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-notice-pass-518!"
PIN = "73915286"
URL = reverse("accounts:announcement")
LOGIN = reverse("login")


@pytest.fixture
def users():
    result = {}
    for name, roles in [
        ("manager", ["admin"]),
        ("second", ["admin"]),
        ("quality", ["quality"]),
        ("analyst", ["analyst"]),
        ("auditor", ["auditor"]),
        ("root", []),
    ]:
        user = get_user_model().objects.create_user(
            username=name, password=PASSWORD, is_superuser=name == "root", is_staff=name == "root"
        )
        user.groups.set([Group.objects.get_or_create(name=role)[0] for role in roles])
        set_pin(actor=user, pin=PIN, password=PASSWORD)
        result[name] = user
    return result


def change(users, **kwargs):
    values = {
        "actor": users["manager"],
        "pin": PIN,
        "expected_revision": current_announcement().revision,
        "title": "Planned maintenance",
        "body": "The system is unavailable on Saturday morning.",
        "published": True,
        "reason": "Synthetic operational notice",
    }
    values.update(kwargs)
    return change_announcement(**values)


def post(client, user, **overrides):
    client.force_login(user)
    data = {
        "title": "Planned maintenance",
        "body": "The system is unavailable on Saturday morning.",
        "published": "on",
        "revision": current_announcement().revision,
        "reason": "Synthetic operational notice",
        "signature_username": user.username,
        "pin": PIN,
    }
    data.update(overrides)
    return client.post(URL, {k: v for k, v in data.items() if v is not None})


def test_sign_in_page_shows_nothing_until_an_announcement_is_published(client, users):
    assert not LoginAnnouncement.objects.exists()
    assert b"vr-announcement" not in client.get(LOGIN).content
    change(users, published=False)
    assert published_announcement() is None
    response = client.get(LOGIN)
    assert b"vr-announcement" not in response.content
    assert b"Saturday morning" not in response.content


def test_signed_publication_binds_revision_audit_and_signature(client, users):
    saved = change(users)
    assert (saved.pk, saved.revision, saved.published) == (1, 2, True)
    response = client.get(LOGIN)
    assert (
        b'<p class="vr-announcement-title" id="vr-announcement-title">Planned maintenance</p>'
        in (response.content)
    )
    assert b"<p>The system is unavailable on Saturday morning.</p>" in response.content
    signature = ElectronicSignature.objects.get()
    assert signature.meaning == MEANING and signature.signer == users["manager"]
    assert (signature.object_type, signature.object_id, signature.revision) == (
        "accounts.loginannouncement",
        "1",
        2,
    )
    assert signature.authentication_context == {"channel": "trusted-service", "components": ["pin"]}
    event = signature.audit_event
    assert event.action == f"signed.{MEANING}" and event.reason == "Synthetic operational notice"
    assert event.before["published"] is False and event.before["body"] == ""
    assert event.after["published"] is True and event.after["title"] == "Planned maintenance"

    withdrawn = change(users, actor=users["second"], published=False, reason="Maintenance done")
    assert withdrawn.revision == 3
    assert b"vr-announcement" not in client.get(LOGIN).content
    assert LoginAnnouncement.objects.count() == 1
    # The withdrawn text is retained for a later republication and in the audit trail.
    assert withdrawn.body == "The system is unavailable on Saturday morning."
    assert AuditEvent.objects.filter(action=f"signed.{MEANING}").count() == 2


def test_text_is_escaped_then_formatted_for_visitors(client, users):
    change(
        users,
        title="<b>Demo</b>",
        body=(
            "Use <script>alert(1)</script> **synthetic** data.\r\n\r\n"
            "| Username | Role |\r\n|---|---|\r\n| `demo_analyst` | Analyst |\r\n\r\n"
            '[bad](javascript:alert(1)) [docs](https://example.invalid/a) <img src=x onerror="x">'
        ),
    )
    assert "\r" not in current_announcement().body
    html = client.get(LOGIN).content.decode()
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x" not in html and "<b>Demo" not in html
    assert '&lt;img src=x onerror="x"&gt;' in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; <strong>synthetic</strong> data." in html
    assert "&lt;b&gt;Demo&lt;/b&gt;</p>" in html
    assert "<td><code>demo_analyst</code></td><td>Analyst</td>" in html
    assert "javascript:" not in html
    assert '<a href="https://example.invalid/a" rel="noopener noreferrer" target="_blank">' in html


def test_only_the_admin_role_can_open_or_change_the_page(client, users):
    link = f'href="{URL}"'.encode()
    for name in ("quality", "analyst", "auditor", "root"):
        client.force_login(users[name])
        assert client.get(URL).status_code == 403
        assert post(client, users[name]).status_code == 403
        assert link not in client.get(reverse("accounts:access")).content
        with pytest.raises(PermissionDenied):
            change(users, actor=users[name])
    assert not LoginAnnouncement.objects.exists()
    assert not ElectronicSignature.objects.exists()
    client.logout()
    response = client.get(URL)
    assert response.status_code == 302 and response.url.startswith(LOGIN)
    client.force_login(users["manager"])
    response = client.get(URL)
    assert response.status_code == 200
    assert link + b' aria-current="page"' in response.content
    assert b"No announcement text has been saved." in response.content
    assert b"No announcement changes recorded." in response.content
    assert b'name="pin"' in response.content and b"announcement_authorized" in response.content
    assert client.put(URL).status_code == 405


def test_web_change_signs_with_username_and_pin_and_lists_history(client, users):
    response = post(client, users["manager"])
    assert response.status_code == 302 and response.url == URL
    page = client.get(URL)
    assert b"Announcement saved. It is shown on the sign-in page." in page.content
    assert b"Announcement published" in page.content
    assert b"Signed by manager" in page.content and b"revision 2" in page.content
    assert b'data-tone="success"' in page.content
    assert b'name="revision" value="2"' in page.content
    signature = ElectronicSignature.objects.get()
    assert signature.authentication_context["channel"] == "web"
    assert signature.authentication_context["components"] == ["username", "pin"]
    assert b"Planned maintenance" in client.get(LOGIN).content

    response = post(client, users["manager"], published=None, reason="Withdraw the notice")
    assert response.status_code == 302
    page = client.get(URL)
    assert b"Announcement saved. The sign-in page shows no notice." in page.content
    assert b"Announcement withdrawn" in page.content and b"Not published" in page.content
    assert b"vr-announcement" not in client.get(LOGIN).content


def test_rejected_changes_leave_the_announcement_and_keep_pin_evidence(client, users):
    change(users)
    before = LoginAnnouncement.objects.values().get()

    stale = post(client, users["manager"], revision=1, body="Stale edit")
    assert stale.status_code == 422
    assert b"Record changed. Reload and review before signing." in stale.content
    assert b"Stale edit" in stale.content  # Safe input is kept for correction.

    wrong = post(client, users["manager"], pin="00000000", body="Wrong PIN edit")
    assert wrong.status_code == 422 and b"Signature PIN was not accepted." in wrong.content
    assert b'value="00000000"' not in wrong.content
    assert PINCredential.objects.get(user=users["manager"]).failures == 1
    assert AuditEvent.objects.filter(action="signature.denied", actor=users["manager"]).count() == 1

    other = post(client, users["manager"], signature_username="second", body="Borrowed identity")
    assert other.status_code == 422 and b"Enter your own signing username and PIN." in other.content

    empty = post(client, users["manager"], body="   ")
    assert empty.status_code == 422
    assert b"Enter the announcement text before publishing it." in empty.content

    no_reason = post(client, users["manager"], body="No reason", reason="")
    assert no_reason.status_code == 422

    too_long = post(client, users["manager"], body="x" * (LoginAnnouncement.BODY_LIMIT + 1))
    assert too_long.status_code == 422

    unchanged = post(client, users["manager"])
    assert unchanged.status_code == 422
    assert b"The announcement already has this text and status." in unchanged.content

    assert LoginAnnouncement.objects.values().get() == before
    assert ElectronicSignature.objects.count() == 1
    with pytest.raises(ValidationError, match="before publishing"):
        change(users, body="")


def test_page_explains_a_missing_pin_before_asking_for_one(client, users):
    PINCredential.objects.filter(user=users["manager"]).delete()
    client.force_login(users["manager"])
    response = client.get(URL)
    assert b"Enroll your signature PIN before changing the announcement." in response.content
    assert (
        b'name="pin"' not in response.content
        and b"<form"
        not in response.content.split(b'id="announcement-change"')[1].split(
            b'id="announcement-history"'
        )[0]
    )


def test_database_keeps_one_row_and_refuses_an_empty_publication(users):
    change(users)
    with pytest.raises(IntegrityError), transaction.atomic():
        LoginAnnouncement.objects.create(body="A second notice")
    with pytest.raises(IntegrityError), transaction.atomic():
        LoginAnnouncement.objects.filter(pk=1).update(body="")
