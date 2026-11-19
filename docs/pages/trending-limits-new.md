---
title: Draft limits
urls: trending:limits_new
views: trending.views.limits_new
templates: catalog/form.html
models: trending.Chart, trending.Limits, core.AuditEvent
reviewed: 2026-11-19
summary: Draft the next version of a chart's limits and rules, computed from a baseline period of reviewed results or entered by hand. Quality only. Another quality person approves the draft.
---

## Common tasks

### Compute limits from a baseline

1. Under [[Limits]] choose [[Computed from a baseline of results]], then enter [[Baseline from]] and [[Baseline to]].
2. Tick the [[Rules]] to apply and state the [[Basis of the limits]].
3. Enter the [[Reason for change]] and select [[Save draft]].

### Enter the limits yourself

1. Under [[Limits]] choose [[Entered]].
2. Enter [[Lower limit]], [[Upper limit]] or both. Add [[Center line]] and [[Standard deviation (σ)]] when the rules you tick need them.
3. State the [[Basis of the limits]], enter the [[Reason for change]] and select [[Save draft]].

## Good to know

- Computed limits need at least 8 results in the baseline; 20 or more are advised, and the draft says so when it has fewer.
- Results that fail their specification are left out of the baseline, so they do not widen the limits.
- A chart has one draft at a time. With a draft, this page sends you to it.
- Whoever drafts or changes a draft cannot approve it.

## Purpose

Creates the next version of a chart's limits as a draft.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.

## Layout

- **Header**: title "Draft limits · TC-n" and an introduction: "Computed limits are worked out when you save, from the results reviewed in the baseline period, leaving out results that failed their specification; at least 8 are needed and 20 or more are advised. Another quality person approves the draft with a signature, and results reviewed from then on are judged by it."
- **Record** panel: Chart and Unit.
- **Form sections**: Limits (Limits, Baseline from, Baseline to, Center line, Standard deviation (σ), Lower limit, Upper limit), Rules (Rules, Results in a run, Results in a trend), Basis (Basis of the limits), Change control (Reason for change). Buttons **Cancel** (to the chart) and **Save draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save draft** | Always | Quality | Creates the draft; message "Limits vN drafted."; opens the limits version |
| **Cancel** | Always | Quality | Returns to the chart |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Limits | `Limits.basis` | Computed from a baseline of results, Entered | Yes | Computed: center line is the mean of the baseline results and the limits are 3σ either side, σ from the average moving range divided by 1.128. Entered: your own alert limits |
| Baseline from | `baseline_from` | Date | Computed only | First day of the baseline: results whose review was signed from this day |
| Baseline to | `baseline_to` | Date | Computed only | Last day of the baseline, not after today |
| Center line | `center` | Decimal, chart's unit | No (entered) | Needed by the run, 2 of 3 and 4 of 5 rules |
| Standard deviation (σ) | `sigma` | Decimal above 0 | No (entered) | Needed by the 2 of 3 and 4 of 5 rules |
| Lower limit | `lower` | Decimal | Entered: lower, upper or both | Alert limit below |
| Upper limit | `upper` | Decimal | Entered: lower, upper or both | Alert limit above; must be above the lower limit |
| Rules | `rules` | Checkboxes | No | A result outside the limits is always applied. Others: results in a row on the same side of the center line; results in a row each higher or each lower; 2 of 3 results in a row more than 2σ from the center line; 4 of 5 more than 1σ |
| Results in a run | `run_length` | Whole number 6 to 12, default 8 | Yes | For the run rule |
| Results in a trend | `trend_length` | Whole number 5 to 10, default 6 | Yes | For the trend rule |
| Basis of the limits | `rationale` | Text | Yes | Why these limits and rules: the data, the process knowledge or the procedure they come from |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |

## Rules and hidden logic

- **One draft**: with a draft, opening this page gives "TC-n has a draft of its limits: change that draft." and goes to the draft; saving checks it again under lock.
- **Computed figures**: the baseline is the plotted results whose review was signed on the local days from Baseline from to Baseline to and before the moment the draft is saved (a result reviewed later the same day is not part of it), in review order, without results that fail their specification. Center line and σ are rounded half up to the test's reporting decimals plus 2 (6 places when the test reports exact values); the limits are center ± 3σ from those rounded figures. The baseline results are stored with the draft.
- **Baseline refusals**: "State the first day of the baseline."; "State the last day of the baseline."; "The baseline cannot end after today."; "The baseline cannot end before it starts."; fewer than 8 results ("The baseline holds N results; computed limits need at least 8. Choose a longer period or enter the limits."); results that do not vary ("The baseline results do not vary, so no limits can be computed from them. Enter the limits instead.").
- **Entered refusals**: "Enter a lower limit, an upper limit or both."; "The upper limit must be above the lower limit."; "σ must be above zero."; "The center line must lie between the limits." With Entered limits, baseline dates are discarded; with Computed limits, the figures are worked out and replace any typed.
- **Rule refusals**: "A result outside the limits is always a rule."; "The rules chosen need a center line."; "The 2 of 3 and 4 of 5 rules need σ."; "State the basis of these limits."; "Choose between 6 and 12." and "Choose between 5 and 10."; "A reason is required."
- **Version**: the next number after the highest version of the chart; revision 1; drafted by you.
- **Audit**: event `trend_limits.drafted` with the snapshot and your reason.
- Not enforced by this page: which rules suit the test; each further rule finds smaller shifts and also raises more alerts on chance variation.

## Related pages

- Chart record
- Limits record (opens after saving)
- Change draft, Approve limits
