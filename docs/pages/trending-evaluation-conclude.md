---
title: Conclude evaluation
urls: trending:evaluation_conclude
views: trending.views.evaluation_conclude
templates: ops/sign.html
models: trending.Evaluation, trending.EvaluationAlert, impact.Assessment, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-19
summary: Sign the conclusion of an out-of-trend evaluation as Out of trend confirmed or Not confirmed. Quality only, and not whoever recorded its findings or data of a covered result. The signature freezes it.
---

## Common tasks

### Conclude the evaluation

1. Check the alerts and findings shown.
2. Choose the [[Outcome]] and write the [[Conclusion]].
3. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]], then select [[Sign and conclude]].

### Find out why you cannot conclude

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Before any PIN is asked, the page says what is missing: laboratory check, cause, lots and results affected, or an impact assessment that is not concluded.
- Out of trend confirmed also needs actions recorded. That is checked when you sign.
- You cannot conclude an evaluation whose findings you recorded, or one covering a result whose data you recorded.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the conclusion of an open evaluation, with meaning **concluded**.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- Refused with a reason, no PIN control and status 403: "OOT-n is already concluded.", "You recorded findings of this evaluation, or data of a result it covers; another quality person concludes it." or "Not ready to conclude." followed by what is missing.

## Layout

- Breadcrumbs (Trends, Evaluations, OOT-n, Conclude evaluation), then a signing dialog (a plain card without JavaScript): the evaluation and revision, what the signature means, the facts, the signer, the link "Enroll or change your signature PIN", the form, **Cancel** and **Sign and conclude**. Opening the page never signs.
- **Facts**: Chart, Alerts covered (count), Laboratory check, Cause, Lots and results affected, Actions, Quality-system reference, Impact assessment.
- **Denied**: a red "Not permitted" notice with the reason and **Back to record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and conclude** | Not denied | Quality, independent | Signs; message "OOT-n concluded."; returns to the evaluation |
| **Cancel** | Not denied | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Outcome | `Evaluation.outcome` | Out of trend confirmed, Not confirmed | Yes | Confirmed: the results show a real shift or trend, and the actions say what was done. Not confirmed: chance variation, or a laboratory error that was corrected |
| Conclusion | `conclusion` | Text | Yes | What the evaluation concludes about the results and the lots behind them |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Evaluation.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You conclude this out-of-trend evaluation with the outcome you choose. Your signature freezes the alerts it covers, the findings and your conclusion."
- **Checks at signing** (again under the chart's lock and the impact assessment's lock): the evaluation is open; you recorded no findings and no data of a covered result (403 with the independence reason); "Choose the outcome."; "State the conclusion."; the laboratory check, cause and lots and results affected are recorded; for Out of trend confirmed the actions are recorded ("Record the actions taken on a confirmed out-of-trend result."); a named impact assessment is not withdrawn and is concluded. A stale record is refused with "Record changed. Reload and review before signing."
- **Effect**: one transaction stores the outcome, the conclusion, the frozen content (schema `oq.out-of-trend/1`, with the alerts and findings) and its hash and the conclusion time, sets the state to Concluded, raises the revision, and writes audit event `signed.concluded` and an immutable signature bound to the new revision.
- **Result of concluding**: the lot notices of its alerts on the disposition page end. Nothing holds or releases a lot.
- **PIN and session**: the usual refusals (no PIN, wrong PIN, lock, different username, expired session); failed attempts are audited though the conclusion is refused.
- **Database guards**: a concluded evaluation and its alerts can no longer be changed.

## Related pages

- Evaluation record
- Record findings
- [Signature PIN](/signature-pin/)
