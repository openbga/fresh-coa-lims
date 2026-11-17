---
title: Intended use record
urls: validation:use_detail
views: validation.views.use_detail
templates: ops/record.html
models: validation.UseAcceptance, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One record of the laboratory's intended use: its content, the supported assays, the configuration its acceptance froze and, once accepted, what changed since.
---

## Common tasks
### Accept the intended use
1. Select [[Accept]]. It shows to the quality role while the record awaits acceptance, unless you recorded it.
2. Review the facts and sign with your PIN on that page using [[Sign and accept]].
### See what changed since acceptance
1. Read the notice at the top. [[Changed since acceptance]] means approved versions or the release differ from those frozen.
2. Check [[Changes since acceptance]]: each row is a code whose approved version in force is not the one frozen.
### Check the supported assays
1. In [[Supported assays]], compare the version accepted with the one in force now. [[None in force]] marks a method with no approved version now.
### Withdraw a record that will not be accepted
1. Select [[Withdraw]]. It shows to the quality role while the record awaits acceptance.
2. Give a reason on that page, then record a new intended use to correct it.
## Good to know
- Accept does not show once the process owner or system owner is no longer an active account with a working role. Withdraw the record and record it again.
- The record holds no work. Changes are shown for the laboratory to assess under its own change control.
- A superseded record is kept as accepted, with a link to the record that replaced it.
- An accepted record cannot be withdrawn. Only accepting a newer record supersedes it.
- While the record awaits acceptance, Approved configuration in force now shows what the signature would freeze; afterwards the frozen copy is shown.

## Purpose

Show one record of the laboratory's intended use: its content, the supported assays, what the acceptance froze, and, for the accepted record, what has changed since.

## Who can use it

- Sign-in required. Roles allowed to view: Analyst, Reviewer, Quality, Admin, Auditor; others receive 403.
- **Accept** is shown to a Quality user who did not record the record, while it awaits acceptance and its process owner and system owner are still active accounts with a working role.
- **Withdraw** is shown to any Quality user, the recorder included, while it awaits acceptance.
- The server checks both again on the action pages.

## Layout

- Breadcrumbs, the record number (UA-n), the state label, and the action buttons.
- A notice (see Rules).
- **Details**: Title, Intended use, Outside the intended use, Methods in force that are not supported assays (shown while awaiting acceptance or accepted), Process owner, System owner, Other responsibilities, Validation report, Validation report link, Known issues and conditions, Recorded by, Recorded, Accepted, Accepted release (once accepted), Running release, Superseded, Superseded by (once superseded), Withdrawn, Revision. An empty value shows a dash.
- **Supported assays**: Method (its title and code), Accepted (the version frozen at acceptance, empty before), In force now. A method with no version in force shows "None in force".
- **Changes since acceptance** (accepted record only): Kind, Code, Accepted, In force now, Change.
- **Approved configuration frozen at acceptance** (once accepted or superseded) or **Approved configuration in force now** (while awaiting acceptance): Kind, Code, Version, Content hash (first 12 characters).
- **Signatures** and **History** of the record.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Accept** | Awaiting acceptance, you are Quality and did not record it, and both owners are still active | Quality | Opens the signing page |
| **Withdraw** | Awaiting acceptance | Quality | Opens the withdrawal page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| State | `UseAcceptance.state` | Label | — | Awaiting acceptance, Accepted, Superseded, Withdrawn |
| Accepted / Accepted release | `UseAcceptance.accepted_at`, `.accepted_release` | Time, text | — | When signed and the release then running; "Not stated by the deployment" when the deployment gives none |
| Running release | — | Text | — | The release running now |
| Superseded / Superseded by | `UseAcceptance.superseded_at`, `.superseded_by` | Time, record | — | The later acceptance that replaced this one, linked |
| Withdrawn | `UseAcceptance.withdrawn_at` | Time | — | When withdrawn |
| Revision | `UseAcceptance.revision` | Integer | — | Raised by each change of state |
| Content hash | — | Text | — | Start of the approved content hash of a version; blank for rule sets and any version that has none |

## Rules and hidden logic

- **Notice**: "What an acceptance does" (info) says the acceptance records the decision that the system is fit for the use described, holds no work, and that changes are shown for the laboratory's own change control. On the accepted record it becomes "Changed since acceptance" (warning) when approved versions in force differ from the frozen ones or the running release differs from the accepted release; "Release not compared" (info) when nothing else changed but a release is not stated now or was not stated at acceptance; otherwise "Current acceptance" (success). A superseded record shows "Superseded" with the later record and time; it is kept as accepted.
- When the deployment states no release now, the notice says: "The deployment does not state its release (set SOURCE_REVISION), so the running release cannot be compared with the accepted one." When it states one now but none was stated at acceptance: "No release was stated when this record was accepted, so the running release (...) cannot be compared with it."
- **Changes since acceptance** compares codes. Each code whose version in force is not the frozen one gets a row: "Another version in force", "No longer in force" or "Newly in force". The kinds are Rule set, Specification, Method, Sampling plan and Stability protocol.
- The frozen configuration shows the SHA-256 of the frozen record and the time it applied.
- Supersession: when a newer record is accepted, the one accepted before becomes Superseded. At most one record is accepted at a time (a database constraint).
- Nothing on this page changes anything; no work is held by these records.

## Related pages

- [Intended use](/validation/) list
- Accept intended use; Withdraw intended use
