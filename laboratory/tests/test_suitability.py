"""The instruments, reagents and standards a method version lists as suitable, checked at the bench
beside calibration, release and expiry: what is refused, what answers a line, the evidence kept,
the choices offered and the register shown beside each line."""

import pytest
from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent
from laboratory import services, suitability
from laboratory.models import ResourceUse

from .helpers import (
    PIN,
    accept_new_calibration,
    make_reagent,
    qualify_analyst,
    qualify_equipment,
)

pytestmark = pytest.mark.django_db(transaction=True)

METHOD = "HPLC-ASSAY"


def line(kind="instrument", name="HPLC", required=True, method_qualified=False):
    return {"kind": kind, "name": name, "required": required, "method_qualified": method_qualified}


def instrument(people, asset, category, *, qualified=True, activity="IQ/OQ/PQ"):
    item = services.register_equipment(
        actor=people["analyst"],
        asset_id=asset,
        description=f"Synthetic {category}",
        category=category,
        location="Room 1",
        requires_qualification=True,
        reason="Synthetic registration",
    )
    accept_new_calibration(people, item)
    if qualified:
        qualify_equipment(people, item, activity=activity)
    return item


@pytest.fixture
def bench(people):
    qualify_analyst(people, people["analyst"], METHOD)
    standard = make_reagent(people, "RS-1", kind="reference_standard", name="Caffeine  RS")
    return {
        "hplc": instrument(people, "LC-1", "hplc"),
        "balance": instrument(people, "BAL-1", "Analytical balance"),
        "uv": instrument(people, "UV-1", "UV-Vis"),
        "standard": standard,
        "solution": make_reagent(
            people, "WS-1", kind="prepared_solution", name="Working standard", parent=standard
        ),
        "solvent": make_reagent(people, "R-1", name="Acetonitrile"),
    }


def use(people, lines, *, equipment=(), reagents=()):
    with transaction.atomic():
        return services.use_in_work(
            actor=people["analyst"],
            activity=METHOD,
            context_type="analytical.analyticaltest",
            context_id=1,
            test_code="assay",
            equipment_ids=[e.pk for e in equipment],
            reagent_ids=[r.pk for r in reagents],
            reason="Result entry",
            suitable=lines,
        )


def refused(people, lines, **selected):
    with pytest.raises(services.UseBlocked) as caught:
        use(people, lines, **selected)
    assert not ResourceUse.objects.exists()
    return caught.value


LINES = [
    line(),
    line(name="analytical balance", required=False),
    line("reference_standard", "Caffeine RS"),
    line("reagent", "Acetonitrile", required=False),
]


def test_listed_resources_are_used_and_the_evidence_names_their_lines(people, bench):
    evidence = use(
        people,
        LINES,
        equipment=[bench["hplc"], bench["balance"]],
        reagents=[bench["solution"], bench["solvent"]],
    )
    assert [e["suitable_as"] for e in evidence["equipment"]] == ["HPLC", "analytical balance"]
    # The working solution answers the standard's line through the lot it was prepared from.
    assert [r["suitable_as"] for r in evidence["reagents"]] == [
        [{"kind": "reference_standard", "name": "Caffeine RS", "lot": "RS-1"}],
        [{"kind": "reagent", "name": "Acetonitrile", "lot": "R-1"}],
    ]
    stored = ResourceUse.objects.get(reagent_lot=bench["solution"])
    assert stored.eligibility["suitable_as"][0]["lot"] == "RS-1"


def test_without_lines_any_fit_resource_is_used_as_before(people, bench):
    evidence = use(people, [], equipment=[bench["uv"]], reagents=[bench["solvent"]])
    assert "suitable_as" not in evidence["equipment"][0]
    assert "suitable_as" not in evidence["reagents"][0]


def test_an_instrument_of_another_category_is_refused_and_audited_by_the_caller(people, bench):
    blocked = refused(
        people, LINES, equipment=[bench["hplc"], bench["uv"]], reagents=[bench["standard"]]
    )
    (finding,) = [f for f in blocked.findings if not f.ok]
    assert finding.subject == "UV-1"
    assert (
        "category “UV-Vis” is not one that method HPLC-ASSAY lists as suitable"
        in (finding.reasons[0])
    )
    assert "“HPLC”, “analytical balance”" in finding.reasons[0]
    assert not AuditEvent.objects.filter(action="resource.used").exists()


def test_a_lot_not_listed_nor_prepared_from_one_is_refused(people, bench):
    other = make_reagent(people, "R-2", name="Methanol")
    blocked = refused(people, LINES, equipment=[bench["hplc"]], reagents=[bench["standard"], other])
    (finding,) = [f for f in blocked.findings if not f.ok]
    assert finding.subject == "R-2"
    assert "does not list the reagent “Methanol” as suitable" in finding.reasons[0]


def test_every_required_line_must_be_answered(people, bench):
    blocked = refused(people, LINES, equipment=[bench["balance"]], reagents=[bench["solvent"]])
    method = blocked.findings[-1]
    assert method.subject == "Method HPLC-ASSAY" and not method.ok
    assert method.reasons == (
        "Select an instrument of the category “HPLC”; method HPLC-ASSAY requires one.",
        "Select a reference standard “Caffeine RS” or a solution prepared from it; method "
        "HPLC-ASSAY requires one.",
    )
    # Nothing selected at all: the required lines still refuse.
    assert len(refused(people, LINES).findings[-1].reasons) == 2


def test_lines_of_one_kind_leave_the_other_kind_open(people, bench):
    evidence = use(people, [line()], equipment=[bench["hplc"]], reagents=[bench["solvent"]])
    assert "suitable_as" not in evidence["reagents"][0]
    evidence = use(
        people,
        [line("reagent", "Acetonitrile")],
        equipment=[bench["uv"]],
        reagents=[bench["solvent"]],
    )
    assert "suitable_as" not in evidence["equipment"][0]


def test_a_line_can_ask_for_an_instrument_qualified_for_the_method(people, bench):
    lines = [line(method_qualified=True)]
    blocked = refused(people, lines, equipment=[bench["hplc"]])
    assert blocked.findings[1].reasons == (
        "No approved, current qualification of this instrument for method HPLC-ASSAY.",
    )
    qualification = qualify_equipment(people, bench["hplc"], activity=" hplc-assay ")
    evidence = use(people, lines, equipment=[bench["hplc"]])
    assert evidence["equipment"][0]["method_qualification"] == qualification.pk
    # A revoked qualification no longer counts.
    services.revoke_qualification(
        actor=people["quality"],
        pin=PIN,
        qualification=qualification,
        expected_revision=qualification.revision,
        reason="Method transferred to another instrument",
    )
    with pytest.raises(services.UseBlocked):
        use(people, lines, equipment=[bench["hplc"]])


def test_fitness_and_suitability_reasons_are_reported_together(people, bench):
    services.take_out_of_service(actor=people["analyst"], equipment=bench["uv"], reason="Drift")
    blocked = refused(people, LINES, equipment=[bench["uv"]])
    reasons = [r for f in blocked.findings if f.subject == "UV-1" for r in f.reasons]
    assert reasons[0] == "Equipment is out of service."
    assert "is not one that method" in reasons[1]


def test_apply_refuses_findings_that_do_not_match_the_selection(people, bench):
    with pytest.raises(ValueError):
        suitability.apply([], LINES, activity=METHOD, equipment=[bench["hplc"]], reagents=[])


# Choices at the bench and the register on the method page ----------------------------------


def test_the_bench_offers_only_what_the_version_lists(people, bench):
    everything = services.bench_choices()
    assert {pk for pk, _ in everything["equipment"]} == {
        bench[k].pk for k in ("hplc", "balance", "uv")
    }
    narrowed = services.bench_choices([line(method_qualified=True), *LINES[2:]], METHOD)
    assert [label for _, label in narrowed["equipment"]] == [
        "LC-1 · Synthetic hplc · Ready · Not qualified for HPLC-ASSAY"
    ]
    assert {pk for pk, _ in narrowed["reagents"]} == {
        bench[k].pk for k in ("standard", "solution", "solvent")
    }
    qualify_equipment(people, bench["hplc"], activity=METHOD)
    narrowed = services.bench_choices([line(method_qualified=True)], METHOD)
    assert [label for _, label in narrowed["equipment"]] == ["LC-1 · Synthetic hplc · Ready"]
    assert len(narrowed["reagents"]) == len(everything["reagents"])  # no lot line: all offered


def test_the_register_beside_each_line(people, bench):
    expired = make_reagent(
        people,
        "RS-OLD",
        kind="reference_standard",
        name="caffeine rs",
        release=False,
        received_on=timezone.localdate() - timezone.timedelta(days=400),
        expiry_days=-1,
    )
    rows = suitability.register(
        [line(method_qualified=True), line("reference_standard", "Caffeine RS"), line(name="GC")],
        activity=METHOD,
    )
    hplc, standard, gc = rows
    assert [(e["id"], e["label"], e["tone"]) for e in hplc["entries"]] == [
        ("LC-1", "Ready · Not qualified for the method", "warning")
    ]
    assert [e["id"] for e in standard["entries"]] == ["RS-1", "WS-1"]
    assert expired.identifier not in [e["id"] for e in standard["entries"]]
    assert gc["entries"] == [] and gc["more"] == 0


def test_register_names_by_kind(people, bench):
    names = suitability.register_names()
    assert names["instrument"] == ["Analytical balance", "hplc", "UV-Vis"]
    assert names["reference_standard"] == ["Caffeine RS"]
    assert names["prepared_solution"] == ["Working standard"]
    assert names["reagent"] == ["Acetonitrile"]


def test_each_kind_of_lot_is_constrained_on_its_own(people, bench):
    lines = [line("reference_standard", "Caffeine RS")]
    other_standard = make_reagent(people, "RS-2", kind="reference_standard", name="Theophylline RS")
    wrong_solution = make_reagent(
        people, "WS-2", kind="prepared_solution", name="Working standard", parent=other_standard
    )
    mobile_phase = make_reagent(
        people, "MP-1", kind="prepared_solution", name="Mobile phase A", parent=bench["solvent"]
    )
    # Solvents, buffers and solutions made from them stay open while no reagent is listed.
    evidence = use(people, lines, reagents=[bench["solution"], bench["solvent"], mobile_phase])
    assert [("suitable_as" in r) for r in evidence["reagents"]] == [True, False, False]
    # Another standard, or a solution prepared from one, is refused.
    used = ResourceUse.objects.count()
    for lot in (other_standard, wrong_solution):
        with pytest.raises(services.UseBlocked) as caught:
            use(people, lines, reagents=[bench["standard"], lot])
        (finding,) = [f for f in caught.value.findings if not f.ok]
        assert finding.subject == lot.identifier
    assert ResourceUse.objects.count() == used
    offered = {pk for pk, _ in services.bench_choices(lines, METHOD)["reagents"]}
    assert {bench["standard"].pk, bench["solution"].pk, bench["solvent"].pk, mobile_phase.pk} <= (
        offered
    )
    assert not {other_standard.pk, wrong_solution.pk} & offered


def test_the_bench_says_which_kinds_a_required_line_asks_for(people, bench):
    choices = services.bench_choices(
        [line(required=False), line("reagent", "Acetonitrile")], METHOD
    )
    assert choices["required"] == {"equipment": False, "reagents": True}


def test_method_qualification_matches_as_at_entry_and_danger_stays_danger(people, bench):
    lines = [line(method_qualified=True)]
    qualify_equipment(people, bench["hplc"], activity="  hplc-assay ")
    labels = [label for _, label in services.bench_choices(lines, METHOD)["equipment"]]
    assert labels == ["LC-1 · Synthetic hplc · Ready"]
    other = instrument(people, "LC-2", "HPLC", qualified=False)
    services.take_out_of_service(actor=people["analyst"], equipment=other, reason="Leak")
    (row,) = suitability.register(lines, activity=METHOD)
    entries = {e["id"]: (e["label"], e["tone"]) for e in row["entries"]}
    assert entries["LC-1"] == ("Ready", "success")
    assert entries["LC-2"] == ("Out of service · Not qualified for the method", "danger")
