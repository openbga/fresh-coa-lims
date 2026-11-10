---
title: Assess sampling deviation
urls: sampling:deviation_assess
views: sampling.views.deviation_assess
templates: sampling/deviation_assess.html
models: sampling.DeviationReview, sampling.SamplingRecord, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-10
---

## Purpose

Independent, signed quality assessment of a deviation recorded with a sampling record: accept the sample as still acceptable evidence, or reject it. Until accepted, the deviation blocks QC disposition of the lot.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The person who sampled or recorded the record is blocked: the page opens with status 403, shows "You sampled or recorded this sample; another person must assess." and no form. No role can bypass this.
- With no deviation awaiting assessment you are redirected to the lot with the error "This record has no deviation awaiting assessment."
- The signing username you type must equal your signed-in username.

## Layout

- **Breadcrumbs**: Sampling, lot number, "Assess deviation <sample reference>". Header line: sample reference, "assessment record revision N" and the status "Awaiting quality assessment".
- **Sampling record being assessed**: Lot, Sampled (time, sampler, location), Plan, "Containers (sampled / required / total)" with container IDs, Amount, Deviation.
- **Sign deviation assessment**: statement that your signature records whether the sample remains acceptable evidence ("Accepting clears the sampling block for this sample; rejecting keeps the lot blocked until the record is corrected or the material is resampled."), "Signer:" with your name and username, and a link "Enroll or change your signature PIN".
- **Form**: Decision, Assessment, Signing username, Signature PIN. Buttons **Cancel** and **Sign assessment**.
- **Blocked state**: alert "Not permitted" with the reason and "Independent assessment cannot be bypassed by any role.", plus a button "Back to <lot number>".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign assessment** | Not blocked | Quality, not the sampler or recorder | Verifies your PIN, records the decision and signature, shows "Deviation for <sample> accepted." or "Deviation for <sample> rejected." and returns to the lot |
| **Cancel** | Form shown | Quality | Returns to the lot without signing |
| Enroll or change your signature PIN | Form shown | Signer | Opens the Signature PIN page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Decision | — | Choice: "Accept the deviation" or "Reject the deviation" | Yes | The assessment outcome; sets the status to Accepted by quality or Rejected by quality. |
| Assessment | `AuditEvent.reason` | Text, max 2000 | Yes | Help: "Why the sample is or is not still representative." |
| Signing username | — | Text, max 150 | Yes | Must match your signed-in username. |
| Signature PIN | — | Password (digits) | Yes | Never stored or logged; re-entered every time. |
| Expected revision | `DeviationReview.revision` | Hidden integer | Yes | Assessment revision shown when the page opened; signing fails if it changed. |
| Status | `DeviationReview.status` | Awaiting quality assessment, Accepted by quality, Rejected by quality | — | Shown in the header line. |

## Rules and hidden logic

- **Pending only**: only a pending assessment can be decided. The server also refuses "This deviation has already been assessed."
- **Latest record only**: "This record was corrected; assess the latest record instead." A corrected (superseded) record cannot be assessed.
- **Lot in Quarantine**: "Only deviations of quarantined lots can be assessed."
- **Independence**: sampler and recorder are refused again at signing: "You sampled or recorded this sample; another person must assess."
- **Stale record**: "Record changed. Reload and review before signing." if the assessment revision changed.
- **Signature**: meaning is "accepted" or "rejected". It records who, when and the assessment revision it binds to (the revision after the change). Audit event `signed.accepted` or `signed.rejected` with your assessment text is written in the same transaction.
- **Lot revision**: the lot's record revision increases by 1, so a disposition prepared earlier goes stale.
- **Immutable once decided**: a decided assessment cannot be changed or deleted (database trigger), nor can any assessment be deleted. A rejected deviation is resolved by correcting the record (which creates a new pending assessment if it still has a deviation) or by resampling.
- **PIN and session**: "Enroll a signature PIN first." "Signature PIN was not accepted." (5 consecutive failures lock the PIN for 15 minutes: "Signature PIN is temporarily locked.") "Enter your own signing username and PIN." "Session expired. Sign in again before signing." Failed attempts are audited even though the assessment is refused.
- **Failed submission** returns status 422 with the form and error summary.

## Related pages

- Lot requirements and sampling (record page): shows the assessment status and the **Assess deviation** button.
- Correct sampling, Record sampling.
- [Signature PIN](/signature-pin/)
- [Audit trail](/audit/)
