---
title: Study record
urls: stability:study_detail
views: stability.views.study_detail
templates: ops/record.html
models: stability.Study, stability.Pull, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

A study's lot, protocol and every scheduled pull with its timing status.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.
- **Pulls**: timepoint (links to the pull), due date, window, status (Upcoming, Due, Overdue, Pulled, Accepted, Missed), tests, pulled by and a next-step link (**Record pull** or **Mark missed**).
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Close study** | Active; you did not start it | Quality | Opens the signing page |
| **Record pull** / **Mark missed** (in the table) | Pull scheduled; Mark missed only after its window closes | Analyst / Analyst, Quality | Opens the form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Protocol | `Study.lot`, `Study.protocol` | Links | — | What is under study |
| Container and closure, Time zero | `Study.*` | Text, date | — | Study design |
| Lot rule basis at start | `Study.rule_basis` | Text | — | Rule set code, version and revision at the start |
| Closed | `Study.closed_at` | Time | — | Signature time of closure |

## Rules and hidden logic

- Windows are the due date plus or minus the timepoint's window days.

## Related pages

- [Stability studies](/stability/studies/)
- [Stability pulls](/stability/pulls/)
