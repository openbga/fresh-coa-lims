---
title: Record equipment qualification
urls: laboratory:equipment_qualification_new
views: laboratory.views.qualification_new
templates: ops/form.html
models: laboratory.Qualification, laboratory.Equipment, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record installation/operational/performance qualification evidence for one instrument.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record qualification** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Stage or intended use | `Qualification.activity` | Text, max 120 | Yes | IQ, OQ, PQ or requalification |
| Scope note | `Qualification.scope_note` | Text | No | Limits of the qualification |
| Evidence reference | `Qualification.evidence_ref` | Text, max 200 | Yes | Controlled training or qualification record and revision |
| Evidence link | `Qualification.evidence_url` | http(s) URL | No | Untrusted external link |
| Valid from | `Qualification.valid_from` | Date | Yes | First valid day |
| Valid until (inclusive) | `Qualification.valid_until` | Date | Yes | Last valid day; cannot precede Valid from |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the evidence |

## Rules and hidden logic

- The record starts as Awaiting approval and counts toward fitness only after a different Quality signer approves it and only inside its validity dates.
- Event `qualification.recorded`.

## Related pages

- Equipment record
- [Qualifications](/laboratory/qualifications/)
