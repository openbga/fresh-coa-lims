---
title: Study record
urls: stability:study_detail
views: stability.views.study_detail
templates: ops/record.html
models: stability.Study, stability.Pull, analytical.AnalyticalTest, core.ElectronicSignature
reviewed: 2026-11-17
summary: One stability study: its lot, protocol, next pull, the pull schedule by condition and time point, and the reviewed results so far. Quality users close the study here.
---

## Common tasks
### Find the next pull to take
1. Read [[Next pull]] in [[Details]] for the earliest scheduled pull and its status.
2. In [[Pull schedule]], select a cell to open that pull.
### Record a pull or mark it missed
1. In [[Pulls]], select [[Record pull]] in the [[Next]] column. Analysts see it while the pull is scheduled.
2. A quality user without the analyst role sees [[Mark missed]] there once the pull's window has closed.
### Compare results over time
1. Scroll to the Results section of a storage condition. Each row is a time point and each column a test with its acceptance criterion.
### Close the study
1. Select [[Close study]]. It shows to quality users who did not start the study, while it is active.
2. Choose completed or terminated and sign with your PIN on that page.
## Good to know
- A stability result never changes the lot's record. [[Criteria not met]] means quality decides whether the lot or other lots need a hold or other action.
- Accepted does not mean conforming. An accepted pull tested in the system reads "Accepted · meets acceptance criteria" or "Accepted · acceptance criteria not met".
- Each result is judged against the criterion frozen on its test, which can differ from the protocol's current one.
- The person who started the study cannot close it, even with the quality role.

## Purpose

A study's lot, protocol and every scheduled pull with its timing status; where a study is closed.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs (Studies, this study), title (protocol product and lot number), identifier, state label (Active, Completed, Terminated) and action buttons.
- **Details**: the facts below, starting with **Next pull**: the earliest scheduled pull's time point and due date, followed by its status label (Overdue, Due now, Upcoming); blank when no pull is scheduled.
- **Pull schedule** (when the study has pulls): one row per storage condition (label and setpoint), one column per time point (label and planned date); each cell is that pull's status and links to the pull, "—" where the condition has no pull at that time point. A cell whose pull is due now is marked.
- **Pulls**: timepoint (links to the pull), due date, window, status (Upcoming, Due now, Overdue, Awaiting acceptance, Accepted, Missed; an accepted pull tested in the system reads "Accepted · meets acceptance criteria" or "Accepted · acceptance criteria not met"), tests, pulled by and a next-step link (**Record pull** or **Mark missed**).
- **Notice** "Criteria not met" (danger), when a pull of the study was accepted with the outcome "does not meet": it lists the time points and says the record of the lot is not changed by a stability result and that any hold or other action is for quality to decide.
- **Results · <condition>** (one for each storage condition that has a pull tested in the system): rows are the condition's time points by interval, each linking to its pull; columns are the tests, each headed "<name> (<code>): <acceptance criterion>". A cell shows the reviewed result with unit (green), "<result> · out of specification" (red), "<result> · open" or "In testing" while undecided, and for a time point without tests "Missed", "Not pulled yet", "Sample <reference>, tested with the lot", "External evidence" or "No test assigned". Where the criterion changed between time points, the heading names the test only and each result adds "(against <criterion>)". Time points are rows so that the table grows down the page and a phone shows every result. Empty: "No results yet."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Close study** | Study Active, you are Quality, and you did not start the study | Quality | Opens the signing page. It is the primary button only once no pull is still scheduled; until then it is a secondary button |
| **Record pull** (Next column) | Pull Scheduled and you are an Analyst | Analyst | Opens the form |
| **Mark missed** (Next column) | Pull Scheduled, today is after its window, and you are Analyst or Quality | Analyst, Quality | Opens the reason form |

Only one link shows in a pull row: Record pull takes precedence for Analysts. The server checks study and pull state and roles again.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Protocol | `Study.lot`, `Study.protocol` | Links | — | What is under study (lot number, protocol identifier) |
| Container and closure, Time zero | `Study.*` | Text, date | — | Study design |
| Lot rule basis at start | `Study.rule_basis` | Text | — | Rule set code, version and revision at the start |
| Started by | `Study.created_by` | User | — | Cannot close the study |
| Closed | `Study.closed_at` | Time | — | Time of closure; blank while Active |
| Revision | `Study.revision` | Integer | — | Raised by each change |
| Pulls table | `Pull.*`, `ProtocolTimepoint.*` | Rows | — | Timepoint (condition and label, links to the pull), Due, Window (from to to), Status, Tests (codes), Pulled by, Next. Empty: "No pulls scheduled." |

## Rules and hidden logic

- Windows are the due date plus or minus the timepoint's window days. Status is Upcoming, Due now or Overdue while Scheduled (by today's local date), then Awaiting acceptance (pulled), Accepted or Missed; the labels match the pull list's Status filter.
- Pulls are listed by due date, then identifier.
- The Results sections read only pulls with tests of their own; they judge each result against the criterion frozen on its test, not the protocol's current one.
- **Close study** is refused while testing of the study's pulls is in progress (see Close study). Once a study is closed its pulls take no more testing.
- A closed study and its pulls are immutable.

## Related pages

- [Stability studies](/stability/studies/)
- Protocol record, Lot record (from the links)
- Close study (signing page)
- [Stability pulls](/stability/pulls/)
