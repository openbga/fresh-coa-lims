---
title: Sign lot disposition
urls: quality:disposition
views: quality.views.sign
templates: signatures/sign.html, signatures/dialog.html
models: laboratory.ContractApproval, quality.Lot, quality.LotReceipt, quality.SupplierCertificate, quality.SupplierCertificateResult, quality.SupplierCertificateWithdrawal, quality.SupplierResultAcceptance, suppliers.SupplierQualification, quality.Sample, quality.Result, sampling.LotAssignment, sampling.SamplingRecord, analytical.AnalyticalTest, analytical.Observation, analytical.Investigation, stability.Hold, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-15
---

## Purpose

Record the signed QC disposition of a quarantined lot with meaning **approved**, which releases it. This is a QC disposition, not manufacturer release.

## Who can use it

- Sign-in required. **Quality** role only; others receive 403.
- Never a user who authored any of the lot's receipt, supplier certificate, sampling or test data, or who proposed a supplier result in place of a test, even with the quality role (see Independence). Such a user sees the reason, a **Return to the lot** link and no signing form (status 403); no PIN is requested.
- Requires an enrolled signature PIN.

## Layout

- A signing dialog (a plain card without JavaScript): meaning, lot number, the lot record revision shown, the signer, the resulting revision the signature binds (shown + 1), a PIN enrolment link, the form, **Sign approved** and **Cancel**.
- **Supplier certificate notice**: above the form, one warning for each supplier certificate of the lot that is not withdrawn and states a result which does not meet the specification (see Rules). It is information only.
- **Supplier result notice**: above the form, one warning for each supplier result that was accepted in place of a laboratory test and still stands (see Rules). It is information only.
- **Contract laboratory notice**: above the form, one warning for each test of the lot whose result was reported by a contract laboratory under an approval that has been revoked since (see Rules). It is information only.
- For a data author, the same card shows the refusal in place of the form, without the dialog behaviour and without these notices.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign approved** | You are not an author of the lot's receipt, supplier certificate, sampling or test data | Quality, independent of the lot's data | Lot becomes Released; "Lot released."; returns to the lot record |
| **Cancel** / Escape | Always | Any | Returns to the lot record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Disposition rationale |
| Signing username | — | Text | Yes | Must equal your own username; re-entered for every signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; cleared after errors |
| Expected revision (hidden) | `Lot.revision` | Integer | Yes | Lot revision shown when the page opened |
| Supplier certificate notice | `SupplierCertificate.number`, `SupplierCertificateResult.conforms` | Text | — | Certificate number and the names of the tests whose stated result does not meet the specification |
| Supplier result notice | `SupplierResultAcceptance.evidence`, `SupplierQualification.state`, `.revoked_at` | Text | — | The test, the supplier's stated result, the certificate number, the acceptance (SRA-n) and the qualification relied on (SQ-n); when that qualification was revoked since, also when |
| Contract laboratory notice | `Observation.eligibility` (contract), `ContractApproval.state`, `.revoked_at` | Text | — | The test (T-n and its code), the approval relied on (CLA-n) and when it was revoked |
| Frozen evidence (not shown) | `Lot.disposition_evidence` | JSON | — | Native path: assignment ID and hash plus the analytical evidence snapshot, which lists the supplier results accepted in place of tests apart from the laboratory's results |

## Rules and hidden logic

- **Always checked first**: the lot is still Quarantine ("This lot has already been dispositioned."), has no active hold ("<hold> (<kind> hold) is active: <reason>"), and its rule set is still approved and effective ("An approved, effective rule revision is required."). These apply to both paths below.
- **Opening vs. signing**: the page opens for any quality user whatever the lot's state; the state, hold and evidence checks run only when you sign. The authorship check runs on opening too, so an author is told before entering a PIN.
- **Native path** (the lot has a requirement assignment or native tests; always outside DEBUG). Each failing condition is listed as its own message:
- *Native, requirements*: a current assignment with status Requirements assigned; none assigned or an applicability hold blocks.
- *Native, samples*: at least one ("The lot requires a sampled and tested record.").
- *Native, sampling provenance*: every sample has a current sampling record under the assigned plan revision; any sampling deviation needs an accepted independent assessment (pending or rejected blocks).
- *Native, analytical evidence*: no open test, none awaiting review, no nonconforming result (unless an investigation invalidated it) and no result against a superseded requirement, no open or confirmed investigation, and a reviewed conforming result for every required test on every sample. A requirement answered by an accepted supplier result is the exception: it needs no test on any sample, and an Open test of it that holds no observation and is in no QC batch does not block.
- *Native, supplier results in place of tests*: a proposal awaiting acceptance blocks ("SRA-1: the supplier's result for assay awaits acceptance by a reviewer."). An acceptance that no longer stands blocks ("SRA-1: the accepted supplier result for assay no longer stands: REASONS. Withdraw it, then propose the supplier's result again or test the requirement in the laboratory."), and its requirement is then unanswered (for example "Sample S-TEST-001 has no assay test assigned."). Also "SRA-1: the accepted supplier result for assay does not match the lot's current requirement or is not signed." and "assay has both a laboratory result and an accepted supplier result (SRA-1); withdraw the acceptance."
- *Native, sampling still required*: accepted supplier results do not replace the sample and its sampling record. A lot whose requirements are all answered by supplier results still needs both. This is a design default of this product.
- *Native, no mixed evidence*: foundation manual results on the lot block ("Mixed foundation and native evidence requires reconciliation.").
- *Native, frozen evidence*: on release the assignment ID and hash and the analytical evidence snapshot are stored on the lot. Each accepted supplier result is frozen in it with what it relied on and its acceptance signature.
- **Manual foundation path** (development only: DEBUG and neither assignment nor native tests): at least one sample ("The lot requires a sample and reviewed results."); all required rule-set tests per sample ("Required tests are missing."); every result Reviewed and conforming ("All results must conform and have independent review.").
- **Independence**: "You cannot disposition a lot containing your own receipt, supplier certificate, sampling or test data." Authors are users who recorded or corrected the lot's receipt details, including the recorder of a record that a correction later replaced; recorded, corrected or withdrew a supplier certificate of the lot, including the recorder of a record that was later corrected or withdrawn; proposed a supplier result in place of a test, also when the proposal was withdrawn since; sampled or recorded any sampling record of the lot, including corrected originals and intermediate corrections; recorded observations (including corrected originals), submitted tests, recorded batch QC, opened an investigation, or wrote investigative entries; and, on the manual path, the analysts of the results. Holding several roles never waives this. Writing rules or specifications, assigning requirements or tests, recording or signing a supplier qualification, or signing reviews, supplier result acceptances, assessments and conclusions is not authorship. The check is shown when the page opens and repeated under the lot lock when signing.
- **Contract laboratory notice**: for each test of the lot that is not invalidated, whose current result was reported by a contract laboratory and whose approval has been revoked since, the page shows "T-12 assay was reported by a contract laboratory. The approval this result relied on (CLA-3) was revoked on 2026-11-14 10:30 UTC. The result stands as recorded. The approval's record lists every result that relied on it, for quality to assess under the laboratory's procedure. This does not block the disposition." The result still counts as the test's reviewed result. Place a hold from Holds if the lot must wait for the assessment. Not enforced by this page: the software records no assessment of such a result.
- **Reported results and independence**: whoever recorded or corrected a contract laboratory's report on one of the lot's tests recorded its observations and is an author of the lot's test data. Recording or signing the laboratory's approval is not authorship.
- **Receipt authors**: the receipt check applies on both the native and the manual path. The analyst who received the lot through New material lot recorded its receipt details and so cannot sign its disposition. The check reads the receipt records only: a lot received before receipt details were kept has no receipt author until an analyst records them.
- **Supplier certificate authors**: the check applies on both the native and the manual path. It reads every supplier certificate record of the lot and every withdrawal, so a user stays an author after their record was corrected or withdrawn by someone else. A lot without supplier certificates has no such author. Proposers of supplier results are refused with the same message, on both paths.
- **Supplier certificate notice**: for each supplier certificate whose current record is not withdrawn and states a result that does not meet the specification, the page shows "Supplier certificate COA-TEST-001 states a result that does not meet the specification: Assay. Supplier results are not laboratory tests and do not block this disposition." with that certificate's number and the names of those tests. The notice never blocks signing and needs no acknowledgement. A withdrawn certificate raises no notice. The notice uses the comparison stored when the result was recorded.
- **Supplier result notice**: for each supplier result accepted in place of a test that still stands, the page shows "Assay: the supplier's stated result 99.60 % on certificate COA-TEST-001 was accepted in place of a laboratory test (SRA-1, SQ-1)." When the qualification relied on was revoked after the acceptance, the notice continues "The supplier qualification this acceptance relied on (SQ-1) was revoked on 2026-11-14 10:30 UTC. The acceptance stands as signed. The qualification's record lists every result accepted under it, for quality to assess under the laboratory's procedure. This does not block the disposition." The notice never blocks signing and needs no acknowledgement. Place a hold from Holds, or withdraw the acceptance, if the lot must wait. Not enforced by this page: the software records no assessment of such an acceptance.
- **Supplier results and release**: signing does not require a supplier certificate. A stated result that was not accepted in place of a test is not read by the release checks and answers no requirement. A result that does not meet the specification blocks nothing by itself; only an active hold does. An accepted result answers its requirement and is part of the evidence frozen on release. Not enforced by this page: the supplier's qualification is not checked again when you sign. It was checked when the result was proposed and when it was accepted; a revocation since is shown in the notice and does not block.
- **Receipt details are not a release condition**: signing does not require receipt details to exist and does not read the examination on receipt. A recorded discrepancy blocks nothing by itself; only an active hold does. Not enforced by this page: whether the supplier named on the receipt is qualified.
- **Stale page**: any new sample, test change or hold since opening, receipt details recorded later or corrected, a supplier certificate recorded, corrected or withdrawn, and a supplier result proposed, accepted or withdrawn in place of a test, change the lot revision: "Record changed. Reload and review before signing."
- **Identity and PIN**: "Enter your own signing username and PIN." on a mismatch (audited as `signature.identity_denied`); "Enroll a signature PIN first."; "Signature PIN was not accepted."; 5 consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are recorded (`signature.denied`) even though the disposition is refused.
- **Session**: defaults are a 15-minute idle and 8-hour absolute limit; sessions without recorded login times count as expired. On expiry the next request signs you out with "Your session expired. Sign in again to continue." The inline "Session expired. Sign in again before signing." is an extra safeguard at the moment of signing.
- **Effect**: one transaction sets Released, raises the lot revision by 1, writes `signed.approved` and stores an immutable signature (signer, meaning, server time, bound revision, content hash). There is no reject or reversal path in this version.

## Related pages

- Lot record.
- Lot requirements and sampling; Assess sampling deviation; Lot testing; Holds.
- Record receipt details; Correct receipt details.
- Supplier certificate record; Record supplier certificate.
- Supplier result acceptance record; Supplier qualification record (after a revocation).
- Test record; Contract laboratory approval record (after a revocation).
- [Signature PIN](/signature-pin/)
