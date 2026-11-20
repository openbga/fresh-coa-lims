"""Shelf-life evaluation pages: the role boundaries, the two-step draft, the record page with its
drawing, the conclusion's signing page and the study's side (synthetic data only)."""

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from stability import shelf_life
from stability.models import ShelfLifeEvaluation

from .helpers import FALLING, PIN, studies_with_results

pytestmark = pytest.mark.django_db(transaction=True)


def drafted(client, people, study):
    client.force_login(people["quality"])
    response = client.post(
        f"{reverse('stability:shelf_life_new')}?study={study.pk}",
        {
            "condition": "Long-term",
            "test_code": "assay",
            "direction": "decreases",
            "purpose": "Synthetic data for a proposed shelf life",
            "reason": "Synthetic evaluation",
        },
    )
    evaluation = ShelfLifeEvaluation.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("stability:shelf_life_detail", args=[evaluation.pk])
    return evaluation


def test_only_quality_drafts_and_the_first_step_chooses_a_study(client, people):
    studies, _ = studies_with_results(people, [FALLING[0]])
    new = reverse("stability:shelf_life_new")
    for role in ("analyst", "reviewer", "auditor", "admin"):
        client.force_login(people[role])
        assert client.get(new).status_code == 403
        body = client.get(reverse("stability:shelf_life_list")).content.decode()
        assert new not in body
    client.force_login(people["quality"])
    page = client.get(new)
    assert page.status_code == 200 and "Continue" in page.content.decode()
    response = client.post(new, {"study": studies[0].pk})
    assert response.status_code == 302 and response["Location"] == f"{new}?study={studies[0].pk}"
    second = client.get(response["Location"]).content.decode()
    assert "Long-term" in second and "Assay (assay) · 95 to 105 %" in second
    assert "Draft evaluation" in second
    # A study that does not exist, or no number at all, starts again at the first step.
    assert "Continue" in client.get(f"{new}?study=999999").content.decode()
    assert "Continue" in client.get(f"{new}?study=x1").content.decode()


def test_a_refused_draft_keeps_what_was_entered(client, people):
    studies, _ = studies_with_results(people, [FALLING[0]])
    client.force_login(people["quality"])
    response = client.post(
        f"{reverse('stability:shelf_life_new')}?study={studies[0].pk}",
        {
            "condition": "Long-term",
            "test_code": "assay",
            "direction": "decreases",
            "purpose": "Kept purpose",
            "reason": "",
        },
    )
    assert response.status_code == 422
    assert "Kept purpose" in response.content.decode()
    assert not ShelfLifeEvaluation.objects.exists()


def test_the_record_page_draws_the_results_and_offers_the_next_step(client, people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = drafted(client, people, studies[0])
    detail = reverse("stability:shelf_life_detail", args=[evaluation.pk])
    conclude = reverse("stability:shelf_life_conclude", args=[evaluation.pk])
    body = client.get(detail).content.decode()
    # The drafter sees why it cannot conclude, not a button.
    assert "another quality person concludes" in body and f'href="{conclude}"' not in body
    assert "<svg" in body and 'class="vr-shelf-mark"' in body
    assert "Poolability of the studies" in body and "Equal slopes" in body
    assert "Pooled: one line for all studies" in body
    result = shelf_life.of(evaluation)
    assert f"{result.estimate_months} months" in body
    assert body.count('data-kind="confidence"') >= 2  # the curve and its key
    client.force_login(people["quality2"])
    body = client.get(detail).content.decode()
    assert f'href="{conclude}"' in body
    for role in ("analyst", "auditor", "admin"):
        client.force_login(people[role])
        page = client.get(detail)
        assert page.status_code == 200
        assert f'href="{conclude}"' not in page.content.decode()
        assert client.get(conclude).status_code == 403


def test_concluding_signs_and_the_page_then_shows_what_was_frozen(client, people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = drafted(client, people, studies[0])
    conclude = reverse("stability:shelf_life_conclude", args=[evaluation.pk])
    client.force_login(people["quality2"])
    page = client.get(conclude).content.decode()
    shown = re.search(r'name="data_hash" value="([0-9a-f]{64})"', page).group(1)
    result = shelf_life.of(evaluation)
    longest = result.longest_supported
    assert f"{longest} months" in page
    data = {
        "signature_username": people["quality2"].username,
        "expected_revision": evaluation.revision,
        "data_hash": shown,
        "outcome": "supported",
        "shelf_life_months": longest + 1,
        "conclusion": "Synthetic conclusion",
        "pin": PIN,
        "reason": "Independent statistical review",
    }
    refused = client.post(conclude, data)
    assert refused.status_code == 422 and f"at most {longest} months" in refused.content.decode()
    data["shelf_life_months"] = longest
    response = client.post(conclude, data)
    assert response.status_code == 302
    evaluation.refresh_from_db()
    assert evaluation.state == "concluded" and evaluation.shelf_life_months == longest
    body = client.get(response["Location"]).content.decode()
    assert f"Concluded · {longest} months" in body and "As concluded" in body
    assert (
        shelf_life.figures(shelf_life.replay(evaluation.content)) == (evaluation.content["figures"])
    )
    # A concluded evaluation takes no change, withdrawal or second signature.
    for name in ("shelf_life_change", "shelf_life_withdraw"):
        moved = client.get(reverse(f"stability:{name}", args=[evaluation.pk]))
        assert moved.status_code == 302
    assert client.get(conclude).status_code == 403


def test_change_and_withdraw_pages(client, people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = drafted(client, people, studies[0])
    change = reverse("stability:shelf_life_change", args=[evaluation.pk])
    client.force_login(people["quality2"])
    page = client.get(change).content.decode()
    assert all(study.identifier in page for study in studies)
    response = client.post(
        change,
        {
            "expected_revision": 1,
            "studies": [studies[0].pk, studies[1].pk],
            "direction": "either",
            "purpose": "Synthetic annual review",
            "reason": "Third batch left out",
        },
    )
    assert response.status_code == 302
    evaluation.refresh_from_db()
    assert evaluation.revision == 2 and evaluation.study_links.count() == 2
    stale = client.post(
        change,
        {
            "expected_revision": 1,
            "studies": [studies[0].pk],
            "direction": "either",
            "purpose": "Synthetic annual review",
            "reason": "Stale",
        },
    )
    assert stale.status_code == 422 and "Record changed" in stale.content.decode()
    withdraw = reverse("stability:shelf_life_withdraw", args=[evaluation.pk])
    response = client.post(withdraw, {"expected_revision": 2, "reason": "Superseded plan"})
    assert response.status_code == 302
    evaluation.refresh_from_db()
    assert evaluation.state == "withdrawn"
    body = client.get(reverse("stability:shelf_life_detail", args=[evaluation.pk])).content
    assert b"Withdrawn" in body


def test_the_list_filters_and_the_study_and_overview_lead_to_it(client, people):
    studies, _ = studies_with_results(people, FALLING)
    evaluation = drafted(client, people, studies[0])
    listing = reverse("stability:shelf_life_list")
    client.force_login(people["auditor"])
    body = client.get(listing, {"status": "draft"}).content.decode()
    assert evaluation.identifier in body
    assert (
        evaluation.identifier not in client.get(listing, {"status": "concluded"}).content.decode()
    )
    assert evaluation.identifier in client.get(listing, {"q": "SYN-SL"}).content.decode()
    study = client.get(reverse("stability:study_detail", args=[studies[1].pk])).content.decode()
    assert "Shelf-life evaluations" in study and evaluation.identifier in study
    assert "Evaluate shelf life" not in study
    client.force_login(people["quality"])
    study = client.get(reverse("stability:study_detail", args=[studies[1].pk])).content.decode()
    assert f"{reverse('stability:shelf_life_new')}?study={studies[1].pk}" in study
    overview = client.get(reverse("stability:overview")).content.decode()
    assert "Shelf-life evaluations in draft" in overview


def test_a_concluded_evaluation_shows_the_figures_it_froze(client, people, monkeypatch):
    from stability import regression

    studies, _ = studies_with_results(people, FALLING)
    evaluation = drafted(client, people, studies[0])
    client.force_login(people["quality2"])
    conclude = reverse("stability:shelf_life_conclude", args=[evaluation.pk])
    page = client.get(conclude).content.decode()
    shown = re.search(r'name="data_hash" value="([0-9a-f]{64})"', page).group(1)
    response = client.post(
        conclude,
        {
            "signature_username": people["quality2"].username,
            "expected_revision": 1,
            "data_hash": shown,
            "outcome": "supported",
            "shelf_life_months": 12,
            "conclusion": "Synthetic conclusion",
            "pin": PIN,
            "reason": "Independent statistical review",
        },
    )
    assert response.status_code == 302
    detail = reverse("stability:shelf_life_detail", args=[evaluation.pk])
    body = client.get(detail).content.decode()
    assert "Pooled: one line for all studies" in body and "As signed" not in body
    # A later release that tested poolability at another level would choose another model; the
    # page keeps what was signed and says the drawing differs.
    monkeypatch.setattr(regression, "SIGNIFICANCE", Decimal("0.999"))
    body = client.get(detail).content.decode()
    assert "Pooled: one line for all studies" in body
    assert "As signed" in body and "now give other figures" in body


def test_a_limit_that_never_meets_the_criterion_offers_only_the_search_horizon(client, people):
    studies, _ = studies_with_results(people, [("99.0", "99.5", "100.0", "100.4")])
    evaluation = drafted(client, people, studies[0])
    client.force_login(people["quality2"])
    page = client.get(reverse("stability:shelf_life_conclude", args=[evaluation.pk]))
    body = page.content.decode()
    assert "120 months" in body and "The search horizon" in body
    assert "Before concluding" in body  # fewer than three studies; beyond the data
