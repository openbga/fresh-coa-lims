---
title: Limits record
urls: trending:limits_detail
views: trending.views.limits_detail
templates: ops/record.html
models: trending.Limits, trending.Chart, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One version of a chart's limits and rules: the figures, the rules, the baseline results and the basis, with its signature and history. Quality changes a draft here and another quality person approves it.
---

## Common tasks

### Review a draft before approving it

1. Check the center line, limits, rules, the [[Basis of the limits]] and, for computed limits, the [[Baseline results]].
2. Select [[Approve limits]] and sign with your PIN on the page that opens.

### Change a draft

1. Select [[Change draft]]. It shows to quality while the version is a draft.
2. Save the changes; the draft is worked out again from its baseline as it now stands.

### See what judged a result

1. Read the version's state: In force, Superseded (a later version applies from the time shown) or Draft.
2. Open the chart from [[Chart]] to see the results it judged.

## Good to know

- Approval is refused while the baseline results changed since the draft was saved. Save the draft again, then another quality person can approve it.
- You cannot approve a draft you drafted or changed; the page shows the reason in place of the approve button.
- An approved version never changes. To change limits, draft a new version; approving it ends this one.
- Drafts from fewer than 20 baseline results are shown as uncertain.

## Purpose

Shows one limits version of a chart, with everything that defines it and leads to changing or approving a draft.

## Who can use it

- Sign-in required. Viewing: analyst, reviewer, quality, admin or auditor; others receive 403.
- **Change draft** and **Approve limits** show to the quality role only, while the version is a draft. Approving also needs independence (see rules).

## Layout

- **Header**: "Limits vN · test name · MAT-CODE", the state (Draft, In force, Superseded), TC-n vN, "Revision N" and the action buttons.
- **Notice**, drafts only: "Baseline changed" (amber) when the baseline results are no longer those used; "Short baseline" (blue) when a computed draft has fewer than 20 results. Superseded versions show "Superseded" ("A later version applies to results reviewed from <time>.").
- **Details**: Chart (link with its title), Basis, for computed limits Baseline (first to last day), Baseline results (count) and Worked out (when the figures were worked out; results reviewed later are not part of the baseline), then Center line, Standard deviation, Lower limit, Upper limit, Rules, Basis of the limits, Drafted by, Drafted, and Approved and Superseded when they exist.
- **Baseline results** (computed limits): Test, Lot, Result, Review signed. Empty: "No baseline result."
- **Signatures** and **History**: the approval signature and the audit events of the version.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve limits** | Draft, you did not draft or change it, baseline unchanged | Quality | Opens the signed approval page; it is the primary button |
| The reason "You drafted or changed these limits; another quality person approves them." or the baseline-changed text | Draft, quality, approval refused | Quality | Shown in place of the approve button |
| **Change draft** | Draft | Quality | Opens the Change draft form |
| Chart, T-n links | Always | Any viewer | Open the chart or the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Chart | `Limits.chart` | TC-n with title | — | The chart the version belongs to |
| Basis | `basis` | Computed from a baseline of results, Entered | — | How the limits were set |
| Baseline, Baseline results, Worked out | `baseline_from`, `baseline_to`, `baseline`, `computed_at` | Dates, count, moment | — | Computed limits only |
| Center line, Standard deviation, Lower limit, Upper limit | `center`, `sigma`, `lower`, `upper` | Figures in the chart's unit | — | Empty when not stated |
| Rules | `rules`, `run_length`, `trend_length` | Rule texts | — | The rules applied, with the run and trend lengths |
| Basis of the limits | `rationale` | Text | — | Why these limits and rules |
| Drafted by, Drafted | `drafted_by`, `drafted_at` | Person, date and time | — | Who drafted it and when |
| Approved, Superseded | `approved_at`, `superseded_at` | Date and time | — | Shown when set |
| Revision | `revision` | Integer | — | Rises with each change to the draft |

## Rules and hidden logic

- **State shown**: Draft; In force (approved, not superseded); Superseded (a later version was approved).
- **Who cannot approve**: whoever drafted the version or changed it, read from the audit trail. The page shows the reason in place of the button.
- **Baseline check**: for computed limits the baseline results are read again; if they differ from those stored, approval is refused with "The results of the baseline changed since the draft was saved (a result was invalidated or its lot assigned again). Save the draft again to work out its limits from them."
- **Short baseline**: "These limits come from N results. Limits from fewer than 20 are uncertain; review them when more results are available."
- **Immutability**: once approved the figures, rules and frozen content never change; only the superseded time is set when a later version is approved. The database refuses deleting a version.

## Related pages

- Chart record
- Change draft, Approve limits
- [Trend charts](/trends/)
