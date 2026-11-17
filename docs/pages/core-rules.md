---
title: Rule sets
urls: core:rules
views: core.views.rules
templates: core/rules.html
models: core.RuleSet, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

List rule set revisions (required tests, signature meanings, whether a supplier's results may stand in for tests, and for an additional rule set where it applies) and create new draft revisions for independent approval.

## Who can use it

- Sign-in required. Viewing: **admin**, **quality**, **analyst**, **reviewer** or **auditor**; others receive 403.
- **Create draft**: **quality** only. Other viewers have no creation form and receive 403 for direct submissions, even when the submitted form is invalid.
- **Review and approve**: shown only to quality users for another person's draft. Admin alone grants no configuration or approval authority.

## Layout

- Title "Rule sets" and a note that presets are synthetic and approved revisions cannot be edited.
- A second note: "A lot is received under one rule set. A rule set whose policy states `applies_to` is an additional one: it is never chosen at receipt and applies, with the lot's own rule set, to every lot whose requirements are assigned for a material, stage and scope it names."
- **Revisions table**: Rule ("code vN"), Segment, Status with any approval signatures, Effective (start, and "to <end>" when an end is set; a retired revision adds "Superseded by version N from <time>" or "Superseded by version N before it took effect"), Policy, Action. Under the policy of an additional rule set: "Applies in addition to a lot's own rule set" followed by what it names, for example "· stages incoming · scopes eu-market". Empty: "No rule revisions yet."
- **New revision** form with **Create draft**, for quality users only, under the note "Use the same code to create the next version. When it is approved, an approved version of the same code whose effective period it overlaps stops applying from this version's start, or from the moment of approval if that is later."

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
| Policy | `RuleSet.policy` | JSON | Yes | `required_tests` (non-empty list), `review_meaning` = reviewed, `disposition_meaning` = approved, and optionally `supplier_results` = `{"own_tests": [...]}` and `applies_to` = `{"materials": [...], "stages": [...], "scopes": [...]}` (at least one of the three). No other key is accepted. Help: "Optional keys: supplier_results, with own_tests, lets a qualified supplier's result stand in for a test other than those listed. applies_to, with materials, stages and scopes (at least one, each a list of codes), makes this an additional rule set: it is not chosen when a lot is received and applies to every lot whose requirements are assigned for a material, stage and scope it names." |
| Applies in addition (shown under Policy) | `RuleSet.policy` (`applies_to`) | Material codes, stage codes, scope names | — | Where an additional rule set applies; only the dimensions it names are listed |
| Effective from | `RuleSet.effective_from` | Date and time | Yes | Start of the effective interval |
| Superseded (shown under Effective) | `RuleSet.superseded_from`, `superseded_by` | Date and time, version | — | Set when a later approved version of the code retired this one: the moment it stopped applying and the version that took over |
| Effective until | `RuleSet.effective_until` | Date and time | No to save, yes to approve | End of the interval; must be after the start |
| Reason | `AuditEvent.reason` | Text | Yes | Why the revision is created |
| Version (shown in Rule) | `RuleSet.version` | Integer | — | Assigned automatically: last version of the code + 1 |
| Status | `RuleSet.status` | draft, approved | — | Only approved, effective revisions can be used by lots |
| Signature line (under Status) | `ElectronicSignature.signer_name`, `meaning`, `signed_at`, `revision` | Text, ISO date-time, integer | — | Approval signature manifestation: signer, meaning, time and bound revision |

## Rules and hidden logic

- **Policy validation**: "Unsupported or missing rule policy keys.", "At least one required test code is needed.", "This foundation supports reviewed and approved signature meanings.", "supplier_results must hold exactly own_tests: a list of the test codes the laboratory always performs itself, each listed once (the list may be empty).", "own_tests must be among required_tests; not required: water." (the codes that are not required), "applies_to must say where the rule set applies with at least one of materials, stages and scopes, each a list of codes listed once.", "applies_to names “eu market”, which is not a scope name: use letters, digits, - and _, at most 60 characters."
- **Additional rule set (optional key `applies_to`)**: a rule set whose policy states `applies_to` is not a lot's own rule set. It is never offered on New material lot. When a lot's requirements are assigned, decided or replaced, the latest version in force of each additional rule set applies beside the lot's own rule set if every dimension it names matches: `materials` holds the lot's material code, `stages` its stage code (`incoming`, `in_process`, `finished`, `stability`) and `scopes` at least one of the scopes the lot is assigned under. A dimension left out matches every lot. Example: `"applies_to": {"scopes": ["eu-market"]}`.
- **What an additional rule set does**: each of its `required_tests` must be required by a specification that applies to the lot, otherwise the lot is held ("Rule set <code> v<N> requires tests that no specification applying to the lot requires: <codes>"). A scope it names needs no specification of its own. The version that applied is frozen with the lot's requirements; tests are assigned and the lot is dispositioned only while that version is in force. A supplier's result stands in for a test only when every rule set the lot is under allows it, so an additional rule set without `supplier_results` allows none for the lots it applies to.
- **Known codes**: every material under `applies_to` must be the code of a material ("applies_to names unknown materials: mat-x.") and every stage one of the stage codes ("applies_to names unknown stages: release. Use finished, in_process, incoming, stability."). Each list is non-empty, of text without surrounding spaces, each code once.
- **Scope names**: every scope under `applies_to` must be a scope name as it is entered for a lot: letters, digits, - and _, at most 60 characters. Any other name is refused and named in the message, because no lot could ever be assigned under it and the rule set would have no effect. Checked when the draft is created and again at approval.
- **A code keeps its kind**: every version of a code is of the same kind. "Rule set <code> applies in addition to a lot's own rule set, so every version states applies_to." when a new version of an additional rule set leaves the key out; "Rule set <code> is chosen when a lot is received, so no version states applies_to. Create an additional rule set under another code." when a new version of a lot's own rule set adds it. Checked against the latest version of the code when the draft is created, and again at approval.
- **Supplier results (optional key)**: a policy with `supplier_results` lets a result stated on a qualified supplier's certificate stand in for a test of a lot received under this rule revision. `own_tests` lists the test codes the laboratory always performs itself, for example `{"own_tests": ["identity"]}`; a supplier result is never accepted for them. An empty list keeps no test with the laboratory. `supplier_results` must be an object holding only `own_tests`; each code is text without surrounding spaces, listed once, and one of `required_tests`.
- **Without the key**: a rule revision that has no `supplier_results` allows no reliance at all. Every required test is performed by the laboratory, whatever qualification a supplier holds.
- **The key is not enough by itself**: a supplier result also needs a signed supplier qualification that covers the supplier, the material, the test and the date the lot was received, and an acceptance signed on the lot.
- **Lots keep their revision**: a lot uses the rule revision chosen when it was received. Approving a later revision with `supplier_results` does not change lots already received. Only a signed replacement of a lot's requirements during testing moves a quarantined lot to the version of its rule set in force then (Replace lot requirements). An additional rule set version likewise applies to a lot from the next time its requirements are assigned, decided or replaced, and the lot keeps the version frozen then.
- **Own tests must be required**: every code in `own_tests` must be one of `required_tests`, compared exactly, upper and lower case included. A code that is not required, for example a misspelt one, is refused and named in the message.
- **Not enforced by this page**: the test codes are not checked against any specification, and the scope names under `applies_to` are checked for their form only, not against the scopes of the specifications. A scope name that no lot is assigned under never matches.
- **Interval**: "Provide a reason and a valid effective interval." when the end is not after the start.
- **Effective interval**: start inclusive, end exclusive. Approved revisions, their policy and their intervals are never edited. Approving a later version of the same code whose interval overlaps an approved one retires the earlier one from the later of the new version's start and the moment of approval, never retroactively; a revision retired before it started never applies. A revision applies only while inside its interval and not retired.
- **Versioning**: new revisions start as draft; approved revisions are never edited. Creation is serialized so two drafts cannot get the same version.
- **Order and paging**: the table is not explicitly sorted and not paginated. A refused submission re-renders the page with a form-level error (status 200); success reloads the page with no message.
- **Audit**: writes `rule.created` with the revision snapshot.

## Related pages

- Approve rule revision.
- [Material lots](/lots/): lots choose an approved rule revision; additional rule sets are not offered there.
- [Lots](/sampling/): Lot requirements and sampling shows the additional rule sets frozen for a lot.
- [Suppliers](/suppliers/): supplier qualifications are recorded on each supplier record.
