"""Where a lot is (quality/route.py): stages derived from recorded data only, and the lot list
gets them from its one annotated query (no query per row)."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from core.models import RuleSet
from quality.models import Lot
from quality.route import stages, summary
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db


def states(route):
    return [stage["state"] for stage in route]


def counts(**changes):
    values = {
        "state": "quarantine",
        "assignment": "ready",
        "samples": 2,
        "tests": 6,
        "entered": 3,
        "reviewed": 0,
        "issued": False,
        "investigation_open": False,
    }
    values.update(changes)
    return stages(**values)


def test_results_in_progress_shows_its_share():
    route = counts()
    assert states(route) == ["done", "done", "current", "pending", "pending", "pending"]
    assert route[2]["progress"] == 50 and summary(route) == "3 of 6 entered"


def test_unassigned_lot_starts_at_the_requirements():
    route = counts(assignment="", samples=0, tests=0, entered=0)
    assert states(route)[0] == "current" and summary(route) == "Not assigned"
    assert set(states(route)[1:]) == {"pending"}


def test_applicability_hold_and_open_investigation_are_held():
    assert counts(assignment="hold")[0]["state"] == "held"
    route = counts(entered=6, reviewed=5, investigation_open=True)
    assert states(route)[3] == "held" and route[3]["progress"] == 80


def test_decisions_and_certificate():
    released = counts(state="released", entered=6, reviewed=6)
    assert states(released) == ["done"] * 5 + ["current"]
    assert summary(released) == "Not issued"
    issued = counts(state="released", entered=6, reviewed=6, issued=True)
    assert states(issued) == ["done"] * 6 and summary(issued) == "Certificate issued"
    rejected = counts(state="rejected")
    assert rejected[4]["state"] == "rejected" and summary(rejected) == "Rejection signed"
    cancelled = counts(state="cancelled")
    assert set(states(cancelled)) == {"pending"} and summary(cancelled) == "Received in error"


def test_lot_list_route_costs_no_query_per_row(client, django_user_model):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    user = django_user_model.objects.create_user("route-reader")
    user.groups.add(Group.objects.get_or_create(name="auditor")[0])
    rules = RuleSet.objects.create(
        code="route-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=user,
    )
    client.force_login(user)

    def listing(lots):
        for n in range(Lot.objects.count(), lots):
            Lot.objects.create(
                number=f"SYN-ROUTE-{n:03}", material="Synthetic", rules=rules, created_by=user
            )
        with CaptureQueriesContext(connection) as queries:
            response = client.get(reverse("quality:lot_list"))
        assert response.status_code == 200
        return len(queries), response.content.decode()

    listing(2)  # the first request also loads the account's preferences into the session
    few, _ = listing(2)
    many, body = listing(12)
    assert many == few  # the route counts come from the list's own query
    assert body.count('class="vr-microroute"') == 12 and "Not assigned" in body


def test_lot_record_lists_what_signing_enforces_and_shows_holds(client, django_user_model):
    """The QC disposition aside lists exactly quality.services.disposition_blockers, the list
    dispose_lot checks (stability holds, then sampling and analytical evidence); active holds are
    header pills."""
    import html
    import re

    from quality.services import disposition_blockers
    from stability.gates import lot_blockers as hold_blockers
    from stability.services import place_hold

    quality = django_user_model.objects.create_user("route-quality")
    quality.groups.add(Group.objects.get_or_create(name="quality")[0])
    rules = RuleSet.objects.create(
        code="route-hold-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=quality,
    )
    lot = Lot.objects.create(
        number="SYN-ROUTE-HOLD", material="Synthetic", rules=rules, created_by=quality
    )
    hold = place_hold(actor=quality, lot=lot, kind="quality", reason="Synthetic hold reason")
    client.force_login(quality)
    body = client.get(reverse("quality:lot_detail", args=[lot.pk])).content.decode()
    aside = body[body.index('id="disposition-heading"') : body.index('id="receipt-heading"')]
    checklist = aside[aside.index('class="vr-checklist"') : aside.index("</ul>")]
    listed = [
        html.unescape(re.sub(r"<[^>]+>", "", item)).strip()
        for item in re.findall(r"<li>(.*?)</li>", checklist, re.S)
    ]
    assert listed == disposition_blockers(lot)
    assert listed[: len(hold_blockers(lot))] == hold_blockers(lot)  # holds first
    assert any("no specification or sampling requirements are assigned." in m for m in listed)
    meta = body[
        body.index('class="vr-page-meta"') : body.index("</ul>", body.index("vr-page-meta"))
    ]
    assert f'title="{hold.identifier}"' in meta and "Quality hold</span>" in meta
    # A quality reviewer's next step is the disposition, whatever other roles they hold.
    disposition = reverse("quality:disposition", args=[lot.pk])
    assert f'class="btn btn-primary" href="{disposition}"' in body


@pytest.mark.django_db(transaction=True)
def test_lot_record_shows_native_tests_per_sample(client, integrated):
    """A native lot's Samples and results panel lists each sample's analytical tests (status,
    reportable result, link to the test) from the tests the record already loaded."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from tests.test_integrated_journey import assign_and_sample, observed_test

    data = integrated
    sample = assign_and_sample(data)
    observed_test(data, sample, "99.5")
    from analytical.models import AnalyticalTest

    test = AnalyticalTest.objects.get(sample=sample)
    client.force_login(data["people"]["approver"])
    url = reverse("quality:lot_detail", args=[data["lot"].pk])
    client.get(url)  # warm the session's preferences
    with CaptureQueriesContext(connection) as one:
        body = client.get(url).content.decode()
    panel = body[body.index('id="samples-heading"') : body.index('id="signatures-heading"')]
    assert reverse("analytical:test_detail", args=[test.pk]) in panel
    assert test.test_code in panel and ">Awaiting review<" in panel
    assert test.reportable_display in panel
    assert "No results recorded." not in panel  # the legacy table is not shown for native tests
    # A second sample adds no query: the tests come from the record's own lot query.
    second = sampling_second_sample(data)
    observed_test(data, second, "99.6")
    with CaptureQueriesContext(connection) as two:
        client.get(url)
    assert len(two) - len(one) <= 2  # its sample row and its sampling record, not per test


def sampling_second_sample(data):
    from decimal import Decimal

    from sampling import services as sampling

    record = sampling.record_sampling(
        actor=data["people"]["analyst"],
        lot=data["lot"],
        reference="SYN-INTEGRATED-S002",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C002",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Second synthetic sample",
    )
    return record.sample


def test_lot_record_keeps_legacy_results(client, django_user_model):
    """A lot with only foundation results keeps the legacy results table."""
    analyst = django_user_model.objects.create_user("route-legacy")
    analyst.groups.add(Group.objects.get_or_create(name="analyst")[0])
    rules = RuleSet.objects.create(
        code="route-legacy-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=analyst,
    )
    lot = Lot.objects.create(
        number="SYN-ROUTE-LEGACY", material="Synthetic", rules=rules, created_by=analyst
    )
    lot.samples.create(reference="SYN-LEGACY-S1", collected_at=timezone.now(), created_by=analyst)
    client.force_login(analyst)
    body = client.get(reverse("quality:lot_detail", args=[lot.pk])).content.decode()
    panel = body[body.index('id="samples-heading"') : body.index('id="signatures-heading"')]
    assert "SYN-LEGACY-S1" in panel and "No results recorded." in panel
    assert "Tests of sample" not in panel


def test_lot_record_lists_its_retention_obligations(client, django_user_model):
    """A lot-level retention obligation (no reserve sample) has its home on the lot record, with
    Set anchor for the roles stability.services.set_anchor allows, and none once it is set."""
    from stability.services import add_obligation, set_anchor

    analyst = django_user_model.objects.create_user("route-retention")
    analyst.groups.add(Group.objects.get_or_create(name="analyst")[0])
    auditor = django_user_model.objects.create_user("route-retention-auditor")
    auditor.groups.add(Group.objects.get_or_create(name="auditor")[0])
    rules = RuleSet.objects.create(
        code="route-retention-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=analyst,
    )
    lot = Lot.objects.create(
        number="SYN-ROUTE-RET", material="Synthetic", rules=rules, created_by=analyst
    )
    url = reverse("quality:lot_detail", args=[lot.pk])
    client.force_login(analyst)
    assert 'id="retention-heading"' not in client.get(url).content.decode()  # none, no panel
    obligation = add_obligation(
        actor=analyst,
        lot=lot,
        anchor_kind="last_distribution",
        offset_months=12,
        basis="Synthetic retention basis",
        reason="Synthetic",
    )
    anchor_url = reverse("stability:anchor_set", args=[obligation.pk])
    body = client.get(url).content.decode()
    row = body[body.index(f'data-obligation="{obligation.pk}"') :]
    row = row[: row.index("</tr>")]
    assert "Synthetic retention basis" in row and "Anchor not yet known" in row
    assert f'href="{anchor_url}">Set anchor</a>' in row
    client.force_login(auditor)  # may read, may not set the anchor
    body = client.get(url).content.decode()
    assert 'id="retention-heading"' in body and anchor_url not in body
    set_anchor(
        actor=analyst,
        obligation=obligation,
        anchor_date=timezone.localdate(),
        reason="Synthetic last distribution",
    )
    client.force_login(analyst)
    body = client.get(url).content.decode()
    assert anchor_url not in body and "Anchor not yet known" not in body
