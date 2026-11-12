"""Synthetic contract fixtures standing in for approved catalog specification snapshots.

These payloads are illustrative test data, not validated methods, compendial limits or segment
requirements. Replace them by configuring ANALYTICAL_REQUIREMENT_PROVIDER once approved
specification/method revisions are published.
"""

import copy

from .contracts import SCHEMA, SCHEMA_V2

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


def requirement_payload(code):
    if code in SPECIFICATIONS_V2:
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


def synthetic_eligibility(*, actor, test):
    """Explicit test override only: treats every analyst as qualified for synthetic methods."""
    return {"policy": "synthetic-test-fixture", "user": actor.pk, "activity": test.spec.method.code}
