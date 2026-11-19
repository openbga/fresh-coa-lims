---
title: Reassessment record
urls: quality:reassessment_detail
views: quality.reassessment_views.reassessment_detail
templates: ops/record.html
models: quality.Reassessment, quality.Lot, analytical.AnalyticalTest, analytical.Investigation, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One reassessment of a released lot: the sample, its tests and results, and the quality conclusion that gives the lot a later retest date or ends its use. Analysts assign tests; quality concludes or withdraws.
---

## Common tasks

### Test the reassessment's sample

1. Select [[Assign tests]]. It shows to analysts while the reassessment is open and tests are missing.
2. Open each test from the [[Tests]] section to record, review and sign it on its own page.

### Conclude the reassessment

1. Select [[Conclude]] once every test is reviewed and conforms. It shows to quality while the reassessment is open.
2. Choose the outcome and sign with your PIN on that page.

### Withdraw a reassessment started in error

1. Select [[Withdraw]] under More. It shows to quality while the reassessment is open and nothing stops it.
2. Give the reason and sign with your PIN on that page.

## Good to know

- The tests belong to the reassessment. The lot's record, its dates as frozen at release and its disposition do not change.
- You cannot conclude a reassessment you started, produced test data for or investigated, even with the quality role.
- A failing result is never withdrawn. Once its investigation is concluded, quality concludes that the material is not suitable, which ends the lot's use.
- A suitable conclusion gives the lot a new retest date in force; the date frozen at release stays. Under a reserved release, [[Concluded under]] names the qualification relied on.
- Concluded and Withdrawn are final. A new reassessment can start only after one that did not end the lot's use.

## Purpose

The record of one reassessment of a released lot: the sample taken for it, its own tests and their results, the investigations of those results and the conclusion by quality. It is where analysts reach the tests and where quality concludes or withdraws.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; others receive 403.
- **Assign tests**: analyst. **Conclude** and **Withdraw**: quality. Buttons show only to those roles and only while the reassessment is Open; the server checks again on the action pages.
- A quality user who started the reassessment, recorded or submitted data for one of its tests or investigated one of its results sees, in place of **Conclude**, the note "You started, tested or investigated it: another quality person concludes it." The conclusion page refuses them too.
- Admin is read-only here: an account holding only Admin sees no action buttons. Admin plus a role keeps that role's actions; independence rules apply to everyone.

## Layout

- **Header**: breadcrumbs (Material lots, the lot number, the reassessment), the title "Reassessment of <lot number>", the identifier (RA-n) and the status label, then the action buttons. Status: **Open**; **Suitable** or **Use ended** once concluded; **Withdrawn**.
- **Details**: Lot (a link, with its material), Retest date when started, Expiry date ("None" when not stated), Sample, Date sampled, Quantity taken, Containers sampled, Reason, Started by, Started, New retest date, Concluded under (a Suitable conclusion signed under a reservation), Decided, Reason for the decision, Revision.
- **Notice** (when one applies): "Suitable" with "The lot's retest date in force is <date>, set by this reassessment."; "Use ended" with the statement that the lot keeps its released disposition as signed, takes no certificate and is not reassessed again; "Withdrawn" with the reason; or, while open, "Out of specification" when a result does not meet its acceptance criterion or an investigation confirmed a failure.
- **Tests**: one row for each test, reruns and retests included. Columns Test (label, name and code, a link), Result and status, Acceptance criterion (the one frozen when assigned) and Kind. Result and status reads Open; Awaiting review; "Conforms · reviewed"; "Out of specification · awaiting review" or "· reviewed"; Invalidated; or Not completed. A note above says what comes next: "No test is assigned yet.", the reason the material cannot be found suitable, "Every test has a reviewed result that conforms. A quality person concludes it.", "Concluded: <outcome>." or "Withdrawn; its tests take no more work."
- **Signatures** and **History**: the conclusion or withdrawal signature, and the audit events of the reassessment with their reasons and actors.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign tests** | Open, tests still to assign and they can be stated; primary while there are no tests | Analyst | Opens Assign reassessment tests |
| (reason shown instead) | Open and the specifications cannot state the tests | Analyst | Shows "Tests cannot be assigned: …" in place of the button |
| **Conclude** | Open, and you did not start, test or investigate it | Quality | Opens Conclude reassessment; primary once there are tests and the material can be found suitable |
| **Withdraw** (under More, red) | Open and not in progress and no result failed | Quality | Opens Withdraw reassessment |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `Reassessment.lot` | Link | — | The released lot and its material |
| Retest date when started, Expiry date | `Reassessment.dates_basis` | Date | — | The lot's dates in force when the reassessment started |
| Sample, Date sampled, Quantity taken, Containers sampled | `sample_reference`, `sampled_on`, `quantity`, `quantity_unit`, `containers` | Text, date, decimal with unit | — | What was sampled for the reassessment |
| Reason | `Reassessment.reason` | Text | — | Why the material is examined again |
| Concluded under | `Reassessment.result_evidence` (`authorization`) | Link and text | — | The qualification the signer relied on for each activity a rule set reserved, as a link to QUAL-n and "For release decisions in “REL-TEST” (Rule set RS-TEST v2)" under it. Frozen at signing |
| Started by, Started | `started_by`, `started_at` | User, date and time | — | Who started it, and when |
| New retest date | `Reassessment.retest_on` | Date | — | Set only by a suitable conclusion |
| Decided, Reason for the decision | `decided_at`, `decision_reason` | Date and time, text | — | When and why it was concluded or withdrawn |
| Revision | `Reassessment.revision` | Integer | — | Raised by each test assigned or changed, and by the conclusion or withdrawal; signing pages bind to it |

## Rules and hidden logic

- **States**: Open, then Concluded (outcome Suitable or Use ended) or Withdrawn. One reassessment of a lot is open at a time. A concluded or withdrawn reassessment takes no more testing.
- **The lot is not changed**: the tests name no lot, so nothing that reads the lot's tests counts them. The lot's record, revision, dates as frozen at release and disposition stay as signed.
- **Concluded under**: shown only when the conclusion was signed under a reservation. It is the evidence frozen with the signature and also appears on the qualification record under Decisions relying on it.
- **What a suitable conclusion does**: the new retest date becomes the lot's retest date in force, shown on the lot record and in the lot list, printed on the next certificate with a "Reassessed" line. What a use-ended conclusion does: the lot shows "Use ended", takes no certificate and no further reassessment.
- **Conclude shows** as the primary button only when there are tests and the material can be found suitable; a quality user may still open it to conclude that the material is not suitable.
- **Withdraw is hidden** while testing is in progress (a test awaiting review, an open test holding results or raw data that were not submitted, or an open investigation), and the header says "Withdrawal waits until no testing is in progress." in its place; it is also hidden when a result failed, which the Out of specification notice explains.
- **Tests and investigations**: each test is recorded, reviewed, investigated and retested like any test, with a retest on the same sample and no resample. An open investigation of a reassessment test holds the reassessment: it cannot be concluded as suitable until quality concludes the investigation. A failing result confirmed by its investigation is concluded as the end of the lot's use.
- **Signatures and audit events**: `lot.reassessment_started`, `test.assigned` for each test, `signed.reassessed` or `signed.withdrawn`. Signatures show the signer, meaning, server time and bound revision.
- **Rejecting a QC batch**: a test of a concluded or withdrawn reassessment is left as it is when its QC batch is rejected.

## Related pages

- Lot record (the Reassessments card lists this record)
- Assign reassessment tests; Conclude reassessment; Withdraw reassessment
- Test record (each test); Investigation record
- Lot export record (lists the reassessment and its tests)
