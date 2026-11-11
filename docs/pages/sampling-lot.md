---
title: Lot requirements and sampling
urls: sampling:lot
views: sampling.views.lot_detail
templates: sampling/lot_detail.html
models: quality.Lot, sampling.LotAssignment, sampling.SamplingRecord, sampling.SamplingPlanRevision, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Shows the approved requirements frozen for one lot (specification tests, methods, sampling plan), the sampling that was recorded against them, and the history. It is the starting point for assigning requirements and recording sampling.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **Assign requirements** or **Change requirements**: **analyst** or **quality**, lot in Quarantine, and no analytical test exists yet for the lot.
- **Record sampling**: **analyst** only, shown only when sampling can be recorded: lot in Quarantine, requirements assigned and not on hold, and the assigned plan version still Approved.
- **Assess deviation**: **quality** only, never the person who sampled or recorded the record.
- **Correct**: **analyst** only, lot in Quarantine, on records not yet corrected.
- Buttons follow role and state; the server rechecks on each action.

## Layout

- **Breadcrumbs**: Sampling, lot number. Under the heading: "Lot status" (Quarantine or Released), "record revision N" and a link **Open lot record**.
- **Closed banner** (lot not in Quarantine): "Closed" and "This lot is no longer in quarantine. Its requirements and sampling records are read-only."
- **Sampling readiness for QC disposition** (first panel): "No sampling blockers" with "Every sample has current sampling provenance against the assigned plan. Testing and other gates still apply.", or a "Blocked" alert "QC disposition is blocked by sampling until:" listing the reasons (see Rules).
- **Current requirements**: when testing has started on a quarantined lot, a "Fixed" note reads "Testing has started, so these requirements cannot be reassigned."
  - No assignment: "Applicability hold: no requirements assigned" and "Assign the approved specification and sampling plan for this lot's material and stage before sampling or testing."
  - On hold: "Applicability hold", "This lot cannot be sampled, tested against limits or dispositioned until quality resolves:" and the reasons, plus Requested and Recorded facts.
  - Assigned: Material, Stage and scope, Specification (link to its version), Sampling plan (link, basis, "at least" amount), Rule set (when present), Frozen (who, when, shortened hash); then a table Test (code and name), Acceptance criterion, Method version (with controlled procedure), Suitability evidence, Required ("Required" or "Information only").
- **Sampling records**: table Sample, Sampled, "Containers (sampled / required / total)", Amount, Plan, Deviation, Status ("Current" or "Corrected"), and **Correct** for analysts. A resample shows "Resample of <original sample>" under its reference. A deviation shows its assessment status ("Awaiting quality assessment", "Accepted by quality" or "Rejected by quality"), who decided and when, and an **Assess deviation** button. Empty: "No sampling recorded" ("Record sampling against the assigned plan once requirements are assigned."), with a **Record sampling** button for analysts when requirements are assigned.
- **Earlier requirement assignments**: shown when more than one assignment exists; each marked "Superseded".
- **History**: audit events of all assignments, sampling records and deviation assessments.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign requirements** / **Change requirements** | Viewer is analyst or quality and no assignment blocker applies (lot in Quarantine, no analytical test yet); label is Change when an assignment exists | Analyst, quality | Opens the Assign requirements form |
| **Record sampling** | Viewer is an analyst and no sampling blocker applies (Quarantine, requirements assigned, plan approved) | Analyst | Opens the Record sampling form |
| **Correct** | Lot open, viewer is analyst, record not yet corrected | Analyst | Opens the Correct sampling form |
| **Assess deviation** | Record has a pending deviation assessment, is not corrected, lot in Quarantine, viewer has the quality role and neither sampled nor recorded it | Quality | Opens the Assess sampling deviation page |
| **Open lot record** | Always | Any viewer | Opens the quality lot record |
| Specification / Sampling plan links | Requirements assigned | Any viewer | Open the frozen specification version or the plan |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot status | `Lot.state` | Quarantine, Released | — | Only quarantined lots accept changes here. |
| Record revision | `Lot.revision` | Integer | — | Increases when requirements are assigned, a sample is recorded (once), a record is corrected or a deviation is assessed; signing pages bind to it. |
| Specification, Sampling plan | `LotAssignment.payload` | "code vN" | — | Versions frozen when requirements were assigned. |
| Frozen hash | `LotAssignment.payload_hash` | SHA-256, shortened | — | Hash of the frozen requirement content. |
| Acceptance criterion | payload test line | Decimal limits with unit, or expected text | — | "≥" or ">" lower, "≤" or "<" upper, "(rounded to N)" when rounding applies. |
| Sample | `Sample.reference` | Text | — | Sample identifier; corrections show "Corrects record N". |
| Sampled | `SamplingRecord.sampled_at`, `sampled_by`, `location` | Date and time, user, text | — | When, by whom and where; "Recorded by" appears when another user entered it. |
| Containers | `containers_sampled`, `containers_required`, `containers_total` | Integers | — | Sampled / required by the plan / in the lot, then the container IDs. |
| Amount | `SamplingRecord.quantity`, `quantity_unit` | Decimal with unit | — | Total amount collected. |
| Deviation | `SamplingRecord.deviation` | Text | — | "Deviation" label and text, or "None". |
| Deviation assessment | `DeviationReview.status`, `decided_by`, `decided_at` | Status, user, date and time | — | Quality's signed decision on the deviation; blocks disposition until accepted. |
| Resample of | `SamplingRecord.resample_of` | Sample reference | — | Original sample a resample replaces. |
| Status | derived | Current, Corrected | — | Corrected means a later record supersedes it. |

## Rules and hidden logic

- **Frozen content**: an assignment stores the approved specification, methods and plan as they were; later approvals do not change it until requirements are assigned again.
- **Fixed after testing starts**: once any analytical test exists for the lot, requirements cannot be reassigned (no controlled supersession in this version); the change button is hidden and the server refuses.
- **Append-only**: assigning again adds a new assignment that supersedes the previous one; earlier ones stay listed. Corrections add records; originals are preserved.
- **Readiness blockers** (computed on each view; these exact reasons): "Applicability hold: no specification or sampling requirements are assigned."; "Applicability hold: <hold reason>" for each recorded hold reason; "No sampling has been recorded against the approved sampling plan."; "Sample <ref> has no sampling record against the approved plan."; "Sample <ref> was sampled under <plan vN>; the current requirements use <plan vN>."; "Sampling deviation for sample <ref> awaits quality assessment."; "Sampling deviation for sample <ref> was rejected; correct the record or resample." Only the latest record of each sample counts. Testing and other gates are outside this panel.
- **Hold**: a hold blocks sampling here; its reasons are listed exactly as recorded.
- **Roles**: quality users can assign requirements but cannot record or correct sampling; that is analyst only.
- **Ordering**: sampling records oldest first; assignments newest first, history oldest first.
- Audit actions are shown as stored, for example `lot.requirements_assigned`, `sampling.recorded`, `sampling.corrected`.

## Related pages

- [Lots](/sampling/)
- [Material lots](/)
- Assign requirements, Record sampling, Correct sampling.
