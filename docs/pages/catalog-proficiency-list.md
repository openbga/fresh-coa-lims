---
title: Proficiency testing
urls: catalog:proficiency_list
views: catalog.proficiency_views.proficiency_list
templates: ops/list.html
models: catalog.ProficiencyParticipation, catalog.Method
reviewed: 2026-11-19
summary: Every participation in a proficiency testing scheme or other interlaboratory comparison. Find a round, see its outcome and state, or plan a new one. Quality plans; the list is open to all readers.
---

## Common tasks

### Find a participation

1. Type a word of the method code or title, the provider, the scheme, the round or the test item in [[Search]].
2. Narrow the list with [[Status]], [[Kind]] or [[Outcome]], then apply the filter.
3. Select the PT number to open the participation.

### See what needs attention

1. Choose [[Results overdue]] in [[Status]] for rounds past their due day with no report, or [[Results reported]] for rounds whose results were sent to the provider and that are not reviewed yet.
2. Choose [[Follow-up open]] for rounds that need corrective follow-up.

### Plan a participation

1. Select [[New participation]]. It shows only to quality users.
2. Fill in the form and select [[Plan participation]].

## Good to know

- Planned and Results overdue both mean no report is recorded yet; the due day decides which one shows.
- Outcome stays empty until a quality person has reviewed the participation.
- A cancelled participation stays in the list with its reason in its history.
- Analysts, reviewers, quality, admin and auditor accounts can read the list; only quality can plan.

## Purpose

The register of the laboratory's participation in proficiency testing schemes and other interlaboratory comparisons, one row per round and method.

## Who can use it

- Sign-in required. Roles that can open it: analyst, reviewer, quality, admin and auditor. Others receive 403.
- **New participation** shows to the quality role only. The server checks the role again on the form.

## Layout

- **Section tabs**: Specifications, Methods, Method evidence, Proficiency testing (current), Materials.
- **Header**: title "Proficiency testing", an introduction ("Each participation compares the laboratory's results for one method with those of other laboratories: a round of a proficiency testing scheme or another interlaboratory comparison. Quality plans each one, the laboratory records its results with the provider's scores, and an independent quality person reviews the outcome.") and the **New participation** button.
- **Filter**: Search, Status, Kind, Outcome.
- **Table** columns: Participation (PT-n link with the round beneath), Method (code link with the title beneath, sortable), Provider (scheme beneath), Kind, Results due (sortable), Outcome, State. Kind gives way first on narrow screens. **Columns** chooses which columns show.
- **Empty states**: "No records yet" ("Quality plans the rounds the laboratory takes part in, method by method.") with **New participation** for quality; "Nothing matches these filters" when a filter excludes everything.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New participation** | Quality role | Quality | Opens the New participation form |
| PT number | Each row | Any reader | Opens the participation |
| Method code | Each row | Any reader | Opens the method record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches method code, method title, provider, scheme, round and test item (contains, any case) |
| Method (address only) | `ProficiencyParticipation.method` | Hidden, from the address | No | Set by **All participations** on a method's page: lists that method's participations only, matched exactly. Without it, every method is listed |
| Status | — | All, Planned, Results overdue, Results reported, Follow-up open, Closed, Cancelled | No | Keeps one displayed state (see rules) |
| Kind | `ProficiencyParticipation.kind` | All, Proficiency testing scheme, Interlaboratory comparison | No | Keeps one kind |
| Outcome | `ProficiencyParticipation.outcome` | All, Satisfactory, Questionable, Unsatisfactory, Not evaluated | No | Keeps one reviewed outcome |
| Participation | `ProficiencyParticipation.pk`, `round_ref` | PT-n | — | Identifier and round |
| Method | `ProficiencyParticipation.method` | Code and title | — | The method compared |
| Provider | `provider`, `scheme` | Text | — | Provider or organizer, with the scheme beneath |
| Kind | `kind` | Label | — | Proficiency testing scheme or Interlaboratory comparison |
| Results due | `results_due` | Date | — | Day the results are due to the provider |
| Outcome | `outcome` | Status label | — | Empty until reviewed |
| State | — | Status label | — | Planned, Results overdue, Results reported, Follow-up open, Closed or Cancelled |

## Rules and hidden logic

- **State shown**: an open participation is "Results reported" once a reported day is recorded (the record says what review still needs); otherwise "Results overdue" when its due day is before today, else "Planned". The Status filter uses the same rules (Planned: due today or later).
- **Order and paging**: newest due day first by default (then newest record). Sort by Method (code, then due day) or Results due. Paged on the server.
- **Filters**: held in the address, so a filtered list can be bookmarked. An unknown filter value gives no filter.
- **Method from a method page**: `?method=<id>` limits the list to one method, matched by its record, not by text; it is combined with the other filters.
- **Permissions**: reading is open to the five roles above. Admin status alone gives no action.

## Related pages

- New participation
- Participation record (each row)
- [Methods](/catalog/methods/) and [Method evidence](/catalog/method-evidence/)
- [Reminders](/planning/reminders/)
