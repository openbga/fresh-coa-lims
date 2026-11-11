---
title: Authorize retest
urls: analytical:authorize
views: analytical.views.authorize
templates: analytical/sign.html, analytical/_summary.html
models: analytical.Investigation, analytical.AnalyticalTest, analytical.InvestigationEntry, quality.Sample, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-10
---

## Purpose

Quality signs authorization of one justified retest or resample within the specification's allowance. A linked Open test is created.

## Who can use it

- Sign-in required. **Quality** only; others receive 403.
- Never a user who generated the original test's data (observation recorders including superseded ones, submitter, batch QC recorders).
- Requires an enrolled signature PIN.

## Layout

- Card "Authorize retest · INV-n": "Your signature records authorized for INV-n at record revision N", summary (investigation facts, Allowance "X of N retests or resamples used"), signer, PIN link, form, **Cancel**, **Sign and authorize**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and authorize** | Always | Quality | "Retest authorized; the linked test is ready to record."; returns to the investigation |
| **Cancel** | Always | Quality | Nothing signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Authorize | `AnalyticalTest.kind` | "Retest of the original sample" or "Resample: test a newly collected sample" | Yes | Which test to create |
| New sample (resample only) | `AnalyticalTest.sample` | Choice | Only for resample | Samples of this lot that have no tests |
| Scientific justification and plan | `InvestigationEntry.text`, `AuditEvent.reason` | Text, max 2000 | Yes | Stored as an "Authorized retest or resample" entry |
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Investigation.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **Checked before the PIN form opens** (on opening and on submitting, with the same rules the signature uses): no PIN field is shown and no PIN checked when authorization is impossible. Redirects to the investigation with the first applicable warning: "Lot LOT-TEST-001 is no longer in quarantine."; "This investigation is closed."; "You cannot authorize retesting of your own result."; "Record the laboratory assessment first."; "The approved specification allows no further retests or resamples.". Retest/resample choice and the resample sample are checked on signing.
- **Preconditions**: investigation open ("This investigation is closed."); not your own data ("You cannot authorize retesting of your own result."); laboratory assessment recorded ("Record the laboratory assessment first."); allowance left ("The approved specification allows no further retests or resamples."); lot in quarantine.
- **Allowance**: linked tests that are not Invalidated count; those invalidated by batch rejection do not.
- **Kind**: "Choose retest or resample." if neither is posted.
- **Resample**: "Choose the newly collected sample to test."; "A resample must be a new, untested sample of this lot."
- **Effect**: a new Open test (same code and frozen specification) is linked to the investigation, and an "Authorized retest or resample" entry with your justification is added (reference "T-n retest" or "T-n resample"); lot revision rises by 1; `signed.authorized` and an immutable signature are stored.
- **Stale page, identity, session and PIN** messages as for other signings: "Record changed. Reload and review before signing."; "Enter your own signing username and PIN."; "Session expired. Sign in again before signing."; "Signature PIN was not accepted."; five failures lock for 15 minutes.
- The retest does not replace the original; only a conclusion can invalidate it.

## Related pages

- Investigation record (return target).
- [Signature PIN](/signature-pin/)
