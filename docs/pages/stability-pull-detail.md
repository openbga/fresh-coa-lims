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

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.
- **Testing evidence** (pulled pulls with a linked sample): whether required tests are reviewed and conforming.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record pull** | Scheduled, study active | Analyst | Opens the form |
| **Mark missed** | Scheduled and window closed | Analyst, Quality | Opens the reason form |
| **Link evidence** | Pulled | Analyst | Opens the evidence form |
| **Accept pull** | Pulled; you did not pull or document it | Reviewer | Opens the signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Due / Window / Required tests | `Pull.due_date`, `ProtocolTimepoint.*` | Dates, codes | — | Schedule |
| Pulled on / by, Quantity, Held at, Chamber | `Pull.*` | Date, user, decimal with unit | — | Collection |
| Sample / External sample / External evidence | `Pull.sample`, `.external_sample_ref`, `.evidence_ref` | Text, link | — | Link to the testing spine or an external stability system |
| Deviation / Missed reason / Accepted | `Pull.deviation_reason`, `.missed_reason`, `.accepted_at` | Text, time | — | Exceptions and acceptance |

## Rules and hidden logic

- Results stay in the testing spine; this page only reports whether acceptance would be blocked.

## Related pages

- Study record
- [Stability pulls](/stability/pulls/)
