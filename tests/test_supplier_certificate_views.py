"""Supplier certificates through the pages: recording, the records, corrections, withdrawal."""

import pytest
from django.urls import reverse

from core.models import AuditEvent
from quality import certificates
from quality import services as quality
from quality.models import SupplierCertificate, SupplierCertificateWithdrawal
from tests.receipts import on_site_receipt, supplier_receipt
from tests.test_integrated_journey import dispose
from tests.test_supplier_certificates import (
    assign,
    basis,
    build_supplied_world,
    certify,
    correct,
    sample_and_test,
    stated,
    withdraw,
)

pytestmark = pytest.mark.django_db(transaction=True)
OTHER_ROLES = ["reviewer", "quality", "auditor", "admin"]
MEETS, FAILS = "Meets the specification", "Does not meet the specification"


@pytest.fixture
def world(django_user_model):
    return build_supplied_world(django_user_model)


def url(name, record):
    return reverse(f"quality:{name}", args=[record.pk])


def posted(lot, **changes):
    """A submitted certificate form, as text: three results stated, two tests left blank."""
    data = {
        "number": "COA-SYN-0001",
        "issued_by": "Synthetic Ingredients Supply",
        "issued_on": "2026-11-02",
        "stated_lot": "SUP-LOT-SYN-001",
        "document_ref": "DMS-SYN-COA-0001",
        "notes": "",
        "basis": basis(lot),
        "assay__value": "99.60",
        "assay__method": "Supplier HPLC-07",
        "assay__limits": "98.0 - 102.0 %",
        "identity__outcome": "conforms",
        "identity__stated": "Complies",
        "tamc__value": "10",
        "tamc__less_than": "on",
        "reason": "Synthetic certificate transcribed",
    }
    return data | changes


def sign_in(client, world, name="analyst2"):
    client.force_login(world["people"][name])


def test_new_page_offers_every_requirement_beside_the_receipt(client, world):
    sign_in(client, world)
    response = client.get(url("certificate_new", world["lot"]))
    body = response.content.decode()
    assert response.status_code == 200
    for legend in (
        "Certificate",
        "Assay: specification 98 to 102 %",
        "Identity: specification Conforms to the reference standard (expected: Conforms)",
        "Impurity: specification less than 5 mg/g",
        "Salmonella: specification Absent in 25 g (expected: Absent)",
        "Total aerobic count: specification at most 200 CFU/g",
        "Change control",
    ):
        assert f"<legend>{legend}</legend>" in body
    for shown in (
        "Record supplier certificate",
        "kept apart from the laboratory&#x27;s own tests",
        "sup-syn-001 · Synthetic Ingredients Supply",
        "SUP-LOT-SYN-001",
        "MFG-SYN-0009",
        "Assay result (%)",
        "Total aerobic count stated as less than this value",
        "Identity wording on the certificate",
        "Not stated on the certificate",
    ):
        assert shown in body
    form = response.context["form"]
    assert form["basis"].value() == basis(world["lot"])
    assert form["issued_on"].value() is None  # The date is stated, not assumed.
    assert [choice for choice, _ in form.fields["salmonella__outcome"].choices] == [
        "",
        "absent",
        "present",
    ]


def test_certificate_is_recorded_through_the_form(client, world):
    lot = world["lot"]
    sign_in(client, world)
    response = client.post(url("certificate_new", lot), posted(lot))
    certificate = SupplierCertificate.objects.get()
    assert response.status_code == 302 and response.url == url("certificate_detail", certificate)
    assert [(line.test_code, line.value_text) for line in certificate.results.all()] == [
        ("assay", "99.60"),
        ("identity", "Conforms"),
        ("tamc", "<10"),
    ]
    assert certificate.recorded_by == world["people"]["analyst2"]
    body = client.get(response.url).content.decode()
    for shown in (
        "Supplier certificate recorded.",
        "Supplier certificate COA-SYN-0001",
        "They are not the laboratory's own tests",
        "As on the receipt",
        "DMS-SYN-COA-0001",
        "99.60",
        "&lt;10",
        "Stated as: Complies",
        "Supplier HPLC-07",
        "98.0 - 102.0 %",
        "98 to 102 %",
        "at most 200 CFU/g",
        "Not stated",
        "Correct supplier certificate",
        "Withdraw supplier certificate",
        "Synthetic certificate transcribed",
    ):
        assert shown in body, shown
    assert body.count(MEETS) == 3 and FAILS not in body
    assert "Requirement no longer current" not in body
    record = client.get(url("lot_detail", lot)).content.decode()
    assert f'href="{url("certificate_detail", certificate)}"' in record
    assert "All meet the specification" in record and "Current" in record
    assert "counts towards QC disposition only when it is accepted in place of a test" in record


def test_refused_form_keeps_entries_and_records_nothing(client, world):
    lot = world["lot"]
    sign_in(client, world)
    response = client.post(
        url("certificate_new", lot),
        posted(
            lot,
            number="",
            issued_on="2999-01-01",
            identity__stated="",
            impurity__method="Supplier GC-02",
            salmonella__stated="Negative",
            tamc__value="1.5",
        ),
    )
    form = response.context["form"]
    assert response.status_code == 422
    assert form.errors["number"] == ["This field is required."]
    assert form.errors["identity__stated"] == [
        "Enter the wording of the result on the certificate."
    ]
    incomplete = "Enter the result, or clear this test if the certificate does not state it."
    assert form.errors["impurity__value"] == [incomplete]
    assert form.errors["salmonella__outcome"] == [incomplete]
    assert form.errors["tamc__value"] == ["A count must be a whole number of zero or more."]
    assert form["assay__value"].value() == "99.60"
    assert not SupplierCertificate.objects.exists()
    # The date passes the form and is refused by the service, beside its field.
    response = client.post(url("certificate_new", lot), posted(lot, issued_on="2999-01-01"))
    assert response.status_code == 422
    assert response.context["form"].errors["issued_on"] == [
        "The date of the certificate cannot be in the future."
    ]
    assert not SupplierCertificate.objects.exists() and not AuditEvent.objects.filter(
        action__startswith="supplier_certificate."
    )


def test_a_form_submitted_twice_records_one_certificate(client, world):
    lot = world["lot"]
    sign_in(client, world)
    data = posted(lot)
    assert client.post(url("certificate_new", lot), data).status_code == 302
    # The first record advanced nothing the form depends on: the same page is still current.
    response = client.post(url("certificate_new", lot), data)
    assert response.status_code == 422
    assert response.context["form"].errors["number"] == [certificates.DUPLICATE]
    assert SupplierCertificate.objects.count() == 1


@pytest.mark.parametrize(
    "typed", ["1e2", "1E+2", "+99.6", "100.", ".5", "099.60", "1_0_0", "１００", "99,6", "-0"]
)
def test_a_number_is_entered_as_printed_or_refused(client, world, typed):
    """Nothing is reformatted: the text kept is the text entered, so other notations are
    refused instead of becoming a different text."""
    lot = world["lot"]
    sign_in(client, world)
    response = client.post(url("certificate_new", lot), posted(lot, assay__value=typed))
    assert response.status_code == 422
    assert response.context["form"].errors["assay__value"] == [certificates.NOT_PLAIN]
    assert not SupplierCertificate.objects.exists()


@pytest.mark.parametrize("typed", ["99.60", "100", "0.5", "-1.50", "0", " 99.6 "])
def test_a_printed_number_is_kept_as_entered(client, world, typed):
    lot = world["lot"]
    sign_in(client, world)
    response = client.post(url("certificate_new", lot), posted(lot, assay__value=typed))
    assert response.status_code == 302
    line = SupplierCertificate.objects.get().results.get(test_code="assay")
    assert line.value_text == typed.strip()


def test_a_wording_that_is_too_long_has_one_error(client, world):
    lot = world["lot"]
    sign_in(client, world)
    response = client.post(url("certificate_new", lot), posted(lot, identity__stated="w" * 201))
    assert response.status_code == 422
    assert response.context["form"].errors["identity__stated"] == [
        "Ensure this value has at most 200 characters (it has 201)."
    ]


def test_a_certificate_needs_a_result(client, world):
    lot = world["lot"]
    sign_in(client, world)
    blank = {
        "assay__value": "",
        "assay__method": "",
        "assay__limits": "",
        "identity__outcome": "",
        "identity__stated": "",
        "tamc__value": "",
        "tamc__less_than": "",
    }
    response = client.post(url("certificate_new", lot), posted(lot) | blank)
    assert response.status_code == 422
    assert response.context["form"].non_field_errors() == [certificates.NO_RESULTS]
    assert not SupplierCertificate.objects.exists()


def test_requirements_changed_after_the_page_opened_are_refused(client, world):
    lot = world["lot"]
    sign_in(client, world)
    data = posted(lot)
    assign(world)
    # The refusal is reported at once, beside any field error, with the entries kept.
    response = client.post(url("certificate_new", lot), data | {"number": ""})
    form = response.context["form"]
    assert response.status_code == 422
    assert form.non_field_errors() == [certificates.REQUIREMENTS_STALE]
    assert form.errors["number"] == ["This field is required."]
    assert form["assay__value"].value() == "99.60"
    assert not SupplierCertificate.objects.exists()
    # The form shown again shows the current requirements and carries their token, so after
    # the review it is submitted again without retyping.
    assert form["basis"].value() == basis(lot) != data["basis"]
    response = client.post(url("certificate_new", lot), data | {"basis": form["basis"].value()})
    assert response.status_code == 302 and SupplierCertificate.objects.count() == 1


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_other_roles_read_and_cannot_change(client, world, role):
    lot = world["lot"]
    certificate = certify(world)
    sign_in(client, world, role)
    for name, record in [
        ("certificate_new", lot),
        ("certificate_correct", certificate),
        ("certificate_withdraw", certificate),
    ]:
        assert client.get(url(name, record)).status_code == 403
        assert client.post(url(name, record), posted(lot)).status_code == 403
    response = client.get(url("certificate_detail", certificate))
    body = response.content.decode()
    assert response.status_code == 200 and "Results stated by the supplier" in body
    assert "Correct supplier certificate" not in body
    assert "Withdraw supplier certificate" not in body
    record = client.get(url("lot_detail", lot)).content.decode()
    assert "COA-SYN-0001" in record and "Record supplier certificate" not in record
    assert SupplierCertificate.objects.count() == 1
    assert not SupplierCertificateWithdrawal.objects.exists()


def test_pages_need_a_signed_in_user_and_an_existing_record(client, world):
    certificate = certify(world)
    for name, record in [("certificate_new", world["lot"]), ("certificate_detail", certificate)]:
        response = client.get(url(name, record))
        assert response.status_code == 302 and response.url.startswith(reverse("login"))
    sign_in(client, world)
    for name in ("certificate_new", "certificate_detail", "certificate_correct"):
        assert client.get(reverse(f"quality:{name}", args=[999999])).status_code == 404


def test_a_lot_that_cannot_hold_a_certificate_explains_why(client, world):
    people = world["people"]
    on_site = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-SC-ONSITE",
        material=world["material"].name,
        rules=world["rules"],
        reason="Synthetic receipt",
        receipt=on_site_receipt(),
    )
    assign(world, on_site)
    unassigned = quality.receive_lot(
        actor=people["analyst"],
        number="SYN-SC-UNASSIGNED",
        material=world["material"].name,
        rules=world["rules"],
        reason="Synthetic receipt",
        receipt=supplier_receipt(world["supplier"]),
    )
    sign_in(client, world)
    for lot, message, shown in [
        (on_site, certificates.NOT_SUPPLIED, "This lot was made on site"),
        (unassigned, certificates.NO_REQUIREMENTS, certificates.NO_REQUIREMENTS),
    ]:
        for method in (client.get, client.post):
            response = method(url("certificate_new", lot), follow=True)
            assert response.redirect_chain == [(url("lot_detail", lot), 302)]
            assert message in [str(m) for m in response.context["messages"]][0]
        record = client.get(url("lot_detail", lot)).content.decode()
        assert shown.replace("'", "&#x27;") in record
        assert "Record supplier certificate" not in record
    ready = client.get(url("lot_detail", world["lot"])).content.decode()
    assert f'href="{url("certificate_new", world["lot"])}"' in ready
    assert "No supplier certificate is recorded." in ready
    assert not SupplierCertificate.objects.exists()


def test_correction_opens_with_the_record_and_keeps_the_original(client, world):
    lot = world["lot"]
    original = certify(
        world,
        [
            stated("assay", "99.60", method="Supplier HPLC-07"),
            stated("identity", outcome="conforms", wording="Complies"),
            stated("tamc", "10", less=True),
        ],
    )
    sign_in(client, world)
    response = client.get(url("certificate_correct", original))
    form = response.context["form"]
    assert response.status_code == 200
    assert (form["number"].value(), form["assay__value"].value()) == ("COA-SYN-0001", "99.60")
    assert (form["tamc__value"].value(), form["tamc__less_than"].value()) == ("10", True)
    assert form["identity__outcome"].value() == "conforms"
    assert form["identity__stated"].value() == "Complies"
    assert form["impurity__value"].value() is None and form["reason"].value() is None
    assert "Reason for correction" in response.content.decode()
    data = posted(lot, assay__value="97.90", reason="Assay misread from the second page")
    response = client.post(url("certificate_correct", original), data)
    corrected = SupplierCertificate.objects.get(corrects=original)
    assert response.status_code == 302 and response.url == url("certificate_detail", corrected)
    # The replaced record leads to the current one.
    old = client.get(url("certificate_detail", original))
    assert old.status_code == 302 and old.url == url("certificate_detail", corrected)
    body = client.get(response.url).content.decode()
    assert "Supplier certificate corrected; the original is kept." in body
    assert body.count('class="vr-history-item"') == 2
    assert '<del class="vr-prior">99.60 %</del>' in body and "97.90 %" in body
    assert f'<del class="vr-prior">{MEETS}</del>' in body
    assert "Assay misread from the second page" in body
    assert "Supplier HPLC-07" in body  # A detail that did not change is still shown.
    assert original.results.get(test_code="assay").value_text == "99.60"
    record = client.get(url("lot_detail", lot)).content.decode()
    assert f'href="{url("certificate_detail", corrected)}"' in record
    assert f'href="{url("certificate_detail", original)}"' not in record
    assert FAILS in record and "Assay" in record


def test_a_record_replaced_after_the_page_opened_is_refused(client, world):
    lot = world["lot"]
    original = certify(world)
    sign_in(client, world)
    data = posted(lot, assay__value="97.90", reason="Assay misread")
    correct(world, original, [stated("assay", "98.5")], actor="analyst")
    response = client.post(url("certificate_correct", original), data)
    assert response.status_code == 422
    assert response.context["form"].non_field_errors() == [certificates.CERTIFICATE_STALE]
    assert response.context["form"]["assay__value"].value() == "97.90"
    assert SupplierCertificate.objects.count() == 2
    # A correction prepared before the requirements changed is refused with the entries kept.
    current = SupplierCertificate.objects.get(corrects=original)
    stale = posted(lot, assay__value="97.90", reason="Assay misread")
    assign(world)
    response = client.post(url("certificate_correct", current), stale)
    assert response.status_code == 422
    assert response.context["form"].non_field_errors() == [certificates.REQUIREMENTS_STALE]
    assert response.context["form"]["basis"].value() == basis(lot)
    assert SupplierCertificate.objects.count() == 2
    # Opening the page for the replaced record leads to the current one with the reason.
    response = client.get(url("certificate_correct", original), follow=True)
    current = SupplierCertificate.objects.get(corrects=original)
    assert response.redirect_chain[-1] == (url("certificate_detail", current), 302)
    assert certificates.CERTIFICATE_STALE in [str(m) for m in response.context["messages"]]


def test_withdrawal_marks_the_record_and_ends_its_actions(client, world):
    lot = world["lot"]
    certificate = certify(world, [stated("assay", "97.5")])
    sign_in(client, world)
    page = client.get(url("certificate_withdraw", certificate))
    body = page.content.decode()
    assert page.status_code == 200
    for shown in ("Withdraw supplier certificate", "btn btn-danger", "COA-SYN-0001", "wrong lot"):
        assert shown in body
    response = client.post(url("certificate_withdraw", certificate), {"reason": ""})
    assert response.status_code == 422 and not SupplierCertificateWithdrawal.objects.exists()
    response = client.post(
        url("certificate_withdraw", certificate), {"reason": "Belongs to lot SYN-SC-002"}
    )
    assert response.status_code == 302 and response.url == url("certificate_detail", certificate)
    body = client.get(response.url).content.decode()
    for shown in (
        "Supplier certificate withdrawn; the record is kept.",
        "This certificate record was withdrawn and no longer stands.",
        "Belongs to lot SYN-SC-002",
        "Supplier certificate withdrawn",
        "97.5",
        FAILS,
    ):
        assert shown in body, shown
    assert "Correct supplier certificate" not in body
    assert "does not hold the lot by itself" not in body  # Nothing to act on once withdrawn.
    for name in ("certificate_correct", "certificate_withdraw"):
        response = client.get(url(name, certificate), follow=True)
        assert response.redirect_chain == [(url("certificate_detail", certificate), 302)]
        assert [str(m) for m in response.context["messages"]] == [certificates.WITHDRAWN]
    response = client.post(url("certificate_withdraw", certificate), {"reason": "Again"})
    assert response.status_code == 422
    assert response.context["form"].non_field_errors() == [certificates.WITHDRAWN]
    record = client.get(url("lot_detail", lot)).content.decode()
    assert "Withdrawn" in record and "Record supplier certificate" in record
    assert FAILS not in record and "1 stated" in record  # A withdrawn record raises nothing.
    assert SupplierCertificateWithdrawal.objects.count() == 1


def test_a_result_outside_the_specification_is_shown_and_does_not_hold_the_lot(client, world):
    lot = world["lot"]
    certificate = certify(world, [stated("assay", "97.5"), stated("tamc", "20")])
    sign_in(client, world, "auditor")
    body = client.get(url("certificate_detail", certificate)).content.decode()
    assert body.count(FAILS) == 1 and body.count(MEETS) == 1
    assert "does not hold the lot by itself" in body
    assert f'href="{reverse("stability:hold_list")}"' in body
    record = client.get(url("lot_detail", lot)).content.decode()
    assert FAILS in record and "All meet the specification" not in record
    # The quality user sees it where the disposition is signed; it is not a refusal.
    sign_in(client, world, "approver")
    page = client.get(url("disposition", lot))
    body = page.content.decode()
    assert page.status_code == 200 and 'name="pin"' in body
    assert "Supplier certificate COA-SYN-0001 states a result that does not meet" in body
    assert "do not block this disposition" in body
    withdraw(world, certificate)
    assert (
        "Supplier certificate COA-SYN-0001"
        not in client.get(url("disposition", lot)).content.decode()
    )


def test_lot_number_and_replaced_requirements_are_flagged(client, world):
    lot = world["lot"]
    certificate = certify(world, [stated("assay", "99.6")], stated_lot="SUP-LOT-SYN-777")
    sign_in(client, world)
    body = client.get(url("certificate_detail", certificate)).content.decode()
    assert "Differs from the receipt" in body and "As on the receipt" not in body
    assert "Requirement no longer current" not in body
    assert "Differs from the receipt" in client.get(url("lot_detail", lot)).content.decode()
    assign(world)
    body = client.get(url("certificate_detail", certificate)).content.decode()
    assert "Requirement no longer current" in body
    assert "correct the certificate record to compare it with the current requirements" in body
    assert MEETS in body  # The comparison stands as recorded.
    assert "Requirement no longer current" in client.get(url("lot_detail", lot)).content.decode()
    sign_in(client, world, "auditor")
    body = client.get(url("certificate_detail", certificate)).content.decode()
    assert "Its comparison stands as recorded." in body and "correct the certificate" not in body


def test_a_lot_corrected_to_made_on_site_keeps_and_explains_its_certificates(client, world):
    lot = world["lot"]
    certificate = certify(world)
    quality.correct_receipt(
        actor=world["people"]["analyst"],
        receipt=quality.current_receipt(lot),
        reason="Synthetic correction: the lot was made on site",
        **on_site_receipt(),
    )
    sign_in(client, world)
    record = client.get(url("lot_detail", lot)).content.decode()
    assert "COA-SYN-0001" in record and "Record supplier certificate" not in record
    assert "The receipt details now state that this lot was made on site." in record
    body = client.get(url("certificate_detail", certificate)).content.decode()
    assert "Correct supplier certificate" not in body  # It would be refused.
    assert "Withdraw supplier certificate" in body
    response = client.get(url("certificate_correct", certificate), follow=True)
    assert [str(m) for m in response.context["messages"]] == [certificates.NOT_SUPPLIED]
    response = client.post(url("certificate_withdraw", certificate), {"reason": "Made on site"})
    assert response.status_code == 302 and certificates.is_withdrawn(certificate)


def test_a_released_lot_shows_its_certificates_without_actions(client, world):
    certificate = certify(world)
    sample_and_test(world)
    lot = dispose(world, world["people"]["approver"])
    sign_in(client, world)
    body = client.get(url("certificate_detail", certificate)).content.decode()
    assert "COA-SYN-0001" in body and "Correct supplier certificate" not in body
    for name, record in [
        ("certificate_new", lot),
        ("certificate_correct", certificate),
        ("certificate_withdraw", certificate),
    ]:
        target = lot if name == "certificate_new" else certificate
        back = url("lot_detail" if name == "certificate_new" else "certificate_detail", target)
        for method in (client.get, client.post):
            response = method(url(name, record), follow=True)
            assert response.redirect_chain == [(back, 302)]
            assert [str(m) for m in response.context["messages"]] == [certificates.QUARANTINE_ONLY]
    record = client.get(url("lot_detail", lot)).content.decode()
    assert "COA-SYN-0001" in record and "Record supplier certificate" not in record
    assert SupplierCertificate.objects.count() == 1
