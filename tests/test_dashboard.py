"""Dashboard (quality.dashboard): who may open it, what its queues count, and that its cost does
not grow with the number of lots."""

import re
from html import unescape

import pytest
from django.contrib.auth.models import Group
from django.core.paginator import Page
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import RuleSet
from quality import services as quality
from quality.models import Lot
from sampling import services as sampling
from tests.receipts import on_site_receipt
from tests.test_integrated_journey import assign_and_sample, observed_test
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db

READERS = ("analyst", "reviewer", "quality", "admin", "auditor")


def user_with(django_user_model, name, *roles):
    user = django_user_model.objects.create_user(name)
    user.groups.set([Group.objects.get_or_create(name=role)[0] for role in roles])
    return user


def queues(response):
    """{queue label: count} as the page shows them."""
    html = response.content.decode()
    pattern = r'class="vr-queue-label"[^>]*>([^<]+)<.*?class="vr-queue-count"[^>]*>(\d+)<'
    return {label: int(count) for label, count in re.findall(pattern, html, re.S)}


@pytest.fixture
def rules(django_user_model):
    author = user_with(django_user_model, "dashboard-author")
    return RuleSet.objects.create(
        code="dashboard-rules",
        segment="synthetic",
        status="approved",
        effective_from=timezone.now(),
        author=author,
    )


def make_lots(rules, count, *, state="quarantine", prefix="SYN-DASH"):
    start = Lot.objects.count()
    for n in range(start, start + count):
        Lot.objects.create(
            number=f"{prefix}-{n:03}",
            material="Synthetic",
            rules=rules,
            created_by=rules.author,
            state=state,
        )


@pytest.mark.parametrize("role", READERS)
def test_every_reader_role_opens_it_and_only_analysts_get_new_lot(client, django_user_model, role):
    client.force_login(user_with(django_user_model, f"dash-{role}", role))
    response = client.get(reverse("quality:dashboard"))
    assert response.status_code == 200
    body = response.content.decode()
    assert '<h1 class="vr-page-title">Dashboard</h1>' in body
    assert (f'href="{reverse("quality:lot_new")}"' in body) == (role == "analyst")
    # The sidebar marks Dashboard, not Lots, on the dashboard.
    current = re.findall(r'aria-current="page">(?:(?!</a>).)*data-label="([^"]+)"', body, re.S)
    assert current == ["Dashboard"]


def test_accounts_without_a_role_are_sent_to_account_access(client, django_user_model):
    client.force_login(user_with(django_user_model, "dash-none", "unrelated"))
    response = client.get(reverse("quality:dashboard"))
    assert response.status_code == 302 and response.url == reverse("accounts:access")
    client.logout()
    response = client.get(reverse("quality:dashboard"))
    assert response.status_code == 302 and response.url.startswith(reverse("login"))


def test_queues_count_lots_where_they_wait(client, django_user_model, rules):
    make_lots(rules, 3)
    make_lots(rules, 2, state="released", prefix="SYN-DASH-REL")
    make_lots(rules, 1, state="rejected", prefix="SYN-DASH-REJ")
    client.force_login(user_with(django_user_model, "dash-reader", "auditor"))
    shown = queues(client.get(reverse("quality:dashboard")))
    assert shown["Requirements not assigned"] == 3  # quarantine lots only
    assert shown["Certificates to issue"] == 2  # released, no issued certificate
    assert shown["Tests open"] == 0 and shown["Awaiting review"] == 0
    assert len(shown) == 24  # zero queues stay visible


def test_cost_does_not_grow_with_the_number_of_lots(client, django_user_model, rules):
    client.force_login(user_with(django_user_model, "dash-count", "quality"))
    url = reverse("quality:dashboard")
    client.get(url)  # the first request also loads the account's preferences into the session

    def measured(lots):
        make_lots(rules, lots)
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured)

    assert measured(1) == measured(20)


def linked_queues(response):
    """[(label, list url, count)] of every queue that links to a list, as the page shows them."""
    html = response.content.decode()
    pattern = (
        r'<a class="vr-queue-label" href="([^"]+)">([^<]+)</a>'
        r'<span class="vr-queue-count"[^>]*>(\d+)<'
    )
    return [(label, unescape(url), int(n)) for url, label, n in re.findall(pattern, html)]


def listed(response):
    """The number of rows a list returns over all its pages."""
    for key in ("page_obj", "page"):
        page = response.context.get(key)
        if isinstance(page, Page):
            return page.paginator.count
    raise AssertionError("the list has no page of rows")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("role", READERS)
def test_every_queue_count_equals_the_rows_of_the_list_it_opens(
    client, django_user_model, integrated, role
):
    data, people = integrated, integrated["people"]
    sample = assign_and_sample(data)  # requirements assigned and sampled: not awaiting sampling
    observed_test(data, sample, "100.25")  # submitted: awaiting review

    def received(number, *, assigned=False):
        lot = quality.receive_lot(
            actor=people["receiver"],
            number=number,
            material=data["material"].name,
            rules=data["lot"].rules,
            reason="Synthetic dashboard receipt",
            receipt=on_site_receipt(),
        )
        if assigned:
            sampling.assign_requirements(
                actor=people["analyst"],
                lot=lot,
                material=data["material"],
                stage="incoming",
                reason="Assign approved synthetic policy",
            )
        return lot

    received("SYN-DASH-WAIT", assigned=True)  # awaiting sampling
    unassigned = received("SYN-DASH-NONE")  # requirements not assigned
    quality.add_sample(  # a sample with no test assigned
        actor=people["receiver"],
        lot=unassigned,
        reference="SYN-DASH-NONE-S1",
        collected_at=timezone.now(),
        reason="Synthetic sample",
    )
    released = received("SYN-DASH-REL", assigned=True)
    # Released with requirements assigned and no sample: never awaiting sampling.
    Lot.objects.filter(pk=released.pk).update(state="released")

    client.force_login(user_with(django_user_model, f"dash-queue-{role}", role))
    page = client.get(reverse("quality:dashboard"))
    shown = linked_queues(page)
    assert {label for label, _, _ in shown} == set(queues(page))  # every count is a link
    counts = {label: count for label, _, count in shown}
    assert counts["Awaiting sampling"] == 1
    assert counts["Requirements not assigned"] == 1
    assert counts["Awaiting review"] == 1
    assert counts["Certificates to issue"] == 1
    assert counts["Samples without assigned tests"] == 1
    for label, url, count in shown:
        response = client.get(url)
        assert response.status_code == 200, (label, url)
        assert listed(response) == count, (label, url)
