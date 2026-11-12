---
title: Investigation record
urls: analytical:investigation_detail
views: analytical.views.investigation_detail
templates: analytical/investigation_detail.html, analytical/_history.html, analytical/_investigation_status.html, analytical/_test_status.html
models: analytical.Investigation, analytical.InvestigationEntry, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-12
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

- **Header**: "INV-n out-of-specification investigation"; status, Lot link, Opened, Revision; action buttons.
- **Open**: alert "Lot held" with the trigger. **Closed**: **Conclusion** card (Outcome, Assignable cause, Conclusion, Closed).
- **Results and lineage** ("N of M retests used"): Test, Kind, Sample, Replicates, Reportable, Status. First row is "Original result".
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
| Retests used | `AnalyticalTest.investigation` | Count | — | Linked tests not Invalidated, against the specification's retest allowance |
| Entry type | `InvestigationEntry.kind` | Text | — | Laboratory assessment, Hypothesis or test plan, Evidence, Escalation, Authorized retest or resample, Impact on other lots or products |

## Rules and hidden logic

- **Lot hold**: while open, the lot cannot receive an approving QC disposition until quality signs a conclusion. Retests never replace the original result unless the conclusion documents an assignable cause; averaging or discarding the original is not supported.
- **Allowance**: retest or resample limit comes from the frozen specification (0 to 3).
- **Records are append-only**: entries and history cannot be edited. Each change raises the investigation revision.
- Not enforced by this page: any time limit for phases, or Phase II before a retest.

## Related pages

- [Investigations](/testing/investigations/)
- Lot testing page, Test record.
- Record entry, Escalate, Authorize retest, Conclude.
