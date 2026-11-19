---
title: Close follow-up
urls: catalog:proficiency_close
views: catalog.proficiency_views.proficiency_close
templates: ops/sign.html
models: catalog.ProficiencyParticipation, impact.Assessment, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-19
summary: Sign that the corrective follow-up of a participation is complete and was shown to work. Quality only, and not whoever recorded the follow-up, report or results. The signature freezes it and closes the participation.
---

## Common tasks

### Close the follow-up

1. Check the outcome, the review and the follow-up shown.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and close]]. You return to the participation.

### Find out why you cannot close it

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Before any PIN is asked, the page says what is missing: cause, actions, reported results, effectiveness check, or an impact assessment that is not concluded.
- You cannot close a follow-up you recorded, nor one for a participation whose report or results you recorded or performed.
- Closing freezes the follow-up with its own hash; the review stays as signed.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the closure of the corrective follow-up of a reviewed participation, with meaning **closed**.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- Refused with a reason, no PIN control and status 403: "PT-n has no corrective follow-up open." (also for a participation that is closed or open), "You recorded its follow-up, or results or the report of this participation; another quality person closes it." or "Not ready to close." followed by what is missing.

## Layout

- Breadcrumbs (Proficiency testing, PT-n, Close follow-up), then a signing dialog (a plain card without JavaScript): the participation and revision, what the signature means, the facts, the signer, the link "Enroll or change your signature PIN", the form, **Cancel** and **Sign and close**. Opening the page never signs.
- **Facts**: Participation, Outcome, Review, Cause, Corrective actions, Results already reported, Impact assessment (label and state), Quality-system reference, Effectiveness check.
- **Denied**: a red "Not permitted" notice with the reason and **Back to record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and close** | Not denied | Quality, independent | Signs; message "Follow-up of PT-n closed."; returns to the participation |
| **Cancel** | Not denied | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `ProficiencyParticipation.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You confirm that the corrective follow-up of this participation is complete and was shown to work. Your signature freezes it and closes the participation."
- **Checks at signing** (again under the lock): follow-up is open; you did not record the follow-up, the report or a result nor perform a result (403 with the independence reason); and "Record the cause found.", "Record the corrective actions.", "Record whether results already reported could be affected.", "Record how the actions were shown to work.", and for a linked impact assessment "<label> was withdrawn: link another impact assessment or none." or "<label> is still open: conclude it before closing the follow-up." The Quality-system reference is not required.
- **Impact assessment lock**: the linked assessment is read under lock, so a withdrawal signed meanwhile waits for the closure or the closure for it.
- **Stale record**: "Record changed. Reload and review before signing."
- **Effect**: one transaction stores the frozen follow-up (schema `oq.proficiency-follow-up/1`, tied to the review's hash) and its hash, sets the state to Closed with the time, raises the revision, and writes audit event `signed.closed` and an immutable signature.
- **PIN and session**: the usual refusals (no PIN, wrong PIN, lock, different username, expired session); failed attempts are audited though the closure is refused.
- **Database guards**: a closed participation can no longer be changed.

## Related pages

- Participation record
- Record follow-up
- [Signature PIN](/signature-pin/)
