---
title: Record contract laboratory result
urls: analytical:contract_result
views: analytical.views.contract_result
templates: analytical/form.html, analytical/_summary.html
models: analytical.AnalyticalTest, analytical.Observation, quality.Lot, quality.Sample, laboratory.ContractLaboratory, laboratory.ContractApproval, laboratory.ContractUse
reviewed: 2026-11-14
---

## Purpose

Records what an outside contract laboratory's report states for a test, as the test's own result, every replicate at once. When the test already holds a contract laboratory result, the same page corrects that result as a whole.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403. The test record shows **Record contract laboratory result** or **Correct contract laboratory result** only to analysts.
- You need no qualification for the method. The page checks the laboratory's approval, not you, and no equipment or lots are selected.
- A test that cannot take a report redirects you to the test record with a warning (see Rules).
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Record contract laboratory result · T-n" ("Correct contract laboratory result · T-n" for a correction) and breadcrumbs.
- Summary card: Test, Lot and sample, Specification, Record revision, Method, Replicates and **What is checked**. A correction adds Result being corrected, Reported by and Report kept at, and one more sentence under What is checked.
- Note: "Fields marked * are required. The server records the time and your identity."
- Form: **Contract laboratory**, **Report number**, **Date of the report**, **Where the report is kept**, then the result fields of every replicate. A correction ends with **Reason for correction**.
- Result fields, numeric and count tests: **Reported value (unit)** and **Reported as less than this value**. Qualitative tests: **Reported result** (radio pair) and **Wording on the report**. With more than one replicate each label starts with the replicate, for example "Replicate 2 reported value (%)".
- **Cancel**, **Record contract laboratory result** (or **Correct contract laboratory result**).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record contract laboratory result** | The test holds no result | Analyst | Adds one observation per replicate; "Contract laboratory result recorded."; returns to the test |
| **Correct contract laboratory result** | The test holds a contract laboratory result | Analyst | Adds a linked correction of every replicate; "Contract laboratory result corrected; the result recorded before is kept."; returns to the test |
| **Cancel** | Always | Analyst | Returns to the test without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Contract laboratory | `Observation.eligibility` (contract: laboratory and approval), `ContractUse.approval` | Menu, starts at "Select the laboratory" | Yes | "Laboratories with a signed approval for this method. The approval must cover the date of the report." Each choice reads "code · name · approved from to until", with every signed period, also one that has run out. In a correction the laboratory already recorded stays in the menu when it holds no signed, unrevoked approval any more, as "code · name · as recorded" |
| Report number | `Observation.eligibility` (contract: report), `ContractUse.report_number` | Text, max 120 | Yes | "As printed on the laboratory's report or certificate of analysis." |
| Date of the report | `Observation.eligibility` (contract: report), `ContractUse.report_date` | Date | Yes | "As printed. It cannot be in the future." The approval must cover this date |
| Where the report is kept | `Observation.raw_reference` | Text, max 200 | Yes | "Document number or location in your controlled records." Shown as Original record on the test |
| Reported value (unit) | `Observation.value`, `qualifier`, `value_text` | Decimal, 20 digits, 8 decimals; unit from the specification | Yes (numeric and count tests) | "As the report states it; at most 8 decimal places." (count: "Whole number of zero or more, as the report states it.") followed by "Do not convert a result stated in another unit, and never enter a nondetect as zero." |
| Reported as less than this value | `Observation.qualifier` ("<") | Checkbox | No (numeric and count tests) | "For a result printed as <10. It is kept as reported and never becomes zero or the number." |
| Reported result | `Observation.outcome`, `value_text` | Radio: Conforms / Does not conform, or Absent / Present (the pair approved for the test) | Yes (qualitative tests) | Help text shows the acceptance, e.g. "Acceptance: Absent in 25 g (expected: Absent)." |
| Wording on the report | `Observation.observed_text` | Text, max 200 | Yes (qualitative tests) | "The result in the report's own words, e.g. Complies." |
| Reason for correction | `Observation.reason` | Text, max 2000 | Yes (correction only) | "The result recorded before stays visible in the record." |
| Expected revision (hidden) | `AnalyticalTest.revision` | Integer | Yes | Test revision when the page opened |
| Test / Lot and sample / Specification / Record revision (summary) | `AnalyticalTest`, `Lot.number`, `Sample.reference` | Text | — | As on Record observation |
| Method (summary) | `AnalyticalTest.requirement` method | Text | — | "code revision N": the method the approval must name |
| Replicates (summary) | `AnalyticalTest.requirement` replicates | Text | — | "N: the report must state each of them" ("it" for one) |
| What is checked (summary) | — | Text | — | "The laboratory needs a signed approval for this method that covers the date of its report. Its batch QC, instruments, reagents and any calculation inputs stay in its own report, which the reviewer checks." A correction adds "A correction that keeps the laboratory and the report keeps the approval already relied on." |
| Result being corrected / Reported by / Report kept at (summary) | `Observation.value_text`, `eligibility`, `raw_reference` | Text | — | Correction only: the current replicates as recorded, "code · name · report number dated date", and where that report is kept. The form starts with these values |

## Rules and hidden logic

- **Wrong state** (opening or submitting): you are redirected to the test record with the first applicable warning: "Lot LOT-TEST-001 is no longer in quarantine."; "This test is not accepting results." (test not Open); "This test is in a QC batch of this laboratory. It is tested here; a contract laboratory's result cannot be recorded on it."; "This test holds observations made in this laboratory. A test is tested here or reported by a contract laboratory, never both."; "No bench check is configured; results are held."; "No contract laboratory is approved for method METHOD. Quality records and signs the approval under Laboratory, Contract laboratories." (first entry only: a correction always offers the laboratory already recorded).
- **Tested here or reported, never both**: a test holding a contract laboratory result takes no observation made here, no correction of a single replicate, and cannot join a QC batch.
- **Approval**: a first entry, and a correction that names another laboratory or report, is accepted only when the laboratory holds an approval for the test's method code (upper and lower case ignored, any version of the method) that is signed, not revoked, and whose dates include the date of the report, both days inclusive. An approval that has since run out still covers a report dated within it. A revoked approval covers nothing. When several cover the date, the one recorded last is relied on.
- **Refusal by the approval** is shown beside Contract laboratory as "Refused: cl-syn-001: reason". Reasons: "The laboratory is not approved for method “METHOD”."; "No approval for method “METHOD” covers a report dated 2026-01-05."; "The approval for method “METHOD” that covers 2026-01-05 is still awaiting its signature."; "The approval for method “METHOD” that covered 2026-01-05 was revoked; a revoked approval is relied on no further."
- **Refused report**: nothing is stored. A refusal by the approval is audited as `contract.report_refused` on your account, with the test, the method, the laboratory, the report number and date and the reasons. Other errors on this page are not audited.
- **Report details**: "The report cannot be dated in the future." (today in the deployment time zone) appears beside the date. The server repeats the required checks: "Enter the number of the laboratory's report.", "The report number has at most 120 characters.", "Record where the laboratory's report is kept.", "Enter the date of the report.", "Replicate 1: Enter the value the report states.", "Replicate 1: Enter the wording of the result on the report."
- **As reported**: each value is stored as entered ("99.80", "<10") or as the outcome label ("Absent"). When the method has a calculation the value is still entered as reported: no inputs are asked for and nothing is calculated here.
- **Specification still applies**: the report must state every replicate the frozen requirement asks for. Its rounding and limits decide the reportable result and conformance at submission, and an out-of-specification result opens an investigation as for any test.
- **Reading validation** (above the form, nothing saved): "Replicate 1: A count must be a whole number of zero or more."; "Replicate 1: A less-than result needs a value greater than zero."
- **Not recorded here**: the contract laboratory's batch QC, instruments, reagent lots, analysts' qualification and calculation inputs. They stay in its report. The test is submitted and reviewed without a QC batch of this laboratory.
- **Stale page**: "Record changed. Reload and review before continuing."
- **Effect**: in one transaction every replicate is stored with you as recorder, together with the evidence relied on: the laboratory (code, name, location), the approval (CLA number, method, dates, evidence reference, scope, signing time) and the report (number, date). One acceptance is added to the lists on the laboratory and approval records. The test and lot revisions rise by 1 and `contract_result.recorded` is audited.
- **Correction**: replaces the whole result. A reason is required. Every replicate gets a new row linked to the one it supersedes, carrying that reason; the originals stay visible, struck through. "The correction changes nothing." when the laboratory, the report, where it is kept and every replicate are the same. `contract_result.corrected` is audited with the result before and after. Only an Open test can be corrected: a reviewer returns a submitted test first.
- **Correction of the same report**: when the laboratory, the report number and the date of the report stay the same, the correction keeps the evidence already frozen on the result. The approval is not checked again and no acceptance is added to the lists on the laboratory and approval records. This also works after the approval was revoked, so a transcription error can still be fixed.
- **Correction naming another laboratory or report**: a change of laboratory, report number or date of the report is a new acceptance. It is checked against an approval exactly as a first entry is, is refused and audited when none covers it, and adds a row to those lists.
- **Independence**: whoever records or corrects the report is an author of the result. They cannot review the test ("You cannot review your own test.") or sign the lot's QC disposition, even with those roles. Recording or signing the laboratory's approval is not authorship: a Quality user who did so and also holds the analyst role may record a report under it.
- **After a revocation**: results already recorded stay and can still be corrected as the same report. The test record and the Sign review page show an "Approval revoked" notice, the lot's QC disposition signing page shows a warning, and the approval record lists the results that relied on it.
- **Certificate of analysis**: under the method the certificate prints "Tested by contract laboratory NAME, LOCATION. Report NUMBER dated DATE."
- **Not enforced by this page**: that the entry matches the report (the reviewer checks it against the report); the Scope text of the approval, for example the materials it covers (it is shown with the result on the test record for a person to check); the unit the report used.
- **Assumption**: relying on a contract laboratory's result under a signed approval for the method, matching that approval to the date of the report, and letting a correction of the same report keep the approval already relied on are design defaults of this product. They are not a statement of what any regulation requires or permits.
- Validation errors show on the form with status 422; your entries are kept and nothing is saved. Unknown test: 404.

## Related pages

- Test record (return target).
- [Contract laboratories](/laboratory/contract-laboratories/) (register and approvals).
- Contract laboratory approval record (lists the results that relied on it).
- [Testing: tests](/testing/)
