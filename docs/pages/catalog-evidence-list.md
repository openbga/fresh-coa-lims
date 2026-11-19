---
title: Method evidence
urls: catalog:evidence_list
views: catalog.evidence_views.evidence_list
templates: ops/list.html
models: catalog.MethodEvidence, catalog.MethodRevision
reviewed: 2026-11-19
summary: Every record of the evidence that a method is suitable for its intended use: validations, verifications, transfers. Find a record, see its conclusion and state, or start a new one.
---

## Common tasks

### Find an evidence record

1. Type a word of the title, the method code or title, the procedure, the report or the source in [[Search]].
2. Narrow the list with [[Status]], [[Kind]] or [[Conclusion]], then apply the filter.
3. Select the record number to open it.

### Record new evidence

1. Select [[New evidence record]]. It shows to analysts, reviewers and quality users.
2. Fill in the form and select [[Record draft]].

### Check which methods rely on a record

1. Look at [[Approved versions]] for the record. Open the record to see the versions.

## Good to know

- A new record is a draft. It supports no method version until a quality user who did not record or change it approves it.
- Approved versions counts only approved method versions that rely on the record.
- A withdrawn record stays in the list. Versions already approved on it keep it as approved.
- Reading is open to analysts, reviewers, quality, admin and auditor accounts; only the first three can record.

## Purpose

The register of method evidence records. Each summarizes a report kept in the laboratory's document system and states whether the method is suitable for its intended use.

## Who can use it

- Sign-in required. Roles that can open it: analyst, reviewer, quality, admin and auditor. Others receive 403.
- **New evidence record** shows to analyst, reviewer and quality users. The server checks the role again on the form.

## Layout

- **Section tabs**: Specifications, Methods, Method evidence (current), Materials.
- **Header**: title "Method evidence", an introduction and the new button.
- **Filter**: Search, Status (All, Draft, Approved, Withdrawn), Kind, Conclusion.
- **Table** columns: Record (MEV-n link with the title beneath), Method (code link with title beneath), Kind, Report, Completed on, Conclusion, Approved versions, State. Report and Approved versions give way first on narrow screens.
- **Empty state**: "Record the validation, verification or transfer of a method."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New evidence record** | Analyst, reviewer or quality | Same roles | Opens the New method evidence record form |
| Record number | Each row | Any reader | Opens the record |
| Method code | Each row | Any reader | Opens the method record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches the title, method code, method title, procedure studied, report or source (contains, any case) |
| Status | `MethodEvidence.state` | Choice: All, Draft, Approved, Withdrawn | No | Keeps one state |
| Kind | `MethodEvidence.kind` | Choice: All and the four suitability kinds | No | Keeps one kind |
| Conclusion | `MethodEvidence.conclusion` | Choice: All, Suitable for the intended use, Not suitable | No | Keeps one conclusion |
| Record | `MethodEvidence.pk`, `title` | MEV-n | — | Identifier and title |
| Method | `MethodEvidence.method` | Code and title | — | The method the record is for |
| Report | `MethodEvidence.report_ref` | Text | — | Report and revision |
| Completed on | `MethodEvidence.completed_on` | Date | — | Day the report was completed |
| Approved versions | `MethodRevision.evidence` count | Integer | — | Approved method versions relying on the record |
| State | `MethodEvidence.state` | Label | — | Draft, Approved or Withdrawn |

## Rules and hidden logic

- **Order and paging**: newest completion date first by default (then newest record). You can sort by Method (code, then completion date) and Completed on. The list is paged on the server.
- **Filters**: held in the address, so a filtered list can be bookmarked. An unknown filter value gives no filter.
- **Permissions**: reading is open to the five roles above. Admin status alone gives no action.

## Related pages

- New method evidence record
- Method evidence record (each row)
- [Methods](/catalog/methods/)
