---
title: Rehearsal record
urls: validation:rehearsal_detail
views: validation.views.rehearsal_detail
templates: ops/record.html
models: validation.Rehearsal, validation.RehearsalFile, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One rehearsal: what was done, its criteria and outcome, the evidence files and its acceptance. Attach evidence, accept or withdraw it here.
---

## Common tasks
### Attach the evidence
1. Select [[Attach evidence]]. It shows only to the person who recorded the rehearsal, while it awaits acceptance.
2. Choose the file, say what it is and select [[Attach file]] on that page.
### Accept the rehearsal
1. Select [[Accept]]. It shows to the quality role once evidence is attached, unless you recorded the rehearsal.
2. Sign with your PIN on that page using [[Sign and accept]].
### Download an evidence file
1. Under [[Evidence files]], select the file name.
### Withdraw a rehearsal that will not be accepted
1. Select [[Withdraw]]. It shows to its recorder or a quality person while it awaits acceptance.
2. Give a reason on that page, then record a new rehearsal to correct it.
## Good to know
- An accepted rehearsal can still show Accepted: criteria not met. The acceptance confirms the record is true, not that the criteria were met.
- Evidence files are never edited or deleted. Each download is checked against its SHA-256.
- Attaching a file raises the record's revision, so a signing page opened earlier is refused as changed.
- You cannot accept a rehearsal you recorded, even with the quality role.

## Purpose

Show one rehearsal: what was done, the criteria and outcome, the evidence files, and its acceptance.

## Who can use it

- Sign-in required. Roles allowed to view: Analyst, Reviewer, Quality, Admin, Auditor; others receive 403.
- **Attach evidence**: the person who recorded it (Quality or Admin), while it awaits acceptance.
- **Accept**: a Quality user who did not record it, while it awaits acceptance and holds at least one evidence file.
- **Withdraw**: its recorder (Quality or Admin) or any Quality user, while it awaits acceptance.
- The server checks each again on the action pages.

## Layout

- Breadcrumbs, RH-n, the status label and the action buttons.
- A notice (see Rules).
- **Details**: Rehearsal of, Title, Performed, Release before (upgrade only), Release, Environment, Procedure, Acceptance criteria, Outcome, Observations, Issues and actions, Recorded by, Recorded, Accepted, Withdrawn, Revision. An empty value shows a dash.
- **Evidence files**: File (download link), What it is, Size, SHA-256, Attached by, Attached; empty state "No evidence attached yet."
- **Signatures** and **History** of the rehearsal.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Attach evidence** | Awaiting acceptance, and you recorded it | Recorder | Opens the evidence form |
| **Accept** | Awaiting acceptance, evidence attached, you are Quality and did not record it | Quality | Opens the signing page |
| **Withdraw** (under **More**) | Awaiting acceptance, and you recorded it or are Quality | Recorder, Quality | Opens the withdrawal page |
| File name link | Each evidence file | Any viewer | Downloads the stored bytes |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `Rehearsal.state`, `.outcome` | Label | — | Awaiting acceptance, Withdrawn, Accepted: criteria met, Accepted: criteria not met |
| Outcome | `Rehearsal.outcome` | Label | — | What the recorder stated |
| Revision | `Rehearsal.revision` | Integer | — | Raised by each attached file and each change of state |
| Size | `RehearsalFile.size` | Bytes, shown in KiB/MiB | — | Size of the stored file |
| SHA-256 | `RehearsalFile.sha256` | Text | — | Checksum of the stored bytes |

## Rules and hidden logic

- **Notice**: "What a rehearsal record does" (info) says it is the evidence that a recovery, downtime or upgrade was tried and how it went; the acceptance confirms the record and does not make the criteria met. "Evidence needed" (warning) shows while awaiting acceptance with no file: it cannot be accepted. "Criteria not met" (danger) shows on an accepted rehearsal whose outcome is not met: follow the issues and actions under your procedure and record a new rehearsal when done.
- An accepted rehearsal with the outcome not met stays accepted: the acceptance confirms that the record is true, not that the criteria were met.
- Files are never edited or deleted. The checksum is checked at every download.

## Related pages

- [Rehearsals](/validation/rehearsals/)
- Attach evidence; Accept rehearsal; Withdraw rehearsal
