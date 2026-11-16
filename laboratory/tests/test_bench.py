"""The bench entry points used by result entry, and the impact lists that name the results."""

import json
import re
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from analytical.models import AnalyticalTest, QCBatch
from core.models import AuditEvent
from laboratory import services
from laboratory.models import Equipment, ReagentLot, ResourceUse

from .helpers import (
    accept_new_calibration,
    make_equipment,
    make_lot,
    make_reagent,
    make_sample,
    qualify_analyst,
)

pytestmark = pytest.mark.django_db(transaction=True)

ACTIVITY = "HPLC-ASSAY"
TEST_CONTEXT = "analytical.analyticaltest"
BATCH_CONTEXT = "analytical.qcbatch"


def call(people, *, equipment=(), reagents=(), actor=None, context=(TEST_CONTEXT, 1)):
    return services.use_in_work(
        actor=actor or people["analyst"],
        activity=ACTIVITY,
        context_type=context[0],
        context_id=context[1],
        test_code="assay",
        equipment_ids=[e.pk for e in equipment],
        reagent_ids=[r.pk for r in reagents],
        reason="Result entry",
    )


def make_test(people, number="SYN-LOT-1", reference="SYN-S-1", **values):
    lot = make_lot(people, number)
    sample = make_sample(people, lot, reference)
    return AnalyticalTest.objects.create(
        lot=lot,
        sample=sample,
        test_code="assay",
        requirement={},
        requirement_hash="0" * 64,
        created_by=people["analyst"],
        **values,
    )


def make_batch(people, number="QB-1"):
    return QCBatch.objects.create(
        number=number,
        method_code="HPLC-ASSAY",
        method={},
        method_hash="0" * 64,
        created_by=people["analyst"],
    )


def test_outside_a_transaction_is_refused(people):
    equipment = make_equipment(people)
    qualify_analyst(people, people["analyst"])
    with pytest.raises(RuntimeError):
        call(people, equipment=[equipment])
    assert not ResourceUse.objects.exists()


def test_success_writes_one_use_per_resource_and_returns_the_evidence(people):
    equipment = make_equipment(people)
    reagent = make_reagent(people)
    analyst = people["analyst"]
    qualification = qualify_analyst(people, analyst)
    with transaction.atomic():
        evidence = call(people, equipment=[equipment], reagents=[reagent])
    uses = {(u.equipment_id, u.reagent_lot_id): u for u in ResourceUse.objects.all()}
    assert len(uses) == 2
    assert evidence["user"] == analyst.pk and evidence["activity"] == ACTIVITY
    assert evidence["qualification"] == qualification.pk
    [eq] = evidence["equipment"]
    assert eq["id"] == equipment.pk and eq["asset_id"] == "BAL-001"
    assert eq["use"] == uses[(equipment.pk, None)].pk
    assert eq["calibration"] and eq["calibration_due"]
    [rg] = evidence["reagents"]
    assert rg["id"] == reagent.pk and rg["identifier"] == "RG-001"
    assert rg["use"] == uses[(None, reagent.pk)].pk and rg["released_at"]
    assert json.loads(json.dumps(evidence)) == evidence
    event = AuditEvent.objects.get(action="resource.used")
    assert event.actor == analyst and event.after["context"] == f"{TEST_CONTEXT}:1"
    stored = uses[(equipment.pk, None)]
    assert stored.eligibility["analyst"]["qualification"] == qualification.pk
    assert stored.test_code == "assay" and stored.context_id == "1"


def test_no_resources_checks_only_the_analyst(people):
    qualify_analyst(people, people["analyst"])
    with transaction.atomic():
        evidence = call(people)
    assert evidence["equipment"] == [] and evidence["reagents"] == []
    assert evidence["qualification"]
    assert not ResourceUse.objects.exists()
    assert not AuditEvent.objects.filter(action="resource.used").exists()
    with pytest.raises(services.UseBlocked), transaction.atomic():
        call(people, actor=people["analyst2"])  # not qualified


def refuse(people, **kwargs):
    with pytest.raises(services.UseBlocked) as caught, transaction.atomic():
        call(people, **kwargs)
    assert not ResourceUse.objects.exists()
    assert not AuditEvent.objects.filter(action="resource.used").exists()
    return " ".join(caught.value.messages)


def test_every_refusal_kind_writes_nothing(people):
    good = make_equipment(people, "BAL-OK")
    # Unqualified analyst.
    assert "qualification" in refuse(people, equipment=[good])
    qualify_analyst(people, people["analyst"])
    # Out of service.
    off = make_equipment(people, "BAL-OFF")
    services.take_out_of_service(actor=people["analyst"], equipment=off, reason="Drift")
    assert "out of service" in refuse(people, equipment=[good, off])
    # Failed calibration (also takes it out of service).
    failed = make_equipment(people, "BAL-FAIL")
    accept_new_calibration(people, failed, outcome="fail", accept=False, performed_hours_ago=0)
    assert "calibration" in refuse(people, equipment=[Equipment.objects.get(pk=failed.pk)])
    # Expired calibration.
    stale = make_equipment(people, "BAL-OLD", ready=False)
    accept_new_calibration(people, stale, days_valid=-1, performed_hours_ago=72)
    assert "expired" in refuse(people, equipment=[stale])
    # Reagents: unreleased, rejected, expired, rejected source.
    unreleased = make_reagent(people, "RG-NEW", release=False)
    assert "released" in refuse(people, reagents=[unreleased])
    rejected = make_reagent(people, "RG-REJ")
    services.reject_reagent(actor=people["analyst"], reagent=rejected, reason="Bad")
    assert "rejected" in refuse(people, reagents=[rejected])
    expired = make_reagent(
        people,
        "RG-EXP",
        release=False,
        received_on=timezone.localdate() - timedelta(days=9),
        expiry_date=timezone.localdate() - timedelta(days=1),
    )
    assert "expired" in refuse(people, reagents=[expired])
    source = make_reagent(people, "RG-SRC")
    prepared = make_reagent(
        people, "RG-PREP", kind="prepared_solution", parent=source, expiry_days=30
    )
    services.reject_reagent(actor=people["analyst"], reagent=source, reason="Recall")
    assert "Source lot RG-SRC was rejected" in refuse(people, reagents=[prepared])


def test_rollback_leaves_no_use_and_the_refusal_audit_survives(people):
    equipment = make_equipment(people)
    off = make_equipment(people, "BAL-OFF")
    services.take_out_of_service(actor=people["analyst"], equipment=off, reason="Drift")
    qualify_analyst(people, people["analyst"])
    # Success followed by a rollback by the caller leaves nothing behind.
    with pytest.raises(RuntimeError), transaction.atomic():
        call(people, equipment=[equipment])
        raise RuntimeError("caller fails later")
    assert not ResourceUse.objects.exists()
    assert not AuditEvent.objects.filter(action="resource.used").exists()
    # A refusal is audited after the rollback, in its own transaction.
    refusals = []
    try:
        with transaction.atomic():
            call(people, equipment=[equipment, off])
    except services.UseBlocked as exc:
        refusals = [
            {"subject": f.subject, "reasons": list(f.reasons)} for f in exc.findings if not f.ok
        ]
    services.record_blocked_use(
        actor=people["analyst"],
        activity=ACTIVITY,
        context_type=TEST_CONTEXT,
        context_id=1,
        refusals=refusals,
        reason="Result entry",
    )
    event = AuditEvent.objects.get(action="resource.use_blocked")
    assert event.actor == people["analyst"]
    assert event.after["refusals"][0]["subject"] == "BAL-OFF"
    assert event.after["context"] == f"{TEST_CONTEXT}:1" and event.reason == "Result entry"
    assert not ResourceUse.objects.exists()


def test_unknown_or_malformed_ids_raise_validation_error_and_write_nothing(people):
    equipment = make_equipment(people)
    qualify_analyst(people, people["analyst"])
    for kwargs in (
        {"equipment_ids": [equipment.pk, 99999]},
        {"reagent_ids": [99999]},
        {"equipment_ids": ["abc"]},
    ):
        with pytest.raises(ValidationError), transaction.atomic():
            services.use_in_work(
                actor=people["analyst"],
                activity=ACTIVITY,
                context_type=TEST_CONTEXT,
                context_id=1,
                reason="Result entry",
                **kwargs,
            )
    assert not ResourceUse.objects.exists()
    assert not AuditEvent.objects.filter(action__startswith="resource.").exists()


def test_authorize_use_still_audits_its_refusals_and_needs_a_resource(people):
    equipment = make_equipment(people)
    with pytest.raises(services.UseBlocked):
        services.authorize_use(
            actor=people["analyst"],
            context_type="quality.sample",
            context_id=1,
            activity=ACTIVITY,
            equipment=[equipment],
            reason="Attempt",
        )
    assert AuditEvent.objects.filter(action="resource.use_blocked").count() == 1


def test_choices_label_items_with_their_status_and_skip_rejected_lots(people):
    ready = make_equipment(people, "BAL-READY")
    off = make_equipment(people, "BAL-OFF")
    services.take_out_of_service(actor=people["analyst"], equipment=off, reason="Drift")
    overdue = make_equipment(people, "BAL-OLD", ready=False)
    accept_new_calibration(people, overdue, days_valid=-1, performed_hours_ago=72)
    waiting = make_reagent(people, "RG-NEW", release=False)
    good = make_reagent(people, "RG-OK")
    bad = make_reagent(people, "RG-REJ")
    services.reject_reagent(actor=people["analyst"], reagent=bad, reason="Bad")
    with_queries = pytest.importorskip("django.test.utils").CaptureQueriesContext
    from django.db import connection

    with with_queries(connection) as queries:
        choices = services.bench_choices()
    assert len(queries) <= 3
    equipment = dict(choices["equipment"])
    assert equipment[ready.pk].startswith("BAL-READY · Synthetic analytical balance")
    assert equipment[ready.pk].endswith("Ready")
    assert equipment[off.pk].endswith("Out of service")
    assert equipment[overdue.pk].endswith("Calibration overdue")
    reagents = dict(choices["reagents"])
    assert bad.pk not in reagents
    assert reagents[good.pk] == "RG-OK · Synthetic buffer (Reagent) · Ready"
    assert reagents[waiting.pk].endswith("Awaiting release")
    assert ReagentLot.objects.count() == 3


def use_context(people, equipment, context):
    qualify_analyst(people, people["analyst"])
    with transaction.atomic():
        call(people, equipment=[equipment], context=context)


def fail_calibration(people, equipment):
    accept_new_calibration(people, equipment, outcome="fail", accept=False, performed_hours_ago=0)


def test_work_labels_link_tests_and_batches_and_survive_unknown_contexts(people):
    from laboratory.ui import work_labels

    test = make_test(people)
    batch = make_batch(people)
    labels, links, details = work_labels(
        [(TEST_CONTEXT, test.pk), (BATCH_CONTEXT, batch.pk), (TEST_CONTEXT, 99999), ("x.y", "7")]
    )
    key = (TEST_CONTEXT, str(test.pk))
    assert labels[key] == f"{test.label} · lot SYN-LOT-1 · sample SYN-S-1"
    assert links[key] == reverse("analytical:test_detail", args=[test.pk])
    assert labels[(BATCH_CONTEXT, str(batch.pk))] == "QC batch QB-1"
    assert links[(BATCH_CONTEXT, str(batch.pk))] == reverse(
        "analytical:batch_detail", args=[batch.pk]
    )
    assert labels[(TEST_CONTEXT, "99999")] == f"{TEST_CONTEXT} 99999"
    assert labels[("x.y", "7")] == "x.y 7" and (TEST_CONTEXT, "99999") not in links
    assert details[key]["lot"] == "SYN-LOT-1"


def test_equipment_page_lists_the_results_after_a_failed_calibration(client, people):
    equipment = make_equipment(people)
    test = make_test(people, state="reviewed", reportable_text="99.8")
    batch = make_batch(people)
    for number in (1, 2):
        extra = make_test(people, f"SYN-LOT-B{number}", f"SYN-B{number}")
        extra.batch = batch
        extra.save()
    use_context(people, equipment, (TEST_CONTEXT, test.pk))
    use_context(people, equipment, (BATCH_CONTEXT, batch.pk))
    use_context(people, equipment, ("external.batch", "EXT-9"))
    client.force_login(people["quality"])
    url = reverse("laboratory:equipment_detail", args=[equipment.pk])
    assert "Uses to assess" not in client.get(url).content.decode().split("Recent uses")[0]
    fail_calibration(people, equipment)
    page = client.get(url).content.decode()
    impact = page.split("Uses to assess after failure")[1].split("Recent uses")[0]
    assert f'href="{reverse("analytical:test_detail", args=[test.pk])}"' in impact
    assert f"{test.label} · lot SYN-LOT-1 · sample SYN-S-1" in impact
    assert "assay" in impact and "Reviewed" in impact and "99.8" in impact
    assert f'href="{reverse("analytical:batch_detail", args=[batch.pk])}"' in impact
    assert "QC batch QB-1" in impact and re.search(r">\s*2\s*<", impact)
    assert "external.batch EXT-9" in impact


def test_return_page_shows_the_same_scope_the_signer_assesses(client, people):
    equipment = make_equipment(people)
    test = make_test(people, state="submitted")
    batch = make_batch(people)
    use_context(people, equipment, (TEST_CONTEXT, test.pk))
    use_context(people, equipment, (BATCH_CONTEXT, batch.pk))
    fail_calibration(people, equipment)
    accept_new_calibration(people, equipment, performed_hours_ago=0)
    url = reverse("laboratory:equipment_return", args=[equipment.pk])
    client.force_login(people["quality"])
    page = client.get(url).content.decode()
    uses, _ = services.impact_scope(Equipment.objects.get(pk=equipment.pk))
    assert f"{len(uses)} use(s) to assess" in page
    assert f"{test.label} · lot SYN-LOT-1 · sample SYN-S-1" in page and "Awaiting review" in page
    assert "QC batch QB-1" in page and "0 test(s)" in page
    assert f'name="assessed" value="{",".join(map(str, uses))}|' in page


def test_use_search_finds_uses_by_lot_number_and_batch_number(client, people):
    equipment = make_equipment(people)
    test = make_test(people, number="LOTSEARCH-9")
    batch = make_batch(people, "QBSEARCH-5")
    use_context(people, equipment, (TEST_CONTEXT, test.pk))
    use_context(people, equipment, (BATCH_CONTEXT, batch.pk))
    use_context(people, equipment, ("external.batch", "EXT-9"))
    client.force_login(people["auditor"])
    url = reverse("laboratory:use_list")
    by_lot = client.get(url, {"q": "LOTSEARCH"}).content.decode()
    assert test.label in by_lot and "QC batch" not in by_lot and "external.batch" not in by_lot
    by_batch = client.get(url, {"q": "QBSEARCH"}).content.decode()
    assert "QC batch QBSEARCH-5" in by_batch and test.label not in by_batch
    listing = client.get(url).content.decode()
    assert "external.batch EXT-9" in listing


def test_roles_around_the_pages_are_unchanged(client, people):
    equipment = make_equipment(people)
    off = Equipment.objects.get(pk=equipment.pk)
    services.take_out_of_service(actor=people["analyst"], equipment=off, reason="Drift")
    url = reverse("laboratory:equipment_return", args=[equipment.pk])
    for who in ("analyst", "reviewer", "auditor"):
        client.force_login(people[who])
        assert client.get(url).status_code == 403
    client.force_login(people["quality"])
    assert client.get(url).status_code == 200
    client.force_login(people["auditor"])
    assert (
        client.get(reverse("laboratory:equipment_detail", args=[equipment.pk])).status_code == 200
    )
    # Only analysts may open the manual use page.
    assert client.get(reverse("laboratory:use_new")).status_code == 403
