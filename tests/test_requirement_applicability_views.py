"""Several scopes and rule sets on a lot through the pages: the assignment form, the lot's
requirements page, the signed decision of conflicting requirements, the replacement with a
choice, and what the rule set, lot record and disposition pages show."""

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import AuditEvent, ElectronicSignature
from quality.models import Lot
from sampling import services as sampling
from sampling.models import LotAssignment
from tests.test_integrated_journey import PIN
from tests.test_requirement_applicability import (
    ASSAY,
    CONFLICT,
    REASON,
    TIGHT,
    WATER,
    assign,
    complete,
    conflicting,
    decide,
    extra_rules,
    overlay,
    revise,
    sample_and_tests,
    world,  # noqa: F401
)

pytestmark = pytest.mark.django_db(transaction=True)


def text(response):
    return " ".join(response.content.decode().split())


def basis_of(page):
    return re.search(r'name="basis" value="([0-9a-f]{64})"', page).group(1)


def signing(user, lot, page, **changes):
    data = {
        "signature_username": user.username,
        "expected_revision": lot.revision,
        "basis": basis_of(page),
        "reason": REASON,
        "pin": PIN,
    }
    data.update(changes)
    return data


def test_requirements_are_assigned_under_several_scopes_through_the_form(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    overlay(world, "eu-market", ASSAY, WATER)
    extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay"])
    url = reverse("sampling:assign", args=[lot.pk])
    client.force_login(people["analyst"])
    page = text(client.get(url))
    assert 'name="scopes"' in page and 'value="general"' in page
    assert "Scopes in the configuration" in page and "general, cust-a, eu-market" in page
    form = {
        "material": world["material"].pk,
        "stage": "incoming",
        "reason": "Lot for the synthetic market and customer",
    }
    response = client.post(url, form | {"scopes": "general, eu market!"})
    assert response.status_code == 422
    assert "is not a scope name" in text(response)
    assert not LotAssignment.objects.filter(lot=lot).exists()

    response = client.post(url, form | {"scopes": "eu-market cust-a,general"}, follow=True)
    assert response.redirect_chain == [(reverse("sampling:lot", args=[lot.pk]), 302)]
    assignment = sampling.current_assignment(lot)
    assert assignment.status == "ready" and assignment.scopes == ["general", "cust-a", "eu-market"]
    shown = text(response)
    assert "Stage and scopes" in shown and "general, cust-a, eu-market" in shown
    assert "synthetic-rt-eu-market v1</a> (eu-market)" in shown
    assert "Additional rule sets" in shown and "synthetic-cust-rules v1 · requires assay" in shown
    assert '<th scope="col">Stated by</th>' in shown and "<td>general, eu-market</td>" in shown
    # The form opens again with what the lot was assigned under.
    assert 'value="general, cust-a, eu-market"' in text(client.get(url))
    # The lot record names the rule sets the requirements added.
    record = text(client.get(reverse("quality:lot_detail", args=[lot.pk])))
    assert "Applied in addition by the lot's requirements: synthetic-cust-rules v1" in record


def test_quality_decides_conflicting_requirements_on_the_page(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    conflicting(world)
    lot.refresh_from_db()
    lot_url = reverse("sampling:lot", args=[lot.pk])
    decide_url = reverse("sampling:decide", args=[lot.pk])

    # A reviewer reads the conflict and is offered no decision.
    client.force_login(people["reviewer"])
    listed = text(client.get(lot_url))
    assert CONFLICT in listed and "Requirements the specifications state differently" in listed
    assert "98 – 102 %" in listed and "99 – 101 %" in listed
    assert decide_url not in listed
    assert client.get(decide_url).status_code == 403
    assert client.post(decide_url, {}).status_code == 403

    approver = people["approver"]
    client.force_login(approver)
    listed = text(client.get(lot_url))
    assert decide_url in listed and ">Decide conflicting requirements</a>" in listed
    page = text(client.get(decide_url))
    assert "A lot has to meet every specification that binds it." in page
    assert "The statements differ in: limits." in page
    assert "Specifications in force" in page and "Requirements stated one way" in page
    assert "<dt>Sampling plan</dt><dd>synthetic-rt-plan v1</dd>" in page
    assert "<strong>synthetic-rt-eu-market v1</strong> (eu-market) · Assay: 99 – 101 %" in page
    assert page.count('type="radio" name="choice-assay"') == 2
    assert 'value="eu-market"' in page and 'value="general"' in page and "checked" not in page
    assert "requirements decided" in page and f"revision <strong>{lot.revision}</strong>" in page

    # Without a choice nothing is signed, and the PIN is not kept.
    response = client.post(decide_url, signing(approver, lot, page))
    assert response.status_code == 422
    assert "Choose which requirement applies" in text(response)
    assert sampling.current_assignment(lot).status == "hold"
    # A wrong PIN is refused and recorded; the choice made stays selected on the page.
    denied = AuditEvent.objects.filter(action="signature.denied").count()
    response = client.post(
        decide_url, signing(approver, lot, page, pin="00000000") | {"choice-assay": "eu-market"}
    )
    assert response.status_code == 422 and "PIN was not accepted" in text(response)
    assert AuditEvent.objects.filter(action="signature.denied").count() == denied + 1
    assert re.search(r'value="eu-market"[^>]* checked', text(response))
    assert PIN not in text(response) and "00000000" not in text(response)

    response = client.post(
        decide_url, signing(approver, lot, page) | {"choice-assay": "eu-market"}, follow=True
    )
    assert response.redirect_chain == [(lot_url, 302)]
    shown = text(response)
    assert "Decision signed. The requirements are frozen for this lot." in shown
    assert "quality decided which requirement applies" in shown
    assert f"Signed by <strong>{approver.get_full_name()}</strong>" in shown
    assert "with the meaning requirements decided" in shown and REASON in shown
    assert "<strong>synthetic-rt-eu-market v1</strong> (eu-market) applies, 99 – 101 %" in shown
    assert "Not applied: synthetic-rt-spec v1 (general), 98 – 102 %" in shown
    assert decide_url not in shown
    current = sampling.current_assignment(lot)
    assert current.origin == "decided" and current.assigned_by == approver
    signature = ElectronicSignature.objects.get(meaning="requirements_decided")
    assert signature.revision == Lot.objects.get(pk=lot.pk).revision
    # Decided once: the page sends the reader back.
    response = client.get(decide_url, follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    assert "not held for a decision" in text(response)
    # The earlier hold stays in the lot's history.
    assert "Applicability hold" in shown and "Earlier requirement assignments" in shown


def test_a_refused_signature_leaves_a_page_that_can_be_signed(client, world):  # noqa: F811
    """After a stale refusal the page shows what applies now and carries its token."""
    people, lot = world["people"], world["lot"]
    conflicting(world)
    lot.refresh_from_db()
    decide_url = reverse("sampling:decide", args=[lot.pk])
    approver = people["approver"]
    client.force_login(approver)
    opened = text(client.get(decide_url))
    revise(world, "synthetic-rt-eu-market", {**TIGHT, "lower_limit": Decimal("99.5")})
    response = client.post(
        decide_url, signing(approver, lot, opened) | {"choice-assay": "eu-market"}
    )
    refused = text(response)
    assert response.status_code == 422
    assert "changed after this page was opened" in refused
    assert "99.5 – 101 %" in refused and "synthetic-rt-eu-market v2" in refused
    assert basis_of(refused) != basis_of(opened)
    assert basis_of(refused) == sampling.decision_preview(lot).basis
    assert sampling.current_assignment(lot).status == "hold"
    # The statement that was chosen is the one that changed: nothing stays selected.
    assert refused.count('type="radio" name="choice-assay"') == 2 and "checked" not in refused
    response = client.post(decide_url, signing(approver, lot, refused))
    assert response.status_code == 422 and "Choose which requirement applies" in text(response)
    # Reviewed as shown and signed again, with the PIN entered again.
    assert 'name="pin"' in refused and PIN not in refused
    response = client.post(
        decide_url, signing(approver, lot, refused) | {"choice-assay": "eu-market"}, follow=True
    )
    assert response.redirect_chain == [(reverse("sampling:lot", args=[lot.pk]), 302)]
    (item,) = sampling.current_assignment(lot).payload["decisions"]
    assert item["text"].startswith("99.5 – 101 %")


def test_after_a_decision_only_quality_assigns_the_requirements_again(
    client,
    world,  # noqa: F811
    django_user_model,
):
    from django.contrib.auth.models import Group

    from tests.test_integrated_journey import PASSWORD

    bench = django_user_model.objects.create_user(username="rt_bench", password=PASSWORD)
    bench.groups.add(Group.objects.get_or_create(name="analyst")[0])
    lot = world["lot"]
    conflicting(world)
    lot_url = reverse("sampling:lot", args=[lot.pk])
    assign_url = reverse("sampling:assign", args=[lot.pk])
    client.force_login(bench)
    assert assign_url in text(client.get(lot_url))
    decide(world)
    assert assign_url not in text(client.get(lot_url))
    response = client.get(assign_url, follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    assert "Only quality assigns its requirements again" in text(response)
    form = {"material": world["material"].pk, "stage": "incoming", "scopes": "general"}
    response = client.post(assign_url, form | {"reason": "Synthetic"}, follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    assert sampling.current_assignment(lot).origin == "decided"
    client.force_login(world["people"]["author"])
    assert assign_url in text(client.get(lot_url))


def test_choices_are_read_only_from_names_that_could_be_codes():
    from django.http import QueryDict

    from sampling.forms import chosen_scopes

    data = QueryDict(
        "choice-assay=eu-market&choice-water=&choice-=x&choice-a b=x&choice-id=<script>"
        "&other=1&choice-" + "x" * 81 + "=general&choice-tamc=cust_a"
    )
    assert chosen_scopes(data) == {"assay": "eu-market", "tamc": "cust_a"}


def test_a_person_who_recorded_the_lots_data_is_shown_no_pin(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    conflicting(world)
    lot.refresh_from_db()
    decide_url = reverse("sampling:decide", args=[lot.pk])
    receiver = people["analyst"]  # received the lot and also holds the quality role
    client.force_login(receiver)
    # The lot page explains who decides and offers this person no decision.
    listed = text(client.get(reverse("sampling:lot", args=[lot.pk])))
    assert "recorded none of this lot's data decides" in listed and decide_url not in listed
    response = client.get(decide_url)
    page = text(response)
    assert response.status_code == 403
    assert "Someone who authored none of it decides which requirement applies." in page
    assert "Independence cannot be bypassed by any role" in page
    assert 'name="pin"' not in page and 'type="radio"' not in page
    response = client.post(
        decide_url,
        {
            "signature_username": receiver.username,
            "expected_revision": lot.revision,
            "basis": sampling.decision_preview(lot).basis,
            "reason": REASON,
            "pin": PIN,
            "choice-assay": "eu-market",
        },
    )
    assert response.status_code == 403
    assert sampling.current_assignment(lot).status == "hold"


def test_a_decision_page_says_what_else_holds_the_lot(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    conflicting(world)
    extra_rules(world, "synthetic-eu-rules", {"scopes": ["eu-market"]}, ["water"])
    client.force_login(people["approver"])
    # The lot page explains; the decision is offered once the configuration is complete.
    listed = text(client.get(reverse("sampling:lot", args=[lot.pk])))
    assert "once the other reasons above are resolved in the configuration" in listed
    assert reverse("sampling:decide", args=[lot.pk]) not in listed
    page = text(client.get(reverse("sampling:decide", args=[lot.pk])))
    assert "The requirements cannot be decided now" in page
    assert "requires tests that no specification applying to the lot requires: water" in page
    assert 'name="pin"' not in page and 'type="radio"' not in page
    assert "99 – 101 %" in page
    # A signature posted all the same signs nothing and says so with its status.
    lot.refresh_from_db()
    response = client.post(
        reverse("sampling:decide", args=[lot.pk]),
        {
            "signature_username": people["approver"].username,
            "expected_revision": lot.revision,
            "basis": sampling.decision_preview(lot).basis,
            "reason": REASON,
            "pin": PIN,
            "choice-assay": "eu-market",
        },
    )
    assert response.status_code == 422
    assert sampling.current_assignment(lot).status == "hold"


def test_a_conflict_that_arises_in_testing_is_chosen_on_the_replacement_page(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    overlay(world, "eu-market", ASSAY)
    assign(world, "general", "eu-market")
    complete(world, sample_and_tests(world))
    revise(world, "synthetic-rt-eu-market", TIGHT)
    lot.refresh_from_db()
    lot_url = reverse("sampling:lot", args=[lot.pk])
    replace_url = reverse("sampling:replace", args=[lot.pk])
    approver = people["approver"]
    client.force_login(approver)
    listed = text(client.get(lot_url))
    assert "the specifications in force state assay differently" in listed
    assert replace_url in listed

    page = text(client.get(replace_url))
    assert "Requirements stated differently" in page
    assert page.count('type="radio" name="choice-assay"') == 2 and "checked" not in page
    assert "Choose a requirement for each test" in page
    assert 'name="pin"' not in page and "Sign replacement" not in page

    page = text(client.get(replace_url, {"choice-assay": "eu-market"}))
    assert re.search(r'value="eu-market"[^>]* checked', page)
    assert "Your signature confirms the choice for the versions now in force." in page
    assert '<input type="hidden" name="choice-assay" value="eu-market">' in page
    assert "Sign replacement" in page and "1 test is superseded and 4 carry over" in page
    assert "synthetic-rt-eu-market v1" in page and "synthetic-rt-eu-market v2" in page

    # Signed without the choice the page showed, nothing changes.
    response = client.post(replace_url, signing(approver, lot, page))
    assert response.status_code == 422 and "Nothing was signed." in text(response)
    assert sampling.current_assignment(lot).origin == "assigned"
    response = client.post(
        replace_url, signing(approver, lot, page) | {"choice-assay": "eu-market"}, follow=True
    )
    assert response.redirect_chain == [(lot_url, 302)]
    shown = text(response)
    assert "Requirements replaced and signed." in shown
    assert (
        'The specifications state <span class="vr-id">assay</span> differently: '
        "synthetic-rt-eu-market v2 (eu-market) applies, 99 – 101 %" in shown
    )
    assert "Specification synthetic-rt-eu-market v1 replaced by synthetic-rt-eu-market v2." in shown
    assert "Specification synthetic-rt-spec v1 replaced" not in shown
    current = sampling.current_assignment(lot)
    assert current.origin == "replaced" and current.payload["decisions"][0]["scope"] == "eu-market"
    # The disposition page tells the signer about the decision and what the lot is under.
    disposition = text(client.get(reverse("quality:disposition", args=[lot.pk])))
    assert "The specifications that apply to this lot state assay differently (limits)." in (
        disposition
    )
    assert "requirements were assigned under the scopes general, eu-market" in disposition

    # Nothing has been revised since, yet the choice can be reviewed again and changed by
    # another signed replacement: the page stays open and signs nothing by itself.
    lot.refresh_from_db()
    listed = text(client.get(lot_url))
    assert "To apply another one" in listed and replace_url in listed
    page = text(client.get(replace_url))
    assert "there is nothing to replace" in page and 'name="pin"' not in page
    assert re.search(r'value="eu-market"[^>]* checked', page)
    assert "Specifications frozen for the lot" in page
    unsigned = {
        "signature_username": approver.username,
        "expected_revision": lot.revision,
        "basis": "0" * 64,
        "reason": REASON,
        "pin": PIN,
    }
    assert client.post(replace_url, unsigned).status_code == 422
    assert sampling.current_assignment(lot).payload["decisions"][0]["scope"] == "eu-market"
    page = text(client.get(replace_url, {"choice-assay": "general"}))
    assert "Sign replacement" in page and "0 tests are superseded" in page
    response = client.post(
        replace_url, signing(approver, lot, page) | {"choice-assay": "general"}, follow=True
    )
    assert response.redirect_chain == [(lot_url, 302)]
    assert sampling.current_assignment(lot).payload["decisions"][0]["scope"] == "general"


def test_a_stale_replacement_asks_for_the_choice_again(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    overlay(world, "eu-market", ASSAY)
    assign(world, "general", "eu-market")
    complete(world, sample_and_tests(world))
    revise(world, "synthetic-rt-eu-market", TIGHT)
    lot.refresh_from_db()
    replace_url = reverse("sampling:replace", args=[lot.pk])
    approver = people["approver"]
    client.force_login(approver)
    opened = text(client.get(replace_url, {"choice-assay": "eu-market"}))
    assert "Sign replacement" in opened
    # The statement that was chosen is revised before the signature arrives.
    revise(world, "synthetic-rt-eu-market", {**TIGHT, "upper_limit": Decimal("100.5")})
    response = client.post(
        replace_url, signing(approver, lot, opened) | {"choice-assay": "eu-market"}
    )
    refused = text(response)
    assert response.status_code == 422
    assert "changed after this page was opened. Nothing was signed." in refused
    assert "99 – 100.5 %" in refused and "checked" not in refused
    assert 'name="pin"' not in refused and "Sign replacement" not in refused
    assert sampling.current_assignment(lot).origin == "assigned"
    # Chosen again on what applies now, reviewed and signed.
    page = text(client.get(replace_url, {"choice-assay": "eu-market"}))
    response = client.post(
        replace_url, signing(approver, lot, page) | {"choice-assay": "eu-market"}, follow=True
    )
    assert response.redirect_chain == [(reverse("sampling:lot", args=[lot.pk]), 302)]
    (item,) = sampling.current_assignment(lot).payload["decisions"]
    assert item["text"].startswith("99 – 100.5 %")


def test_rule_set_pages_say_where_an_additional_rule_set_applies(client, world):  # noqa: F811
    people = world["people"]
    extra_rules(world, "synthetic-cust-rules", {"scopes": ["cust-a"]}, ["assay"])
    assign(world, "general", "cust-a")
    draft = extra_rules(
        world,
        "synthetic-cust-rules",
        {"scopes": ["cust-a"], "stages": ["incoming"]},
        ["assay", "tamc"],
        approved=False,
    )
    client.force_login(people["approver"])
    listed = text(client.get(reverse("core:rules")))
    assert "A rule set whose policy states <code>applies_to</code> is an additional one" in listed
    assert "Applies in addition to a lot's own rule set · scopes cust-a" in listed
    assert "· stages incoming · scopes cust-a" in listed
    page = text(client.get(reverse("core:rule_approve", args=[draft.pk])))
    assert "<dt>Applies to</dt>" in page and "stages incoming; scopes cust-a;" in page
    # The lot whose requirements froze version 1 is counted where its retirement is shown.
    assert "1 lot in quarantine is on it" in page
    # A refused policy is reported on the form.
    client.force_login(people["author"])
    response = client.post(
        reverse("core:rules"),
        {
            "code": "synthetic-bad-rules",
            "segment": "chemical",
            "policy": '{"required_tests": ["assay"], "review_meaning": "reviewed", '
            '"disposition_meaning": "approved", "applies_to": {"stages": ["release"]}}',
            "effective_from": "2026-01-01 00:00",
            "reason": "Synthetic",
        },
    )
    assert "applies_to names unknown stages: release." in text(response)
