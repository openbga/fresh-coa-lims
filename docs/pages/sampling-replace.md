---
title: Replace lot requirements
urls: sampling:replace
views: sampling.views.replace
templates: sampling/replace.html
models: quality.Lot, sampling.LotAssignment, analytical.AnalyticalTest, analytical.Investigation, quality.SupplierResultAcceptance, core.RuleSet, catalog.SpecificationRevision, core.ElectronicSignature, core.PINCredential, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

Once testing has started, a quarantined lot keeps the requirements frozen for it. This page lets quality replace them, with a signature, by the versions in force now, for example after a specification, a method or the rule set was revised. Tests whose requirement changed are kept and marked superseded; the rest carry over.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden. The **admin** role alone does not grant this page.
- Never a user who authored any of the lot's data: receipt details, supplier certificates, sampling records or test data, or who proposed a supplier's result for it (the same people who cannot sign its disposition). Such a user sees the page with a "Not permitted" alert, "You recorded receipt, supplier certificate, sampling or test data of this lot, or proposed a supplier's result for it. Someone who authored none of it replaces its requirements. Independence cannot be bypassed by any role, including administrators.", a **Back to <lot>** button and no form (status 403). No PIN is requested.
- The page opens only when a replacement can be considered. Otherwise you are returned to Lot requirements and sampling with one of these messages:
- "Only quarantined lots can have their requirements replaced."
- "Testing has not started on this lot. Assign its requirements again instead; that needs no signature before testing."
- "The lot has no assigned requirements to replace." (none assigned, or an applicability hold)
- "Requirement replacement is not configured for testing, so the lot keeps its requirements."
- "The versions frozen for this lot are the ones in force now. There is nothing to replace."

## Layout

- **Breadcrumbs**: Sampling, lot number, Replace requirements. Title "Replace requirements ·" and the lot number. Under it: lot number, "lot record revision N" and the status Quarantine.
- **Versions in force now**: an explanation that the replacement freezes the versions in force now for the same material, stage and scope, and keeps the sampling plan "because the lot's samples were taken under it". Facts: Material, stage and scope; Rule set (the lot's version, then "→" and the version in force, or "· unchanged"); Specification (the frozen version, then "→" and a link to the version in force, or "· unchanged"); Sampling plan ("code vN · kept").
- **The requirements cannot be replaced now** (only when refused): a "Refused" alert listing every reason (see Rules), "Nothing was changed. The lot keeps the requirements it has." and **Back to <lot>**. No signing form is shown.
- **Requirements** table, one row per test line of the specification in force, then lines only the frozen requirements had: Test (code and name), Change ("Unchanged", "Changed", "Added" or "Removed"), Frozen for the lot, In force now. Each side reads like "98 – 102 % · rounded to 2 decimals · method M-TEST-001 v2", with "2 replicates" when more than one, and "Information only" under a line that is not required. A missing side reads "Not in the frozen requirements" or "Not in the specification in force".
- **Effect on the lot's tests** (count of listed tests): an explanation that a test carries over only when its requirement is exactly the same (name, acceptance criterion, rounding, replicates and method version), that any other test is kept as recorded, marked superseded, takes no more work and never counts toward the disposition, and that assigning the required tests afterwards repeats a superseded test. Table: Test (link), Code, Sample, Status now ("Open", "Open · results or raw data recorded", "Awaiting review" or "Reviewed", with "· out of specification" when a result does not conform), Reportable, Effect ("Carries over", "Superseded no longer required" or "Superseded requirement changed"). Invalidated and already superseded tests are not listed.
- **Supplier results** (warning, when a supplier's result is proposed or accepted in place of a test of the lot): names each test code and acceptance, and says it "stops standing and blocks the disposition until it is withdrawn on the lot record. It can then be proposed again against the new requirements."
- **Sign replacement** (when nothing refuses it): the statement of what the signature means (meaning **requirements replaced**, the lot, the record revision shown, how many tests are superseded and how many carry over, the resulting revision N + 1), "Signer:" with your name and username, a link "Enroll or change your signature PIN", the form, **Cancel** and **Sign and replace requirements**.
- **Foot line**: the lot number, when the page was viewed and by whom.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and replace requirements** | No refusal and you authored none of the lot's data | Quality, independent of the lot's data | Replaces the requirements and signs; returns to the lot with "Requirements replaced and signed. Assign the required tests again for the tests that were superseded." or, when none was superseded, "Requirements replaced and signed. Every test carried over." |
| **Cancel** / **Back to <lot>** | Always | Any viewer of the page | Returns to Lot requirements and sampling; nothing is recorded |
| Test links | Tests listed | Any viewer of the page | Open the test record |
| Specification link | The specification in force differs | Any viewer of the page | Opens that specification version |
| Enroll or change your signature PIN | Form shown | Signer | Opens the Signature PIN page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for the replacement | `LotAssignment.reason`, `AuditEvent.reason` | Text, max 2000 | Yes | Help: "Why this lot is tested against the versions now in force, for example the change record that requires it." Stored on the new assignment, the signature's audit event and every test it supersedes. |
| Signing username | — | Text, max 150 | Yes | Must equal your signed-in username. |
| Signature PIN | `PINCredential` (checked, never stored) | Password (digits) | Yes | Re-entered for every signature; never shown again after an error. |
| Expected revision (hidden) | `Lot.revision` | Integer | Yes | Lot record revision shown when the page opened. |
| Basis (hidden) | — | Text, max 64 | Yes | Fingerprint of what the page showed: the assignment replaced, the rule set version, the specification content and requirement lines in force, each listed test with its status and effect, and the supplier results. Signing is refused if any of it changed. |
| Rule set | `Lot.rules`, `RuleSet.version` | "code vN" | — | The lot's rule set version and the approved version of the same rule set in force now. |
| Specification, Sampling plan | `LotAssignment.payload` | "code vN" | — | Frozen versions and the specification version in force now; the plan is kept. |
| Change | — | Unchanged, Changed, Added, Removed | — | Comparison of each requirement line, frozen and in force. |
| Effect | `AnalyticalTest.state` | Carries over, Superseded | — | What signing does to each test still open, awaiting review or reviewed. |

## Rules and hidden logic

- **What is resolved**: at the moment of signing, the approved version in force of the lot's own rule set (the highest version that applies now), and the specification and method versions in force for the material, stage and scope of the current requirements. The sampling plan version is kept. Nothing is merged or guessed.
- **Refusals** (nothing is recorded and no hold is placed on the lot; each one listed):
- "Rule set <code> has no approved version effective now."
- the hold reasons of Assign requirements other than the sampling plan ones, for example "Specification <code> has no approved version effective now.", "Method <code> has no approved version effective now." or "Rule set requires tests missing from the specification: <codes>"
- "Requirement for <code> is held: …" or "No required tests in the new requirements." when testing could not execute the new requirements
- "<investigation> is open on this lot (<trigger>). Conclude it first: a result is investigated against the requirement it was tested under."
- "<test> <code> holds results or raw-data files that were not submitted, and its requirement would change. Complete and submit it first, so that what was recorded is evaluated against the requirement it was tested under."
- **Carry over or supersede**: a test carries over when its stored requirement has the same content as the new one; the document it came from does not matter. A test of a code whose requirement changed, or that is no longer required (removed or information only), becomes Superseded. A superseded test and everything recorded on it are kept unchanged; it takes no more work, answers no requirement and never counts toward the disposition. Tests already invalidated or superseded are not touched.
- **After signing**: the lot gate reports a sample whose test was superseded ("Sample <ref> has no <code> test under the lot's current requirements: the earlier test was superseded when they were replaced. Assign the required tests."). **Assign required tests** on Lot testing then creates a linked repeat (kind "Repeat under replaced requirements") on the sample of the superseded test. A requirement line that was added gets an original test.
- **Supplier results**: every supplier's result proposed or accepted for the lot stops standing after a replacement, also for a requirement line that is unchanged, and blocks the disposition until it is withdrawn on the lot record.
- **Effect** (one transaction, or nothing): superseded tests change state and their revision increases by 1; a new requirement assignment (origin "Replaced during testing") supersedes the current one and keeps the evidence of what changed, which tests carried over or were superseded, the supplier results and the lot revision the signature is bound to; the lot moves to the rule set version in force; the lot revision increases by 1 and the signature is bound to it. Earlier assignments and every test stay in the record.
- **Signature and audit**: signature meaning `requirements_replaced` on the lot (signer, server time, bound revision, content hash). Audit events with your reason: `signed.requirements_replaced` (lot), `lot.requirements_replaced` (new assignment: requirements, rule set and specification before and after, lines changed, tests superseded and carried over) and `test.superseded` for each superseded test (state before, why, result, requirement hash).
- **Independence**: the authorship check runs when the page opens and again when signing, under the locks ("You recorded receipt, supplier certificate, sampling or test data of this lot, …"). Holding several roles never waives it. Assigning requirements or tests is not authorship.
- **Stale page**: the server works out the replacement again when you sign. "The versions in force or the lot's tests changed after this page was opened. Review the replacement again before signing." when what you saw changed (a version approved or retired, a test assigned, submitted or reviewed, a supplier result proposed or withdrawn); "Record changed. Reload and review before signing." when the lot revision changed; "The lot's tests changed after the replacement was prepared. Reload and review it again." when a test was added while signing. Any of the refusals above found at that moment is also reported. Open the page again to review.
- **Identity and PIN**: "Enter your own signing username and PIN." on a mismatch (audited as `signature.identity_denied`); "Enroll a signature PIN first."; "Signature PIN was not accepted."; 5 consecutive failures lock the PIN for 15 minutes ("Signature PIN is temporarily locked."). Failures are recorded (`signature.denied`) even though the replacement is refused. "Session expired. Sign in again before signing." and "Sign in again before signing." for session problems.
- **Failed submission** returns status 422 with the form and the errors; the reason and username are kept, the PIN is not.
- **Not enforced by this page**: whether a change record exists for the replacement; the reason is free text.

## Related pages

- Lot requirements and sampling (record page): the **Replace requirements** button, and the "Replaced" record afterwards.
- Lot testing: assign the required tests again to repeat superseded tests.
- Test record; Specification version; Lot record (supplier results).
- Sign lot disposition: shows each replacement as a notice.
- [Rule sets](/rules/)
- [Signature PIN](/signature-pin/)
