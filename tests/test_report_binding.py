"""The platform CoA collector must follow the assignment signed at disposition."""

from copy import deepcopy

import pytest

from analytical import services as analytical
from catalog.services import digest
from reporting import services as reporting
from sampling.models import LotAssignment
from tests.test_integrated_journey import PIN, assign_and_sample, dispose, observed_test
from tests.test_integrated_journey import integrated as integrated  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_later_assignment_cannot_replace_disposition_bound_certificate_methods(integrated):
    data, people = integrated, integrated["people"]
    test, _ = observed_test(data, assign_and_sample(data), "100.25")
    analytical.review_test(
        actor=people["reviewer"],
        pin=PIN,
        test=test,
        expected_revision=test.revision,
        reason="Independent original-data review",
    )
    lot = dispose(data, people["approver"])
    before, preview_hash, blockers = reporting.preview(lot)
    assert blockers == []
    signed_assignment = LotAssignment.objects.get(pk=lot.disposition_evidence["assignment_id"])

    # Services forbid reassignment after testing/release. Simulate an erroneous append-only
    # import to prove reporting resolves the signed pointer, never the newest assignment.
    unrelated_payload = deepcopy(signed_assignment.payload)
    unrelated_payload["tests"][0]["method"]["code"] = "SYN-UNRELATED-LATER"
    later = LotAssignment.objects.create(
        lot=lot,
        material=signed_assignment.material,
        stage=signed_assignment.stage,
        scope=signed_assignment.scope,
        status=signed_assignment.status,
        specification_revision=signed_assignment.specification_revision,
        plan_revision=signed_assignment.plan_revision,
        payload=unrelated_payload,
        payload_hash=digest(unrelated_payload),
        supersedes=signed_assignment,
        reason="Synthetic erroneous import to exercise signed-source binding",
        assigned_by=people["author"],
    )
    assert lot.qc_assignments.first() == later
    after, current_hash, blockers = reporting.preview(lot)
    assert blockers == []
    assert current_hash == preview_hash
    assert after["methods"] == before["methods"]
    assert after["native"]["assignment_id"] == signed_assignment.pk

    report = reporting.issue_report(
        actor=people["approver"],
        pin=PIN,
        lot=lot,
        recipient="Synthetic frozen-source check",
        evidence_hash=preview_hash,
        reason="Issue exactly the disposition-bound evidence reviewed",
    )
    version = report.versions.get(number=1)
    assert version.snapshot["methods"] == before["methods"]
    assert "SYN-UNRELATED-LATER" not in str(version.snapshot)
    assert reporting.read_pdf(actor=people["reviewer"], version=version) == bytes(version.pdf)
