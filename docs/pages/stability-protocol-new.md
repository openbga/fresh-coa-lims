---
title: New protocol
urls: stability:protocol_new
views: stability.views.protocol_new
templates: ops/form.html
models: stability.Protocol, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Draft the next version of a stability protocol; conditions and timepoints are added afterwards.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft** | Always | Analyst or Quality; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `Protocol.code` | Text, max 60 | Yes | Identifier shared by all versions |
| Title, Product | `Protocol.title`, `.product` | Text, max 160 | Yes | What the protocol covers |
| Document ref / Document url | `Protocol.document_ref`, `.document_url` | Text; http(s) link | Ref required | Approved protocol document and revision in the QMS |
| Test profile ref | `Protocol.test_profile_ref` | Text, max 200 | No | Stable specification/test-profile revision |
| Basis | `Protocol.basis` | Text | Yes | Why these conditions and schedule apply |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- The version is the next number for the code. If the latest version is still a draft: "<code> v<n> is still a draft; approve or leave it."
- The header cannot be edited after creation; content is added by the author while the protocol is a draft. Event `protocol.created`.

## Related pages

- [Stability protocols](/stability/protocols/)
