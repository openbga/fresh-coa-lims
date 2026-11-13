"""Synthetic contract fixtures standing in for approved catalog specification snapshots.

These payloads are illustrative test data, not validated methods, compendial limits or segment
requirements. Replace them by configuring ANALYTICAL_REQUIREMENT_PROVIDER once approved
specification/method revisions are published. ``SyntheticBench`` likewise stands in for the
laboratory bench checks and is only for explicit test overrides of ANALYTICAL_BENCH.
"""

import copy
import itertools

from django.core.exceptions import ValidationError
from django.db import connection

from .contracts import SCHEMA, SCHEMA_V2, SCHEMA_V3, WorkRefused

UNIT = "% label claim"
METHODS = {
    "SYN-HPLC": {
        "code": "SYN-HPLC",
        "revision": 1,
        "requires_batch": True,
        "qc_checks": [
            {
                "code": "blank",
                "name": "Reagent blank",
                "unit": UNIT,
                "lower_limit": None,
                "upper_limit": "0.05",
            },
            {
                "code": "control",
                "name": "Control standard recovery",
                "unit": "%",
                "lower_limit": "98.0",
                "upper_limit": "102.0",
            },
        ],
    },
    "SYN-IR": {"code": "SYN-IR", "revision": 1, "requires_batch": False, "qc_checks": []},
    "SYN-KF": {"code": "SYN-KF", "revision": 1, "requires_batch": False, "qc_checks": []},
    "SYN-MICRO": {"code": "SYN-MICRO", "revision": 1, "requires_batch": False, "qc_checks": []},
    # Seven-key methods: resource requirements and an optional calculation.
    "SYN-UV": {
        "code": "SYN-UV",
        "revision": 3,
        "requires_batch": False,
        "qc_checks": [],
        "requires_equipment": True,
        "requires_reagent": True,
        "calculation": {
            "formula": "sample_abs / standard_abs * standard_conc / sample_conc * 100",
            "inputs": [
                {"code": "sample_abs", "name": "Sample absorbance", "unit": "AU"},
                {"code": "standard_abs", "name": "Standard absorbance", "unit": "AU"},
                {"code": "standard_conc", "name": "Standard concentration", "unit": "mg/mL"},
                {"code": "sample_conc", "name": "Sample concentration", "unit": "mg/mL"},
            ],
            "unit": UNIT,
            "decimals": 2,
        },
    },
    "SYN-KF-BENCH": {
        "code": "SYN-KF-BENCH",
        "revision": 2,
        "requires_batch": False,
        "qc_checks": [],
        "requires_equipment": True,
        "requires_reagent": False,
        "calculation": None,
    },
    "SYN-LC-BENCH": {
        "code": "SYN-LC-BENCH",
        "revision": 1,
        "requires_batch": True,
        "qc_checks": [
            {
                "code": "control",
                "name": "Control standard recovery",
                "unit": "%",
                "lower_limit": "98.0",
                "upper_limit": "102.0",
            },
        ],
        "requires_equipment": True,
        "requires_reagent": True,
        "calculation": None,
    },
}
SPECIFICATIONS = {
    "identity": {
        "source": "fixture:SYN-SPEC-IDENTITY@1",
        "test_code": "identity",
        "name": "Identity match ratio",
        "unit": "ratio",
        "lower_limit": "0.90",
        "upper_limit": "1.10",
        "replicates": 1,
        "reporting_decimals": 2,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-IR",
    },
    "assay": {
        "source": "fixture:SYN-SPEC-ASSAY@1",
        "test_code": "assay",
        "name": "Assay",
        "unit": UNIT,
        "lower_limit": "95.0",
        "upper_limit": "105.0",
        "replicates": 2,
        "reporting_decimals": 1,
        "replicate_limits": True,
        "max_retests": 2,
        "method": "SYN-HPLC",
    },
    "water": {
        "source": "fixture:SYN-SPEC-WATER@1",
        "test_code": "water",
        "name": "Water content",
        "unit": "% w/w",
        "lower_limit": None,
        "upper_limit": "0.50",
        "replicates": 1,
        "reporting_decimals": 2,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-KF",
    },
}


# oq.test-requirement/2 shapes: a count, an exclusive numeric limit and qualitative results.
SPECIFICATIONS_V2 = {
    "tamc": {
        "source": "fixture:SYN-SPEC-TAMC@1",
        "test_code": "tamc",
        "name": "Total aerobic microbial count",
        "result_type": "count",
        "unit": "CFU/g",
        "lower_limit": None,
        "upper_limit": "1000",
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": None,
        "criterion": "",
        "replicates": 2,
        "reporting_decimals": 0,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-MICRO",
    },
    "impurity": {
        "source": "fixture:SYN-SPEC-IMPURITY@1",
        "test_code": "impurity",
        "name": "Single unspecified impurity",
        "result_type": "numeric",
        "unit": "%",
        "lower_limit": None,
        "upper_limit": "0.10",
        "lower_inclusive": True,
        "upper_inclusive": False,
        "expected_result": None,
        "criterion": "",
        "replicates": 1,
        "reporting_decimals": 2,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-KF",
    },
    "pathogen": {
        "source": "fixture:SYN-SPEC-PATHOGEN@1",
        "test_code": "pathogen",
        "name": "Synthetic pathogen screen",
        "result_type": "qualitative",
        "unit": "",
        "lower_limit": None,
        "upper_limit": None,
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": "absent",
        "criterion": "Absent in 25 g",
        "replicates": 2,
        "reporting_decimals": None,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-MICRO",
    },
    "appearance": {
        "source": "fixture:SYN-SPEC-APPEARANCE@1",
        "test_code": "appearance",
        "name": "Appearance",
        "result_type": "qualitative",
        "unit": "",
        "lower_limit": None,
        "upper_limit": None,
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": "conforms",
        "criterion": "White crystalline powder",
        "replicates": 1,
        "reporting_decimals": None,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-IR",
    },
}


# oq.test-requirement/3 shapes: the /2 keys with a seven-key method.
SPECIFICATIONS_V3 = {
    "uv_assay": {
        "source": "fixture:SYN-SPEC-UV-ASSAY@1",
        "test_code": "uv_assay",
        "name": "Assay by UV",
        "result_type": "numeric",
        "unit": UNIT,
        "lower_limit": "95.0",
        "upper_limit": "105.0",
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": None,
        "criterion": "",
        "replicates": 2,
        "reporting_decimals": 1,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-UV",
    },
    "kf_water": {
        "source": "fixture:SYN-SPEC-KF-WATER@1",
        "test_code": "kf_water",
        "name": "Water content by titration",
        "result_type": "numeric",
        "unit": "% w/w",
        "lower_limit": None,
        "upper_limit": "0.50",
        "lower_inclusive": True,
        "upper_inclusive": True,
        "expected_result": None,
        "criterion": "",
        "replicates": 1,
        "reporting_decimals": 2,
        "replicate_limits": True,
        "max_retests": 1,
        "method": "SYN-KF-BENCH",
    },
}


def requirement_payload(code):
    if code in SPECIFICATIONS_V3:
        spec = SPECIFICATIONS_V3[code]
        payload = {**copy.deepcopy(spec), "schema": SCHEMA_V3}
    elif code in SPECIFICATIONS_V2:
        spec = SPECIFICATIONS_V2[code]
        payload = {**copy.deepcopy(spec), "schema": SCHEMA_V2}
    elif code in SPECIFICATIONS:
        spec = SPECIFICATIONS[code]
        payload = {
            **copy.deepcopy(spec),
            "schema": SCHEMA,
            "result_type": "numeric",
            "bounds": "inclusive",
        }
    else:
        return None
    payload["method"] = copy.deepcopy(METHODS[spec["method"]])
    return payload


class FixtureProvider:
    """Requirement provider interface: requirements(lot) and methods()."""

    def requirements(self, lot):
        """Map each code required by the lot's rule revision to a payload, or None if missing."""
        return {code: requirement_payload(code) for code in lot.rules.policy["required_tests"]}

    def methods(self):
        return [copy.deepcopy(m) for m in METHODS.values() if m["requires_batch"]]


# Synthetic bench: id -> (identifier, name, status). Only "in service" equipment and "released"
# lots are fit for use.
EQUIPMENT = {
    1: ("SYN-BAL-01", "Analytical balance", "in service"),
    2: ("SYN-UV-01", "UV spectrometer", "in service"),
    3: ("SYN-UV-02", "UV spectrometer", "out of service"),
}
REAGENTS = {
    1: ("SYN-RS-001", "Reference standard", "released"),
    2: ("SYN-RS-002", "Reference standard", "expired"),
}
BENCH_LOG = []  # (call, details) in call order, for tests of lock order and refusal audit
UNQUALIFIED = set()  # usernames the synthetic bench treats as not qualified
_USES = itertools.count(1)


class SyntheticBench:
    """Bench interface for explicit test overrides only; never a deployment default.

    Every analyst is qualified unless listed in UNQUALIFIED; equipment must be in service and
    reagent or standard lots released.
    """

    def choices(self):
        return {
            "equipment": [(pk, f"{a} {n} · {st}") for pk, (a, n, st) in EQUIPMENT.items()],
            "reagents": [(pk, f"{i} {n} · {st}") for pk, (i, n, st) in REAGENTS.items()],
        }

    def lock_actor(self, actor):
        if not connection.in_atomic_block:
            raise RuntimeError("lock_actor needs the caller's transaction.")
        BENCH_LOG.append(("lock_actor", {"actor": actor.pk}))

    def authorize(
        self,
        *,
        actor,
        method_code,
        test_code,
        context_type,
        context_id,
        equipment_ids,
        reagent_ids,
        reason,
    ):
        if not connection.in_atomic_block:
            raise RuntimeError("authorize needs the caller's transaction.")
        BENCH_LOG.append(
            (
                "authorize",
                {
                    "method_code": method_code,
                    "test_code": test_code,
                    "context_type": context_type,
                    "context_id": context_id,
                    "equipment_ids": list(equipment_ids),
                    "reagent_ids": list(reagent_ids),
                    "reason": reason,
                },
            )
        )
        if set(equipment_ids) - set(EQUIPMENT) or set(reagent_ids) - set(REAGENTS):
            raise ValidationError("Unknown equipment or reagent lot.")
        refusals = []
        if actor.get_username() in UNQUALIFIED:
            refusals.append(
                {
                    "subject": actor.get_username(),
                    "reasons": [f"No approved, current qualification for “{method_code}”."],
                }
            )
        for pk in equipment_ids:
            asset, _, status = EQUIPMENT[pk]
            if status != "in service":
                refusals.append({"subject": asset, "reasons": [f"Equipment is {status}."]})
        for pk in reagent_ids:
            identifier, _, status = REAGENTS[pk]
            if status != "released":
                refusals.append({"subject": identifier, "reasons": [f"Lot is {status}."]})
        if refusals:
            raise WorkRefused(refusals)
        return {
            "policy": "synthetic-test-fixture",
            "user": actor.pk,
            "activity": method_code,
            "qualification": None,
            "equipment": [
                {"id": pk, "asset_id": EQUIPMENT[pk][0], "use": next(_USES)} for pk in equipment_ids
            ],
            "reagents": [
                {"id": pk, "identifier": REAGENTS[pk][0], "use": next(_USES)} for pk in reagent_ids
            ],
        }

    def record_refusal(
        self, *, actor, method_code, test_code, context_type, context_id, refusals, reason
    ):
        BENCH_LOG.append(
            (
                "record_refusal",
                {
                    "in_transaction": connection.in_atomic_block,
                    "actor": actor.pk,
                    "method_code": method_code,
                    "test_code": test_code,
                    "context_type": context_type,
                    "context_id": context_id,
                    "refusals": refusals,
                    "reason": reason,
                },
            )
        )
