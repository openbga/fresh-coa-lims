---
title: Equipment record
urls: laboratory:equipment_detail
views: laboratory.views.equipment_detail
templates: ops/record.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.Qualification, laboratory.ResourceUse, core.ElectronicSignature
reviewed: 2026-11-17
summary: One instrument's fitness for use: its calibrations, qualification evidence, service state and recorded uses, with the actions that keep it fit or take it out of service.
---

## Common tasks
### Record a calibration
1. Select [[Record calibration]]. It shows for the analyst and quality roles.
2. Fill in the form on that page. A failed calibration takes the equipment out of service at once.
### Accept a calibration
1. In [[Calibrations]], select [[Accept]] in the row. It shows only to a reviewer, on a calibration awaiting acceptance that someone else recorded.
2. Sign with your PIN on that page.
### Take the equipment out of service or return it
1. Select [[Take out of service]] and give the reason on that page. It shows while the equipment is in service.
2. To return it, a quality user selects [[Return to service]] and signs an impact assessment of [[Uses to assess after failure]].
### Assess what a failure affected

1. Select [[More]] then [[Assess impact]]. Quality users only.
2. Set the period of concern on the form that opens and select [[Start assessment]].

### Record qualification evidence
1. Select [[Record qualification]] and fill in the form on that page.
2. A quality user who did not record it approves it on the qualification record.
## Good to know
- A passing calibration counts only once a different reviewer accepts it. A failed one counts the moment it is recorded.
- Whoever took the equipment out of service, including by recording a failed calibration, cannot return it to service.
- Uses to assess after failure start at the last accepted passing calibration before the failure. A later pass does not shorten the list; only the signed return to service does.
- The lot, test state and result shown for each use are read now, not as they were when the equipment was used.
- Calibrations and qualifications are never edited. A correction is a new record, and the history keeps every change.

## Purpose

One instrument's fitness evidence: calibrations, qualification, service state and recorded uses.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title (the description), asset ID and fitness label, action buttons. While out of service, a red notice: "This equipment cannot be used. Returning it requires an independently accepted passing calibration and a signed impact assessment."
- **Details**: the facts below, starting with **Calibration due**.
- **Calibrations**: every calibration, newest first: performed, due (inclusive), outcome, state, standard, certificate (a link when a URL was given), recorded by, and **Accept** where you may accept. Empty: "No calibration recorded. Equipment is not fit for use until a passing calibration is independently accepted."
- **Qualification evidence**: stage or use (links to the qualification), state (Awaiting approval, Approved, "Approved, starts <date>" before its valid-from date, Expiring soon (amber, effective and its last valid day within 30 days), Expired or Revoked), valid from, valid until, evidence reference. Empty: "No qualification evidence recorded." or, when not required, "Qualification is not required for this equipment."
- **Uses to assess after failure** (only while out of service): up to 50 uses, oldest first. Columns: used, work, lot, test, state, reportable result, tests in batch, by. For a result of an analytical test the work links to the test and the row shows its lot number (for a stability test, the study's lot), test code, current state and reportable result (blank until one is reported). For a QC batch the work links to the batch and the row shows how many tests are in it. Any other context shows only its raw label and the test code as recorded. Empty: "No recorded uses since the last accepted passing calibration."
- **Recent uses**: the latest 25, newest first (used, work, activity, test, by). Empty: "No use recorded."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record calibration** | Recorder role | Analyst, Quality | Opens the calibration form |
| **Record qualification** | Scientific role | Analyst, Reviewer, Quality | Opens the equipment qualification form |
| **Assess impact** (under **More**) | Quality role | Quality | Opens New impact assessment with this equipment chosen, to assess the tests, lots, studies and certificates it may have affected. Changes nothing on this record |
| **Take out of service** (under **More**) | In service | Analyst, Reviewer, Quality | Opens the reason form |
| **Return to service** | Out of service, and you did not take it out of service (otherwise the header shows "The person who removed equipment from service cannot return it.") | Quality | Opens the signed return-to-service page |
| **Accept** (in the table) | Calibration awaiting acceptance, not recorded by you | Reviewer | Opens the acceptance signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Fitness label | — | Label | — | As on the list (Out of service, Not calibrated, Calibration failed, Calibration overdue, Not qualified, Due soon, Ready) |
| Calibration due | Due date of the latest counted calibration | Date; when overdue or due soon, the fitness label in its tone (Calibration overdue red, Due soon amber) with the date under it | — | First fact in Details; blank when the equipment has never been calibrated |
| Category, Location | `Equipment.category`, `.location` | Text | — | Identity |
| Qualification required | `Equipment.requires_qualification` | Yes/No | — | Whether qualification evidence is part of fitness |
| Service state / Last status change / Changed by | `Equipment.state`, `.status_changed_at`, `.status_changed_by` | In service or Out of service; time with zone; user | — | Who last put it out of or into service; blank for equipment never changed |
| Uses: Work | `ResourceUse.context_type`, `.context_id` | Text or link | — | Work the resource was used for: the sample reference for sample work; for a native analytical test its label, lot number and sample reference (for a test of a stability pull "stability pull <pull>" in place of the sample), linking to the test; for a QC batch "QC batch <number>", linking to the batch; the raw context as recorded otherwise |
| Revision | `Equipment.revision` | Integer | — | Rises on every state change |

## Rules and hidden logic

- **Uses to assess**: uses of this equipment from the start of the last independently accepted passing calibration that precedes the earliest failure not yet covered by a signed return to service (all uses if there is none). A later passing calibration does not shrink the list; only the signed return does.
- **Results named**: the lot, state, result and batch size are read when the page opens, so they show the current state of the test, not its state at the time of use. A test or batch that can no longer be found keeps its raw label.
- **Buttons**: Record calibration (Analyst, Quality) and Record qualification (Analyst, Reviewer, Quality) always show for those roles; Take out of service only while in service; Return to service only while out of service. The server re-checks role, independence and state when you open or save.
- Signatures and history include those of the equipment's calibrations and qualifications. An unknown ID returns 404.

## Related pages

- Calibration, out-of-service, return-to-service and qualification forms (use the action buttons)
- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Qualifications](/laboratory/qualifications/)
