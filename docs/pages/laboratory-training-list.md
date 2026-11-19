---
title: Training
urls: laboratory:training_list
views: laboratory.views.training_list
templates: ops/list.html
models: laboratory.TrainingRecord
reviewed: 2026-11-19
summary: Every person's training in a method or activity, with the trainee's acknowledgement. Find a record, or record new training. Training qualifies nobody; a qualification relies on it.
---

## Common tasks
### Find a training record
1. Type a person, an activity, a procedure or course, or a trainer in [[Search]].
2. To narrow, choose [[Status]] (for example [[Awaiting acknowledgement]]), [[Kind]] or [[Outcome]].
3. Select [[Apply]], then select a training record to open it.
### Record someone's training
1. Select [[New training record]]. It shows for the analyst, reviewer and quality roles.
2. Fill in the form on that page. The trainee then acknowledges it with their signature.
### See every training record again
1. Select [[Clear all]] to remove the search and the filters.
## Good to know
- A training record qualifies nobody. A qualification can rely on it once the trainee has acknowledged it.
- Not yet competent is an assessment result. It stays on record, but no qualification can rely on it.
- To find the assessments that found a trainee not yet competent, choose [[Not yet competent]] in [[Outcome]].
- The record with the latest completion date comes first, not the one recorded most recently.

## Purpose

Training records of people by method or activity: the evidence that qualifications rely on. Recording training does not qualify anyone.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- **New training record** is shown to Analyst, Reviewer and Quality. The server refuses everyone else, including an account holding only the Admin role (403).
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons. Admin plus a laboratory role keeps that role's actions.

## Layout

- **Section tabs**: Overview, Equipment, Calibrations, Qualifications, Training, Reagents and standards, Contract laboratories, Resource use. These links stay in one row above the header. The current page is highlighted.
- **Header**: title and a **New training record** button for Analyst, Reviewer and Quality. The introduction reads "Training records of each person by method or activity. A record qualifies nobody: once the trainee acknowledges it, a qualification can rely on it."
- **Toolbar**: **Search** (activity, procedure or course, trainer, or the trainee's username, first name or last name; case-insensitive "contains"), **Status** (All, Awaiting acknowledgement, Acknowledged), **Kind** (All, Read and understood, Instruction or demonstration, Supervised practice, Assessment of competence) and **Outcome** (All, Completed, Competent, Not yet competent). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Training (TRN-n, links to the record, with the procedure or course under it), Trainee, Activity, Kind, Outcome, Completed on, State. Sort by Completed on (newest first by default) or Activity.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Record a person's training in a method or activity.", with **New training record**); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New training record** | Your role can record training | Analyst, Reviewer, Quality | Opens the New training record form |
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Rows per page** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `TrainingRecord.state` | Choice | No | Awaiting acknowledgement or Acknowledged, the stored state |
| Kind | `TrainingRecord.kind` | Choice | No | Read and understood, Instruction or demonstration, Supervised practice or Assessment of competence |
| Outcome | `TrainingRecord.outcome` | Choice | No | Completed, Competent or Not yet competent |
| Training | `TrainingRecord.id`, `.document_ref` | Text | — | TRN- plus the record number; the controlled procedure or course below it |
| Trainee / Activity | `TrainingRecord.trainee`, `.activity` | Person, text | — | Who was trained, and the method or activity code |
| Outcome | `TrainingRecord.outcome` | Label | — | Completed, Competent or Not yet competent (amber: no qualification can rely on it) |
| Completed on | `TrainingRecord.completed_on` | Date | — | The day the training or assessment was completed |
| State | `TrainingRecord.state` | Label | — | Awaiting acknowledgement or Acknowledged |

## Rules and hidden logic

- **Order**: by Completed on, newest first, unless you sort; ties break on record number. Unknown sort keys fall back to the default.
- Search, Status, Kind and Outcome combine: a record must match all of them.
- A record is immutable once recorded. The only change is the trainee's acknowledgement (database guard); there is no edit or delete.

## Related pages

- [Laboratory operations](/laboratory/)
- [Qualifications](/laboratory/qualifications/)
- Training record
