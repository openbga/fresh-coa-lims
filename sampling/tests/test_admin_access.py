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
from django.utils import timezone

from catalog import evidence, proficiency
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
from laboratory.models import Equipment
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
    "catalog:evidence_list": (),
    "catalog:evidence_detail": ("evidence_draft",),
    "catalog:proficiency_list": (),
    "catalog:proficiency_detail": ("pt_open",),
    "sampling:lots": (),
    "sampling:lot": ("lot",),
    "sampling:plans": (),
    "sampling:plan": ("plan",),
}
EXTRA_READS = [  # approved versions render differently from drafts
    ("catalog:specification_revision", ("spec_approved",)),
    ("catalog:method", ("method_approved",)),
    ("catalog:evidence_detail", ("evidence_approved",)),
    ("catalog:proficiency_detail", ("pt_follow_up",)),
    ("catalog:proficiency_detail", ("pt_planned",)),
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
    "catalog:method_resource_new": (("method_draft",), "approver"),
    "catalog:method_resource_remove": (("method_draft", "method_resource"), "approver"),
    "catalog:file_import_set": (("method_draft",), "approver"),
    "catalog:file_import_clear": (("method_draft",), "approver"),
    "catalog:method_withdraw": (("method_draft",), "approver"),
    "catalog:material_new": ((), "approver"),
    "catalog:suitability_set": (("method_draft",), "approver"),
    "catalog:evidence_new": ((), "analyst"),
    "catalog:evidence_edit": (("evidence_draft",), "analyst"),
    "catalog:evidence_characteristic_new": (("evidence_draft",), "analyst"),
    "catalog:evidence_characteristic_remove": (("evidence_draft", "characteristic"), "analyst"),
    "catalog:evidence_approve": (("evidence_draft",), "approver"),
    "catalog:evidence_withdraw": (("evidence_draft",), "analyst"),
    "catalog:proficiency_new": ((), "approver"),
    "catalog:proficiency_edit": (("pt_open",), "author"),
    "catalog:proficiency_cancel": (("pt_planned",), "author"),
    "catalog:proficiency_report": (("pt_open",), "analyst"),
    "catalog:proficiency_result_new": (("pt_open",), "analyst"),
    "catalog:proficiency_result_remove": (("pt_open", "pt_result"), "analyst"),
    "catalog:proficiency_review": (("pt_open",), "approver"),
    "catalog:proficiency_follow_up": (("pt_follow_up",), "approver"),
    "catalog:proficiency_close": (("pt_follow_up",), "author"),
    "sampling:assign": (("lot",), "analyst"),
    "sampling:replace": (("lot_testing",), "approver"),
    "sampling:decide": (("lot_conflict",), "approver"),
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


def lot_in_testing(people, ready):  # noqa: F811
    """A second lot whose testing has started and whose method was revised since: the only
    state in which its requirements can be replaced."""
    from analytical.models import AnalyticalTest
    from quality.services import receive_lot
    from sampling import services as sampling
    from tests.receipts import on_site_receipt

    from .test_services import sample

    lot = receive_lot(
        actor=people["analyst"],
        number="SYN-LOT-T1",
        material=ready["material"].name,
        rules=ready["rules"],
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    second = {**ready, "lot": lot}
    assign(people, second)
    taken = sample(people, second, reference="SYN-S-T1")
    AnalyticalTest.objects.create(
        lot=lot,
        sample=taken.sample,
        test_code="assay",
        requirement=sampling.test_requirements(lot)["assay"],
        requirement_hash="0" * 64,
        created_by=people["analyst"],
    )
    method = ready["spec"].tests.get(code="assay").method
    approve(method_revision(people["author"], method=method), people["approver"])
    return lot


def lot_with_conflict(people, ready):  # noqa: F811
    """A third lot assigned under the general scope and a market scope whose specification
    states the assay differently: held until quality decides which requirement applies."""
    from quality.services import receive_lot
    from tests.receipts import on_site_receipt

    author = people["author"]
    overlay = specification(author, ready["material"], code="spec-eu", scope="eu-market")[1]
    method = ready["spec"].tests.get(code="assay").method
    numeric_line(author, overlay, method, code="assay", low="99.0", high="101.0")
    approve(overlay, people["approver"])
    lot = receive_lot(
        actor=people["analyst"],
        number="SYN-LOT-C1",
        material=ready["material"].name,
        rules=ready["rules"],
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    held = assign(people, {**ready, "lot": lot}, scopes=["general", "eu-market"])
    assert held.status == "hold", held.hold_reasons
    return lot


def method_evidence(people, method):
    """A draft evidence record of ``method`` with one characteristic, ready for approval."""
    item = evidence.record_evidence(
        actor=people["analyst"],
        method=method,
        reason="Synthetic evidence",
        kind="validation",
        title="Synthetic validation",
        procedure_ref="SOP-SYN-GC rev 1",
        intended_use="Synthetic use",
        report_ref="VR-SYN-GC rev 1",
        completed_on=timezone.localdate(),
        conclusion="suitable",
        statement="Suitable",
    )
    line = evidence.add_characteristic(
        actor=people["analyst"],
        evidence=item,
        reason="Synthetic characteristic",
        characteristic="accuracy",
        detail="",
        criterion="98-102 %",
        result="100 %",
        outcome="met",
    )
    item.refresh_from_db()
    return item, line


def participations(people, method):
    """A participation planned only, one ready for review and one under corrective follow-up
    recorded by the approver, so that the author can close it."""
    today = timezone.localdate()

    def planned():
        return proficiency.plan_participation(
            actor=people["author"],
            method=method,
            reason="Synthetic plan",
            kind="proficiency_test",
            provider="Synthetic PT Provider",
            round_ref="Round 1",
            test_item="Synthetic item",
            results_due=today + timedelta(days=10),
        )

    def recorded(score):
        item = planned()
        line = proficiency.add_result(
            actor=people["analyst"],
            participation=item,
            expected_revision=item.revision,
            reason="Synthetic result",
            measurand="Synthetic analyte",
            reported_value="1.0",
            score_kind="z",
            score=Decimal(score),
            performed_by=people["analyst"],
        )
        item.refresh_from_db()
        proficiency.record_report(
            actor=people["analyst"],
            participation=item,
            expected_revision=item.revision,
            reason="Synthetic report",
            received_on=today,
            reported_on=today,
            data_ref="WS-SYN-1",
            report_ref="SYN-PT report",
            report_on=today,
        )
        item.refresh_from_db()
        return item, line

    pt_open, pt_result = recorded("0.5")
    pt_follow_up, _ = recorded("3.5")
    proficiency.review_participation(
        actor=people["approver"],
        pin=PIN,
        participation=pt_follow_up,
        expected_revision=pt_follow_up.revision,
        reason="Synthetic review",
        conclusion="Bias",
        follow_up=True,
    )
    pt_follow_up.refresh_from_db()
    proficiency.record_follow_up(
        actor=people["approver"],
        participation=pt_follow_up,
        expected_revision=pt_follow_up.revision,
        reason="Synthetic follow-up",
        cause="Synthetic cause",
        actions="Synthetic actions",
        reported_results="None affected",
        effectiveness="Repeat passed",
    )
    return {
        "pt_planned": planned().pk,
        "pt_open": pt_open.pk,
        "pt_result": pt_result.pk,
        "pt_follow_up": pt_follow_up.pk,
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
    Equipment.objects.create(
        asset_id="SYN-GC-01", description="Synthetic GC", category="GC", created_by=author
    )
    method_resource = catalog.add_method_resource(
        actor=author, revision=method_draft, reason="Suitable", kind="instrument", name="GC"
    )
    plan_draft = plan_revision(author, material(author, code="syn-api-002"))
    evidence_draft, characteristic = method_evidence(people, method_draft.method)
    evidence_approved, _ = method_evidence(people, method_draft.method)
    evidence.approve_evidence(
        actor=people["approver"],
        pin=PIN,
        evidence=evidence_approved,
        expected_revision=evidence_approved.revision,
        reason="Synthetic approval",
    )
    assign(people, ready)
    record = short(people, ready)
    testing = lot_in_testing(people, ready)
    conflict = lot_with_conflict(people, ready)
    return {
        "lot_testing": testing.pk,
        "lot_conflict": conflict.pk,
        "spec": ready["spec"].specification.pk,
        "spec_approved": ready["spec"].pk,
        "spec_draft": spec_draft.pk,
        "line": spec_draft.tests.first().pk,
        "method": method_draft.method_id,
        "method_approved": ready["spec"].tests.first().method_id,
        "method_draft": method_draft.pk,
        "qc_check": qc_check.pk,
        "calc_input": calc_input.pk,
        "method_resource": method_resource.pk,
        "plan": plan_draft.plan_id,
        "plan_approved": ready["plan"].plan_id,
        "plan_draft": plan_draft.pk,
        "lot": ready["lot"].pk,
        "record": record.pk,
        "evidence_draft": evidence_draft.pk,
        "evidence_approved": evidence_approved.pk,
        "characteristic": characteristic.pk,
        **participations(people, method_draft.method),
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
