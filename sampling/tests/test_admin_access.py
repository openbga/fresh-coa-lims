"""Admin sees everything in catalog and sampling but can change nothing without a lab role.

Every named route of both apps is classified as read or mutation, and each runs against real,
actionable records: a positive control opens every mutation page, so a 403 for admin
comes from the role check, not from a missing or unusable record.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.urls import get_resolver, reverse

from catalog import services as catalog
from catalog.models import Method
from catalog.tests.factories import (
    PIN,
    approve,
    material,
    method_revision,
    numeric_line,
    person,
    specification,
    window,
)
from core.models import AuditEvent, ElectronicSignature
from quality.models import Lot

from .test_gate import short
from .test_services import assign, plan_revision, ready  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

# Route name -> (fixture keys for URL args, user that must be able to open it).
READ = {
    "catalog:specifications": (),
    "catalog:specification": ("spec",),
    "catalog:specification_revision": ("spec_draft",),
    "catalog:methods": (),
    "catalog:method": ("method",),
    "catalog:materials": (),
    "sampling:lots": (),
    "sampling:lot": ("lot",),
    "sampling:plans": (),
    "sampling:plan": ("plan",),
}
EXTRA_READS = [  # approved versions render differently from drafts
    ("catalog:specification_revision", ("spec_approved",)),
    ("catalog:method", ("method_approved",)),
    ("sampling:plan", ("plan_approved",)),
]
MUTATIONS = {
    "catalog:specification_new": ((), "approver"),
    "catalog:specification_version_new": (("spec",), "approver"),
    "catalog:test_new": (("spec_draft",), "approver"),
    "catalog:test_remove": (("spec_draft", "line"), "approver"),
    "catalog:specification_approve": (("spec_draft",), "approver"),
    "catalog:specification_withdraw": (("spec_draft",), "approver"),
    "catalog:method_new": ((), "approver"),
    "catalog:method_version_new": (("method",), "approver"),
    "catalog:method_approve": (("method_draft",), "approver"),
    "catalog:qc_check_new": (("method_draft",), "approver"),
    "catalog:qc_check_remove": (("method_draft", "qc_check"), "approver"),
    "catalog:calculation_set": (("method_draft",), "approver"),
    "catalog:calculation_clear": (("method_draft",), "approver"),
    "catalog:calculation_input_new": (("method_draft",), "approver"),
    "catalog:calculation_input_remove": (("method_draft", "calc_input"), "approver"),
    "catalog:method_withdraw": (("method_draft",), "approver"),
    "catalog:material_new": ((), "approver"),
    "sampling:assign": (("lot",), "analyst"),
    "sampling:sampling_new": (("lot",), "analyst"),
    "sampling:sampling_correct": (("record",), "analyst"),
    "sampling:deviation_assess": (("record",), "approver"),
    "sampling:plan_new": ((), "approver"),
    "sampling:plan_version_new": (("plan",), "approver"),
    "sampling:plan_approve": (("plan_draft",), "approver"),
    "sampling:plan_withdraw": (("plan_draft",), "approver"),
}
# A plausible submission for every form; admin must be refused before any of it is used.
PAYLOAD = {
    "reason": "Admin attempt (synthetic)",
    "signature_username": "admin-a",
    "pin": PIN,
    "expected_revision": "1",
    "decision": "accept",
    "code": "syn-admin",
    "title": "Synthetic admin attempt",
    "name": "Synthetic admin attempt",
}


@pytest.fixture
def world(people, ready):  # noqa: F811
    """Approved and draft versions of every controlled record, and a lot with a deviation."""
    author = people["author"]
    approved = ready["spec"]
    spec_draft = catalog.new_specification_revision(
        actor=author,
        specification=approved.specification,
        effective_from=approved.effective_until,
        effective_until=approved.effective_until + timedelta(days=30),
        basis="Synthetic next version",
        reason="Next version",
    )
    start, end = window()
    method_draft = catalog.create_method(
        actor=author,
        code="gc-batch",
        title="Synthetic batch GC",
        technique="GC",
        document_ref="SOP-SYN-GC rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-GC",
        requires_batch=True,
        effective_from=start,
        effective_until=end,
        reason="Synthetic method",
    )[1]
    qc_check = catalog.add_qc_check(
        actor=author,
        revision=method_draft,
        reason="QC",
        code="blank",
        name="Blank",
        unit="%",
        upper_limit=Decimal("0.05"),
    )
    calc_input = catalog.add_calculation_input(
        actor=author,
        revision=method_draft,
        reason="Input",
        code="peak_area",
        name="Peak area",
        unit="peak area",
    )
    plan_draft = plan_revision(author, material(author, code="syn-api-002"))
    assign(people, ready)
    record = short(people, ready)
    return {
        "spec": ready["spec"].specification.pk,
        "spec_approved": ready["spec"].pk,
        "spec_draft": spec_draft.pk,
        "line": spec_draft.tests.first().pk,
        "method": method_draft.method_id,
        "method_approved": ready["spec"].tests.first().method_id,
        "method_draft": method_draft.pk,
        "qc_check": qc_check.pk,
        "calc_input": calc_input.pk,
        "plan": plan_draft.plan_id,
        "plan_approved": ready["plan"].plan_id,
        "plan_draft": plan_draft.pk,
        "lot": ready["lot"].pk,
        "record": record.pk,
    }


def url(world, name, keys):
    return reverse(name, args=[world[key] for key in keys])


def mutation_urls(world):
    return {url(world, name, keys) for name, (keys, _) in MUTATIONS.items()}


def state():
    """Row counts of every catalog/sampling model plus audit, signatures and lot revisions."""
    counts = {
        model._meta.label: model.objects.count()
        for label in ("catalog", "sampling")
        for model in apps.get_app_config(label).get_models()
    }
    counts["audit"] = AuditEvent.objects.count()
    counts["signatures"] = ElectronicSignature.objects.count()
    counts["lots"] = list(Lot.objects.order_by("pk").values_list("pk", "revision", "state"))
    return counts


def test_every_route_is_classified():
    names = set()
    for namespace in ("catalog", "sampling"):
        resolver = get_resolver().namespace_dict[namespace][1]
        names |= {f"{namespace}:{n}" for n in resolver.reverse_dict if isinstance(n, str)}
    assert not set(READ) & set(MUTATIONS)
    assert names == set(READ) | set(MUTATIONS)


def test_controls_can_open_every_mutation(client, people, world):
    """Proves the admin denials below are role denials on usable records, not 404s/redirects."""
    for name, (keys, control) in MUTATIONS.items():
        client.force_login(people[control])
        assert client.get(url(world, name, keys)).status_code == 200, (name, control)


def test_admin_reads_everything_without_actions(client, people, world):
    client.force_login(people["admin"])
    forbidden = mutation_urls(world)
    for name, keys in [*READ.items(), *EXTRA_READS]:
        response = client.get(url(world, name, keys))
        assert response.status_code == 200, name
        body = response.content.decode()
        assert not [link for link in forbidden if f'href="{link}"' in body], name
        for label in ("Review and approve", "Withdraw draft", "Assess deviation"):
            assert f">{label}<" not in body, (name, label)
    lot = client.get(url(world, "sampling:lot", ("lot",))).content.decode()
    assert "awaits quality assessment" in lot and "History" in lot


def test_admin_cannot_open_or_submit_any_mutation(client, people, world):
    client.force_login(people["admin"])
    before = state()
    for name, (keys, _) in MUTATIONS.items():
        target = url(world, name, keys)
        assert client.get(target).status_code == 403, name
        assert client.post(target, PAYLOAD).status_code == 403, name
    assert state() == before


def test_admin_with_lab_roles_keeps_actions_and_independence(client, people, world):
    lab_admin = person("admin-lab", "admin", "quality", "analyst")
    client.force_login(lab_admin)
    revision = client.get(url(world, "catalog:specification_revision", ("spec_draft",)))
    assert url(world, "catalog:specification_approve", ("spec_draft",)) in revision.content.decode()
    lot = client.get(url(world, "sampling:lot", ("lot",))).content.decode()
    for name in ("sampling:sampling_new", "sampling:deviation_assess", "sampling:sampling_correct"):
        keys = MUTATIONS[name][0]
        assert url(world, name, keys) in lot, name

    # No self-review: the admin role is not a bypass of independent approval or assessment.
    own = method_revision(lab_admin, code="own-draft")
    response = client.get(reverse("catalog:method_approve", args=[own.pk]))
    assert response.status_code == 403
    with pytest.raises(PermissionDenied):
        approve(own, lab_admin)
    own_spec = specification(lab_admin, material(lab_admin, code="syn-api-003"), code="own-spec")[1]
    numeric_line(lab_admin, own_spec, Method.objects.get(pk=world["method_approved"]))
    assert (
        client.get(reverse("catalog:specification_approve", args=[own_spec.pk])).status_code == 403
    )
    sampled = short(
        people,
        {"lot": Lot.objects.get(pk=world["lot"])},
        reference="SYN-S-ADM",
        actor=lab_admin,
    )
    response = client.get(reverse("sampling:deviation_assess", args=[sampled.pk]))
    assert response.status_code == 403
    assert "another person must assess" in response.content.decode()
