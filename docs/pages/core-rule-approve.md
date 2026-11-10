---
title: Approve rule revision
urls: core:rule_approve
views: core.views.rule_approve
templates: core/form.html
models: core.RuleSet, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-10
---

## Purpose

Independently review a draft rule revision and sign its approval so lots can use it.

## Who can use it

- Sign-in required. **Quality** role only; others receive 403.
- Never the revision's author: the page still opens for the author, but signing is refused with a 403 page ("Rule authors cannot approve their own revision."), after the PIN check.

## Layout

- Title "Approve <code vN>", a signing statement (signer, meaning approved), facts: Rule policy, Author, Effective interval, Revision, then the form and **Sign approval**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign approval** | Always | Quality, not the author | Status becomes approved and returns to Rule sets |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Reason | `AuditEvent.reason` | Text | Yes | Approval rationale |
| Revision (hidden) | `RuleSet.revision` | Integer | Yes | Revision reviewed; the signature binds revision + 1 |
| Rule policy (shown) | `RuleSet.policy` | JSON | — | Required tests and signature meanings being approved |
| Author (shown) | `RuleSet.author` | User | — | Who created the draft; cannot approve it |
| Effective interval (shown) | `RuleSet.effective_from`, `RuleSet.effective_until` | ISO date-times | — | Start inclusive, end exclusive |
| Revision line (shown) | `RuleSet.revision` | "Reviewing N; signature binds approved revision N+1" | — | Revision you review versus the revision your signature binds |

## Rules and hidden logic

- **Preconditions** (checked at signing, not when the page opens): status draft ("Only draft rules can be approved." shown on the form); valid policy; an effective end date ("An effective end date is required for approval."); no overlap with an approved revision of the same code ("Effective dates overlap an approved revision.").
- **Stale page**: "Record changed. Reload and review before signing."
- **Identity and PIN**: username and PIN are re-entered for every signature; "Enter your own signing username and PIN." on mismatch; "Enroll a signature PIN first."; "Signature PIN was not accepted."; 5 consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are recorded even though the approval is refused.
- **Session**: defaults are a 15-minute idle and 8-hour absolute limit; sessions without recorded login times count as expired. On expiry the next request signs you out with "Your session expired. Sign in again to continue." The inline "Session expired. Sign in again before signing." is an extra safeguard at the moment of signing.
- **Effect**: one transaction sets approved, revision +1, writes `signed.approved` and an immutable signature. Approvals are serialized so overlapping revisions cannot both be approved.
- **Intervals**: a revision is effective from its start (inclusive) until its end (exclusive). Approved intervals cannot be changed, so approve a non-overlapping replacement revision before the current one expires; lots cannot be received under an expired rule.

## Related pages

- [Rule sets](/rules/)
- [Signature PIN](/signature-pin/)
