---
title: Study record
urls: stability:study_detail
views: stability.views.study_detail
templates: ops/record.html
models: stability.Study, stability.Pull, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

A study's lot, protocol and every scheduled pull with its timing status; where a study is closed.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs (Studies, this study), title (protocol product and lot number), identifier, state label (Active, Completed, Terminated) and action buttons.
- **Details**: the facts below.
- **Pulls**: timepoint (links to the pull), due date, window, status (Upcoming, Due, Overdue, Pulled, Accepted, Missed), tests, pulled by and a next-step link (**Record pull** or **Mark missed**).
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Close study** | Study Active, you are Quality, and you did not start the study | Quality | Opens the signing page |
| **Record pull** (Next column) | Pull Scheduled and you are an Analyst | Analyst | Opens the form |
| **Mark missed** (Next column) | Pull Scheduled, today is after its window, and you are Analyst or Quality | Analyst, Quality | Opens the reason form |

Only one link shows in a pull row: Record pull takes precedence for Analysts. The server checks study and pull state and roles again.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Protocol | `Study.lot`, `Study.protocol` | Links | — | What is under study (lot number, protocol identifier) |
| Container and closure, Time zero | `Study.*` | Text, date | — | Study design |
| Lot rule basis at start | `Study.rule_basis` | Text | — | Rule set code, version and revision at the start |
| Started by | `Study.created_by` | User | — | Cannot close the study |
| Closed | `Study.closed_at` | Time | — | Time of closure; blank while Active |
| Revision | `Study.revision` | Integer | — | Raised by each change |
| Pulls table | `Pull.*`, `ProtocolTimepoint.*` | Rows | — | Timepoint (condition and label, links to the pull), Due, Window (from to to), Status, Tests (codes), Pulled by, Next. Empty: "No pulls scheduled." |

## Rules and hidden logic

- Windows are the due date plus or minus the timepoint's window days. Status is Upcoming, Due or Overdue while Scheduled (by today's local date), then Pulled, Accepted or Missed.
- Pulls are listed by due date, then identifier.
- A closed study and its pulls are immutable.

## Related pages

- [Stability studies](/stability/studies/)
- Protocol record, Lot record (from the links)
- Close study (signing page)
- [Stability pulls](/stability/pulls/)
