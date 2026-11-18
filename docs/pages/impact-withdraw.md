---
title: Withdraw impact assessment
urls: impact:withdraw
views: impact.views.assessment_withdraw
templates: ops/sign.html
models: impact.Assessment, impact.Item, stability.Hold, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: Withdraw, with a signature, an impact assessment started in error. It and its records are kept as recorded. Not possible while a hold placed through it is active. Quality only.
---

## Common tasks

### Withdraw an assessment started in error

1. Select [[Withdraw]] under More on the assessment.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]], then select [[Sign and withdraw]].

### Withdraw when a hold is active

1. Release the hold on its own page first, signed by a quality person who did not place it.
2. Or conclude the assessment instead.

## Good to know

- Withdrawal is for an assessment started in error. A real problem is concluded, not withdrawn.
- The assessment and its records stay as they were. They take no more decisions.
- The page shows [[Not permitted]] with no PIN control when a hold placed through the assessment is active.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the withdrawal of an open impact assessment with meaning **withdrawn**.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- Any quality user can withdraw, including the person who started it. Assumption: the code applies no independence rule to withdrawal.
- Refused with a reason and no PIN control (403): "This impact assessment is no longer open."; "A hold placed through this assessment is active (<holds>). Release it with its signature first, or conclude the assessment."

## Layout

- Breadcrumbs (Impact assessments, IA-n, Withdraw), then a signing dialog (a plain card without JavaScript) with the record and revision, the meaning, key facts (the same as on the conclude page), the signer, the form, **Cancel** and **Sign and withdraw**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and withdraw** | Not denied | Quality | Signs with meaning **withdrawn**; message "IA-n withdrawn; the record is kept."; returns to the record |
| **Cancel** | Always | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Assessment, Cause, Period of concern, Records | — | Display | — | What is withdrawn |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `Assessment.decision_reason`, audit reason | Text, max 2000 | Yes | Why it was started in error; shown on the record |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Assessment.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You withdraw an impact assessment started in error. It and its records are kept as recorded and take no more decisions."
- Open and no active hold are checked again under the lock when signing. A change since the page opened fails as stale: "Record changed. Reload and review before signing."
- **Effect**: state Withdrawn, time and reason stored, revision raised, audit event `signed.withdrawn` and an immutable signature. No evidence is frozen.
- **Identity, session and PIN**: as on the conclude page; failed PIN attempts are counted even though the action is rejected.
- **Database guards**: a withdrawn assessment states its reason and can no longer be changed or deleted, nor can its records.
- The assessment changes none of the records it names. A certificate is withdrawn on the certificate's own page.

## Related pages

- Impact assessment record (Cancel returns here)
- Conclude impact assessment
- Hold record (releasing a hold)
