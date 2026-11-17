---
title: New protocol
urls: stability:protocol_new
views: stability.views.protocol_new
templates: ops/form.html
models: stability.Protocol, core.AuditEvent
reviewed: 2026-11-17
summary: Draft the next version of a stability protocol code. You add its storage conditions and timepoints afterwards on the protocol record. Analysts and quality users only.
---

## Common tasks
### Draft a protocol
1. Enter [[Code]], [[Title]], [[Product]], [[Document ref]] and [[Basis]].
2. To test pulls in the system, choose the specification in [[Acceptance criteria (specification)]]. Leave it empty to link samples or external evidence instead.
3. Enter a [[Reason]] and select [[Create draft]]. The protocol record opens; add conditions and timepoints there.
### Draft the next version of an existing code
1. Enter the existing code in [[Code]]. The draft gets the next version number.
2. Fill in the rest and select [[Create draft]]. The approved version stays in force until the new one is approved.
## Good to know
- The header, including the specification, cannot be changed after you save. Naming another specification needs a new protocol version.
- You cannot draft a new version while the code still has a draft. Approve or withdraw that draft first.
- You become the author, so you cannot approve this protocol yourself. A different quality user signs it.
- The specification is not checked against the protocol's tests now. That happens when the protocol is approved.

## Purpose

Draft the next version of a stability protocol; conditions and timepoints are added afterwards.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Stability and retention, Protocols, New protocol), title "New protocol", the introduction "Creates the next version of the code. Approved versions are frozen.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Create draft** | Always | Analyst or Quality; others receive 403 | Saves, shows "Draft protocol created. Add conditions and timepoints." and opens the protocol record; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `Protocol.code` | Text, max 60 | Yes | Identifier shared by all versions |
| Title, Product | `Protocol.title`, `.product` | Text, max 160 | Yes | What the protocol covers (product or material under study) |
| Document ref / Document url | `Protocol.document_ref`, `.document_url` | Text, max 200; http(s) link | Ref required, URL optional | Approved protocol document and revision in the QMS |
| Test profile ref | `Protocol.test_profile_ref` | Text, max 200 | No | Stable specification/test-profile revision |
| Acceptance criteria (specification) | `Protocol.specification` | Choice of specifications, listed by code as "<code> · <title> (<material code>, <stage>, scope <scope>)" | No | The specification whose approved version in force states the acceptance criterion of each test, for example the shelf-life specification of the product. With one, pulls are tested in the system. Empty: pulls link a sample or external evidence. Cannot be changed later; a new protocol version names another |
| Basis | `Protocol.basis` | Text | Yes | Why these conditions and schedule apply |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- The version is the next number for the code. If the latest version is still a draft: "<code> v<n> is still a draft; approve or leave it."
- The author is you; the author cannot later approve it. A different Quality user must approve.
- The specification is part of the header and is fixed at creation. Nothing checks it against the protocol's tests at this step; that happens when the protocol is approved.
- The header cannot be edited after creation; content is added by the author while the protocol is a draft. Event `protocol.created`.

## Related pages

- [Stability protocols](/stability/protocols/)
- Protocol record (where you add conditions and timepoints next)
