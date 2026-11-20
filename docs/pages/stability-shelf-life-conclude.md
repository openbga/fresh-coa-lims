---
title: Conclude evaluation
urls: stability:shelf_life_conclude
views: stability.shelf_life_views.shelf_life_conclude
templates: ops/sign.html
models: stability.ShelfLifeEvaluation, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-19
summary: Sign the conclusion of a shelf-life evaluation and record the shelf life it supports, no longer than the estimate. Quality only, and not whoever drafted or changed it or produced data of a result it uses.
---

## Common tasks

### Conclude the evaluation

1. Check the figures shown, especially [[Estimated shelf life]] and [[Longest you can record]].
2. Choose the [[Outcome]], enter the [[Shelf life (months)]] and write the [[Conclusion]].
3. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]], then select [[Sign and conclude]].

### Find out why you cannot conclude

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- The most you can record is the estimate rounded down to whole months, or 120 when the limit never reaches the criterion.
- If a result changed since you opened this page, the signature is refused. Reload and review the figures.
- You cannot conclude an evaluation you drafted or changed, or one that uses a result whose data you produced. Reviewing a result or accepting a pull does not count.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the conclusion of a draft, with meaning **concluded**. The signature freezes the results, the figures worked out from them and the shelf life recorded. The laboratory decides what shelf life to record; the system records it.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- Refused with a reason, no PIN control and status 403: "SLE-n is concluded." (or withdrawn); "You drafted or changed this evaluation, or produced data of a result it uses; another quality person concludes it."; or "Not ready to conclude." followed by what is missing.

## Layout

- Breadcrumbs, then a signing dialog: the evaluation and revision, what the signature means, the facts, the signer, the link "Enroll or change your signature PIN", the form, **Cancel** and **Sign and conclude**. Opening the page never signs.
- **Facts**: Test (with condition), Acceptance criterion, Studies fitted, Estimated shelf life, Longest you can record ("None: no shelf life is supported" when zero; the estimate rounded down to whole months, or 120 months, the search horizon, when the limit never meets the criterion), Data cover, and the "Before concluding" warning of the record page when fewer than three studies are fitted or the estimate lies beyond the data.
- **Denied**: a red "Not permitted" notice with the reason and **Back to record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and conclude** | Not denied | Quality, independent | Signs; message "SLE-n concluded."; returns to the record |
| **Cancel** | Not denied | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Outcome | `ShelfLifeEvaluation.outcome` | Shelf life supported, No shelf life supported | Yes | Supported: the shelf life you record is no longer than the estimate. None supported: the data do not support one yet, or at all |
| Shelf life (months) | `shelf_life_months` | Whole months, 1 to 999 | When supported | At most the estimate rounded down. Leave empty when none is supported |
| Conclusion | `conclusion` | Text, max 4000 | Yes | What the data support and on what basis: model, batches, any extrapolation and the supporting data |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision, data hash (hidden) | `revision`, digest | Integer, text | Yes | What the page showed when it opened |

## Rules and hidden logic

- Meaning text: "You conclude what shelf life these data support. Your signature freezes the results, the figures worked out from them and the shelf life you record."
- **Checks at signing** (again under the lock of the studies): the evaluation is a draft; you are not an author; the data digest equals the one the page carried ("The results or the evaluation changed since this page was opened. Reload it and review the figures before signing."); "Choose the outcome."; "State the conclusion and its basis."; for Supported, "State the shelf life in whole months." and not above the longest ("The data support at most N months: the estimate rounded down to whole months."); for none supported, "Leave the shelf life empty when the data support none."; when the limit meets the criterion at time zero, the data support no shelf life; when the estimate is under one month, "The estimate is under one month, so the data support no whole month of shelf life." Without a fit, "Not ready to conclude."
- **Extrapolation**: the page does not stop a shelf life beyond the data cover; the conclusion should state its basis. Not enforced by this page: any limit on extrapolation.
- **Effect**: one transaction stores the outcome, the months, the conclusion, the frozen content (schema `oq.shelf-life/1`) and its hash and the time, sets Concluded, raises the revision, and writes an immutable signature with meaning "concluded" bound to the new revision.
- **Independence**: the drafter, anyone who changed the draft and anyone who produced data of a result it uses cannot conclude.
- **PIN and session**: the usual refusals; failed attempts are audited though the conclusion is refused.
- **Database guards**: a concluded evaluation never changes.

## Related pages

- Evaluation record
- [Signature PIN](/signature-pin/)
