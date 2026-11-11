"""Synthetic contract fixtures standing in for approved catalog specification snapshots.

These payloads are illustrative test data, not validated methods, compendial limits or segment
requirements. Replace them by configuring ANALYTICAL_REQUIREMENT_PROVIDER once approved
specification/method revisions are published.
"""

import copy

from .contracts import SCHEMA

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


def requirement_payload(code):
    spec = SPECIFICATIONS.get(code)
    if spec is None:
        return None
    payload = {
        **copy.deepcopy(spec),
        "schema": SCHEMA,
        "result_type": "numeric",
        "bounds": "inclusive",
    }
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
