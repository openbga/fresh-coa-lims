---
title: New qualification
urls: laboratory:qualification_new
views: laboratory.views.qualification_new
templates: ops/form.html
models: laboratory.Qualification, core.AuditEvent
reviewed: 2026-11-19
summary: Record qualification evidence for a person and an activity: to perform the work, review results, make release decisions or issue certificates. It qualifies nobody until a different quality user approves it.
---

## Common tasks
### Record qualification evidence
1. Choose the person in [[Qualified person]] and enter the method or activity code in [[Activity]].
2. In [[Qualified for]] choose [[Performing the work]], [[Reviewing results]], [[Release decisions]] or [[Issuing certificates]]; pick supporting training in [[Training records]].
3. Enter [[Evidence reference]], [[Valid from]] and [[Valid until (inclusive)]], with [[Scope note]] or [[Evidence link]] if needed.
4. Give a [[Reason]] and select [[Record qualification]]. The new record opens, awaiting approval.
### Start from a training record
1. Open the training record and select [[Record qualification]].
2. The person, the activity and that training record are filled in. Check them, then complete the form.
### Leave without recording
1. Select [[Cancel]] to return to the Qualifications list. Nothing is saved.
## Good to know
- You cannot record evidence about yourself, and the person's account must be active. Neither of you can approve it.
- When the analyst records work, the activity they enter must match this one. Upper and lower case are ignored.
- Reviewing results is its own qualification. A method version that asks for qualified reviewers checks this one, not the qualification to perform.
- Release decisions and Issuing certificates are recorded only for a person with the quality role. A rule set that reserves those decisions names the activity.
- Only acknowledged training in the same activity can be cited. An assessment that found the person not yet competent cannot.

## Purpose

Record qualification evidence for a person and activity, for performing the work, reviewing its results, release decisions or issuing certificates, with the training it relies on. Recording does not qualify anyone.

## Who can use it

- Sign-in required. Roles: Analyst, Reviewer or Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Laboratory, Qualifications, Record qualification), title "New qualification", the introduction "Recording evidence does not qualify anyone. A different quality signer approves it; the person concerned can neither record nor approve their own.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record qualification** | Always | Analyst, Reviewer or Quality; others receive 403 | Saves and opens the new qualification record with "Qualification recorded; independent approval needed."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Qualified person | `Qualification.user` | Choice of active accounts by username (any role) | Yes | The person the evidence is about; never yourself |
| Activity | `Qualification.activity` | Text, max 120 | Yes | Method or activity code; matching is case-insensitive |
| Qualified for | `Qualification.work` | Choice: Performing the work, Reviewing results, Release decisions, Issuing certificates | Yes | Default Performing the work. Analyst entry checks only qualifications to perform; a method version that asks for qualified reviewers checks those to review. A rule set that reserves release or certificates checks Release decisions or Issuing certificates for the activity it names. Each needs its own evidence |
| Training records | `Qualification.training` | Multiple choice of training records | No | The person's acknowledged training in this activity that the evidence relies on, listed as TRN-n, trainee, activity, kind and date. Choices exclude records awaiting acknowledgement and assessments found Not yet competent. Frozen with the record |
| Scope note | `Qualification.scope_note` | Text | No | Limits of the qualification |
| Evidence reference | `Qualification.evidence_ref` | Text, max 200 | Yes | Controlled training or qualification record and revision |
| Evidence link | `Qualification.evidence_url` | http(s) URL | No | Untrusted external link |
| Valid from | `Qualification.valid_from` | Date | Yes | First valid day |
| Valid until (inclusive) | `Qualification.valid_until` | Date | Yes | Last valid day; cannot precede Valid from |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the evidence |

## Rules and hidden logic

- **Release decisions and Issuing certificates**: recorded only for a person with the quality role. Messages, in the error summary at the top of the form: "Release decisions are signed with the quality role: choose a person who holds it." and "Certificates are issued with the quality role: choose a person who holds it." The Activity is the one a rule set names under `authorization` in its policy (upper and lower case ignored).
- You cannot record evidence about yourself ("You cannot record qualification evidence for yourself."); the person's account must be active.
- "Valid until cannot precede valid from." appears on Valid until when the dates are reversed.
- **Training records**: each chosen record must be the training of the qualified person, in the same activity (upper and lower case ignored), acknowledged, and not an assessment found Not yet competent. Messages: "TRN-n is the training of another person.", "TRN-n is training in “<activity>”, not this activity.", "TRN-n is not acknowledged by the trainee yet.", "TRN-n found the trainee not yet competent." (shown on Training records). Approval checks them again.
- **Opened from a training record**: with `?training=<id>` in the address, the person, the activity and that record are filled in, only when that record can support a qualification. You can change them.
- Cancel returns to Qualifications. Instrument qualification is recorded from the equipment record instead.
- The record starts as Awaiting approval and qualifies nobody until a Quality signer who is neither you nor the qualified person approves it; the qualified person can never approve their own.
- Event `qualification.recorded`.

## Related pages

- [Qualifications](/laboratory/qualifications/)
- [Training](/laboratory/training/): the training records a qualification relies on.
