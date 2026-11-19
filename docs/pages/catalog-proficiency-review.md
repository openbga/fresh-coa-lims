---
title: Review outcome
urls: catalog:proficiency_review
views: catalog.proficiency_views.proficiency_review
templates: ops/sign.html
models: catalog.ProficiencyParticipation, catalog.ProficiencyResult, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-19
summary: Sign the review of a participation's outcome. Quality only, and never someone who recorded the report or results or performed a result. The signature freezes the outcome; corrective follow-up may stay open.
---

## Common tasks

### Review the outcome

1. Check the outcome, the report and the results shown.
2. Write the [[Review of the outcome]]; tick [[Corrective follow-up]] if action is needed.
3. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]], then select [[Sign review]].

### Find out why you cannot review

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- An unsatisfactory result needs corrective follow-up: the box is ticked for you and the review is refused without it.
- You cannot review a participation whose report or results you recorded or removed, or whose results you performed.
- With follow-up the participation stays open until another quality person closes it; without it, it is closed now.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the review of the outcome of an open participation, with meaning **reviewed**.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- Refused with a reason, no PIN control and status 403: "PT-n is closed: it no longer changes." (state in lower case) or, under follow-up, "PT-n is reviewed: its plan, report and results no longer change; its corrective follow-up is open.", "You recorded or performed results or the report of this participation; another quality person reviews it." or "Not ready for review." followed by what is missing.

## Layout

- Breadcrumbs (Proficiency testing, PT-n, Review outcome), then a signing dialog (a plain card without JavaScript): the participation and revision, what the signature means, the facts, the signer, the link "Enroll or change your signature PIN", the form, **Cancel** and **Sign review**. Opening the page never signs.
- **Facts**: Outcome (computed now from the results), the plan and report details as on the record, and Results (one line per result: measurand, laboratory's result, score and outcome).
- **Denied**: a red "Not permitted" notice with the reason and **Back to record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign review** | Not denied | Quality, independent | Signs; message "PT-n reviewed."; returns to the participation |
| **Cancel** | Not denied | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Review of the outcome | `review_conclusion` | Text, max 4000 | Yes | How the laboratory performed, compared with its earlier rounds, and whether anything calls for action |
| Corrective follow-up | `follow_up_required` | Checkbox | Required when a result is unsatisfactory | The participation then stays open until another quality person closes the follow-up. Ticked for you when the outcome is unsatisfactory |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You review the outcome of this participation and its results as shown. Your signature freezes them with your review; with corrective follow-up the participation stays open until another quality person closes it."
- **Checks at signing** (again under the lock): the participation is open; you recorded the report, added or removed a result, performed a result, or changed the plan once a result or the reported day was recorded (403 with the independence reason); the same problems as "Before review" on the record; "State the review of the outcome."; and "An unsatisfactory result needs corrective follow-up." when the worst outcome is unsatisfactory and follow-up is not ticked. The page refuses before any PIN is asked while the first three apply.
- **Outcome**: the worst outcome of the results (unsatisfactory, then questionable, then satisfactory); Not evaluated when no result was evaluated. It is computed at signing, not typed.
- **Stale record**: "Record changed. Reload and review before signing." when the revision changed.
- **Effect**: one transaction stores the outcome, your review, the follow-up decision, the frozen content (plan, report, results, outcome, review; schema `oq.proficiency/1`) and its hash, and the review time; the state becomes Follow-up open or Closed (closing time set); the revision rises; audit event `signed.reviewed` and an immutable signature bound to the new revision are written.
- **Follow-up may be ticked for any outcome**; the page does not restrict it to unsatisfactory results.
- **PIN and session**: the usual refusals (no PIN, wrong PIN, lock, different username, expired session); failed attempts are audited though the review is refused.
- Not enforced by this page: whether a questionable outcome needs action; the reviewer decides.

## Related pages

- Participation record
- Close follow-up
- [Signature PIN](/signature-pin/)
