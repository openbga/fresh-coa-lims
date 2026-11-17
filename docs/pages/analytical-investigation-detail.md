---
title: Investigation record
urls: analytical:investigation_detail
views: analytical.views.investigation_detail
templates: analytical/investigation_detail.html, analytical/_history.html, analytical/_investigation_status.html, analytical/_test_status.html
models: analytical.Investigation, analytical.InvestigationEntry, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
---

## Purpose

One out-of-specification investigation: phase, lineage of the original result and any retests, the written record, and quality's signed conclusion.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Record entry**: analyst, reviewer or quality while open.
- **Escalate investigation**: reviewer or quality while in Phase I.
- **Authorize retest**, **Conclude**: quality while open.
- **Admin** alone is a read role: no entry, escalation, authorization or conclusion buttons. Admin together with a lab role gets that role's buttons and its independence rules.

## Layout

- **Header**: "INV-n out-of-specification investigation"; status, Lot link (for a stability test: "Stability pull <pull> · lot <number>", the pull linking to the pull record), Opened, Revision; action buttons.
- **Open**: alert "Lot held" with the trigger. For a stability test the alert is "Pull held": the trigger, "Stability pull <pull> cannot be accepted until quality signs a conclusion.", the retest rule, and that the record of the lot is not changed by the investigation (whether the lot needs a hold or other action is for quality to decide). **Closed**: **Conclusion** card (Outcome, Assignable cause, Conclusion, Closed).
- **Results and lineage** ("N of M retests used"): Test, Kind, Sample (the stability pull for a stability test), Replicates, Reportable, Status. First row is "Original result".
- **Investigation record**: dated entries; empty "No laboratory assessment yet".
- **Electronic signatures** and **History**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record entry** | Investigation open | Analyst, reviewer, quality | Opens the entry form |
| **Escalate investigation** | Phase I open | Reviewer, quality | Opens the escalation form |
| **Authorize retest** | Open | Quality | Opens the signing page |
| **Conclude** | Open | Quality | Opens the signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `Investigation.phase`, `outcome` | Text | — | Phase I open, Phase II open, Closed · OOS confirmed, Closed · original invalidated |
| Trigger | `Investigation.trigger` | Text, max 200 | — | Why it opened, worded for the result type: "Out-of-specification CODE: reportable 0.10 %"; for a less-than result "…: <2000 CFU/g cannot be shown to meet at most 1000 CFU/g"; for a qualitative result "…: observed Present, expected Absent". Longer text is shortened with "…" |
| Replicates | `Observation.value_text`, `observed_text` | Text as recorded, separated by "; ", with unit | — | Current readings of each test; qualitative readings show what was observed in brackets |
| Reportable | `AnalyticalTest.reportable_text` | Text | — | As frozen at submission, e.g. "99.8", "<10" or "Present"; "—" before |
| Outcome | `Investigation.outcome` | Text | — | "Original result invalidated: assignable cause" or "Out-of-specification result confirmed" |
| Assignable cause | `Investigation.assignable_cause` | Text | — | Shown only when recorded |
| Retests used | `AnalyticalTest.investigation` | Count | — | Linked tests not Invalidated, against the specification's retest allowance. A linked test recorded as not completed before it held any observation (corrected ones included) or raw-data file is not counted; one that held any is |
| Entry type | `InvestigationEntry.kind` | Text | — | Laboratory assessment, Hypothesis or test plan, Evidence, Escalation, Authorized retest or resample, Impact on other lots or products |

## Rules and hidden logic

- **Pull hold**: an investigation of a stability test holds the pull (it cannot be accepted) and never the lot; it has no lot. Only a retest of the material that was pulled can be authorized, and once the study is closed its pulls take no more testing, so Authorize retest and Conclude are then refused.
- **Lot hold**: while open, the lot cannot receive an approving QC disposition until quality signs a conclusion. Retests never replace the original result unless the conclusion documents an assignable cause; averaging or discarding the original is not supported.
- **Allowance**: retest or resample limit comes from the frozen specification (0 to 3). Linked tests invalidated by batch rejection, and retests or resamples recorded as not completed without any work held, do not use it.
- **Opened by a test not completed**: when quality records that a test cannot be completed while a reading is outside its limits, this investigation is opened on that test (its trigger reads "Out-of-limit CODE values X in a test that could not be completed"). The original test then shows Not completed and is never reviewed; the investigation can be concluded without that review. A retest or resample of an investigation recorded as not completed leaves the decision to the investigation, which stays open.
- **Records are append-only**: entries and history cannot be edited. Each change raises the investigation revision.
- Not enforced by this page: any time limit for phases, or Phase II before a retest.

## Related pages

- [Investigations](/testing/investigations/)
- Lot testing page, Test record.
- Record entry, Escalate, Authorize retest, Conclude.
