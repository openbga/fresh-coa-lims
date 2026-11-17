---
title: Rehearsal record
urls: validation:rehearsal_detail
views: validation.views.rehearsal_detail
templates: ops/record.html
models: validation.Rehearsal, validation.RehearsalFile, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
---

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
| **Withdraw** | Awaiting acceptance, and you recorded it or are Quality | Recorder, Quality | Opens the withdrawal page |
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
