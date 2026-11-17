---
title: Investigation record
urls: analytical:investigation_detail
views: analytical.views.investigation_detail
templates: analytical/investigation_detail.html, includes/signature_list.html, includes/history_panel.html, analytical/_investigation_status.html, analytical/_test_status.html
models: analytical.Investigation, analytical.InvestigationEntry, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One out-of-specification investigation: the original result and any retests, the written record, and quality's signed conclusion. Its lot or pull stays held while it is open.
---

## Common tasks
### Record the laboratory assessment
1. Select [[Record entry]] and choose the entry type on that page. Analysts, reviewers and quality can add entries while it is open.
### Escalate to a full investigation
1. As a reviewer or quality, select [[Escalate investigation]]. It shows only in Phase I.
### Authorize a retest or resample
1. As quality, select [[Authorize retest]] and sign with your PIN on that page.
2. The linked test appears under [[Results and lineage]], ready to record.
### Conclude the investigation
1. As quality, select [[Conclude]], choose the outcome and sign with your PIN on that page.
## Good to know
- Retests never replace the original result unless the conclusion documents an assignable cause. Averaging or discarding the original is not supported.
- A laboratory assessment entry is needed before a retest is authorized or a conclusion is signed.
- Quality cannot conclude if they opened it, wrote its entries or generated its test data. Escalation and retest authorizations do not count.
- Retests used counts the linked tests that were not invalidated, against the specification's allowance.
- For a stability test the pull is held, not the lot, and the lot's record is not changed.

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
- **Electronic signatures** (count): one line per signature with signer, meaning, server time, the record revision it binds and the start of the content hash. **History**: the attributed audit events, oldest first.

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
| Status | `Investigation.phase`, `outcome` | Text | — | Phase I open · lot held, Phase II open · lot held ("pull held" instead of "lot held" for a stability test), Closed · OOS confirmed, Closed · original invalidated |
| Trigger | `Investigation.trigger` | Text, max 200 | — | Why it opened, worded for the result type: "Out-of-specification CODE: reportable 0.10 %"; for a less-than result "…: <2000 CFU/g cannot be shown to meet at most 1000 CFU/g"; for a qualitative result "…: observed Present, expected Absent". Longer text is shortened with "…" |
| Replicates | `Observation.value_text`, `observed_text` | Text as recorded, separated by "; ", with unit | — | Current readings of each test; qualitative readings show what was observed in brackets |
| Reportable | `AnalyticalTest.reportable_text` | Text | — | As frozen at submission, e.g. "99.8", "<10" or "Present"; "—" before |
| Outcome | `Investigation.outcome` | Text | — | "Original result invalidated: assignable cause" or "Out-of-specification result confirmed" |
| Assignable cause | `Investigation.assignable_cause` | Text | — | Shown only when recorded |
| Retests used | `AnalyticalTest.investigation` | Count | — | Linked tests not Invalidated, against the specification's retest allowance |
| Entry type | `InvestigationEntry.kind` | Text | — | Laboratory assessment, Hypothesis or test plan, Evidence, Escalation, Authorized retest or resample, Impact on other lots or products |

## Rules and hidden logic

- **Pull hold**: an investigation of a stability test holds the pull (it cannot be accepted) and never the lot; it has no lot. Only a retest of the material that was pulled can be authorized, and once the study is closed its pulls take no more testing, so Authorize retest and Conclude are then refused.
- **Lot hold**: while open, the lot cannot receive an approving QC disposition until quality signs a conclusion. Retests never replace the original result unless the conclusion documents an assignable cause; averaging or discarding the original is not supported.
- **Allowance**: retest or resample limit comes from the frozen specification (0 to 3).
- **Records are append-only**: entries and history cannot be edited. Each change raises the investigation revision.
- Not enforced by this page: any time limit for phases, or Phase II before a retest.

## Related pages

- [Investigations](/testing/investigations/)
- Lot testing page, Test record.
- Record entry, Escalate, Authorize retest, Conclude.
