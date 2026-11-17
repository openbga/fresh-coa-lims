---
title: Protocol record
urls: stability:protocol_detail
views: stability.views.protocol_detail
templates: ops/record.html
models: stability.Protocol, catalog.Specification, stability.ProtocolCondition, stability.ProtocolTimepoint, core.ElectronicSignature
reviewed: 2026-11-17
summary: One protocol version: its header, storage conditions, timepoints and the acceptance criteria in force, with the actions that approve it, withdraw it or start a study on it.
---

## Common tasks
### Build a draft protocol
1. Select [[Add condition]] for each approved storage condition. It shows only to the draft's author.
2. Select [[Add timepoint]] for each pull time point and its tests. It shows once the draft has a condition.
### Approve the protocol
1. Select [[Approve]]. It shows to a quality user who is not the author, once the draft has a timepoint.
2. Sign with your PIN on that page. Earlier approved versions of the code become Superseded.
### Start a study
1. On an approved protocol, select [[Start study]]. The study form opens with this protocol chosen.
### Withdraw a draft that will not be approved
1. Select [[Withdraw draft]]. It shows to the draft's author and to quality users.
2. Give the reason on that page. The next version of the code can then be drafted.
## Good to know
- [[Criteria incomplete]] means the specification cannot state a test. A draft cannot be approved, and an approved protocol's pulls cannot get tests, until it is fixed.
- The criteria shown are read from the specification now. Each pull's tests freeze the version in force when assigned, so a later version applies only to later pulls.
- An approved protocol is frozen. To change it, draft a new version of the code.
- Only the author can add conditions or timepoints to a draft. Other analysts and quality users cannot.

## Purpose

One protocol version (code and version number) with its header facts, storage conditions and timepoints, and the actions that move it forward.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons. The status is the filled label; the identifier is a code; a muted line under it gives "Record revision". One primary button, the next step for you; further buttons are secondary or under **More**.
- **Details**: Product, Protocol document (a link when a URL is set, otherwise the reference text), Test profile revision, Acceptance criteria (the specification, as "<code> · <title> (<material>, <stage>, scope <scope>)" and a link to it, or "Not in the system: pulls link a sample or external evidence"), Basis, Author, Approved (time), Content digest, Revision.
- **Storage conditions**: condition, setpoint, temperature (°C), humidity (%).
- **Timepoints**: condition, timepoint, day, window (± days), tests (codes comma separated). Ordered by condition then day. Empty states: "No conditions yet. Add the approved storage conditions." and "No timepoints yet."
- **Acceptance criteria in force** (only when the protocol names a specification): Test, Name, Acceptance criterion, Method (code and revision) for each test code of its timepoints, as the specification's approved version in force states them now; a test it cannot state shows a warning in place of the criterion. Empty: "Add timepoints to see the acceptance criterion of each test." A note names the specification version and says each pull's tests freeze the version in force when they are assigned, so a later version applies to later pulls.
- **Notice** "Criteria incomplete" (warning), when the specification cannot state a test, for a Draft or Approved protocol: it lists the reasons and adds "The protocol cannot be approved until this is resolved in the specification." (Draft) or "Tests cannot be assigned to its pulls until this is resolved in the specification." (Approved). Not shown for a Superseded protocol.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; a short "No signatures yet." line when there are none.
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Draft with at least one timepoint, you have the Quality role and you are not the author | Quality | Opens the signing page, where the full approval preconditions are checked |
| **Add condition** / **Add timepoint** | Draft; you are the author and an Analyst or Quality user (timepoint also needs at least one condition) | Analyst, Quality (author only) | Opens the add form |
| **Withdraw draft** | Draft; you are its author (Analyst or Quality) or a Quality user | Analyst, Quality | Opens the withdrawal form |
| **Start study** | State Approved (not Draft, Superseded or Withdrawn) | Analyst, Quality | Opens the new study form with this protocol preselected |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Product, Protocol document, Test profile revision, Acceptance criteria, Basis | `Protocol.product`, `.document_ref`, `.document_url`, `.test_profile_ref`, `.specification`, `.basis` | Text; document link | — | Header; the header is frozen after creation |
| Title / State | `Protocol.title`, `.state` | Text; Draft, Approved, Superseded or Withdrawn | — | Page title and status label |
| Storage conditions | `ProtocolCondition.*` | Label, setpoint, temperature (°C), humidity (%) | — | Blank when not set |
| Timepoints | `ProtocolTimepoint.*` | Day (interval from time zero), window (± days), test codes | — | Pulls are scheduled from these |
| Author / Approved | `Protocol.author`, `.approved_at` | User, time | — | Authorship and approval time |
| Content digest | `Protocol.content_digest` | First 12 hex characters | — | Fingerprint of all conditions and timepoints, bound by the approval signature |
| Revision | `Protocol.revision` | Integer | — | Rises with every addition and the approval |

## Rules and hidden logic

- Once approved the content is frozen in the database; change it by creating a new version. Superseded versions stay readable.
- The criteria shown are read live from the specification and are not stored on the protocol; they can change when the specification gets a new approved version. Tests freeze them when assigned to a pull.
- Add buttons are visible to the draft's author only, but the server also refuses anyone else.
- Signatures lists the approval signature; History lists `protocol.created`, additions and approval events.

## Related pages

- [Stability protocols](/stability/protocols/)
- [Stability studies](/stability/studies/)
- Add storage condition, Add timepoint, Approve protocol and Withdraw draft protocol (opened from the actions above)
