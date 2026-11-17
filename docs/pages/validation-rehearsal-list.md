---
title: Rehearsals
urls: validation:rehearsal_list
views: validation.views.rehearsal_list
templates: ops/list.html
models: validation.Rehearsal, validation.RehearsalFile
reviewed: 2026-11-17
---

## Purpose

List the recorded rehearsals of recovery from backup, downtime with reconciliation, and upgrades, each with its evidence and acceptance.

## Who can use it

- Sign-in required. Roles allowed to view: Analyst, Reviewer, Quality, Admin, Auditor. Others receive 403.
- **New rehearsal** is shown to Quality and Admin users.

## Layout

- Tabs **Intended use** and **Rehearsals**, the title and an introduction.
- A filter bar: **Search**, **Status**, **Apply**, and **Clear filters** once a filter is set.
- A table with the columns **Record**, **Rehearsal of**, **Title**, **Performed**, **Release**, **Status**, **Files**; paging at 25, 50 or 100 rows.
- Empty state "No records yet": "Record a rehearsal after it took place, attach its evidence, then have a quality person accept it."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New rehearsal** | Always for Quality and Admin | Quality, Admin | Opens the record form |
| Record number (RH-n) | Every row | Any viewer | Opens the rehearsal |
| Headings **Rehearsal of**, **Title**, **Performed** | Always | Any viewer | Sort the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | `Rehearsal.title`, `.release`, `.procedure_ref` | Text, max 100 | No | Case-insensitive match in any of the three |
| Status | `Rehearsal.state` | Choice | No | **All**, **Awaiting acceptance**, **Accepted**, **Withdrawn** |
| Rehearsal of | `Rehearsal.kind` | Label | — | Recovery from backup, Downtime and reconciliation, Upgrade |
| Performed | `Rehearsal.performed_on` | Date | — | The day it was performed |
| Release | `Rehearsal.release` | Text | — | Release or source revision rehearsed |
| Status | `Rehearsal.state`, `.outcome` | Label | — | **Awaiting acceptance**, **Withdrawn**, **Accepted: criteria met**, **Accepted: criteria not met** |
| Files | `RehearsalFile` | Count | — | Number of evidence files attached |

## Rules and hidden logic

- Ordering: most recently performed first by default; ties by record number. Sorting applies to the whole list.
- Withdrawn rehearsals stay in the list; filter by Status to separate them.
- Not enforced by this page: how often a rehearsal is performed. The list shows what was recorded; it does not schedule or warn.

## Related pages

- Rehearsal record (from the record number); Record rehearsal (from **New rehearsal**)
- [Intended use](/validation/)
