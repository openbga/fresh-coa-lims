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

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403. The equipment must exist (404 otherwise).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Laboratory, Equipment, the asset, Record qualification), title "Record qualification · ASSET", the introduction "Recording evidence does not qualify anyone. A different quality signer approves it; the person concerned can neither record nor approve their own.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record qualification** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves and opens the new qualification record with "Qualification recorded; independent approval needed."; domain refusals appear as an error summary and your entries are kept (status 422) |
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

The label of Stage or intended use differs from the person form ("Activity"); help text: "For example IQ, OQ, PQ or requalification."

## Rules and hidden logic

- The record is tied to this equipment (there is no person field). It starts as Awaiting approval and counts toward fitness only after a Quality signer other than you approves it, and only from the approval time and inside its validity dates. Equipment registered with "Requires qualification" off ignores this evidence.
- "Valid until cannot precede valid from." appears on Valid until when the dates are reversed.
- Event `qualification.recorded`.

## Related pages

- Equipment record (Cancel returns here)
- [Qualifications](/laboratory/qualifications/)
