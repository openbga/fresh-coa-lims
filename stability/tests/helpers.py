from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest
from laboratory.eligibility import analyst_eligibility
from laboratory.tests.helpers import PIN, make_lot, make_sample, qualify_analyst
from stability import services

__all__ = [
    "PIN",
    "make_lot",
    "make_sample",
    "approved_protocol",
    "started_study",
    "sample_with_result",
]


def approved_protocol(people, code="SYN-STAB", intervals=(30, 100, 180), window=5):
    author, approver = people["analyst"], people["quality"]
    protocol = services.create_protocol(
        actor=author,
        code=code,
        title="Synthetic stability protocol",
        product="Synthetic powder",
        document_ref="DOC-SYN-1 r1",
        document_url="",
        test_profile_ref="PROFILE-SYN r1",
        basis="Synthetic basis, not a regulatory default",
        reason="Synthetic draft",
    )
    condition = services.add_condition(
        actor=author,
        protocol=protocol,
        label="Long-term",
        setpoint="Synthetic setpoint",
        temperature_c=Decimal("25.0"),
        humidity_pct=Decimal("60.0"),
        reason="Synthetic condition",
    )
    for days in intervals:
        services.add_timepoint(
            actor=author,
            protocol=protocol,
            condition=condition,
            label=f"{days} days",
            interval_days=days,
            window_days=window,
            test_codes=["identity"],
            reason="Synthetic timepoint",
        )
    protocol.refresh_from_db()
    return services.approve_protocol(
        actor=approver,
        pin=PIN,
        protocol=protocol,
        expected_revision=protocol.revision,
        reason="Independent approval",
    )


def started_study(people, *, protocol=None, lot=None, days_ago=100, identifier="STB-001"):
    protocol = protocol or approved_protocol(people)
    lot = lot or make_lot(people)
    return services.start_study(
        actor=people["analyst"],
        identifier=identifier,
        protocol=protocol,
        lot=lot,
        container_closure="Synthetic marketed container",
        start_date=timezone.localdate() - timedelta(days=days_ago),
        reason="Synthetic study start",
    )


def sample_with_result(people, study, *, state="reviewed", value="1.0", reference="STB-S-1"):
    """A sample on the study's lot with an identity test in the native testing spine.

    `state` is "assigned", "submitted" or "reviewed"."""
    sample = make_sample(people, study.lot, reference)
    (test,), holds = analytical.assign_tests(
        actor=people["analyst2"], sample=sample, reason="Required tests"
    )
    assert not holds
    if state == "assigned":
        return sample
    # Native observations require current method-specific qualification (integration contract).
    if not analyst_eligibility(people["analyst2"], "SYN-IR").ok:
        qualify_analyst(people, people["analyst2"], "SYN-IR")
    analytical.record_observation(
        actor=people["analyst2"], test=test, value=Decimal(value), raw_reference="NB-1 p1"
    )
    test = AnalyticalTest.objects.get(pk=test.pk)
    analytical.submit_test(
        actor=people["analyst2"], test=test, expected_revision=test.revision, reason="Complete"
    )
    test = AnalyticalTest.objects.get(pk=test.pk)
    if state == "reviewed":
        analytical.review_test(
            actor=people["reviewer2"],
            pin=PIN,
            test=test,
            expected_revision=test.revision,
            reason="Raw data checked",
        )
    return sample


def review_sample(people, sample):
    for test in AnalyticalTest.objects.filter(sample=sample, state="submitted"):
        analytical.review_test(
            actor=people["reviewer2"],
            pin=PIN,
            test=test,
            expected_revision=test.revision,
            reason="Raw data checked",
        )
