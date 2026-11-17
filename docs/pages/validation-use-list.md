---
title: Intended use
urls: validation:use_list
views: validation.views.use_list
templates: validation/list.html, ops/list.html
models: validation.UseAcceptance
reviewed: 2026-11-17
summary: The laboratory's records of its intended use of the system. See which record is accepted and whether the configuration or release changed since, or record a new one.
---

## Common tasks
### Check the current acceptance
1. Read the notice above the table. [[Current acceptance]] means the approved configuration and the release are those the acceptance froze.
2. If it shows [[Changed since acceptance]], select the accepted record's number to see each change.
### Find a record
1. Type words from the title or the intended use in [[Search]].
2. To see only one state, choose it in [[Status]], then select [[Apply]].
3. Select a record number to open it.
### Record a new intended use
1. Select [[New intended use]]. It shows only to the quality role.
2. Fill in the form and select [[Record intended use]] on that page. A different quality person then accepts it.
### See every record again
1. Select [[Clear all]].
## Good to know
- Only one record is accepted at a time. Accepting a newer record supersedes the one accepted before, and the superseded record is kept.
- These records hold no work. A change since acceptance is shown so you can assess it under your own change control.
- The comparison is made each time the page opens, from the approved versions in force now and the release the deployment states.
- [[Release not compared]] means the deployment does not state its release now, or did not when the record was accepted.

## Purpose

List the records of the laboratory's intended use of the system and show whether the current acceptance still matches the approved configuration and the running release. An accepted record states what the system is used for, the supported assays and the people responsible, and freezes the approved configuration in force when it was signed.

## Who can use it

- Sign-in required. Roles allowed to view: Analyst, Reviewer, Quality, Admin, Auditor. Others receive the standard 403 page.
- **New intended use** is shown to Quality users only.

## Layout

- Tabs **Intended use** and **Rehearsals**, the title, and an introduction.
- A notice about the current acceptance (see Rules).
- A filter bar: **Search**, **Status**, **Apply**, and **Clear all** once a filter is set.
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
  - "Release not compared" (info): the approved configuration in force is the one it froze, but no release is stated now (`SOURCE_REVISION` and `RENDER_GIT_COMMIT` both unset) or none was stated at acceptance, so the release cannot be compared. The column reads "Release not compared". With configuration changes as well, the notice is "Changed since acceptance" and the column reads, for example, "1 change to the configuration and a release that cannot be compared".
  - "Current acceptance" (success): the configuration and release are those it froze.
- The comparison is made each time the page opens, from the approved versions in force now and the release the deployment reports (`SOURCE_REVISION`, else `RENDER_GIT_COMMIT`).
- No work is held because of these records: nothing in the system is blocked by a changed configuration or by the lack of an acceptance.

## Related pages

- Intended use record (from the record number); Record intended use (from **New intended use**).
- [Rehearsals](/validation/rehearsals/)
