---
title: Approve limits
urls: trending:limits_approve
views: trending.views.limits_approve
templates: ops/sign.html
models: trending.Limits, trending.Chart, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-19
summary: Sign the approval of a draft limits version. Quality only, and never the person who drafted or changed it. The version in force until now stops applying and results reviewed from then on are judged by this one.
---

## Common tasks

### Approve the limits

1. Check the limits, rules and basis shown.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and approve]]. You return to the limits record.

### Find out why you cannot approve

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Approval takes effect when you sign: results whose review is signed from then on are judged by this version. Earlier results keep the version that judged them.
- The version in force until now is marked Superseded and stays in the record.
- You cannot approve a draft you drafted or changed. Another quality person does.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the approval of a draft limits version, with meaning **approved**.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- Refused with a reason, no PIN control and status 403: "TC-n vN is already approved.", "You drafted or changed these limits; another quality person approves them." or, for a computed draft, "The results of the baseline changed since the draft was saved (a result was invalidated or its lot assigned again). Save the draft again to work out its limits from them."

## Layout

- Breadcrumbs (Trends, TC-n, Limits vN, Approve limits), then a signing dialog (a plain card without JavaScript): the version and revision, what the signature means, the facts, the signer, the link "Enroll or change your signature PIN", the form, **Cancel** and **Sign and approve**. Opening the page never signs.
- **Facts**: Chart, Basis, for computed limits Baseline, Baseline results and Worked out, Center line, Standard deviation, Lower limit, Upper limit, Rules and Basis of the limits.
- **Denied**: a red "Not permitted" notice with the reason and **Back to record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Quality, independent | Signs; message "TC-n vN approved."; returns to the limits record |
| **Cancel** | Not denied | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Limits.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You approve these limits and rules for this chart. From the moment you sign, every result whose review is signed is judged by them, and the version in force before stops applying."
- **Checks at signing** (again under the chart's lock): the version is a draft; you did not draft or change it (403 with the independence reason); the baseline results are unchanged; and the rules still fit the figures. A stale record is refused with "Record changed. Reload and review before signing."
- **Effect**: one transaction ends the version in force (superseded time set, audit event `trend_limits.superseded` with "Superseded by version N: <reason>"), stores the frozen content (schema `oq.trend-limits/1`) and its hash, sets the state to Approved with the signing time, raises the revision, and writes audit event `signed.approved` and an immutable signature bound to the new revision.
- **PIN and session**: the usual refusals (no PIN, wrong PIN, lock, different username, expired session); failed attempts are audited though the approval is refused.
- **Database guards**: an approved version cannot be changed except for its superseded time.

## Related pages

- Limits record
- Chart record
- [Signature PIN](/signature-pin/)
