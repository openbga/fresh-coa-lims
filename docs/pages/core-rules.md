---
title: Rule sets
urls: core:rules
views: core.views.rules
templates: core/rules.html
models: core.RuleSet, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

List rule set revisions (required tests, signature meanings and whether a supplier's results may stand in for tests) and create new draft revisions for independent approval.

## Who can use it

- Sign-in required. Viewing: **admin**, **quality**, **analyst**, **reviewer** or **auditor**; others receive 403.
- **Create draft**: **quality** only. Other viewers have no creation form and receive 403 for direct submissions, even when the submitted form is invalid.
- **Review and approve**: shown only to quality users for another person's draft. Admin alone grants no configuration or approval authority.

## Layout

- Title "Rule sets" and a note that presets are synthetic and approved revisions cannot be edited.
- **Revisions table**: Rule ("code vN"), Segment, Status with any approval signatures, Effective from, Policy, Action. Empty: "No rule revisions yet."
- **New revision** form with **Create draft**, for quality users only.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Review and approve** | Quality role, draft status and not its author | Quality, not the author; users without quality get 403 | Opens the signing page if eligible; authors and unavailable revisions return here with a reason |
| **Create draft** | Quality role | Quality | Creates the next version of that code as draft and reloads the page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `RuleSet.code` | Slug | Yes | Rule family; reuse a code to create its next version |
| Segment | `RuleSet.segment` | Slug | Yes | Industry segment preset label; not a legal policy |
| Policy | `RuleSet.policy` | JSON | Yes | `required_tests` (non-empty list), `review_meaning` = reviewed, `disposition_meaning` = approved, and optionally `supplier_results` = `{"own_tests": [...]}`. No other key is accepted |
| Effective from | `RuleSet.effective_from` | Date and time | Yes | Start of the effective interval |
| Effective until | `RuleSet.effective_until` | Date and time | No to save, yes to approve | End of the interval; must be after the start |
| Reason | `AuditEvent.reason` | Text | Yes | Why the revision is created |
| Version (shown in Rule) | `RuleSet.version` | Integer | — | Assigned automatically: last version of the code + 1 |
| Status | `RuleSet.status` | draft, approved | — | Only approved, effective revisions can be used by lots |
| Signature line (under Status) | `ElectronicSignature.signer_name`, `meaning`, `signed_at`, `revision` | Text, ISO date-time, integer | — | Approval signature manifestation: signer, meaning, time and bound revision |

## Rules and hidden logic

- **Policy validation**: "Unsupported or missing rule policy keys.", "At least one required test code is needed.", "This foundation supports reviewed and approved signature meanings.", "supplier_results must hold exactly own_tests: a list of the test codes the laboratory always performs itself, each listed once (the list may be empty).", "own_tests must be among required_tests; not required: water." (the codes that are not required)
- **Supplier results (optional key)**: a policy with `supplier_results` lets a result stated on a qualified supplier's certificate stand in for a test of a lot received under this rule revision. `own_tests` lists the test codes the laboratory always performs itself, for example `{"own_tests": ["identity"]}`; a supplier result is never accepted for them. An empty list keeps no test with the laboratory. `supplier_results` must be an object holding only `own_tests`; each code is text without surrounding spaces, listed once, and one of `required_tests`.
- **Without the key**: a rule revision that has no `supplier_results` allows no reliance at all. Every required test is performed by the laboratory, whatever qualification a supplier holds.
- **The key is not enough by itself**: a supplier result also needs a signed supplier qualification that covers the supplier, the material, the test and the date the lot was received, and an acceptance signed on the lot.
- **Lots keep their revision**: a lot uses the rule revision chosen when it was received. Approving a later revision with `supplier_results` does not change lots already received.
- **Own tests must be required**: every code in `own_tests` must be one of `required_tests`, compared exactly, upper and lower case included. A code that is not required, for example a misspelt one, is refused and named in the message.
- **Not enforced by this page**: the codes are not checked against any specification.
- **Interval**: "Provide a reason and a valid effective interval." when the end is not after the start.
- **Effective interval**: start inclusive, end exclusive. Approved revisions and their intervals are immutable; create and approve a non-overlapping replacement before an approved revision expires.
- **Versioning**: new revisions start as draft; approved revisions are never edited. Creation is serialized so two drafts cannot get the same version.
- **Order and paging**: the table is not explicitly sorted and not paginated. A refused submission re-renders the page with a form-level error (status 200); success reloads the page with no message.
- **Audit**: writes `rule.created` with the revision snapshot.

## Related pages

- Approve rule revision.
- [Material lots](/): lots choose an approved rule revision.
- [Suppliers](/suppliers/): supplier qualifications are recorded on each supplier record.
