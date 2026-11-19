---
title: Qualification record
urls: laboratory:qualification_detail
views: laboratory.views.qualification_detail
templates: ops/record.html
models: laboratory.Qualification, core.ElectronicSignature
reviewed: 2026-11-19
summary: One qualification record: who or what it qualifies, for which activity, for what work and dates, the training it relies on, with its approval or revocation signatures and its history.
---

## Common tasks
### Approve the evidence
1. Select [[Approve]]. It shows to the quality role while the record awaits approval, unless you recorded it or it is about you.
2. Sign with your PIN on that page.
### Revoke an approved qualification
1. Select [[Revoke]]. It shows to the quality role on approved records that are not about you.
2. Sign with your PIN on that page. Work after the signature time is blocked.
### Check the evidence
1. Read [[Evidence reference]] and [[Scope]], and open the link under [[Evidence link]] if one was recorded.
2. Under [[Training relied on]], open a training record to see who trained the person and the outcome.
## Good to know
- Qualified for tells what the evidence covers: performing the work or reviewing results. An instrument's qualification shows Intended use.
- Training relied on is frozen when the evidence is recorded and signed with the approval. Whoever recorded one of those training records cannot approve it.
- Approved evidence qualifies only from the approval time and only from Valid from to Valid until.
- Approve still shows on evidence whose last valid day has passed, but signing it is refused. Record new evidence instead.
- A revoked qualification cannot be approved again or edited. Work recorded before the revocation stays; only later work is blocked.

## Purpose

Evidence that a person or instrument is qualified for an activity within stated dates.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title (the activity), the identifier QUAL-n and the state label (Awaiting approval, Approved, "Approved, starts <date>" before its valid-from date, Expiring soon (amber, effective and its last valid day within 30 days), Expired or Revoked), action buttons.
- **Details**: the facts below.
- **Training relied on** (analyst qualifications only): a table of Training (TRN-n link with its procedure or course), Kind, Outcome, Completed on and Trainer or assessor. Empty: "This evidence cites no training record in the system; its evidence reference names the record relied on."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Awaiting approval; you are neither the recorder nor the subject, and recorded none of the training it relies on | Quality | Opens the approval signing page |
| **Revoke** (under **More**) | Approved (including past its last day); you are not the subject | Quality | Opens the revocation signing page |
| Evidence link | An evidence URL was recorded | Any reader | Opens the external link (`noopener noreferrer`); treat its content as untrusted |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Subject / Type | `Qualification.user`, `.equipment` | Username or asset ID; Analyst or Equipment | — | Exactly one subject |
| Qualified for | `Qualification.work` | Performing the work, Reviewing results, or Intended use for equipment | — | What the evidence qualifies the subject to do |
| Training relied on | `Qualification.training` | Training records (TRN-n) | — | The person's acknowledged training the evidence cited when recorded |
| Valid from / Valid until | `Qualification.valid_from`, `.valid_until` | Dates (inclusive) | — | Validity window |
| Evidence reference / Evidence link / Scope | `Qualification.evidence_ref`, `.evidence_url`, `.scope_note` | Text; http(s) link; text | — | Controlled evidence and its limits; blank when not given |
| Recorded by / Revision | `Qualification.recorded_by`, `.revision` | User, integer | — | Authorship and revision |

## Rules and hidden logic

- The identifier is QUAL- plus the record number. State Expired is shown for an approved record after its last valid day.
- Signatures and history are those of this record only. An unknown ID returns 404.
- The record is immutable apart from its state changes (database guard); there is no edit.

## Related pages

- [Qualifications](/laboratory/qualifications/)
