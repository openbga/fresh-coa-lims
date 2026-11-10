---
title: New qualification
urls: laboratory:qualification_new
views: laboratory.views.qualification_new
templates: ops/form.html
models: laboratory.Qualification, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record training or competence evidence for an analyst and activity. Recording does not qualify anyone.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.

## Layout

- Breadcrumbs (Laboratory, Qualifications, Record qualification), title "New qualification", the introduction "Recording evidence does not qualify anyone. A different quality signer approves it; the person concerned can neither record nor approve their own.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record qualification** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves and opens the new qualification record with "Qualification recorded; independent approval needed."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Qualified person | `Qualification.user` | Choice of active accounts by username (any role) | Yes | The person the evidence is about; never yourself |
| Activity | `Qualification.activity` | Text, max 120 | Yes | Method or activity code; matching is case-insensitive |
| Scope note | `Qualification.scope_note` | Text | No | Limits of the qualification |
| Evidence reference | `Qualification.evidence_ref` | Text, max 200 | Yes | Controlled training or qualification record and revision |
| Evidence link | `Qualification.evidence_url` | http(s) URL | No | Untrusted external link |
| Valid from | `Qualification.valid_from` | Date | Yes | First valid day |
| Valid until (inclusive) | `Qualification.valid_until` | Date | Yes | Last valid day; cannot precede Valid from |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the evidence |

## Rules and hidden logic

- You cannot record evidence about yourself ("You cannot record qualification evidence for yourself."); the person's account must be active.
- "Valid until cannot precede valid from." appears on Valid until when the dates are reversed.
- Cancel returns to Qualifications. Instrument qualification is recorded from the equipment record instead.
- The record starts as Awaiting approval and qualifies nobody until a Quality signer who is neither you nor the qualified person approves it; the qualified person can never approve their own.
- Event `qualification.recorded`.

## Related pages

- [Qualifications](/laboratory/qualifications/)
