---
title: Decide conflicting requirements
urls: sampling:decide
views: sampling.views.decide
templates: sampling/decide.html, sampling/includes/conflicts.html
models: quality.Lot, sampling.LotAssignment, catalog.SpecificationRevision, core.RuleSet, core.ElectronicSignature, core.PINCredential, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

A lot assigned under several scopes has to meet the specification of each one. Where those specifications state a test differently, nothing is merged or picked and the lot is on an applicability hold. Before testing has started, this page lets quality decide, with a signature, which requirement applies for each such test; the lot's requirements are then frozen.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden. The **admin** role alone does not grant this page.
- Never a user who authored any of the lot's data: receipt details, supplier certificates, sampling records or test data, or who proposed a supplier's result for it (the same people who cannot sign its disposition). Such a user sees the page with a "Not permitted" alert, "You recorded receipt, supplier certificate, sampling or test data of this lot, or proposed a supplier's result for it. Someone who authored none of it decides which requirement applies. Independence cannot be bypassed by any role, including administrators.", a **Back to <lot>** button, no choices and no form (status 403). No PIN is requested.
- The page opens only when a decision can be considered. Otherwise you are returned to Lot requirements and sampling with one of these messages:
- "Only quarantined lots can have conflicting requirements decided."
- "Testing has started on this lot. Quality decides conflicting requirements when it replaces the lot's requirements."
- "This lot is not held for a decision on conflicting requirements." (no requirements assigned, or they are not on hold)
- "The specifications that apply to this lot no longer state a test differently. Assign the lot's requirements again."

## Layout

- **Breadcrumbs**: Sampling, lot number, Decide conflicting requirements. Title "Decide conflicting requirements ·" and the lot number. Under it: lot number, "lot record revision N" and the status Applicability hold.
- **What applies to this lot**: an explanation that every specification of the lot's scopes applies in full, that a test stated alike is one requirement, and that "A lot has to meet every specification that binds it. Choose the statement under which a passing result also meets the others, or give the reason another specification does not bind this lot. The statements not chosen stay in the record with your decision." Facts: Material and stage; Scopes; Specifications in force (a link to each version with its scope in brackets, for example "SPEC-TEST-EU v1 (eu-market)", or "None"); Additional rule sets in force (only when there are any, each as "code vN · requires <tests>"); Sampling plan (the version the decision freezes, with "· kept" when it is the one the held assignment named); Rule set (the lot's version, then "→" and the version in force with ", the version in force" when it differs); Hold recorded (who and when).
- **The requirements cannot be decided now** (only when something else also holds the lot): a "Refused" alert listing every other reason, "A decision settles only what the specifications state differently. Resolve these in the configuration first; this page then offers the decision." and **Back to <lot>**. No choices and no signing form are shown.
- **Requirements stated differently** (count of tests): one group per test, headed by its code and name, then "The statements differ in: limits." (the words used are under Rules) and the statements. When the decision can be signed, each statement is an option: "**SPEC-TEST-EU v1** (eu-market) · Assay: 99 – 101 % · rounded to 2 decimals · method M-TEST-001 v2", naming every scope that states the test this way and ending "· information only" for a statement that is not required, with the link **Open the specification** under it. Otherwise the statements are a plain list with the same wording, each starting with a link to the specification version.
- **Requirements stated one way** (count of tests; only when there are any): "These are frozen with your decision as the specifications in force state them. Nothing is chosen for them." Table: Test (code and name), Requirement (the statement, with "Information only" under one that is not required), Stated by (the scopes whose specification states it).
- **Sign decision** (when nothing refuses it): the statement of what the signature means (meaning **requirements decided**, the lot, the record revision shown, that "the requirements chosen above are frozen for the lot together with the requirements stated one way, as shown", the resulting revision N + 1, and "If a specification, a method or a rule set in force changes before you sign, signing fails and you must review again."), "Signer:" with your name and username, a link "Enroll or change your signature PIN", the form, **Cancel** and **Sign decision and freeze requirements**.
- **Foot line**: the lot number, when the page was viewed and by whom.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign decision and freeze requirements** | Nothing else holds the lot and you authored none of its data | Quality, independent of the lot's data | Freezes the lot's requirements with the chosen statements and signs; returns to the lot with "Decision signed. The requirements are frozen for this lot." |
| **Cancel** / **Back to <lot>** | Always | Any viewer of the page | Returns to Lot requirements and sampling; nothing is recorded |
| **Open the specification**, specification links | Always (under each option, in a plain list of statements, and under Specifications in force) | Any viewer of the page | Open that specification version |
| Enroll or change your signature PIN | Form shown | Signer | Opens the Signature PIN page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Statement that applies (the options of each test) | `LotAssignment.payload` (decisions), `LotAssignment.decision` (choices) | One option per statement, one choice per test | Yes | The statement that applies to this lot for the test. Nothing is preselected. The other statements are kept with the decision as not applied. |
| Reason for the decision | `LotAssignment.reason`, `AuditEvent.reason` | Text, max 2000 | Yes | Help: "Why the chosen requirements apply to this lot, for example that a result meeting them also meets the others, or the record that says another specification does not bind this lot." Stored on the new assignment, with each choice and on the signature's audit event. |
| Signing username | — | Text, max 150 | Yes | Must equal your signed-in username. |
| Signature PIN | `PINCredential` (checked, never stored) | Password (digits) | Yes | Re-entered for every signature; never shown again after an error. |
| Expected revision (hidden) | `Lot.revision` | Integer | Yes | Lot record revision of the page shown. |
| Basis (hidden) | — | Text, max 64 | Yes | Fingerprint of what the page showed: the hold being decided; the rule set version in force; every specification version that was read (with its scope and approved content), every method version and every additional rule set version; the sampling plan version; each conflicting test with its statements (scopes, specification version, name, requirement, required or not); each requirement stated one way (test, requirement, required or not); and the other hold reasons. Signing is refused if any of it changed. |
| The statements differ in | — | Words, see Rules | — | What the statements of one test differ in. Kept with the decision. |
| Specifications in force | `SpecificationRevision` | "code vN (scope)" | — | The specification version in force for each scope of the hold that has one. |
| Additional rule sets in force | `RuleSet.code`, `version`, `policy` (`required_tests`) | "code vN · requires <tests>" | — | Rule sets in force that apply beside the lot's own because they name its material, stage or scopes. |
| Sampling plan | `SamplingPlanRevision` | "code vN" | — | The sampling plan version in force for the material and stage, or the version the lot's samples were taken under; it is frozen with the decision and is part of the fingerprint. |
| Test, Requirement, Stated by | `SpecificationRevision` (approved content) | Code and name, text, scope names | — | Requirements stated one way: by one specification only, or by several alike. |
| Rule set | `Lot.rules`, `RuleSet.version` | "code vN" | — | The lot's rule set version and the version of the same rule set in force now. |
| Scopes | `LotAssignment.scopes` | Scope names | — | The scopes the hold was recorded under. |
| Hold recorded | `LotAssignment.assigned_by`, `assigned_at` | User, date and time | — | Who assigned the requirements that are on hold, and when. |

## Rules and hidden logic

- **What applies is read once**: when the page opens, and once more at the moment of signing, the versions in force are read for the material, stage and scopes of the hold: the specification of every scope, their methods, the lot's own rule set, the additional rule sets that name the material, stage or scopes, and the sampling plan (as on Assign requirements). At signing, the page's fingerprint (Basis) is checked against that one read and the same read is frozen with your choices; nothing is read a second time. The conflicts listed are those of the versions in force now, which may differ from the reasons recorded with the hold.
- **A conflict**: two specifications state the same test code and the statements differ in anything that testing freezes or in required versus information only. Statements that are the same are one option, with every scope that states it so. "The statements differ in:" uses these words: name, result type, unit, limits, expected outcome, rounding, replicates, whether each replicate must meet the limits, retests allowed, method version, required or information only.
- **Statement wording**: a statement reads like "99 – 101 % · rounded to 2 decimals · method M-TEST-001 v2". It adds "2 replicates" when more than one, "whole-number count" for a count result, "replicates judged by their mean only" when the replicates are not each held to the limits, and "up to 1 retest" (or "up to N retests") when retests are allowed. Two statements of a test that would still read the same (they differ in something without visible effect, such as the replicate rule with a single replicate or the inclusion of a limit that is not set) each end with the differing values as approved, for example "· lower limit included: no" and "· lower limit included: yes".
- **One choice per test**: every listed test needs a choice and no other test takes one: "Choose which requirement applies for each test the specifications state differently." The signature is refused, nothing is recorded and the lot stays on hold. A choice is read only when its test code and scope consist of letters, digits, - and _ (at most 80 characters); anything else counts as no choice.
- **Only conflicts are decided**: any other hold reason (a missing specification, method, rule set or sampling plan version, or a rule set whose required test no specification requires) refuses the decision. Resolve it in the configuration; the page reads what applies each time it opens and then offers the decision. A reason that only other scopes resolve needs the requirements assigned again.
- **Information only**: choosing a statement that is information only makes the test not required for this lot. When a rule set the lot is under requires that test, signing is refused: "Rule set <code> v<N> requires tests that no specification applying to the lot requires: <codes>".
- **Effect** (one transaction, or nothing): a new requirement assignment (origin "Conflict decided by quality") supersedes the hold. It freezes the chosen statements with the requirements stated one way, the specifications of every scope, the methods, the sampling plan and the rule sets. The decision kept with it records, for each test: the scope that was named, what the statements differ in, the statement that applies, the statements not applied, and who decided it, when, why and how (with a decision); and the lot revision the signature is bound to. The lot moves to the version in force of its own rule set when that is not the one it has. The lot revision increases by 1 and the signature is bound to it. The hold stays in the record.
- **Signature and audit**: signature meaning `requirements_decided` on the lot (signer, server time, bound revision, content hash). Audit events with your reason: `signed.requirements_decided` (lot) and `lot.requirements_decided` (new assignment: the hold and its reasons before; after, the scopes, each test with the scope and specification that apply, what the statements differ in, the statement that applies and those not applied, the additional rule sets, the specification and plan versions and the payload hash).
- **Independence**: the authorship check runs when the page opens and again when signing, under the lock ("You recorded receipt, supplier certificate, sampling or test data of this lot, …"). Holding several roles never waives it. Assigning requirements and signing this decision are not authorship of the lot's data.
- **Not carried by a new assignment**: assigning the lot's requirements again before testing never applies an earlier decision. While the specifications still differ, the new assignment is a hold again and is decided again here. After a signed decision only quality assigns the requirements again, and Sign lot disposition then says that the decision was set aside without a signature. Once testing has started, the decision is carried or made again on Replace lot requirements.
- **Stale page**: "The specifications or rule sets in force changed after this page was opened. Review the conflicting requirements again before signing." when anything in the fingerprint changed: a specification, method or rule set version approved or retired (whether or not it is part of a conflict), the sampling plan version, a statement, or a requirement stated one way. "Record changed. Reload and review before signing." when the lot revision changed.
- **After a refused signature**: the page that comes back (status 422) shows what applies now and carries the fingerprint and the lot revision of what it shows, not those of the page that was refused. Review it as shown and sign again; the PIN is entered again. After a stale refusal ("… changed after this page was opened …") no choice stays selected, because the statement that was chosen may be the one that changed: choose again. After any other refusal (a wrong PIN, for example) the choices stay selected. The reason and the username are kept. When nothing is stated differently any more, you are returned to Lot requirements and sampling with "The specifications that apply to this lot no longer state a test differently. Assign the lot's requirements again."
- **Identity and PIN**: "Enter your own signing username and PIN." on a mismatch (audited as `signature.identity_denied`); "Enroll a signature PIN first."; "Signature PIN was not accepted."; 5 consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are recorded (`signature.denied`) even though the decision is refused. "Session expired. Sign in again before signing." and "Sign in again before signing." for session problems.
- **Failed submission** returns status 422 with the form and the errors. A signature posted while something else also holds the lot (no form is shown then) returns status 422 as well; the PIN is not checked and nothing is recorded.
- **Not enforced by this page**: that a result meeting the chosen statement also meets the statements not chosen, or that a record exists for a specification that does not bind the lot. The software compares nothing between the statements beyond naming what differs; the reason is free text.

## Related pages

- Lot requirements and sampling (record page): the **Decide conflicting requirements** button, and the "Decided" record afterwards.
- Assign requirements to a lot: records the hold, and is used again when other scopes are needed or the specifications no longer differ.
- Replace lot requirements: where the same choice is made once testing has started.
- Specification version.
- Sign lot disposition; certificate of analysis: both show each decision with who decided it, when and why.
- [Rule sets](/rules/)
- [Signature PIN](/signature-pin/)
