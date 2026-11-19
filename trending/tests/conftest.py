"""Synthetic configuration and lots for trend charts, through the production services only: an
approved material, method, specification with a numeric assay, sampling plan and rule set, and a
helper that receives a lot and records, submits and reviews its assay result."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from analytical import services as analytical
from catalog import services as catalog
from core.services import approve_rule, save_rule, set_pin
from laboratory import services as laboratory
from quality import services as quality
from sampling import services as sampling
from tests.receipts import on_site_receipt

PIN = "84621357"
PASSWORD = "Synthetic-trend-login-2026!"
ROLES = {
    "author": ["quality"],
    "approver": ["quality"],
    "quality3": ["quality"],
    "analyst": ["analyst"],
    "analyst_quality": ["analyst", "quality"],
    "reviewer": ["reviewer"],
    "receiver": ["analyst"],
    "auditor": ["auditor"],
    "admin": ["admin"],
}


def approve(revision, actor):
    revision.refresh_from_db()
    return catalog.approve_revision(
        actor=actor,
        pin=PIN,
        revision=revision,
        expected_revision=revision.revision,
        reason="Independent synthetic configuration review",
    )


def specification(people, material, method, *, code, stage, unit="%", window):
    author, approver = people["author"], people["approver"]
    start, end = window
    _, revision = catalog.create_specification(
        actor=author,
        code=code,
        title=f"Synthetic {stage} specification",
        material=material,
        stage=stage,
        scope="general",
        basis="Synthetic test limits",
        effective_from=start,
        effective_until=end,
        reason="Synthetic specification",
    )
    catalog.add_test_line(
        actor=author,
        revision=revision,
        reason="Synthetic numeric assay",
        code="assay",
        name="Assay",
        method=method,
        result_type="numeric",
        unit=unit,
        lower_limit=Decimal("90"),
        upper_limit=Decimal("110"),
        lower_inclusive=True,
        upper_inclusive=True,
        reporting_decimals=2,
        replicates=1,
        replicate_limits=True,
        max_retests=0,
        required=True,
    )
    catalog.add_test_line(
        actor=author,
        revision=revision,
        reason="Synthetic identity",
        code="identity",
        name="Identity",
        method=method,
        result_type="qualitative",
        expected_text="Conforms to the reference spectrum",
        expected_result="conforms",
        replicates=1,
        replicate_limits=True,
        max_retests=0,
        required=False,
    )
    return approve(revision, approver)


@pytest.fixture
def trend(django_user_model):
    return make_trend(django_user_model)


def make_trend(django_user_model):
    """The synthetic people and approved configuration (also used by the browser journey)."""
    people = {}
    for name, roles in ROLES.items():
        person = django_user_model.objects.create_user(
            username=f"synthetic_{name}",
            password=PASSWORD,
            first_name="Synthetic",
            last_name=name.title(),
        )
        person.groups.add(*[Group.objects.get_or_create(name=r)[0] for r in roles])
        if name not in ("auditor", "admin"):
            set_pin(actor=person, pin=PIN, password=PASSWORD)
        people[name] = person
    author, approver = people["author"], people["approver"]
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=365)
    rules = save_rule(
        actor=author,
        code="synthetic-trend",
        segment="chemical",
        policy={
            "required_tests": ["assay"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
        effective_from=start,
        effective_until=end,
        reason="Synthetic trend policy",
    )
    rules = approve_rule(
        actor=approver,
        pin=PIN,
        rule=rules,
        expected_revision=rules.revision,
        reason="Independent synthetic policy review",
    )
    material = catalog.create_material(
        actor=author,
        code="syn-trend-api",
        name="Synthetic trend substance",
        kind="raw_material",
        reason="Synthetic master data",
    )
    method, method_revision = catalog.create_method(
        actor=author,
        code="syn-trend-assay",
        title="Synthetic assay",
        technique="Titration",
        document_ref="SOP-SYN-TREND rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-TREND rev 1",
        requires_batch=False,
        effective_from=start,
        effective_until=end,
        reason="Explicit no-batch synthetic method",
    )
    approve(method_revision, approver)
    spec = specification(
        people, material, method, code="syn-trend-spec", stage="incoming", window=(start, end)
    )
    _, plan = sampling.create_plan(
        actor=author,
        code="syn-trend-plan",
        title="Synthetic sampling plan",
        material=material,
        stage="incoming",
        basis="all",
        minimum_quantity=Decimal("10"),
        quantity_unit="g",
        instructions="Take one identified sample from each container.",
        rationale="Synthetic single-container lots only",
        effective_from=start,
        effective_until=end,
        reason="Synthetic sampling plan",
    )
    approve(plan, approver)
    for analyst in ("analyst", "analyst_quality"):
        qualification = laboratory.record_qualification(
            actor=author,
            user=people[analyst],
            activity=method.code,
            evidence_ref="QUAL-SYN-TREND rev 1",
            valid_from=start.date(),
            valid_until=end.date(),
            reason="Synthetic analyst training evidence",
        )
        laboratory.approve_qualification(
            actor=approver,
            pin=PIN,
            qualification=qualification,
            expected_revision=qualification.revision,
            reason="Independent training evidence review",
        )
    return {
        "people": people,
        "rules": rules,
        "material": material,
        "method": method,
        "spec": spec,
        "line": spec.tests.get(code="assay"),
        "window": (start, end),
        "count": 0,
    }


def reviewed_lot(data, value, *, analyst="analyst", stage="incoming", material=None):
    """Receive a lot, assign and sample it, record ``value`` for its assay, submit and review
    it. Returns the reviewed assay test."""
    people = data["people"]
    data["count"] += 1
    number = f"SYN-TREND-{data['count']:03d}"
    lot = quality.receive_lot(
        actor=people["receiver"],
        number=number,
        material="Synthetic trend substance",
        rules=data["rules"],
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    sampler = people[analyst]
    sampling.assign_requirements(
        actor=sampler,
        lot=lot,
        material=material or data["material"],
        stage=stage,
        reason="Assign approved synthetic policy",
    )
    record = sampling.record_sampling(
        actor=sampler,
        lot=lot,
        reference=f"{number}-S1",
        sampled_at=timezone.now(),
        containers_total=1,
        containers_sampled=1,
        container_ids="SYN-C001",
        quantity=Decimal("10"),
        quantity_unit="g",
        location="Synthetic sampling booth",
        reason="Synthetic controlled sampling",
    )
    tests, holds = analytical.assign_tests(
        actor=sampler, sample=record.sample, reason="Assign frozen required tests"
    )
    assert holds == [], holds
    test = next(t for t in tests if t.test_code == "assay")
    analytical.record_observation(
        actor=people[analyst],
        test=test,
        value=Decimal(value),
        raw_reference=f"RAW-{number}",
        reason="Synthetic original observation",
    )
    test.refresh_from_db()
    analytical.submit_test(
        actor=people[analyst], test=test, expected_revision=test.revision, reason="Submit"
    )
    test.refresh_from_db()
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Raw data checked",
    )
    test.refresh_from_db()
    return test


BASELINE = ["100.1", "99.8", "100.3", "99.9", "100.0", "100.2", "99.7", "100.1", "100.0", "99.9"]
