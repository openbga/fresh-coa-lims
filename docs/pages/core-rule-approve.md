---
title: Approve rule revision
urls: core:rule_approve
views: core.views.rule_approve
templates: core/form.html
models: core.RuleSet, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-15
---

## Purpose

Independently review a draft rule revision and sign its approval so lots can use it.

## Who can use it

- Sign-in required. **Quality** role only; others receive 403. Admin alone gives no approval rights. Rule sets hides this action from non-quality viewers and from the draft author.
- Never the revision's author: opening the page redirects to Rule sets with "Rule authors cannot approve their own revision." and does not request a PIN. A direct signing submission is also refused with 403.

## Layout

- Title "Approve <code vN>", a signing statement (signer, meaning approved), facts: Rule policy, Author, Effective interval, Revision.
- **Retired versions** (information alert, when this revision overlaps approved versions of the same code): "This version overlaps the effective period of N approved version(s) of the rule set. Your signature also retires it/them:" then each version with "never applies: this version takes over before it starts" "stops applying on <time>" (this version's start, when it is still ahead) or "stops applying at the moment of your signature, because this version's start has already passed". When lots in quarantine are on a retired version, the line adds "N lot(s) in quarantine is/are on it: from then on its/their requirements are assigned again (before testing has started) or replaced with a signature (once it has) under this version before tests are assigned or reviewed and before disposition." The alert ends "A retired version keeps its approved policy and signature."
- The form and **Sign approval**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign approval** | Approval preconditions pass | Quality, not the author | Status becomes approved and returns to Rule sets |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Reason | `AuditEvent.reason` | Text | Yes | Approval rationale |
| Revision (hidden) | `RuleSet.revision` | Integer | Yes | Revision reviewed; the signature binds revision + 1 |
| Rule policy (shown) | `RuleSet.policy` | JSON | — | Required tests and signature meanings being approved, and `supplier_results` with its `own_tests` when the draft has it |
| Author (shown) | `RuleSet.author` | User | — | Who created the draft; cannot approve it |
| Effective interval (shown) | `RuleSet.effective_from`, `RuleSet.effective_until` | ISO date-times | — | Start inclusive, end exclusive |
| Revision line (shown) | `RuleSet.revision` | "Reviewing N; signature binds approved revision N+1" | — | Revision you review versus the revision your signature binds |

## Rules and hidden logic

- **Preconditions**: status draft ("Only draft rules can be approved."); valid policy, including the optional `supplier_results` key ("supplier_results must hold exactly own_tests: a list of the test codes the laboratory always performs itself, each listed once (the list may be empty)."; "own_tests must be among required_tests; not required: water." (the codes that are not required)); an effective end date ("An effective end date is required for approval."); no approved revision of the same code numbered after this one overlaps it ("Version N is already approved for these dates, and a version cannot retire a later one. Withdraw this draft and create a new version."). Opening an ineligible approval redirects to Rule sets with the reason, without checking the PIN or writing a review/signature. Signing repeats the checks under the record and configuration locks; a previously available page can become invalid before submission.
- **What you approve with `supplier_results`**: lots received under this revision may rely on a qualified supplier's certificate result for every test not listed under `own_tests`, each through an acceptance signed on the lot. A policy without the key allows no such reliance. Every code under `own_tests` must be one of `required_tests`. Check the listed codes against the specifications: they are compared exactly, and the software does not check them against any specification.
- **Stale page**: "Record changed. Reload and review before signing."
- **Identity and PIN**: username and PIN are re-entered for every signature; "Enter your own signing username and PIN." on mismatch; "Enroll a signature PIN first."; "Signature PIN was not accepted."; 5 consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are recorded even though the approval is refused.
- **Session**: defaults are a 15-minute idle and 8-hour absolute limit; sessions without recorded login times count as expired. On expiry the next request signs you out with "Your session expired. Sign in again to continue." The inline "Session expired. Sign in again before signing." is an extra safeguard at the moment of signing.
- **Retiring overlapped versions**: each approved revision of the same code whose remaining interval overlaps this one stops applying at the later of this revision's start and the moment of your signature, or at its own start when it had not begun (it then never applies). A revision already retired is only ever retired earlier. The list on the page is worked out when it opens; signing works it out again at the moment of the signature. The lot count is the number of lots in quarantine whose rule set is that version.
- **Effect**: one transaction sets approved, revision +1, writes `signed.approved` and an immutable signature, and for each retired revision sets when it stops applying and which revision replaced it, with audit event `rule.superseded` (reason "Superseded by the approval of <code vN>." followed by your reason). The retired revision's policy and signature are not changed. Approvals are serialized so two approvals cannot race.
- **Lots under a retired version**: a lot keeps the rule revision it was received under. Once that revision has stopped applying, the lot's rule check fails ("An approved, effective rule revision is required.") where tests are assigned or reviewed and at disposition, until quality replaces the lot's requirements, which moves the lot to the version in force (Replace lot requirements). That replacement is available only once testing has started on the lot.
- **Intervals**: a revision is effective from its start (inclusive) until its end (exclusive), or until it is retired if that is earlier. Approved intervals are never edited; lots cannot be received under an expired or retired rule.

## Related pages

- [Rule sets](/rules/)
- [Signature PIN](/signature-pin/)
