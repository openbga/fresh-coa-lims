---
title: Authorize retest
urls: analytical:authorize
views: analytical.views.authorize
templates: analytical/sign.html, analytical/_summary.html
models: analytical.Investigation, analytical.AnalyticalTest, analytical.InvestigationEntry, quality.Sample, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-17
summary: Quality signs the authorization of one justified retest or resample within the specification's allowance. A linked open test is created for the laboratory.
---

## Common tasks
### Authorize a retest
1. Under [[Authorize]], choose [[Retest of the original sample]]. A pull or reassessment test offers only a retest of the material taken for it.
2. Write the [[Scientific justification and plan]].
3. Enter your [[Signing username]] and [[Signature PIN]], then select [[Sign and authorize]].
### Authorize a resample
1. Choose [[Resample: test a newly collected sample]] and pick the sample in [[New sample (resample only)]].
2. Write the justification, enter your username and PIN, and select [[Sign and authorize]].
## Good to know
- The retest does not replace the original result. Only a conclusion with an assignable cause can invalidate it.
- You cannot authorize retesting of a result whose data you generated.
- A laboratory assessment must be recorded first, and the specification limits how many retests and resamples are allowed.
- A resample must use a new, untested sample of this lot. A stability test can only be retested on the material pulled, and a reassessment test on the sample taken for the reassessment.
- Retests invalidated by a rejected QC batch do not count towards the allowance.

## Purpose

Quality signs authorization of one justified retest or resample within the specification's allowance. A linked Open test is created.

## Who can use it

- Sign-in required. **Quality** only; others receive 403.
- Never a user who generated the original test's data (observation recorders including superseded ones, submitter, batch QC recorders).
- Requires an enrolled signature PIN.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Card "Authorize retest · INV-n": "Your signature records authorized for INV-n at record revision N", summary (investigation facts, Allowance "X of N retests or resamples used", or "X of N retests used" for a stability test), signer, PIN link, form, **Cancel**, **Sign and authorize**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and authorize** | Always | Quality | "Retest authorized; the linked test is ready to record."; returns to the investigation |
| **Cancel** | Always | Quality | Nothing signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Authorize | `AnalyticalTest.kind` | "Retest of the original sample" or "Resample: test a newly collected sample" | Yes | Which test to create |
| New sample (resample only) | `AnalyticalTest.sample` | Choice | Only for resample | Samples of this lot that have no tests; not shown for a stability test |
| Scientific justification and plan | `InvestigationEntry.text`, `AuditEvent.reason` | Text, max 2000 | Yes | Stored as an "Authorized retest or resample" entry |
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Investigation.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **Reassessment test**: the investigation has no lot and no other sample. The form offers only the kind "Retest of the sample taken for the reassessment" and has no sample field; a resample is refused on signing: "A reassessment is tested on the sample taken for it: authorize a retest of that sample." The retest is a test of the same reassessment; the allowance reads "N of M retests used". The reassessment's revision rises by 1, never the lot's.
- **Stability test**: the investigation has no lot and no other sample. The form offers only the kind "Retest of the material that was pulled" and has no sample field; a resample is refused on signing: "A stability pull has no other sample: authorize a retest of the material that was pulled." The retest is a test of the same pull. 
- **Checked before the PIN form opens** (on opening and on submitting, with the same rules the signature uses): no PIN field is shown and no PIN checked when authorization is impossible. Redirects to the investigation with the first applicable warning: "Lot LOT-TEST-001 is no longer in quarantine."; "This investigation is closed."; "You cannot authorize retesting of your own result."; "Record the laboratory assessment first."; "The approved specification allows no further retests or resamples.". For a stability test the first check is instead that the pull takes testing: it must be pulled and not yet accepted and its study active ("Record the pull before testing it.", "This pull is accepted; its tests take no more work.", "Study … is closed; its pulls take no more testing."). Retest/resample choice and the resample sample are checked on signing.
- **Preconditions**: investigation open ("This investigation is closed."); not your own data ("You cannot authorize retesting of your own result."); laboratory assessment recorded ("Record the laboratory assessment first."); allowance left ("The approved specification allows no further retests or resamples."); lot in quarantine (or, for a stability test, the pull open for testing).
- **Allowance**: linked tests that are not Invalidated count; those invalidated by batch rejection do not. A linked test recorded as not completed before it held any observation (corrected ones included) or raw-data file does not count; one that held any does.
- **Kind**: "Choose retest or resample." if neither is posted.
- **Resample**: "Choose the newly collected sample to test."; "A resample must be a new, untested sample of this lot."
- **Effect**: a new Open test (same code and frozen specification) is linked to the investigation, and an "Authorized retest or resample" entry with your justification is added (reference "T-n retest" or "T-n resample"); the lot revision (for a stability test the pull revision, for a reassessment test the reassessment revision, never the lot) rises by 1; `signed.authorized` and an immutable signature are stored.
- **Stale page, identity, session and PIN** messages as for other signings: "Record changed. Reload and review before signing."; "Enter your own signing username and PIN."; "Session expired. Sign in again before signing."; "Signature PIN was not accepted."; five failures lock for 15 minutes.
- The retest does not replace the original; only a conclusion can invalidate it.

## Related pages

- Investigation record (return target).
- [Signature PIN](/signature-pin/)
