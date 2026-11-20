---
title: Shelf-life evaluation record
urls: stability:shelf_life_detail
views: stability.shelf_life_views.shelf_life_detail
templates: stability/shelf_life_detail.html
models: stability.ShelfLifeEvaluation, stability.ShelfLifeStudy, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One shelf-life evaluation: the results over time with their fitted line and confidence limit, the estimated shelf life, the poolability tests and the studies behind it. Quality changes, withdraws or concludes a draft.
---

## Common tasks

### Read the estimate

1. Read [[Estimated shelf life]] and [[Data cover]] in the details.
2. Check the chart, [[Poolability of the studies]] and [[Studies]] to see how it was worked out.
3. Read [[Results]] and [[Not used]] to see which results counted and which did not.

### Change the studies or the expected change

1. Select [[Change]] on a draft. Quality users see it.

### Conclude the evaluation

1. Select [[Conclude]] on a draft. It shows to quality users.
2. If it shows a reason instead, read why you cannot conclude yet.

### Withdraw a draft

1. Select [[Withdraw]] under More.

## Good to know

- A draft is read from the record as it stands now. A concluded evaluation is shown as signed, from the results and figures its signature froze.
- A result is used only from an accepted pull tested in the system. Others are listed under Not used, with the reason.
- Time on stability is the time point's interval in days divided by 365.25 / 12.
- The estimate is a statistical figure for the quality person to judge. The laboratory decides the shelf life it records.

## Purpose

Shows what an evaluation uses and what the statistics make of it, and is where a draft is changed, withdrawn or concluded.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; others receive 403.
- **Change**, **Withdraw** and **Conclude** are shown only to Quality, and only while the evaluation is a draft. A draft you cannot conclude shows the reason in place of **Conclude**. The server checks again.
- Admin is read-only here.

## Layout

- **Header**: breadcrumbs, title (test, protocol, storage condition), identifier "SLE-n", state, **Change**, **Conclude** and **Withdraw** (under More), and "Record revision".
- **Notice** (drafts only): "Before concluding" when fewer than three studies are fitted ("ICH Q1E evaluates the data of at least three batches") or the estimate is beyond the months the data cover; "Withdrawn" for a withdrawn draft.
- **Details**: Protocol, Container closure, Storage condition, Test, Acceptance criterion (with the specification code and version), Expected change, Estimated shelf life, Data cover, then for a concluded evaluation Outcome, Conclusion and Concluded, then Purpose and Drafted by.
- **Results over time**: the chart. Each study has its own marker shape, named in the key. Results outside the acceptance criterion are filled in the danger tone. Solid mean line of each fit, dashed confidence limit (one-sided or two-sided 95 %), the acceptance criterion, a "Data to N months" line and an "Estimate N months" line. Without results it reads "No result yet".
- **Poolability of the studies**: F tests for equal slopes and for equal intercepts given equal slopes, with F, degrees of freedom, p and the verdict at 0.25.
- **Studies**: Study, Results, own slope, Slope used, Intercept used and "Limit meets the criterion". A study with fewer than three time points shows why it is not fitted.
- **Results**: Study, Time point, Months, Condition, Result, Test (links to the test).
- **Not used**: Study, Pull, Why. Shown only when something was left out.
- **Signatures** and **History**: signer, meaning, revision and hash; audit events.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Change** | Draft | Quality | Opens the change form |
| **Conclude** | Draft and you may conclude | Quality | Opens the signing page |
| **Withdraw** (More) | Draft | Quality | Opens the withdrawal form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Estimated shelf life | worked out | Months, rounded down to 0.1 | — | Earliest time the confidence limit meets the criterion, with the model, t and degrees of freedom. "Not reached within 120 months" when it does not. "Not worked out" with the reason when no study has three time points |
| Data cover | worked out | Months | — | Longest time on stability of a result used |
| Acceptance criterion | `lower_limit`, `upper_limit`, `unit` | Limits | — | Kept from the specification version in force when drafted |
| Expected change | `direction` | Choice | — | Which confidence limit is compared |
| Outcome | `outcome`, `shelf_life_months` | Choice | — | "Shelf life supported" or "No shelf life supported", with the months recorded |
| Conclusion | `conclusion` | Text | — | The basis recorded when signing |
| Purpose, Drafted by | `purpose`, `drafted_by` | Text, user | — | Why and by whom |

## Rules and hidden logic

- **Results read**: for each study, accepted pulls tested in the system at the storage condition, plus the study's time-zero pull when that condition has none (an accepted one first). Results are numeric or count, in the evaluation's unit, with a reportable value. A result an investigation invalidated is left out; a confirmed failure stays in.
- **Not used**: a missed pull, a pull not yet accepted, a pull accepted on a linked sample or external evidence, a result in another unit or without a reportable value.
- **Fitting**: a study with results at fewer than three time points is listed, not fitted. Each study is fitted by least squares; poolability follows ICH Q1E at the 0.25 level. Pooled gives one line; a common slope gives each study its own intercept; otherwise each has its own line and the shortest estimate applies. The separate model uses the mean square error pooled from all studies; the common-slope model uses its own, which ICH Q1E does not name.
- **Product choices**: the intercept test uses the mean square error of the common-slope model (ICH Q1E does not name it); time comes from the protocol interval; the search stops at 120 months.
- **Concluded**: the details and tables show the figures the conclusion froze (schema `oq.shelf-life/1`), and which studies were fitted then; the chart is drawn again from the frozen results. If this release's statistics would give other figures, an "As signed" notice says so. The evaluation never changes after conclusion or withdrawal; database guards refuse it.
- **Audit**: `shelf_life.drafted`, `shelf_life.changed`, `shelf_life.withdrawn` and the signature meaning "concluded".

## Related pages

- [Shelf-life evaluations](/stability/shelf-life/)
- Change, Withdraw and Conclude evaluation
- Study record, Test record, Pull record (from the links)
