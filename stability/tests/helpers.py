from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from analytical import services as analytical
from analytical.models import AnalyticalTest
from catalog import services as catalog
from laboratory.eligibility import analyst_eligibility
from laboratory.tests.helpers import PIN, make_lot, make_sample, qualify_analyst
from sampling import services as sampling
from stability import services

__all__ = [
    "PIN",
    "make_lot",
    "make_sample",
    "approved_protocol",
    "draft_protocol",
    "started_study",
    "sample_with_result",
    "shelf_life",
    "specified_study",
    "pulled",
    "assign",
    "observe",
    "submit",
    "review",
    "reviewed",
    "accept",
]


def draft_protocol(
    people,
    code="SYN-STAB",
    intervals=(30, 100, 180),
    window=5,
    *,
    specification=None,
    test_codes=("identity",),
):
    """A draft protocol with one condition and a time point at each interval."""
    author = people["analyst"]
    protocol = services.create_protocol(
        actor=author,
        code=code,
        title="Synthetic stability protocol",
        product="Synthetic powder",
        document_ref="DOC-SYN-1 r1",
        document_url="",
        test_profile_ref="PROFILE-SYN r1",
        specification=specification,
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
            test_codes=list(test_codes),
            reason="Synthetic timepoint",
        )
    protocol.refresh_from_db()
    return protocol


def approved_protocol(people, code="SYN-STAB", intervals=(30, 100, 180), window=5, **options):
    protocol = draft_protocol(people, code, intervals, window, **options)
    return services.approve_protocol(
        actor=people["quality"],
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


# --- Pulls tested in the system ----------------------------------------------------------------

SHELF_LIFE_METHOD = "syn-shelf-assay"


def approve_revision(people, revision):
    revision.refresh_from_db()
    return catalog.approve_revision(
        actor=people["quality2"],
        pin=PIN,
        revision=revision,
        expected_revision=revision.revision,
        reason="Independent synthetic configuration review",
    )


def add_line(people, revision, code="assay", **overrides):
    """A numeric line, 95.0 to 105.0 %, one replicate, one retest allowed."""
    values = {
        "code": code,
        "name": code.title(),
        "result_type": "numeric",
        "unit": "%",
        "lower_limit": Decimal("95"),
        "upper_limit": Decimal("105"),
        "lower_inclusive": True,
        "upper_inclusive": True,
        "reporting_decimals": 1,
        "replicates": 1,
        "replicate_limits": True,
        "max_retests": 1,
        "required": True,
    }
    values.update(overrides)
    return catalog.add_test_line(
        actor=people["quality"], revision=revision, reason="Synthetic line", **values
    )


def shelf_life(people, *, codes=("assay",), requires_batch=False, code="syn-shelf-life"):
    """An approved synthetic shelf-life specification (stage stability) with its material and
    method, and ``analyst2`` qualified for the method. Returns a dict of the records."""
    author = people["quality"]
    start, end = timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=365)
    material = catalog.create_material(
        actor=author,
        code="syn-tablet",
        name="Synthetic tablet",
        kind="finished_product",
        reason="Synthetic master data",
    )
    method, method_revision = catalog.create_method(
        actor=author,
        code=SHELF_LIFE_METHOD,
        title="Synthetic stability-indicating assay",
        technique="Liquid chromatography",
        document_ref="SOP-SYN-STB-001 rev 1",
        suitability_kind="validation",
        suitability_ref="VAL-SYN-STB-001 rev 1",
        requires_batch=requires_batch,
        effective_from=start,
        effective_until=end,
        reason="Synthetic method",
    )
    if requires_batch:
        catalog.add_qc_check(
            actor=author,
            revision=method_revision,
            reason="Synthetic control",
            code="control",
            name="Control standard recovery",
            unit="%",
            lower_limit=Decimal("98"),
            upper_limit=Decimal("102"),
        )
    method_revision = approve_revision(people, method_revision)
    specification, revision = catalog.create_specification(
        actor=author,
        code=code,
        title="Synthetic shelf-life specification",
        material=material,
        stage="stability",
        scope="general",
        basis="Synthetic shelf-life limits",
        effective_from=start,
        effective_until=end,
        reason="Synthetic specification",
    )
    for line in codes:
        add_line(people, revision, line, method=method)
    revision = approve_revision(people, revision)
    qualify_analyst(people, people["analyst2"], SHELF_LIFE_METHOD)
    return {
        "material": material,
        "method": method,
        "method_revision": method_revision,
        "specification": specification,
        "revision": revision,
    }


def lot_of(people, material, number="SYN-STB-LOT-1"):
    """A lot whose assigned requirements state its material. No specification exists for the
    material at the incoming stage, so the assignment is a hold: it still names the material."""
    lot = make_lot(people, number)
    sampling.assign_requirements(
        actor=people["analyst"],
        lot=lot,
        material=material,
        stage="incoming",
        reason="Synthetic assignment naming the material",
    )
    lot.refresh_from_db()
    return lot


def specified_study(people, *, config=None, codes=("assay",), intervals=(30, 100, 180), **options):
    """(study, config): a study on a protocol that names the shelf-life specification."""
    config = config or shelf_life(people, codes=codes, **options)
    protocol = approved_protocol(
        people,
        code="SYN-STAB-TESTED",
        intervals=intervals,
        specification=config["specification"],
        test_codes=codes,
    )
    study = started_study(
        people, protocol=protocol, lot=lot_of(people, config["material"]), identifier="STB-T-001"
    )
    return study, config


def pulled(people, study, interval=100):
    pull = study.pulls.get(timepoint__interval_days=interval)
    return services.record_pull(
        actor=people["analyst"],
        pull=pull,
        pulled_on=pull.due_date,
        quantity=Decimal("5"),
        quantity_unit="g",
        storage_location="Synthetic shelf",
        reason="Synthetic pull",
    )


def assign(people, pull):
    return analytical.assign_pull_tests(
        actor=people["analyst2"], pull=pull, reason="Tests of the time point"
    )


def observe(people, test, value="100.2"):
    return analytical.record_observation(
        actor=people["analyst2"], test=test, value=Decimal(value), raw_reference="NB-STB-1 p1"
    )


def submit(people, test):
    test = AnalyticalTest.objects.get(pk=test.pk)
    return analytical.submit_test(
        actor=people["analyst2"], test=test, expected_revision=test.revision, reason="Complete"
    )


def review(people, test, reviewer="reviewer2"):
    test = AnalyticalTest.objects.get(pk=test.pk)
    return analytical.review_test(
        actor=people[reviewer],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Raw data checked",
    )


def reviewed(people, test, value="100.2"):
    """Record, submit and review one result; returns (test, investigation or None)."""
    observe(people, test, value)
    _, investigation = submit(people, test)
    return review(people, test), investigation


def accept(people, pull, reviewer="reviewer"):
    pull.refresh_from_db()
    return services.accept_pull(
        actor=people[reviewer],
        pin=PIN,
        pull=pull,
        expected_revision=pull.revision,
        reason="Pull and results reviewed",
    )
