"""Trend chart pages: what each role reads and is offered, creating a chart, drafting and
approving limits, the chart drawing, and evaluating alerts through the web forms. Synthetic
data."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import ElectronicSignature
from trending import services
from trending.models import Chart, Evaluation, Limits

from .conftest import BASELINE, PIN, reviewed_lot
from .test_services import approved, chart_of, computed

pytestmark = pytest.mark.django_db(transaction=True)


def login(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def charted(trend, plain_static):
    for value in BASELINE:
        reviewed_lot(trend, value)
    chart = chart_of(trend)
    limits = approved(trend, computed(trend, chart))
    alert = reviewed_lot(trend, "103.0")
    return {**trend, "chart": chart, "limits": limits, "alert": alert}


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def chart_url(chart):
    return reverse("trending:chart_detail", args=[chart.pk])


@pytest.mark.parametrize("role", ["analyst", "reviewer", "author", "admin", "auditor"])
def test_every_laboratory_role_reads_charts_limits_and_evaluations(client, charted, role):
    login(client, charted["people"][role])
    listed = client.get(reverse("trending:chart_list"))
    assert listed.status_code == 200 and charted["chart"].identifier in listed.text
    assert ("New trend chart" in listed.text) == (role == "author")
    page = client.get(chart_url(charted["chart"]))
    assert page.status_code == 200
    assert 'class="vr-trend-plot"' in page.text and "Alert, not evaluated" in page.text
    assert ("Evaluate alerts" in page.text) == (role == "author")
    limits = client.get(reverse("trending:limits_detail", args=[charted["limits"].pk]))
    assert limits.status_code == 200 and "Baseline results" in limits.text
    assert client.get(reverse("trending:evaluation_list")).status_code == 200


def test_a_person_without_a_laboratory_role_reads_nothing(client, charted, django_user_model):
    login(client, django_user_model.objects.create_user("syn-nobody", password="x"))
    assert client.get(reverse("trending:chart_list")).status_code == 403
    assert client.get(chart_url(charted["chart"])).status_code == 403


@pytest.mark.parametrize(
    "name, args",
    [
        ("trending:chart_new", []),
        ("trending:limits_new", ["chart"]),
        ("trending:limits_approve", ["limits"]),
        ("trending:evaluation_new", ["chart"]),
    ],
)
def test_only_quality_opens_the_forms(client, charted, name, args):
    url = reverse(name, args=[charted[a].pk for a in args])
    for role in ("analyst", "reviewer", "auditor", "admin"):
        login(client, charted["people"][role])
        assert client.get(url).status_code == 403, role
        assert client.post(url, {"reason": "x"}).status_code == 403, role


def test_quality_creates_a_chart_and_drafts_limits_through_the_forms(client, trend, plain_static):
    for value in BASELINE[:8]:
        reviewed_lot(trend, value)
    login(client, trend["people"]["author"])
    response = client.post(
        reverse("trending:chart_new"), {"line": trend["line"].pk, "reason": "Follow the assay"}
    )
    chart = Chart.objects.get()
    assert response.status_code == 302 and response.url == chart_url(chart)
    page = client.get(chart_url(chart))
    assert "No approved limits" in page.text and "Draft limits" in page.text
    today = timezone.localdate().isoformat()
    form = {
        "basis": "computed",
        "baseline_from": today,
        "baseline_to": today,
        "rules": ["beyond", "run"],
        "run_length": "8",
        "trend_length": "6",
        "rationale": "First eight lots",
        "reason": "First limits",
    }
    bad = client.post(reverse("trending:limits_new", args=[chart.pk]), {**form, "run_length": 3})
    assert bad.status_code == 422
    response = client.post(reverse("trending:limits_new", args=[chart.pk]), form)
    limits = Limits.objects.get()
    assert response.status_code == 302 and limits.rules == ["beyond", "run"]
    detail = client.get(reverse("trending:limits_detail", args=[limits.pk]))
    assert services.INDEPENDENT_APPROVAL in detail.text and "Short baseline" in detail.text
    denied = client.get(reverse("trending:limits_approve", args=[limits.pk]))
    assert denied.status_code == 403 and 'name="pin"' not in denied.text
    login(client, trend["people"]["approver"])
    sign_url = reverse("trending:limits_approve", args=[limits.pk])
    assert 'name="pin"' in client.get(sign_url).text
    signed = client.post(
        sign_url,
        {
            "reason": "Limits reviewed",
            "pin": PIN,
            "expected_revision": limits.revision,
            "signature_username": "synthetic_approver",
        },
    )
    assert signed.status_code == 302
    assert ElectronicSignature.objects.filter(object_id=str(limits.pk), meaning="approved")


def test_quality_evaluates_alerts_through_the_forms(client, charted):
    people = charted["people"]
    login(client, people["author"])
    new = reverse("trending:evaluation_new", args=[charted["chart"].pk])
    form = client.get(new)
    assert charted["alert"].label in form.text
    response = client.post(new, {"alerts": [charted["alert"].pk], "reason": "Look into it"})
    evaluation = Evaluation.objects.get()
    assert response.status_code == 302
    findings = reverse("trending:evaluation_findings", args=[evaluation.pk])
    response = client.post(
        findings,
        {
            "expected_revision": evaluation.revision,
            "laboratory_check": "No laboratory error",
            "cause": "None found",
            "effect": "The lot conforms",
            "actions": "",
            "quality_reference": "DEV-SYN-1",
            "reason": "Findings",
        },
    )
    assert response.status_code == 302
    page = client.get(reverse("trending:evaluation_detail", args=[evaluation.pk]))
    assert services.INDEPENDENT_CONCLUSION in page.text
    login(client, people["approver"])
    page = client.get(reverse("trending:evaluation_detail", args=[evaluation.pk]))
    assert "Conclude evaluation" in page.text
    evaluation.refresh_from_db()
    response = client.post(
        reverse("trending:evaluation_conclude", args=[evaluation.pk]),
        {
            "outcome": "not_confirmed",
            "conclusion": "Chance variation",
            "reason": "Evaluation reviewed",
            "pin": PIN,
            "expected_revision": evaluation.revision,
            "signature_username": "synthetic_approver",
        },
    )
    assert response.status_code == 302
    evaluation.refresh_from_db()
    assert evaluation.state == "concluded"
    chart_page = client.get(chart_url(charted["chart"]))
    assert "No open alert" in chart_page.text and evaluation.identifier in chart_page.text


def test_the_reminders_and_the_disposition_page_name_an_open_alert(client, charted):
    login(client, charted["people"]["author"])
    page = client.get(reverse("planning:reminders"), {"kind": "trend"})
    assert page.status_code == 200 and charted["chart"].identifier in page.text
    lot = charted["alert"].lot
    sign = client.get(reverse("quality:disposition", args=[lot.pk]))
    assert "raised an out-of-trend alert" in sign.text


def test_the_drawing_keeps_every_mark_in_order(charted):
    from trending import plot
    from trending.series import series_of

    series = series_of(charted["chart"])
    drawing = plot.geometry(charted["chart"], series.points)
    assert [m["kind"] for m in drawing["markers"]] == ["result"] * 10 + ["alert"]
    xs = [Decimal(m["x"]) for m in drawing["markers"]]
    assert xs == sorted(xs)
    # The specification limits (90 to 110 %) lie far outside the results: named, not drawn.
    assert {line["kind"] for line in drawing["lines"]} == {"center", "limit"}
    assert drawing["named_specs"] == ["90", "110"]
    assert drawing["path"].startswith("M") and drawing["path"].count("L") == 10
