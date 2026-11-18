---
title: Impact assessments
urls: impact:list
views: impact.views.assessment_list
templates: ops/list.html
models: impact.Assessment, impact.Item
reviewed: 2026-11-17
summary: All impact assessments: what an equipment, reagent, supplier, contract-laboratory or other problem affected, with its status and how many records still need a decision. Quality starts new ones.
---

## Common tasks

### Find an assessment

1. Type a word of the title, the quality-system reference or the number (for example IA-3 or 3) in [[Search]].
2. Choose a [[Status]] to narrow the list, then apply the filter.
3. Select the assessment number to open it.

### See the assessments that still need work

1. Choose the status Open and look at [[Without a decision]].
2. Sort that column to bring the assessments with most open decisions together.

### Start an assessment

1. Select [[New impact assessment]]. It shows to quality users only.
2. Fill in the form and select [[Start assessment]].

## Good to know

- An assessment records what a problem affected and what is done about it. It changes none of the records it names.
- Without a decision shows a number for open assessments only. Concluded and withdrawn ones leave it empty.
- The same list opens from the quality dashboard gate "Impact assessments open", filtered to Open.
- Analysts, reviewers, quality, admin and auditor accounts read the list. Only quality starts or changes an assessment.

## Purpose

The register of impact assessments. It shows, for each problem found on equipment, a reagent or standard lot, a supplier, a contract laboratory or anything else, the period of concern, the status and how many of the records it names still lack a decision.

## Who can use it

- Sign-in required. Roles that can open it: analyst, reviewer, quality, admin and auditor. Others receive 403.
- **New impact assessment** shows to users holding the quality role only. The server checks the role again on the form.

## Layout

- **Header**: title "Impact assessments", an introduction, and the new button for quality.
- **Filter**: Search and Status (All, Open, Concluded, Withdrawn).
- **Table** columns: Assessment (IA-n with the title beneath, a link), Cause (the cause and the record that failed, for example "Equipment · EQ-001 · balance"), Date found, Status, Records, Without a decision, Started by. Without a decision and Started by are hidden first on narrow screens.
- **Empty state**: "Start one when equipment, a reagent or standard, a supplier, a contract laboratory or anything else may have affected work already done."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New impact assessment** | Always for quality | Quality | Opens the New impact assessment form |
| Assessment number | Each row | Any reader | Opens the assessment record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches the title or the quality-system reference (contains, any case), and the number when the text is IA-n or n |
| Status | `Assessment.state` | Choice: All, Open, Concluded, Withdrawn | No | Keeps one status |
| Assessment | `Assessment.pk` | IA-n | — | The identifier; the title is `Assessment.title` |
| Cause | `Assessment.cause` and the named record | Text | — | What failed |
| Date found | `Assessment.found_on` | Date | — | When the problem was found |
| Status | `Assessment.state` | Label | — | Open, Concluded or Withdrawn |
| Records | `Item` count | Integer | — | Every record the assessment names |
| Without a decision | `Item.decision` empty | Integer | — | Records with no decision; shown for Open assessments only |
| Started by | `Assessment.started_by` | Person | — | Who started it |

## Rules and hidden logic

- **Order and paging**: newest number first by default. You can sort by Assessment, Date found, Status (Concluded, Open, Withdrawn, then newest start) and Without a decision. The list is paged on the server.
- **Filters**: the filter is in the address, so a filtered list can be bookmarked or linked.
- **Permissions**: reading is open to the five roles above. Admin status alone gives no action here.

## Related pages

- New impact assessment
- Impact assessment record (each row)
- [Quality dashboard](/)
