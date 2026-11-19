---
title: Reminders
urls: planning:reminders
views: planning.views.reminders
templates: planning/reminders.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.ReagentLot, stability.Pull, stability.Study
reviewed: 2026-11-19
summary: What falls due in the coming days: calibrations that run out, stability pulls whose window opens, and released reagent and standard lots that expire. Each row opens the record.
---

## Common tasks

### See what falls due this month

1. Open the page: it lists what falls due in the next 30 days, earliest first, overdue items first.
2. Select a row to open the equipment, the stability pull or the reagent lot.

### Look further ahead or at one kind

1. Choose [[Within]] (7 to 90 days) or a [[Kind]] and select [[Apply]].

## Good to know

- Nothing is sent: open this page or the dashboard to see reminders.
- Overdue calibrations and pulls stay listed until they are resolved; expired reagent lots are not listed one by one, a notice links to them.
- A pull counts once its window opens within the days shown, even if its due date is later.
- Only equipment in service with an accepted passing calibration has a calibration reminder.

## Purpose

A dated list of laboratory work that falls due: calibrations of equipment in service, scheduled pulls of active stability studies and released reagent and standard lots reaching their last day of use, so they can be planned before they block work.

## Who can use it

- Sign-in required. The roles **analyst**, **reviewer**, **quality**, **admin** and **auditor** can open it; other accounts receive 403. The page changes nothing.

## Layout

- **Section tabs**, title, today's date and the introduction, which names the last day shown.
- A red notice when released reagent or standard lots are already past their last day of use, with **Open the lots past expiry** (shown for All reminders and Reagents and standards).
- The toolbar: **Within** and **Kind**, **Apply**, and **Clear all** when a filter differs from the default.
- The table: **Reminder** (the equipment, pull or lot, with a detail line), **Date**, **Kind**, **Status**. Empty: "Nothing falls due in this window".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| A reminder | Always | Any reader | Opens the equipment record, the stability pull or the reagent lot |
| **Open the lots past expiry** | Released lots are past expiry | Any reader | Opens Reagents and standards filtered to Released but expired |
| **Apply** / **Clear all** | Always / a filter is set | Any reader | Changes the window or kind / returns to 30 days, all kinds |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Within | — | 7, 14, 30, 60 or 90 days | No | How far ahead to look; default 30 days |
| Kind | — | Choice | No | All reminders; Calibrations; Stability pulls; Reagents and standards |
| Date | `Calibration.due_date`, `Pull.due_date`, `ReagentLot.expiry_date` | Date | — | Calibration valid until, the pull's due date, or the lot's last day of use; the list is sorted by it |
| Status | — | Status | — | Calibration: "Overdue by N days", "Due today", "Due in N days". Pull: "Overdue: window closed …", "Due now, until …", "Window opens in N days". Lot: "Expires today", "Expires in N days" |

## Rules and hidden logic

- Calibrations: equipment in service whose latest counting calibration passed and was accepted, valid until today plus the window or earlier (overdue included).
- Stability pulls: scheduled pulls of active studies whose window (due date ± the time point's window days) opens by the last day shown, including pulls due now and overdue ones, as on the Stability pulls list.
- Reagents and standards: released lots whose last day of use is from today to the last day shown. Lots already past it are counted in the notice only.
- Dates are calendar days in the deployment time zone. Twenty-five rows per page by default.
- Not enforced by this page: no message, e-mail or task is created, and nothing here stops work; the result pages check equipment, calibration and lots when they are used.

## Related pages

- [Equipment](/laboratory/equipment/), [Reagents and standards](/laboratory/reagents/) and [Stability pulls](/stability/pulls/): the records behind each reminder.
- [Work list](/planning/) and [Workload](/planning/workload/).
