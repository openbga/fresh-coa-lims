---
title: Equipment record
urls: laboratory:equipment_detail
views: laboratory.views.equipment_detail
templates: ops/record.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.Qualification, laboratory.ResourceUse, core.ElectronicSignature
reviewed: 2026-11-10
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
- **Uses to assess after failure** (only while out of service): up to 50 uses, oldest first, with the Work label (sample reference for sample work; the raw context as recorded otherwise), test and user; empty: "No recorded uses since the last accepted passing calibration."
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
| Uses: Work | `ResourceUse.context_type`, `.context_id` | Text or link | — | Work the resource was used for: the sample reference for sample work, otherwise the raw context type and ID as recorded |
| Revision | `Equipment.revision` | Integer | — | Rises on every state change |

## Rules and hidden logic

- **Uses to assess**: uses of this equipment from the start of the last independently accepted passing calibration that precedes the earliest failure not yet covered by a signed return to service (all uses if there is none). A later passing calibration does not shrink the list; only the signed return does.
- **Buttons**: Record calibration (Analyst, Quality) and Record qualification (Analyst, Reviewer, Quality) always show for those roles; Take out of service only while in service; Return to service only while out of service. The server re-checks role, independence and state when you open or save.
- Expired qualifications still read "Approved" in the qualification table; check the validity dates.
- Signatures and history include those of the equipment's calibrations and qualifications. An unknown ID returns 404.

## Related pages

- Calibration, out-of-service, return-to-service and qualification forms (use the action buttons)
- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Qualifications](/laboratory/qualifications/)
