"""Replacement of a lot's requirements through the pages: the lot's requirements page, the
signed replacement, and what the testing pages show afterwards."""

import re

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from analytical.models import AnalyticalTest
from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin
from quality.models import Lot
from sampling import services as sampling
from sampling.models import LotAssignment
from tests.test_integrated_journey import PASSWORD, PIN
from tests.test_requirement_replacement import (
    REASON,
    complete,
    new_specification_version,
    world,  # noqa: F401
)
from tests.test_result_types_journey import record, submit

pytestmark = pytest.mark.django_db(transaction=True)


def text(response):
    return " ".join(response.content.decode().split())


def basis_of(page):
    """The token the replacement page carries of what it showed."""
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


def member(django_user_model, name, *roles):
    person = django_user_model.objects.create_user(username=name, password=PASSWORD)
    person.groups.add(*[Group.objects.get_or_create(name=role)[0] for role in roles])
    set_pin(actor=person, pin=PIN, password=PASSWORD)
    return person


def test_quality_reviews_and_signs_the_replacement(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    complete(world, "identity", "assay")
    lot_url = reverse("sampling:lot", args=[lot.pk])
    replace_url = reverse("sampling:replace", args=[lot.pk])
    approver = people["approver"]
    client.force_login(approver)

    # Nothing was revised: the page explains and sends the reader back, without a PIN.
    response = client.get(replace_url, follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    assert "There is nothing to replace" in text(response)

    assert replace_url not in text(client.get(lot_url))
    new_specification_version(world)
    lot.refresh_from_db()
    listed = text(client.get(lot_url))
    assert replace_url in listed and ">Replace requirements</a>" in listed
    assert (
        "The versions in force now are not the ones frozen for this lot: specification "
        "synthetic-rt-spec v2, 1 requirement changed." in listed
    )
    page = text(client.get(replace_url))
    assert "Versions in force now" in page and "synthetic-rt-spec v1" in page
    assert "synthetic-rt-spec v2</a>" in page and "v1 · kept" in page
    assert "98 – 102 % · rounded to 2 decimals · method synthetic-rt-method v1" in page
    assert "98.5 – 101.5 % · rounded to 2 decimals · method synthetic-rt-method v1" in page
    assert page.count(">Unchanged<") == 4 and page.count(">Changed<") == 1
    assert page.count(">Carries over<") == 4 and "requirement changed" in page
    assert "1 test is superseded and 4 carry over" in page
    assert "Sign and replace requirements" in page and 'name="pin"' in page
    assert f"lot revision {lot.revision + 1}" in page

    # A refused signature keeps the page and changes nothing.
    for bad, message in (
        ({"pin": "00000000"}, "Signature PIN was not accepted."),
        ({"signature_username": "someone-else"}, "Enter your own signing username and PIN."),
        ({"basis": "0" * 64}, "changed after this page was opened"),
        ({"expected_revision": lot.revision - 1}, "Record changed. Reload and review"),
        ({"reason": ""}, "This field is required."),
    ):
        response = client.post(replace_url, signing(approver, lot, page, **bad))
        assert response.status_code == 422, bad
        assert message in text(response), bad
        assert 'value="00000000"' not in text(response)
    assert LotAssignment.objects.filter(lot=lot).count() == 1
    assert not AnalyticalTest.objects.filter(state="superseded").exists()

    response = client.post(replace_url, signing(approver, lot, page), follow=True)
    assert response.redirect_chain == [(lot_url, 302)]
    body = text(response)
    assert "Requirements replaced and signed. Assign the required tests again" in body
    assert "These requirements replaced the earlier ones during testing." in body
    assert REASON in body
    assert "with the meaning requirements replaced" in body
    assert "Specification synthetic-rt-spec v1 replaced by synthetic-rt-spec v2." in body
    assert "superseded (had reported 99.60)" in body and "carried over" in body
    assert "Requirements replaced during testing" not in body  # the earlier one was assigned
    assert 'data-audit-action="lot.requirements_replaced"' in body  # in the history
    signature = ElectronicSignature.objects.get(object_type="quality.lot")
    assert signature.meaning == "requirements_replaced" and signature.signer == approver
    assert f"bound to lot revision {signature.revision}" in body

    # Nothing is left to replace: the action is gone, and its address explains.
    assert replace_url not in body and "Newer versions" not in body
    response = client.get(replace_url, follow=True)
    assert "There is nothing to replace" in text(response)

    assay = world["tests"]["assay"]
    detail = text(client.get(reverse("analytical:test_detail", args=[assay.pk])))
    assert "Superseded · requirements replaced" in detail
    assert "It takes no more work and does not count toward the lot" in detail
    assert reverse("analytical:observation_new", args=[assay.pk]) not in detail
    testing = text(client.get(reverse("analytical:lot_testing", args=[lot.pk])))
    assert "Superseded · requirements replaced" in testing
    assert "no assay test under the lot&#x27;s current requirements" in testing
    listing = text(client.get(reverse("analytical:test_list"), {"state": "superseded"}))
    assert assay.label in listing and world["tests"]["identity"].label not in listing

    # The analyst repeats the superseded test from the lot's testing page.
    client.force_login(people["analyst"])
    response = client.post(
        reverse("analytical:lot_testing", args=[lot.pk]),
        {"sample": assay.sample_id, "reason": "Repeat the superseded test"},
        follow=True,
    )
    assert "Assigned 1 test(s)" in text(response)
    repeat = AnalyticalTest.objects.get(lot=lot, kind="revised")
    detail = text(client.get(reverse("analytical:test_detail", args=[repeat.pk])))
    assert "Repeat under replaced requirements" in text(
        client.get(reverse("analytical:lot_testing", args=[lot.pk]))
    )
    assert f">{assay.label}</a>" in detail and "98.5" in detail


def test_the_replacement_page_is_for_quality_who_authored_nothing(
    client,
    world,  # noqa: F811
    django_user_model,
):
    people, lot = world["people"], world["lot"]
    complete(world, "assay")
    new_specification_version(world)
    replace_url = reverse("sampling:replace", args=[lot.pk])
    lot_url = reverse("sampling:lot", args=[lot.pk])
    readers = {
        "reviewer": people["reviewer"],
        "auditor": member(django_user_model, "rr_auditor", "auditor"),
        "admin": member(django_user_model, "rr_admin", "admin"),
        "analyst": member(django_user_model, "rr_analyst", "analyst"),
    }
    before = AuditEvent.objects.count()
    for name, person in readers.items():
        client.force_login(person)
        assert client.get(replace_url).status_code == 403, name
        assert client.post(replace_url, {"pin": PIN}).status_code == 403, name
        listed = text(client.get(lot_url))
        assert replace_url not in listed and "Newer versions" in listed, name
    # The world's analyst also holds the quality role, and received and tested this lot.
    author = people["analyst"]
    client.force_login(author)
    response = client.get(replace_url)
    assert response.status_code == 403
    page = text(response)
    assert "Not permitted" in page and "Someone who authored none of it" in page
    assert 'name="pin"' not in page and "Sign and replace requirements" not in page
    lot.refresh_from_db()
    response = client.post(
        replace_url,
        {
            "signature_username": author.username,
            "expected_revision": lot.revision,
            "basis": sampling.replacement_preview(lot).basis,
            "reason": REASON,
            "pin": PIN,
        },
    )
    assert response.status_code == 403
    assert LotAssignment.objects.filter(lot=lot).count() == 1
    assert AuditEvent.objects.count() == before
    assert not ElectronicSignature.objects.filter(object_type="quality.lot").exists()


def test_the_page_states_why_a_replacement_is_refused(client, world):  # noqa: F811
    people, lot = world["people"], world["lot"]
    assay = world["tests"]["assay"]
    record(world, assay, "97.00")
    _, investigation = submit(world, assay)
    record(world, world["tests"]["tamc"], "<10")
    new_specification_version(world, low="96.0")
    client.force_login(people["approver"])
    replace_url = reverse("sampling:replace", args=[lot.pk])
    response = client.get(replace_url)
    assert response.status_code == 200
    page = text(response)
    assert "The requirements cannot be replaced now" in page
    assert f"{investigation.label} is open on this lot" in page
    assert "Nothing was changed" in page
    assert 'name="pin"' not in page and "Sign and replace requirements" not in page
    lot.refresh_from_db()
    response = client.post(
        replace_url,
        {
            "signature_username": people["approver"].username,
            "expected_revision": lot.revision,
            "basis": "0" * 64,
            "reason": REASON,
            "pin": PIN,
        },
    )
    assert response.status_code == 200 and 'name="pin"' not in text(response)
    assert LotAssignment.objects.filter(lot=lot).count() == 1
    assert Lot.objects.get(pk=lot.pk).revision == lot.revision


def test_before_testing_the_lot_page_offers_assignment_not_replacement(client, django_user_model):
    from tests.test_result_types_journey import build_world

    data = build_world(django_user_model, with_assay=True)
    lot = data["lot"]
    sampling.assign_requirements(
        actor=data["people"]["analyst"],
        lot=lot,
        material=data["material"],
        stage="incoming",
        reason="Assign approved synthetic policy",
    )
    client.force_login(data["people"]["approver"])
    page = text(client.get(reverse("sampling:lot", args=[lot.pk])))
    replace_url = reverse("sampling:replace", args=[lot.pk])
    assert reverse("sampling:assign", args=[lot.pk]) in page and replace_url not in page
    response = client.get(replace_url, follow=True)
    assert "Testing has not started on this lot" in text(response)


def test_a_method_approval_names_the_tests_in_progress_frozen_to_the_retired_version(
    client,
    world,  # noqa: F811
):
    from datetime import timedelta

    from django.utils import timezone

    from catalog import services as catalog
    from catalog.models import Method

    people = world["people"]
    complete(world, "identity")  # reviewed: no longer in progress
    method = Method.objects.get(code="synthetic-rt-method")
    draft = catalog.new_method_revision(
        actor=people["author"],
        method=method,
        technique="Gravimetry",
        document_ref="SOP-SYN-RT rev 2",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-RT rev 2",
        effective_from=timezone.now() - timedelta(minutes=1),
        effective_until=timezone.now() + timedelta(days=400),
        reason="Synthetic method revision",
    )
    client.force_login(people["approver"])
    page = text(client.get(reverse("catalog:method_approve", args=[draft.pk])))
    assert "synthetic-rt-method v1</strong> stops applying at the moment of your signature" in page
    assert "4 tests in progress are frozen to it and keep it." in page
    assert "QC batch of that version" not in page  # the method does not run in batches
