---
title: Intended use
urls: validation:use_list
views: validation.views.use_list
templates: validation/list.html, ops/list.html
models: validation.UseAcceptance
reviewed: 2026-11-17
---

## Purpose

List the records of the laboratory's intended use of the system and show whether the current acceptance still matches the approved configuration and the running release. An accepted record states what the system is used for, the supported assays and the people responsible, and freezes the approved configuration in force when it was signed.

## Who can use it

- Sign-in required. Roles allowed to view: Analyst, Reviewer, Quality, Admin, Auditor. Others receive the standard 403 page.
- **New intended use** is shown to Quality users only.

## Layout

- Tabs **Intended use** and **Rehearsals**, the title, and an introduction.
- A notice about the current acceptance (see Rules).
- A filter bar: **Search**, **Status**, **Apply**, and **Clear filters** once a filter is set.
- A table with the columns **Record**, **Title**, **State**, **Recorded by**, **Recorded**, **Accepted**, **Changes since acceptance**; paging at 25, 50 or 100 rows.
- Empty state "No records yet": "Record the laboratory's intended use, its supported assays and owners, then have a different quality person accept it."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New intended use** | Always for Quality | Quality | Opens the record form |
| Record number (UA-n) | Every row | Any viewer | Opens the record |
| Column headings **Title**, **Recorded**, **Accepted** | Always | Any viewer | Sort the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | `UseAcceptance.title`, `.intended_use` | Text, max 100 | No | Case-insensitive match in the title or the intended-use text |
| Status | `UseAcceptance.state` | Choice | No | **All**, **Awaiting acceptance**, **Accepted**, **Superseded**, **Withdrawn** |
| Record | — | UA-n | — | Record number, linked to the record |
| State | `UseAcceptance.state` | Label | — | As in Status |
| Recorded by | `UseAcceptance.recorded_by` | User | — | Full name and username when a name is held |
| Recorded / Accepted | `UseAcceptance.recorded_at`, `.accepted_at` | Date | — | Empty Accepted until signed |
| Changes since acceptance | — | Text | — | Filled only on the accepted row: for example "2 changes to the configuration and another release", or "None" |

## Rules and hidden logic

- Ordering: newest recorded first by default; ties by record number. Sorting applies to the whole list, not only the page.
- **Notice** above the table, based on the one accepted record (at most one exists):
  - "No accepted intended use": none has been accepted yet.
  - "Changed since acceptance" (warning): the approved versions now in force differ from those the acceptance froze, or the running release is not the accepted one. It states the counts and: "Assess the changes under your change control; record and accept the intended use again when they change it."
  - "Current acceptance": the configuration and release are those it froze.
- The comparison is made each time the page opens, from the approved versions in force now and the release the deployment reports (`SOURCE_REVISION`, else `RENDER_GIT_COMMIT`).
- No work is held because of these records: nothing in the system is blocked by a changed configuration or by the lack of an acceptance.

## Related pages

- Intended use record (from the record number); Record intended use (from **New intended use**).
- [Rehearsals](/validation/rehearsals/)
