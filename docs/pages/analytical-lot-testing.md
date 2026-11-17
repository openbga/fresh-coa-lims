---
title: Lot testing
urls: analytical:lot_testing
views: analytical.views.lot_testing
templates: analytical/lot_testing.html, analytical/_test_status.html, analytical/_investigation_status.html
models: quality.Lot, quality.Sample, quality.SupplierResultAcceptance, analytical.AnalyticalTest, analytical.Investigation
reviewed: 2026-11-17
---

## Purpose

Show a lot's analytical evidence by sample, say what still blocks QC disposition, and let analysts assign the lot's required tests to each sample.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Assign required tests**: analysts only, and only while the lot is Quarantine. The button is hidden otherwise; the server also requires the analyst role.
- **Admin** or **auditor** alone see no assign button, and a posted assignment is refused with 403 before the sample or reason is read.

## Layout

- **Header**: "LOT testing", lot status (Quarantine or the lot's state), material, Rule set, Lot revision; **Lot record** button.
- **Analytical evidence for QC disposition**: either **Blocked** with the list "QC disposition cannot be approved until these are resolved:" or **Complete**.
- **Supplier results accepted in place of tests** (only when the lot has a signed acceptance that still stands), with their number: "These requirements are answered for the whole lot by a result stated on the supplier's certificate. They are not tested here; a test assigned for one stays open and takes no result while the acceptance stands.", then a table: Acceptance, Test, Supplier's result, Supplier certificate, Acceptance and specification, Accepted by.
- **One card per sample** (collection order): sample reference, test count, **Assign required tests**, collection time, and a table: Test, Code, Kind, Status, Reportable, Acceptance and specification. Empty: "No tests assigned".
- **No samples**: "No samples recorded" with a **Lot record** link.
- **Investigations**: list with status and trigger, or "No investigations".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign required tests** (per sample) | Lot is Quarantine and user is an analyst | Analyst | Posts to this page; creates the missing original tests for that sample and a linked repeat for each requirement whose tests were all superseded; redirects back here |
| **Lot record** | Always | Any viewer | Opens the quality lot record |
| Test and investigation links | Rows present | Any viewer | Open the test or investigation |
| Acceptance link (SRA-n) | A supplier result is accepted in place of a test | Any viewer | Opens the supplier result acceptance record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Rule set | `Lot.rules` | "code vN" | — | Rule revision of the lot |
| Lot revision | `Lot.revision` | Integer | — | Rises with every evidence change; a disposition opened earlier then becomes stale |
| Status | `AnalyticalTest.state`, `conforms` | Text | — | Open, "Not tested · supplier result" (an Open test whose requirement a supplier result is proposed or accepted for), Awaiting review, Reviewed · conforms, Out of specification (awaiting review or reviewed), Invalidated, "Superseded · requirements replaced", Not completed |
| Reportable | `AnalyticalTest.reportable_text` | Text with unit (no unit for qualitative tests) | — | As frozen at submission, e.g. "99.8", "<10" or "Absent"; "—" until submitted |
| Acceptance and specification | `AnalyticalTest.requirement` | Text | — | Acceptance text (for example "less than 0.10 %" or "Absent in 25 g (expected: Absent)") above the source and revision of the frozen requirement |
| Acceptance / Test / Supplier's result / Supplier certificate / Accepted by | `SupplierResultAcceptance` (SRA-n), `evidence`; acceptance signature | Link and text | — | The acceptance, the test name and code, the stated result with its unit, the supplier certificate number with the supplier's name, and the reviewer who signed the acceptance |
| Acceptance and specification (supplier result) | `SupplierResultAcceptance.evidence` | Text | — | Acceptance text above the source of the requirement the supplier's result was compared with |
| Reason (hidden) | `AuditEvent.reason` | Text | Yes | Fixed text: "Assign required tests from the lot's approved requirements" |
| Sample (hidden) | `AnalyticalTest.sample` | Sample of this lot | Yes | The card's sample; a sample of another lot, or a value that is not a whole-number ID of at most 19 digits, returns 404 |

## Rules and hidden logic

- **Requirements come from a configured provider** of approved specifications; tests freeze the requirement and its hash at assignment, so later revisions do not change them. Not enforced by this page: which specifications are approved, or that the provider's data is correct. With no provider every requirement is held.
- **Assign**: needs an approved, effective rule set ("An approved, effective rule revision is required."; this also shows once the lot's rule set version was retired by a later approval, until the lot's requirements are assigned again, when it has no test yet, or replaced by quality, once it has); every additional rule set version frozen with the lot's requirements must be in force too, else nothing is assigned and the page shows, for each one, "Rule set RS-EU v1, which applies to this lot in addition to its own, is no longer in force. Assign the lot's requirements again, or have quality replace them once testing has started."; lot must be in quarantine ("Lot ... is no longer in quarantine."). Only supported requirements become tests; the others are listed as warnings "Held: ..." and appear as blockers. Existing tests are not duplicated: a requirement whose tests for this sample (the original and every linked rerun, retest, resample or repeat) include one Open, Awaiting review or Reviewed, or were closed by an investigation or a rejected batch, gets nothing. A requirement whose tests were all superseded when the lot's requirements were replaced gets a linked repeat (kind "Repeat under replaced requirements") of the last superseded test, on the sample that test was made on, under the current requirement. A requirement that a supplier result is proposed or accepted for gets no test; after that record is withdrawn, assign again to create the test. Messages: "Assigned N test(s) to REF."; when nothing was created and nothing is held, "Every required test is already assigned to this sample.". While a supplier result is proposed or accepted for a requirement of the lot: with tests created, also "No test was assigned for assay: a supplier's result is proposed or accepted in place of it." (the codes of such requirements that have no test for this sample); with nothing created and nothing held, "No test to assign: every requirement of this sample has a test or a supplier's result that stands for it." instead. A failed reason shows "Enter a reason to assign tests.".
- **Rule sets the lot is under**: the header shows the lot's own rule set only. Additional rule sets (policy with `applies_to`) apply through the lot's requirements and are listed on Lot requirements and sampling and on the lot record. A lot on an applicability hold, also one waiting for quality to decide requirements the specifications state differently, gets no tests; the hold reasons are listed as "Held: ...".
- **Lot's own tests only**: the page, its blockers and the lot revision count only tests assigned to the lot's samples. Tests of a stability pull of this lot's study name no lot, are not listed here, never block or change the lot, and are reached from the pull record.
- **Revision**: creating at least one test raises the lot revision by 1 and writes a `test.assigned` audit event per test (a repeat also records the test it repeats).
- **Blockers** include open or confirmed investigations, tests that are incomplete, awaiting review or non-conforming, held requirements, and samples missing a required test or a reviewed conforming result. A result tested under a requirement whose content differs from the lot's current approved requirement never counts ("... was tested against a superseded requirement; ..."); a test whose requirement content is the same counts, also after the lot's requirements were replaced. A Superseded test blocks nothing and answers nothing; while its sample has no test under the current requirement the blocker reads "Sample REF has no CODE test under the lot's current requirements: the earlier test was superseded when they were replaced. Assign the required tests."
- **Supplier results in place of tests**: a signed acceptance that still stands answers its requirement for the whole lot. No sample then needs a test of it, and an Open test of it that holds no observation and no raw-data file and is in no QC batch is not counted as incomplete. Such a test shows "Not tested · supplier result", also after the lot is released, and takes no observation, contract laboratory result, raw-data file or QC batch. The same status shows while a proposal awaits acceptance, but then the test still counts as incomplete.
- **Supplier result blockers**: "SRA-1: the supplier's result for assay awaits acceptance by a reviewer."; "SRA-1: the accepted supplier result for assay no longer stands: REASONS. Withdraw it, then propose the supplier's result again or test the requirement in the laboratory."; the same for a proposal that no longer stands, for example after its qualification was revoked ("SRA-1: the proposal for assay no longer stands: REASONS. Withdraw it, …"); "SRA-1: the accepted supplier result for assay does not match the lot's current requirement or is not signed."; "assay has both a laboratory result and an accepted supplier result (SRA-1); withdraw the acceptance." A proposal, and an acceptance that no longer stands, are not listed in the card of accepted results.
- **Samples are still needed**: accepted supplier results answer requirements, not sampling. The lot's QC disposition still needs a sample with its sampling record. This is a design default of this product.
- **Complete** means every required test has a reviewed, conforming result and no investigation is open; with accepted supplier results the page says "Every requirement has a reviewed, conforming result or an accepted supplier result, and no investigation is open." This is laboratory evidence only; QC disposition is a separate signed decision and does not mean manufacturer release.
- Resample or rerun-only samples answer for the sample they replace.

## Related pages

- [Testing: tests](/testing/)
- [Material lots](/)
- Lot record, Test record, Investigation record.
- Lot requirements and sampling; Decide conflicting requirements and Replace lot requirements (quality).
- Supplier result acceptance record.
