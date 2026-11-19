"""Training records, the trainee's acknowledgement, and qualifications that rely on them, against
PostgreSQL: roles, independence, stale and wrong-PIN signing, immutability and the pages."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent, ElectronicSignature, PINCredential
from laboratory import services
from laboratory.eligibility import analyst_eligibility, reviewer_eligibility
from laboratory.models import Qualification, TrainingRecord

from .helpers import PIN, make_equipment, record_training

pytestmark = pytest.mark.django_db(transaction=True)


def qualification(people, user, activity="HPLC-ASSAY", *, work="perform", training=(), **values):
    today = timezone.localdate()
    fields = {
        "scope_note": "",
        "evidence_ref": "QUAL-SYN-1",
        "evidence_url": "",
        "valid_from": today - timedelta(days=1),
        "valid_until": today + timedelta(days=365),
        **values,
    }
    return services.record_qualification(
        actor=people["reviewer"],
        user=user,
        activity=activity,
        work=work,
        training=training,
        reason="Synthetic evidence",
        **fields,
    )


def approve(people, record, signer="quality"):
    return services.approve_qualification(
        actor=people[signer],
        pin=PIN,
        qualification=record,
        expected_revision=record.revision,
        reason="Independent approval",
    )


# --- Recording -------------------------------------------------------------------------------


def test_any_laboratory_role_records_training_for_someone_else(people):
    for recorder in ("analyst", "reviewer", "quality"):
        training = record_training(people, people["analyst2"], recorder=recorder)
        assert training.state == "recorded" and training.recorded_by == people[recorder]
    event = AuditEvent.objects.get(action="training.recorded", object_id=str(training.pk))
    assert event.actor == people["quality"] and event.after["activity"] == "HPLC-ASSAY"
    for refused in ("auditor", "admin"):
        with pytest.raises(PermissionDenied):
            record_training(people, people["analyst2"], recorder=refused)


def test_nobody_records_their_own_training_or_an_inactive_persons(people):
    with pytest.raises(PermissionDenied, match="your own training"):
        record_training(people, people["reviewer"], recorder="reviewer")
    people["analyst2"].is_active = False
    people["analyst2"].save()
    with pytest.raises(ValidationError, match="inactive"):
        record_training(people, people["analyst2"])
    assert not TrainingRecord.objects.exists()


def test_training_is_not_dated_in_the_future_and_its_outcome_fits_its_kind(people):
    with pytest.raises(ValidationError, match="future"):
        record_training(
            people, people["analyst"], completed_on=timezone.localdate() + timedelta(days=1)
        )
    with pytest.raises(ValidationError):
        record_training(people, people["analyst"], kind="read", outcome="competent")
    with pytest.raises(ValidationError):
        record_training(people, people["analyst"], kind="assessment", outcome="completed")
    assessed = record_training(people, people["analyst"], kind="assessment", outcome="competent")
    assert assessed.get_outcome_display() == "Competent"


# --- Acknowledgement -------------------------------------------------------------------------


def test_only_the_trainee_acknowledges_with_their_signature(people):
    training = record_training(people, people["analyst"])
    for other in ("reviewer", "quality", "analyst2"):
        with pytest.raises(PermissionDenied, match="Only the trainee"):
            services.acknowledge_training(
                actor=people[other],
                pin=PIN,
                training=training,
                expected_revision=training.revision,
                reason="Not mine",
            )
    acknowledged = services.acknowledge_training(
        actor=people["analyst"],
        pin=PIN,
        training=training,
        expected_revision=training.revision,
        reason="I received this training",
    )
    assert acknowledged.state == "acknowledged" and acknowledged.acknowledged_at
    signature = ElectronicSignature.objects.get(
        object_type="laboratory.trainingrecord", object_id=str(training.pk)
    )
    assert signature.signer == people["analyst"] and signature.meaning == "acknowledged"
    assert signature.content["document_ref"] == "SOP-SYN-001 rev 2"
    assert AuditEvent.objects.filter(action="signed.acknowledged", actor=people["analyst"]).exists()
    with pytest.raises(ValidationError, match="already acknowledged"):
        services.acknowledge_training(
            actor=people["analyst"],
            pin=PIN,
            training=acknowledged,
            expected_revision=acknowledged.revision,
            reason="Again",
        )


def test_reviewer_and_quality_trainees_acknowledge_too_but_an_auditor_cannot(people):
    for trainee in ("reviewer", "quality"):
        training = record_training(people, people[trainee], recorder="analyst")
        services.acknowledge_training(
            actor=people[trainee],
            pin=PIN,
            training=training,
            expected_revision=training.revision,
            reason="Received",
        )
    for no_lab_role in ("auditor", "admin"):
        with pytest.raises(ValidationError, match="needs the analyst, reviewer or quality role"):
            record_training(people, people[no_lab_role], recorder="analyst")


def test_stale_revision_and_wrong_pin_refuse_the_acknowledgement(people):
    training = record_training(people, people["analyst"])
    with pytest.raises(ValidationError, match="Record changed"):
        services.acknowledge_training(
            actor=people["analyst"],
            pin=PIN,
            training=training,
            expected_revision=training.revision + 1,
            reason="Stale",
        )
    with pytest.raises(ValidationError, match="not accepted"):
        services.acknowledge_training(
            actor=people["analyst"],
            pin="00000000",
            training=training,
            expected_revision=training.revision,
            reason="Wrong PIN",
        )
    training.refresh_from_db()
    assert training.state == "recorded"
    assert PINCredential.objects.get(user=people["analyst"]).failures == 1
    assert AuditEvent.objects.filter(actor=people["analyst"], action="signature.denied").exists()


def test_training_records_are_immutable_and_never_deleted(people):
    training = record_training(people, people["analyst"], acknowledge=True)
    for change in ({"trainer": "Someone else"}, {"state": "recorded"}, {"outcome": "completed"}):
        with pytest.raises(DatabaseError), transaction.atomic():
            TrainingRecord.objects.filter(pk=training.pk).update(**change)
    with pytest.raises(DatabaseError), transaction.atomic():
        TrainingRecord.objects.filter(pk=training.pk).delete()
    pending = record_training(people, people["analyst2"])
    with pytest.raises(DatabaseError), transaction.atomic():
        TrainingRecord.objects.filter(pk=pending.pk).update(activity="OTHER")


# --- Qualifications relying on training ------------------------------------------------------


def test_a_qualification_relies_on_the_persons_acknowledged_training_and_binds_it(people):
    first = record_training(people, people["analyst"], acknowledge=True)
    second = record_training(
        people,
        people["analyst"],
        "hplc-assay",  # the activity matches whatever its case
        kind="assessment",
        outcome="competent",
        acknowledge=True,
    )
    recorded = qualification(people, people["analyst"], training=[second, first])
    assert recorded.training == sorted([first.pk, second.pk])
    event = AuditEvent.objects.get(action="qualification.recorded", object_id=str(recorded.pk))
    assert event.after["training"] == recorded.training
    approved = approve(people, recorded)
    signature = ElectronicSignature.objects.get(
        object_type="laboratory.qualification", object_id=str(approved.pk)
    )
    assert signature.content["training"] == recorded.training
    assert signature.content["work"] == "perform"
    assert list(Qualification.objects.filter(training__contains=[first.pk])) == [approved]


def test_training_that_cannot_support_the_qualification_is_refused(people):
    other_person = record_training(people, people["analyst2"], acknowledge=True)
    other_activity = record_training(people, people["analyst"], "GC-ASSAY", acknowledge=True)
    pending = record_training(people, people["analyst"])
    failed = record_training(
        people,
        people["analyst"],
        kind="assessment",
        outcome="not_yet_competent",
        acknowledge=True,
    )
    for training, message in [
        (other_person, "training of another person"),
        (other_activity, "not this activity"),
        (pending, "not acknowledged"),
        (failed, "not yet competent"),
    ]:
        with pytest.raises(ValidationError, match=message):
            qualification(people, people["analyst"], training=[training])
    assert not Qualification.objects.exists()


def test_an_instrument_has_no_training_and_reviews_nothing(people):
    equipment = make_equipment(people, ready=False)
    training = record_training(people, people["analyst"], acknowledge=True)
    today = timezone.localdate()
    common = {
        "actor": people["reviewer"],
        "equipment": equipment,
        "activity": "OQ",
        "evidence_ref": "OQ-1",
        "valid_from": today,
        "valid_until": today + timedelta(days=30),
        "reason": "Instrument evidence",
    }
    with pytest.raises(ValidationError, match="reviews nothing"):
        services.record_qualification(training=[training], **common)
    with pytest.raises(ValidationError, match="reviews nothing"):
        services.record_qualification(work="review", **common)
    assert services.record_qualification(**common).work == "perform"


def test_performing_and_reviewing_need_their_own_qualification(people):
    analyst = people["analyst"]
    approve(people, qualification(people, analyst, work="review"))
    assert not analyst_eligibility(analyst, "HPLC-ASSAY").ok
    assert reviewer_eligibility(analyst, "hplc-assay").ok
    approve(people, qualification(people, analyst))
    assert analyst_eligibility(analyst, "HPLC-ASSAY").ok
    other = people["analyst2"]
    approve(people, qualification(people, other))
    finding = reviewer_eligibility(other, "HPLC-ASSAY")
    assert not finding.ok
    assert finding.reasons == ("No approved, current qualification to review “HPLC-ASSAY”.",)


# --- Pages -----------------------------------------------------------------------------------


def test_training_pages_from_recording_to_a_qualification(client, people):
    client.force_login(people["reviewer"])
    page = client.get(reverse("laboratory:training_new"))
    assert page.status_code == 200
    data = {
        "trainee": people["analyst"].pk,
        "activity": "HPLC-ASSAY",
        "document_ref": "SOP-SYN-001 rev 2",
        "kind": "assessment",
        "outcome": "completed",
        "trainer": "Synthetic Trainer",
        "completed_on": timezone.localdate().isoformat(),
        "reason": "Training given",
    }
    refused = client.post(reverse("laboratory:training_new"), data)
    assert refused.status_code == 422
    assert "An assessment finds the trainee competent" in refused.content.decode()
    response = client.post(reverse("laboratory:training_new"), {**data, "outcome": "competent"})
    training = TrainingRecord.objects.get()
    detail = reverse("laboratory:training_detail", args=[training.pk])
    assert response.status_code == 302 and response.url == detail
    acknowledge = reverse("laboratory:training_acknowledge", args=[training.pk])
    html = client.get(detail).content.decode()
    assert "Awaiting acknowledgement" in html and acknowledge not in html
    assert "No qualification relies on this training record yet." in html
    assert client.get(acknowledge).status_code == 403

    client.force_login(people["analyst"])
    assert acknowledge in client.get(detail).content.decode()
    signed = client.post(
        acknowledge,
        {
            "signature_username": "analyst",
            "pin": PIN,
            "reason": "I received it",
            "expected_revision": training.revision,
        },
    )
    assert signed.status_code == 302
    training.refresh_from_db()
    assert training.state == "acknowledged"
    # The trainee cannot record a qualification of their own from it.
    new = reverse("laboratory:qualification_new") + f"?training={training.pk}"
    assert new not in client.get(detail).content.decode()

    client.force_login(people["reviewer"])
    assert new in client.get(detail).content.decode()
    form = client.get(new).context["form"]
    assert form.initial["user"] == people["analyst"]
    assert form.initial["activity"] == "HPLC-ASSAY"
    assert [t.pk for t in form.initial["training"]] == [training.pk]
    today = timezone.localdate()
    response = client.post(
        reverse("laboratory:qualification_new"),
        {
            "user": people["analyst"].pk,
            "activity": "HPLC-ASSAY",
            "work": "review",
            "training": [training.pk],
            "evidence_ref": "QUAL-SYN-9",
            "valid_from": today.isoformat(),
            "valid_until": (today + timedelta(days=200)).isoformat(),
            "reason": "Qualified from training",
        },
    )
    recorded = Qualification.objects.get()
    assert response.status_code == 302
    assert (recorded.work, recorded.training) == ("review", [training.pk])
    html = client.get(reverse("laboratory:qualification_detail", args=[recorded.pk])).content
    html = html.decode()
    assert (
        "Reviewing results" in html and "Training relied on" in html and training.identifier in html
    )
    html = client.get(detail).content.decode()
    assert f"QUAL-{recorded.pk}" in html and "Reviewing results" in html
    approve_page = client.get(reverse("laboratory:qualification_approve", args=[recorded.pk]))
    assert approve_page.status_code == 403  # the recorder cannot approve
    client.force_login(people["quality"])
    approve_page = client.get(reverse("laboratory:qualification_approve", args=[recorded.pk]))
    assert training.identifier in approve_page.content.decode()


def test_training_list_filters_and_searches(client, people):
    pending = record_training(people, people["analyst"], document_ref="SOP-ALPHA rev 1")
    done = record_training(people, people["analyst2"], "GC-ASSAY", acknowledge=True)
    failed = record_training(
        people,
        people["analyst2"],
        kind="assessment",
        outcome="not_yet_competent",
        acknowledge=True,
    )
    client.force_login(people["auditor"])
    url = reverse("laboratory:training_list")

    def shown(**params):
        rows = client.get(url, params).context["rows"]
        return {row[0]["text"] for row in rows}

    assert shown() == {pending.identifier, done.identifier, failed.identifier}
    assert shown(status="recorded") == {pending.identifier}
    assert shown(status="acknowledged") == {done.identifier, failed.identifier}
    assert shown(outcome="not_yet_competent") == {failed.identifier}
    assert shown(kind="assessment") == {failed.identifier}
    rows = {row[0]["text"]: row for row in client.get(url).context["rows"]}
    assert rows[failed.identifier][4]["text"] == "Not yet competent"
    assert rows[failed.identifier][4]["tone"] == "warning"
    assert rows[failed.identifier][6]["text"] == "Acknowledged"
    assert shown(q="alpha") == {pending.identifier}
    assert shown(q="gc-assay") == {done.identifier}
    page = client.get(url)
    assert reverse("laboratory:training_new") not in page.content.decode()  # read-only role


def test_qualification_list_shows_and_filters_what_each_is_for(client, people):
    perform = qualification(people, people["analyst"])
    review = qualification(people, people["analyst"], work="review")
    client.force_login(people["auditor"])
    url = reverse("laboratory:qualification_list")
    rows = client.get(url, {"work": "review"}).context["rows"]
    assert [row[0]["href"] for row in rows] == [
        reverse("laboratory:qualification_detail", args=[review.pk])
    ]
    rows = client.get(url, {"work": "perform"}).context["rows"]
    assert [row[3]["text"] for row in rows] == ["Performing the work"]
    assert perform.work == "perform"


def test_overview_counts_training_awaiting_acknowledgement(client, people):
    record_training(people, people["analyst"])
    record_training(people, people["analyst2"], acknowledge=True)
    client.force_login(people["analyst"])
    queues = client.get(reverse("laboratory:overview")).context["queues"]
    (queue,) = [q for q in queues if q["label"] == "Training awaiting acknowledgement"]
    assert queue["count"] == 1
    assert queue["href"] == reverse("laboratory:training_list") + "?status=recorded"


# --- Review findings ---------------------------------------------------------------------------


def test_whoever_recorded_the_training_cited_cannot_approve_the_qualification(client, people):
    training = record_training(people, people["analyst"], recorder="quality", acknowledge=True)
    recorded = qualification(people, people["analyst"], training=[training])
    with pytest.raises(PermissionDenied, match="You recorded training this qualification"):
        approve(people, recorded, signer="quality")
    recorded.refresh_from_db()
    assert recorded.state == "recorded"
    client.force_login(people["quality"])
    detail = reverse("laboratory:qualification_detail", args=[recorded.pk])
    approve_url = reverse("laboratory:qualification_approve", args=[recorded.pk])
    assert approve_url not in client.get(detail).content.decode()
    refused = client.get(approve_url)
    assert refused.status_code == 403
    assert "You recorded training this qualification relies on" in refused.content.decode()
    assert approve(people, recorded, signer="quality2").state == "approved"


def test_an_acknowledgement_needs_its_time_and_a_bad_training_link_opens_a_blank_form(
    client, people
):
    with pytest.raises(DatabaseError), transaction.atomic():
        TrainingRecord.objects.create(
            trainee=people["analyst"],
            activity="HPLC-ASSAY",
            document_ref="SOP rev 1",
            kind="read",
            outcome="completed",
            trainer="Synthetic Trainer",
            completed_on=timezone.localdate(),
            recorded_by=people["reviewer"],
            state="acknowledged",
        )
    client.force_login(people["reviewer"])
    for value in ("abc", "999999", ""):
        page = client.get(reverse("laboratory:qualification_new"), {"training": value})
        assert page.status_code == 200 and not page.context["form"].initial
