---
title: Equipment record
urls: laboratory:equipment_detail
views: laboratory.views.equipment_detail
templates: ops/record.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.Qualification, laboratory.ResourceUse, core.ElectronicSignature
reviewed: 2026-11-12
---

## Purpose

One instrument's fitness evidence: calibrations, qualification, service state and recorded uses.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title (the description), asset ID and fitness label, action buttons. While out of service, a red notice: "This equipment cannot be used. Returning it requires an independently accepted passing calibration and a signed impact assessment."
- **Details**: the facts below.
- **Calibrations**: every calibration, newest first: performed, due (inclusive), outcome, state, standard, certificate (a link when a URL was given), recorded by, and **Accept** where you may accept. Empty: "No calibration recorded. Equipment is not fit for use until a passing calibration is independently accepted."
- **Qualification evidence**: stage or use (links to the qualification), state (Awaiting approval, Approved, "Approved, starts <date>" before its valid-from date, Expired or Revoked), valid from, valid until, evidence reference. Empty: "No qualification evidence recorded." or, when not required, "Qualification is not required for this equipment."
- **Uses to assess after failure** (only while out of service): up to 50 uses, oldest first. Columns: used, work, lot, test, state, reportable result, tests in batch, by. For a result of an analytical test the work links to the test and the row shows its lot number, test code, current state and reportable result (blank until one is reported). For a QC batch the work links to the batch and the row shows how many tests are in it. Any other context shows only its raw label and the test code as recorded. Empty: "No recorded uses since the last accepted passing calibration."
- **Recent uses**: the latest 25, newest first (used, work, activity, test, by). Empty: "No use recorded."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record calibration** | Recorder role | Analyst, Quality | Opens the calibration form |
| **Record qualification** | Scientific role | Analyst, Reviewer, Quality | Opens the equipment qualification form |
| **Take out of service** | In service | Analyst, Reviewer, Quality | Opens the reason form |
| **Return to service** | Out of service | Quality | Opens the signed return-to-service page |
| **Accept** (in the table) | Calibration awaiting acceptance, not recorded by you | Reviewer | Opens the acceptance signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Fitness label | — | Label | — | As on the list (Out of service, Not calibrated, Calibration failed, Calibration overdue, Not qualified, Due soon, Ready) |
| Category, Location | `Equipment.category`, `.location` | Text | — | Identity |
| Qualification required | `Equipment.requires_qualification` | Yes/No | — | Whether qualification evidence is part of fitness |
| Service state / Last status change / Changed by | `Equipment.state`, `.status_changed_at`, `.status_changed_by` | In service or Out of service; time with zone; user | — | Who last put it out of or into service; blank for equipment never changed |
| Uses: Work | `ResourceUse.context_type`, `.context_id` | Text or link | — | Work the resource was used for: the sample reference for sample work; for a native analytical test its label, lot number and sample reference, linking to the test; for a QC batch "QC batch <number>", linking to the batch; the raw context as recorded otherwise |
| Revision | `Equipment.revision` | Integer | — | Rises on every state change |

## Rules and hidden logic

- **Uses to assess**: uses of this equipment from the start of the last independently accepted passing calibration that precedes the earliest failure not yet covered by a signed return to service (all uses if there is none). A later passing calibration does not shrink the list; only the signed return does.
- **Results named**: the lot, state, result and batch size are read when the page opens, so they show the current state of the test, not its state at the time of use. A test or batch that can no longer be found keeps its raw label.
- **Buttons**: Record calibration (Analyst, Quality) and Record qualification (Analyst, Reviewer, Quality) always show for those roles; Take out of service only while in service; Return to service only while out of service. The server re-checks role, independence and state when you open or save.
- Expired qualifications still read "Approved" in the qualification table; check the validity dates.
- Signatures and history include those of the equipment's calibrations and qualifications. An unknown ID returns 404.

## Related pages

- Calibration, out-of-service, return-to-service and qualification forms (use the action buttons)
- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Qualifications](/laboratory/qualifications/)
