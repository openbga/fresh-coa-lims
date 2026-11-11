"""Administrator access: administrators read every certificate page and the stored PDF, but an
administrator without the quality role can neither open nor submit an issuing or amending form.
An administrator who also holds the quality role gets the quality actions and no more: the
authorship rule still applies."""

import pytest
from django.urls import reverse

from core.models import AuditEvent, ElectronicSignature
from reporting import services, urls
from reporting.models import Report, ReportVersion
from reporting.tests.conftest import PASSWORD, PIN, make_user

pytestmark = pytest.mark.django_db(transaction=True)

READ_ROUTES = {"list", "issue_preview", "detail", "amend_preview", "version", "pdf"}
MUTATION_ROUTES = {"new", "issue_sign", "amend_sign"}


@pytest.fixture
def login(client):
    def _login(name):
        assert client.login(username=name, password=PASSWORD)
        return client

    return _login


@pytest.fixture
def admins(django_user_model, people):
    return {
        "admin": make_user(django_user_model, "siteadmin", "admin"),
        "admin_quality": make_user(django_user_model, "adminquality", "admin", "quality"),
    }


@pytest.fixture
def report(people, lot):
    return services.issue_report(
        actor=people["quality"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic Customer A",
        evidence_hash=services.preview(lot)[1],
        reason="Customer shipment certificate",
    )


def state():
    return (
        Report.objects.count(),
        ReportVersion.objects.count(),
        ElectronicSignature.objects.count(),
        AuditEvent.objects.exclude(action="report.downloaded").count(),
    )


def read_urls(report):
    return {
        "list": reverse("reporting:list"),
        "issue_preview": reverse("reporting:issue_preview", args=[report.lot_id]),
        "detail": reverse("reporting:detail", args=[report.pk]),
        "amend_preview": reverse("reporting:amend_preview", args=[report.pk]),
        "version": reverse("reporting:version", args=[report.pk, 1]),
        "pdf": reverse("reporting:pdf", args=[report.pk, 1]),
    }


def mutation_urls(report):
    digest = services.preview(report.lot)[1]
    return {
        "new": reverse("reporting:new"),
        "issue_sign": reverse("reporting:issue_sign", args=[report.lot_id]) + f"?evidence={digest}",
        "amend_sign": reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={digest}",
    }


def test_every_reporting_route_is_classified():
    names = {p.name for p in urls.urlpatterns}
    assert names == READ_ROUTES | MUTATION_ROUTES


def test_admin_can_read_every_page_and_download(login, admins, report):
    client = login("siteadmin")
    for name, url in read_urls(report).items():
        response = client.get(url)
        assert response.status_code == 200, name
    pdf = client.get(read_urls(report)["pdf"])
    assert pdf.content.startswith(b"%PDF-")
    assert AuditEvent.objects.filter(
        action="report.downloaded", actor=admins["admin"], object_id=str(report.pk)
    ).exists()


def test_admin_sees_history_and_no_quality_actions(login, admins, report):
    client = login("siteadmin")
    detail = client.get(read_urls(report)["detail"]).content.decode()
    assert "History" in detail and "report.opened" in detail
    assert "Download PDF" in detail
    assert "Amend certificate" not in detail
    listing = client.get(read_urls(report)["list"]).content.decode()
    assert report.number in listing and "New certificate of analysis" not in listing
    for name in ("issue_preview", "amend_preview"):
        page = client.get(read_urls(report)[name]).content.decode()
        assert "Continue to signing" not in page
        assert "Read only" in page


def test_admin_without_quality_cannot_open_mutation_forms(login, admins, report):
    client = login("siteadmin")
    before = state()
    for name, url in mutation_urls(report).items():
        assert client.get(url).status_code == 403, name
    assert state() == before


def test_admin_without_quality_cannot_post_any_mutation(login, admins, report, people):
    client = login("siteadmin")
    before = state()
    digest = services.preview(report.lot)[1]
    payload = {
        "evidence_hash": digest,
        "reason": "Attempt",
        "remarks": "",
        "recipient": "Synthetic Customer B",
        "expected_version": 1,
        "signature_username": "siteadmin",
        "pin": PIN,
    }
    for name, url in mutation_urls(report).items():
        response = client.post(url, payload)
        assert response.status_code in (403, 405), name
    # Read-only pages accept no POST either.
    for name, url in read_urls(report).items():
        assert client.post(url, payload).status_code == 405, name
    assert state() == before
    assert not Report.objects.filter(recipient="Synthetic Customer B").exists()
    assert report.versions.count() == 1


def test_service_layer_also_refuses_admin_only(admins, report, people):
    with pytest.raises(Exception, match="role does not permit"):
        services.amend_report(
            actor=admins["admin"],
            pin=PIN,
            report=report,
            expected_version=1,
            evidence_hash=services.preview(report.lot)[1],
            reason="Attempt",
        )
    assert report.versions.count() == 1


def test_admin_with_quality_role_keeps_the_quality_actions(login, admins, report):
    client = login("adminquality")
    detail = client.get(read_urls(report)["detail"]).content.decode()
    assert "Amend certificate" in detail
    assert "New certificate of analysis" in client.get(read_urls(report)["list"]).content.decode()
    assert "Continue to signing" in client.get(read_urls(report)["amend_preview"]).content.decode()
    for name, url in mutation_urls(report).items():
        assert client.get(url).status_code == 200, name
    digest = services.preview(report.lot)[1]
    response = client.post(
        reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={digest}",
        {
            "evidence_hash": digest,
            "expected_version": 1,
            "reason": "Corrected wording",
            "remarks": "",
            "signature_username": "adminquality",
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    report.refresh_from_db()
    assert report.version_count == 2


def test_admin_role_is_not_an_independence_bypass(login, people, report):
    """The lot's analyst also holds admin and quality: signing is still refused."""
    from django.contrib.auth.models import Group

    author = people["analyst"]
    author.groups.add(*[Group.objects.get_or_create(name=n)[0] for n in ("admin", "quality")])
    client = login("analyst")
    before = state()
    digest = services.preview(report.lot)[1]
    response = client.post(
        reverse("reporting:amend_sign", args=[report.pk]) + f"?evidence={digest}",
        {
            "evidence_hash": digest,
            "expected_version": 1,
            "reason": "Attempt",
            "remarks": "",
            "signature_username": "analyst",
            "pin": PIN,
        },
    )
    assert response.status_code == 403
    assert state() == before
