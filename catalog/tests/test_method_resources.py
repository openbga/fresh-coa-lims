"""Suitable instruments, reagents and standards of a method version: who lists them, the register
names they must match, the draft-only database guard, the approved content and the method page."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalog import services
from catalog.models import MAX_METHOD_RESOURCES, MethodResource
from core.models import AuditEvent
from laboratory.models import Calibration, Equipment, ReagentLot

from .factories import PASSWORD, approve, method_revision

pytestmark = pytest.mark.django_db(transaction=True)


def equipment(actor, asset, category, **extra):
    return Equipment.objects.create(
        asset_id=asset, description=f"Synthetic {category}", category=category,
        created_by=actor, **extra,
    )  # fmt: skip


def lot(actor, identifier, name, kind="reference_standard", **extra):
    today = timezone.localdate()
    values = {
        "identifier": identifier,
        "kind": kind,
        "name": name,
        "lot_number": f"L-{identifier}",
        "received_on": today - timedelta(days=10),
        "expiry_date": today + timedelta(days=200),
        "recorded_by": actor,
    } | extra
    return ReagentLot.objects.create(**values)


@pytest.fixture
def register(people):
    analyst = people["analyst"]
    return {
        "hplc": equipment(analyst, "SYN-LC-01", "HPLC"),
        "balance": equipment(analyst, "SYN-BAL-01", "Analytical  balance"),
        "standard": lot(analyst, "SYN-RS-1", "Caffeine RS"),
        "solvent": lot(analyst, "SYN-R-1", "Acetonitrile", kind="reagent"),
    }


def add(actor, revision, kind="instrument", name="HPLC", **extra):
    return services.add_method_resource(
        actor=actor, revision=revision, kind=kind, name=name, reason="Suitable", **extra
    )


def test_quality_lists_resources_named_as_the_register_names_them(people, register):
    author = people["author"]
    revision = method_revision(author)
    start = revision.revision
    hplc = add(author, revision, name="  hplc ", method_qualified=True)
    balance = add(author, revision, name="analytical balance", required=False)
    standard = add(author, revision, kind="reference_standard", name="CAFFEINE rs")
    # Kept as the register first recorded it, spaces tidied.
    assert [(r.kind, r.name, r.required, r.method_qualified) for r in revision.resources.all()] == [
        ("instrument", "HPLC", True, True),
        ("instrument", "Analytical balance", False, False),
        ("reference_standard", "Caffeine RS", True, False),
    ]
    revision.refresh_from_db()
    assert revision.revision == start + 3
    events = AuditEvent.objects.filter(action="method_revision.resource_added")
    assert [e.after for e in events] == [hplc.content(), balance.content(), standard.content()]
    assert {e.reason for e in events} == {"Suitable"}
    assert str(hplc) == "Instrument: HPLC"


@pytest.mark.parametrize(
    ("kind", "name", "field"),
    [
        ("instrument", "Spectrometer", "name"),  # no equipment of that category
        ("reagent", "Caffeine RS", "name"),  # a standard's name, not a reagent's
        ("prepared_solution", "Acetonitrile", "name"),
        ("instrument", "   ", "name"),
        ("column", "HPLC", "kind"),
    ],
)
def test_a_name_the_register_does_not_record_is_refused(people, register, kind, name, field):
    revision = method_revision(people["author"])
    with pytest.raises(ValidationError) as refused:
        add(people["author"], revision, kind=kind, name=name)
    assert field in refused.value.message_dict
    assert not MethodResource.objects.exists()


def test_duplicates_qualification_of_lots_and_the_limit_are_refused(people, register):
    author = people["author"]
    revision = method_revision(author)
    add(author, revision)
    with pytest.raises(ValidationError, match="already lists it"):
        add(author, revision, name="Hplc")
    with pytest.raises(ValidationError, match="Only an instrument"):
        add(author, revision, kind="reagent", name="Acetonitrile", method_qualified=True)
    for number in range(MAX_METHOD_RESOURCES - 1):
        lot(people["analyst"], f"SYN-R-X{number}", f"Reagent {number}", kind="reagent")
        add(author, revision, kind="reagent", name=f"Reagent {number}")
    lot(people["analyst"], "SYN-R-LAST", "One too many", kind="reagent")
    with pytest.raises(ValidationError, match="at most 20"):
        add(author, revision, kind="reagent", name="One too many")
    assert revision.resources.count() == MAX_METHOD_RESOURCES


@pytest.mark.parametrize("role", ["analyst", "reviewer", "admin", "auditor"])
def test_only_quality_lists_or_removes_resources(people, register, role):
    revision = method_revision(people["author"])
    item = add(people["author"], revision)
    with pytest.raises(PermissionDenied):
        add(people[role], revision, name="Analytical balance")
    with pytest.raises(PermissionDenied):
        services.remove_method_resource(actor=people[role], item=item, reason="No")
    assert revision.resources.count() == 1


def test_removal_from_a_draft_is_audited_and_checks_the_revision(people, register):
    author = people["author"]
    revision = method_revision(author)
    item = add(author, revision)
    revision.refresh_from_db()
    with pytest.raises(ValidationError, match="changed"):
        services.remove_method_resource(
            actor=author, item=item, reason="Stale", expected_revision=revision.revision - 1
        )
    services.remove_method_resource(
        actor=author, item=item, reason="Not used", expected_revision=revision.revision
    )
    assert not revision.resources.exists()
    event = AuditEvent.objects.get(action="method_revision.resource_removed")
    assert (event.before, event.reason) == (item.content(), "Not used")


def test_approval_freezes_the_lines_and_the_database_refuses_changes(people, register):
    author = people["author"]
    revision = method_revision(author)
    item = add(author, revision)
    with pytest.raises(DatabaseError, match="never changed"), transaction.atomic():
        MethodResource.objects.filter(pk=item.pk).update(required=False)
    approve(revision, people["approver"])
    revision.refresh_from_db()
    assert revision.approved_content["resources"] == [
        {"kind": "instrument", "name": "HPLC", "required": True, "method_qualified": False}
    ]
    with pytest.raises(ValidationError, match="Only draft"):
        add(author, revision, name="Analytical balance")
    with pytest.raises(ValidationError, match="Only draft"):
        services.remove_method_resource(actor=author, item=item, reason="Too late")
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        MethodResource.objects.filter(pk=item.pk).delete()
    with pytest.raises(DatabaseError, match="only be added to a draft"), transaction.atomic():
        MethodResource.objects.create(
            method_revision=revision, kind="instrument", name="Analytical balance",
            created_by=author,
        )  # fmt: skip
    assert revision.resources.count() == 1


def test_whoever_listed_or_removed_a_line_cannot_approve(people, register):
    author, approver = people["author"], people["approver"]
    revision = method_revision(author)
    add(approver, revision)
    with pytest.raises(PermissionDenied, match="edited this draft"):
        approve(revision, approver)
    other = method_revision(author, code="other-method")
    item = add(author, other)
    services.remove_method_resource(actor=approver, item=item, reason="Not validated on it")
    with pytest.raises(PermissionDenied, match="edited this draft"):
        approve(other, approver)
    assert approve(other, people["dual"]).status == "approved"


def test_a_withdrawn_draft_keeps_its_lines(people, register):
    author = people["author"]
    revision = method_revision(author)
    item = add(author, revision)
    revision.refresh_from_db()
    services.withdraw_revision(
        actor=author, revision=revision, expected_revision=revision.revision, reason="Not needed"
    )
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        MethodResource.objects.filter(pk=item.pk).delete()
    with pytest.raises(DatabaseError, match="only be added to a draft"), transaction.atomic():
        MethodResource.objects.create(
            method_revision=revision, kind="instrument", name="Balance", created_by=author
        )
    with pytest.raises(ValidationError, match="Only draft"):
        add(author, revision, name="Analytical balance")
    assert revision.resources.count() == 1


def test_a_line_added_after_the_approval_page_opened_makes_it_stale(people, register):
    author, approver = people["author"], people["approver"]
    revision = method_revision(author)
    revision.refresh_from_db()
    opened = revision.revision
    add(author, revision)
    with pytest.raises(ValidationError):
        approve(revision, approver, expected_revision=opened)
    revision.refresh_from_db()
    assert revision.status == "draft"


def test_a_version_approved_without_lines_hashes_as_before(people, register):
    revision = method_revision(people["author"])
    approve(revision, people["approver"])
    revision.refresh_from_db()
    assert "resources" not in revision.approved_content
    assert revision.content() == revision.approved_content
    assert services.digest(revision.content()) == revision.approved_hash


def test_the_database_refuses_more_than_twenty_lines(people, register):
    revision = method_revision(people["author"])
    MethodResource.objects.bulk_create(
        MethodResource(
            method_revision=revision, kind="reagent", name=f"R{n}", created_by=people["author"]
        )
        for n in range(MAX_METHOD_RESOURCES)
    )
    with pytest.raises(DatabaseError, match="at most 20"), transaction.atomic():
        MethodResource.objects.create(
            method_revision=revision, kind="reagent", name="R20", created_by=people["author"]
        )


def test_a_version_without_lines_keeps_its_content_and_a_new_version_copies_them(people, register):
    author = people["author"]
    plain = method_revision(author, code="plain-method")
    assert "resources" not in plain.content()
    revision = method_revision(author)
    add(author, revision, method_qualified=True)
    add(author, revision, kind="reference_standard", name="Caffeine RS", required=False)
    approve(revision, people["approver"])
    revision.refresh_from_db()
    following = method_revision(author, method=revision.method, start_days=1)
    assert [r.content() for r in following.resources.all()] == revision.approved_content[
        "resources"
    ]
    assert {r.created_by for r in following.resources.all()} == {author}


# Pages -------------------------------------------------------------------------------------------


def client(user):
    browser = Client()
    assert browser.login(username=user.username, password=PASSWORD)
    return browser


def test_method_page_shows_each_line_beside_the_register(people, register):
    author, analyst = people["author"], people["analyst"]
    Calibration.objects.create(
        equipment=register["hplc"], performed_at=timezone.now() - timedelta(days=1),
        due_date=timezone.localdate() + timedelta(days=90), outcome="pass",
        standard_ref="CRM", recorded_by=analyst, state="accepted",
        accepted_at=timezone.now() - timedelta(hours=1),
    )  # fmt: skip
    lot(analyst, "SYN-RS-OLD", "Caffeine RS", expiry_date=timezone.localdate() - timedelta(days=1),
        received_on=timezone.localdate() - timedelta(days=400))  # fmt: skip
    lot(analyst, "SYN-WS-1", "Caffeine working solution", kind="prepared_solution",
        parent=register["standard"])  # fmt: skip
    revision = method_revision(author)
    add(author, revision, method_qualified=True)
    add(author, revision, kind="reference_standard", name="Caffeine RS")
    page = client(author).get(reverse("catalog:method", args=[revision.method_id]))
    html = page.content.decode()
    assert "Suitable instruments, reagents and standards" in html
    assert "In the register now" in html
    assert "SYN-LC-01" in html and "Not qualified for the method" in html
    assert "SYN-BAL-01" not in html  # another category
    # The standard and the solution prepared from it; not the expired lot.
    assert "SYN-RS-1" in html and "SYN-WS-1" in html and "SYN-RS-OLD" not in html
    assert reverse("catalog:method_resource_new", args=[revision.pk]) in html
    # Readers see the lines without the draft's actions.
    html = client(analyst).get(reverse("catalog:method", args=[revision.method_id])).content
    assert b"Suitable instruments, reagents and standards" in html
    assert reverse("catalog:method_resource_new", args=[revision.pk]).encode() not in html


def test_add_and_remove_pages(people, register):
    author = people["author"]
    revision = method_revision(author)
    url = reverse("catalog:method_resource_new", args=[revision.pk])
    browser = client(author)
    page = browser.get(url)
    assert page.status_code == 200
    assert b"instrument|HPLC" in page.content and b"reference_standard|Caffeine RS" in page.content
    refused = browser.post(
        url, {"resource": "reagent|Acetonitrile", "method_qualified": "on", "reason": "x"}
    )
    assert refused.status_code == 422 and not revision.resources.exists()
    done = browser.post(
        url, {"resource": "instrument|HPLC", "required": "on", "reason": "Validated on HPLC"}
    )
    assert done.status_code == 302
    item = revision.resources.get()
    assert (item.name, item.required) == ("HPLC", True)
    revision.refresh_from_db()
    remove = reverse("catalog:method_resource_remove", args=[revision.pk, item.pk])
    assert browser.get(remove).status_code == 200
    stale = browser.post(remove, {"expected_revision": revision.revision - 1, "reason": "x"})
    assert stale.status_code == 422 and revision.resources.exists()
    gone = browser.post(remove, {"expected_revision": revision.revision, "reason": "Not used"})
    assert gone.status_code == 302 and not revision.resources.exists()


def test_pages_refuse_other_roles_and_approved_versions(people, register):
    author = people["author"]
    revision = method_revision(author)
    item = add(author, revision)
    analyst = client(people["analyst"])
    assert (
        analyst.get(reverse("catalog:method_resource_new", args=[revision.pk])).status_code == 403
    )
    remove = reverse("catalog:method_resource_remove", args=[revision.pk, item.pk])
    assert analyst.get(remove).status_code == 403
    approve(revision, people["approver"])
    browser = client(author)
    assert (
        browser.get(reverse("catalog:method_resource_new", args=[revision.pk])).status_code == 302
    )
    assert browser.post(remove, {"expected_revision": 9, "reason": "x"}).status_code == 302
    assert revision.resources.count() == 1
