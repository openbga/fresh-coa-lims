---
title: Pull record
urls: stability:pull_detail
views: stability.views.pull_detail
templates: ops/record.html
models: stability.Pull, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

One scheduled pull: timing, collection details, linked testing or external evidence and acceptance.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs (Studies, the study, the pull), title (condition and timepoint label), identifier (study ID and pull number) and status label, action buttons.
- **Details**: the facts below.
- **Testing evidence** (only when the pull is Pulled and has a linked sample): each current blocker, or "Required tests reviewed and conforming", with a note that acceptance needs every required test reviewed, conforming and free of open investigations.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record pull** | Scheduled and study active | Analyst | Opens the form |
| **Mark missed** | Scheduled and today is after the window closes | Analyst, Quality | Opens the reason form |
| **Link evidence** | Pulled | Analyst | Opens the evidence form |
| **Accept pull** | Pulled; you are a Reviewer and are neither the puller nor the user who last linked evidence | Reviewer | Opens the signing page |

The server checks each again (study active, state, role, independence).

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Study | `Pull.study` | Link | — | Parent study |
| Due / Window / Required tests | `Pull.due_date`, `ProtocolTimepoint.window_days`, `.test_codes` | Dates, codes | — | Schedule; window is due date minus/plus window days |
| Pulled on / Pulled by / Quantity / Held at / Chamber | `Pull.pulled_on`, `.pulled_by`, `.quantity` with `.quantity_unit`, `.storage_location`, `.chamber` | Date, user, decimal with unit, text, equipment | — | Collection; blank until recorded |
| Sample | `Pull.sample` | Sample reference | — | Linked testing-spine sample |
| External sample / External evidence | `Pull.external_sample_ref`, `.evidence_ref`, `.evidence_url` | Text, link | — | External stability system; shown as a link when a URL is given |
| Deviation / Missed reason | `Pull.deviation_reason`, `.missed_reason` | Text | — | Exceptions |
| Accepted | `Pull.accepted_at` | Time | — | Signature time of acceptance |
| Revision | `Pull.revision` | Integer | — | Raised by each change |

## Rules and hidden logic

- Results stay in the testing spine; this page only reports whether acceptance would be blocked. Blockers come from the linked sample's analytical tests and investigations.
- **State**: Scheduled (Upcoming, Due or Overdue by window) -> Pulled -> Accepted, or Scheduled -> Missed. Accepted and Missed are final.
- **Independence**: the Reviewer who accepts must not be the user who recorded the pull or the user who last linked evidence.
- **Audit**: events `pull.recorded`, `pull.evidence_linked`, `pull.missed` and the signed acceptance appear in History and Signatures.

## Related pages

- Study record
- Record pull, Link pull evidence, Mark pull missed, Accept pull (from the actions)
- [Stability pulls](/stability/pulls/)
