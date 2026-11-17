---
title: Record that a test cannot be completed
urls: analytical:test_not_completed
views: analytical.views.test_not_completed
templates: analytical/sign.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.Investigation, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: Quality signs that an open test cannot be completed and why. The test and its data are kept; the test is repeated, or an investigation decides what follows.
---

## Common tasks
### Record that a test cannot be completed
1. On the test record, select [[Record not completed]].
2. Read [[What follows]] in the summary: a repeat, a new investigation, or the test's own investigation.
3. Choose the [[Cause]], where the test is repeated when asked, and give the reason.
4. Enter your signing username and PIN and select [[Sign: not completed]].
### Repeat the test on a replacement sample
1. First record the replacement sample on the lot record.
2. Then record the test as not completed and choose [[On another sample of the lot]] and that sample.
## Good to know
- Only a quality person who recorded none of the test's data can sign this; holding other roles never waives it.
- Readings outside the limits are never discarded: they open an investigation instead of a repeat.
- The test and everything recorded on it stay as they were; it no longer counts toward the lot or the pull.
- A retest that held no reading or file does not use up the specification's retest allowance.

## Purpose

A quality person signs that an open test cannot be completed (the sample was lost, a handling error, an equipment failure or another cause). The test and everything recorded on it are kept. What follows depends on the test: it is repeated, or an investigation decides.

## Who can use it

- Sign-in required. **Quality** only; others receive 403. Requires an enrolled signature PIN.
- Never a user who authored the test's data: recorded or corrected an observation (including superseded ones), attached a raw-data file, recorded QC of its batch, or submitted the test. For a test of an investigation also never the data authors of the result the investigation is about or of any other test of the investigation, nor the investigation's own authors (its opener and the authors of assessment, hypothesis, evidence or impact entries). Holding other roles never waives this.
- **Admin** alone, or a superuser without the quality role, receives 403: admin is not a scientific role.
- The test record shows **Record not completed** to every quality user while the test can take work. The server refuses the signer who authored its data when the page opens and again when signing.

## Layout

- Breadcrumbs (Testing, the lot or stability pull, the test, "Not completed").
- Card "Record that T-n cannot be completed": "Your signature records not completed for T-n at record revision N", then a summary, the signer, a link "Enroll or change your signature PIN", the form, **Cancel** and **Sign: not completed**.
- **Summary rows**, top to bottom:
  - **Test**: the test number, its name and the test code.
  - **Lot and sample** (or **Lot and stability pull**): the lot number, with the sample (or stability pull) under it.
  - **Specification**: the specification code and version (the full requirement source as its tooltip), with the start of the requirement's hash under it.
  - **Acceptance**: the frozen acceptance criterion.
  - **Kind**: the test's kind (Original, Retest, Resample, Rerun after QC failure, Repeat under replaced requirements, Repeat of a test not completed).
  - **Recorded**: the current readings as recorded, joined with ", ", or "No result recorded".
  - **Outside the limits**: only when readings are judged outside the limits (see Rules); those readings.
  - **Corrected readings**: only when a reading was corrected: for each, "replicate N: X corrected to Y (reason)", followed by " · the replaced reading was outside the limits" when it was. A test that is not submitted is reviewed by nobody, so the signer sees every correction here.
  - **Raw-data files**: only when there are some: "N kept with the test".
  - **QC batch**: only when the test is in one; its number.
  - **Retest allowance**: only for a test of an investigation. "It holds readings or files, so it still counts toward the specification's retests." or "It holds no reading or file, so it will not count toward the specification's retests."
  - **What follows**: one of the three cases below, across the full width (as is **Retest allowance**).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign: not completed** | The page opens | Quality | Records the test as not completed; "T-n recorded as not completed."; returns to the test |
| **Cancel** | Always | Quality | Nothing signed; returns to the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Cause | `AnalyticalTest.not_completed_record` | Choice, initial "Choose the cause" | Yes | "The sample was lost, damaged or used up"; "An error in preparing or running the test"; "Equipment, reagent or standard failure"; "Another cause, stated in the reason" |
| Repeat the test | `AnalyticalTest.not_completed_record` | Radio | Yes, when shown | Shown only when the test is repeated. "On the same sample" or "On another sample of the lot". For a stability pull's test the only choice is "On the material that was pulled". When the lot has no sample that qualifies the only choice is "On the same sample", with the help "To repeat it on another sample, record a new sample of the lot first." |
| Sample for the repeat | `AnalyticalTest.sample` | Choice | Only for another sample | Shown when the lot has a qualifying sample and the test is not a stability pull's. Help: "Only for a repeat on another sample: a sample of this lot recorded after this test was assigned, holding no tests of its own and standing in for no other sample. It then stands in for this test's sample, and the lot no longer requires tests of its own on it: choose the replacement sample, not another routine one." |
| Why the test cannot be completed | `AuditEvent.reason` | Text, max 2000 | Yes | Help: "What happened and where it is recorded, for example a deviation number." |
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **What follows** is decided by the test, not by the signer:
  1. **The test belongs to an investigation** (an authorized retest or resample, or a rerun of one). Nothing is repeated and the form has no repeat fields. The summary reads: "The test belongs to INV-n, which decides what follows: its conclusion, or another authorized retest within the specification's limit." The investigation must be open ("This test's investigation is closed."); its revision advances, so a conclusion page opened before is stale.
  2. **Current readings are outside the limits.** No repeat. An investigation is opened on this test and you are its opener; it holds the lot (or the stability pull) until quality concludes it. The summary reads: "The readings outside the limits open an investigation on this test. It holds the lot until quality concludes it; no repeat is assigned." (for a stability test "pull"). The investigation trigger reads "Out-of-limit CODE values X in a test that could not be completed", shortened to 200 characters with "…". It can be concluded although its original test was never reviewed.
  3. **Otherwise the test is repeated.** A linked test of the kind "Repeat of a test not completed" is created, open, under the same frozen requirement, on the same sample (the pulled material for a stability pull) or on another sample of the lot. Summary: "The test is repeated by a linked test of the kind "repeat" under the same frozen requirement."
- **Samples offered for a repeat**: other samples of the lot recorded in the system after this test was assigned (by the server time the sample was recorded, not the sampling time entered on it), that hold no original test and none of whose tests answer for a different sample. A new sample stands in for exactly one sample, and a routine sample recorded before the test is never offered. The chosen sample then takes no tests of its own, so choose the replacement sample, not another routine one.
- **Readings outside the limits**: a current reading counts when it fails the frozen requirement as recorded or once rounded half-up to the reporting precision. When every replicate is recorded and the result submission would calculate fails, all readings count as outside.
- **Refused** (opening redirects to the test with the warning; signing refuses the same under lock):
  - "Lot LOT-TEST-001 is no longer in quarantine." or, for a stability test, the pull's reason (not pulled, accepted, study closed).
  - "This test awaits review: its result is reviewed or, when it conforms, returned for correction. Only an open test is recorded as not completed."
  - "Only an open test is recorded as not completed."
  - "A supplier's result is proposed or accepted in place of this test (SRA-n). Withdraw it on the lot record before testing the requirement in the laboratory."
  - "You recorded or submitted data on this test, recorded QC of its batch or attached its raw data, or you produced the result its investigation is about or investigated it. Another quality person must record that it cannot be completed."
- **Refused on signing**: "Record changed. Reload and review before continuing." (stale revision, or the test's investigation changed); "Choose the cause."; "Choose where the test is repeated."; "Choose the sample the test is repeated on."; "Choose a sample of this lot recorded after this test was assigned, that holds no tests of its own and stands in for no other sample."; "A stability pull has no other sample: authorize a retest of the material that was pulled."; "This test is not repeated: the investigation decides what follows." (a repeat posted when none applies).
- **Retest allowance**: a retest or resample recorded as not completed before it held any observation (corrected ones included) or raw-data file does not count toward the specification's retest allowance; one that held any does.
- **Invalidation**: an investigation cannot be concluded as "Original result invalidated" while one of its retests or resamples was recorded as not completed with readings outside the limits.
- **Effect**: the test becomes Not completed. It takes no more work, answers no requirement and never counts toward the disposition of the lot (or the acceptance of the pull). Observations, raw-data files and QC batch membership stay as recorded. The test stays listed in its QC batch; being not completed does not fix the batch's QC.
- **Frozen with the signature**: cause, the readings as recorded, the readings outside the limits, every corrected reading with what replaced it, the reason and whether it was outside the limits, number of raw-data files, batch, whether the test held any work, what follows, the repeat (test and sample) and the investigation (id and label). The lot's certificate evidence lists the test as excluded with its cause, readings, readings outside the limits, corrections, what follows and its signature.
- **Signature and audit**: meaning `not_completed` (shown as "not completed"), signed by you at the resulting revision N + 1. Audit `signed.not_completed` with your reason; `test.assigned` for a repeat (reason "Repeat of T-n, which could not be completed"); `investigation.opened` when one is opened. State, record, signature and audit commit together. Test revision and the revision of the lot (or pull) rise by 1. Failed credential attempts are recorded even when the signing is refused; five failures lock the PIN for 15 minutes.
- **Stale page, identity, session and PIN** messages as for other signings: "Enter your own signing username and PIN."; "Session expired. Sign in again before signing."; "Signature PIN was not accepted."

## Related pages

- Test record (return target; shows the "Not completed" notice afterwards).
- Investigation record (opened or advanced by this record), Authorize retest, Conclude.
- Lot testing page, Reject lot (an unsubmitted out-of-limit reading is resolved here).
- [Signature PIN](/signature-pin/)
