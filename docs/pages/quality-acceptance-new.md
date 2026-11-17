---
title: Propose supplier result in place of a test
urls: quality:acceptance_new
views: quality.acceptance_views.acceptance_new
templates: catalog/form.html
models: quality.SupplierResultAcceptance, quality.SupplierCertificateResult, quality.SupplierCertificate, quality.Lot, quality.LotReceipt, suppliers.Supplier, suppliers.SupplierQualification, core.RuleSet, core.AuditEvent
reviewed: 2026-11-17
summary: Propose that one result on a supplier's certificate stands in for the laboratory's test of that requirement. A proposal answers nothing until a reviewer signs the acceptance.
---

## Common tasks
### Propose a supplier result
1. Check every fact in the [[Record]] card. It is what the proposal relies on and freezes.
2. Explain why in [[Reason for relying on the supplier's result]].
3. Select [[Propose supplier result]]. The new record opens, awaiting acceptance by a reviewer.
### Submit after what it relies on changed
1. If the page says what the proposal would rely on changed, review the [[Record]] card as shown now, then submit again.
## Good to know
- A proposal blocks the lot's QC disposition until a reviewer accepts it or it is withdrawn.
- Every rule set the lot is under must allow it, and a signed qualification must cover the supplier, material, test and date received.
- Proposing makes you an author of the lot's data: you cannot accept it or sign the lot's disposition, also after a withdrawal.
- Only one proposal or acceptance stands for a requirement of a lot at a time.
- Once the laboratory has started testing the requirement, a supplier result cannot stand in for it.

## Purpose

Proposes that one result stated on a supplier's certificate stands in for the laboratory's own test of that requirement of the lot. A proposal answers nothing: a reviewer signs the acceptance.

## Who can use it

- Sign-in required. **analyst** role only; others receive 403 Forbidden. The supplier certificate record shows **Propose in place of a test** only to analysts, and only for a result that can be proposed.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the analyst role acts with that role only, with no exception to the independence rules.
- A result that cannot be proposed shows no form: you are redirected to the supplier certificate record with the reason (see Rules).

## Layout

- **Breadcrumbs**: Material lots, lot number, "Supplier certificate" with the certificate number (link to the record), Propose supplier result in place of a test.
- **Intro**: "A proposal answers nothing by itself. A reviewer who recorded none of this certificate checks it against the certificate and signs the acceptance. The supplier's stated result then answers this requirement of the lot in place of a laboratory test. It stays the supplier's result and is named as such on the certificate of analysis."
- **Record card**: everything the proposal relies on, as it will be frozen: Lot, Test, Specification, Requirement, Supplier's result, Method stated, Limits stated, Supplier certificate, Lot number on the certificate, Where the certificate is kept, Supplier, Lot received, Supplier qualification and Rule set, then one Additional rule set line for each additional rule set applied by the lot's requirements.
- **Form section**: Change control, with the reason.
- **Buttons**: **Cancel** (to the supplier certificate record) and **Propose supplier result**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Propose supplier result** | Always | Analyst | Adds the proposal as Awaiting acceptance, shows "Supplier result proposed in place of a test; a reviewer accepts it." and opens the supplier result acceptance record |
| **Cancel** | Always | Analyst | Returns to the supplier certificate record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for relying on the supplier's result | `SupplierResultAcceptance.reason` | Text, max 2000 | Yes | Why the supplier's result is relied on; shown on the acceptance record and stored in the audit event |
| Basis (hidden) | — | Hash | Yes | Identifies everything the Record card showed when the page opened. See Stale page. |
| Lot | `Lot.number`, `Lot.material` | Text | — | "number · material" |
| Test / Specification / Requirement | `SupplierCertificateResult.requirement` | Text | — | Test name and code, the acceptance criterion and the source of the requirement the result was compared with |
| Supplier's result | `SupplierCertificateResult.value_text`, `stated_text` | Text | — | As recorded, with the unit (for example "99.60 %"), or the outcome with the certificate's words ("Conforms (stated as: Complies)") |
| Method stated / Limits stated | `SupplierCertificateResult.method`, `limits` | Text | — | As recorded from the certificate; both must be stated |
| Supplier certificate / Lot number on the certificate / Where the certificate is kept | `SupplierCertificate.number`, `issued_on`, `issued_by`, `stated_lot`, `document_ref` | Text | — | "NUMBER dated DATE, issued by ISSUER", and the record's other details |
| Supplier / Lot received | `LotReceipt.supplier`, `received_on` | Text, date | — | From the lot's current receipt details: "code · name, location" and the date received |
| Supplier qualification | `SupplierQualification` (SQ-n), `evidence_ref`, `valid_from`, `valid_until` | Text | — | The qualification relied on: "SQ-n · evidence reference · valid START to END" |
| Rule set | `Lot.rules` → `RuleSet.code`, `version`, `policy` | Text | — | "code version N · the laboratory always performs: identity" ("no test named" when the rule set keeps none) |
| Additional rule set | `LotAssignment.payload` (additional rules) → `RuleSet.code`, `version`, `policy` | Text | — | One line for each additional rule set version frozen with the lot's current requirements, in the same form as Rule set. Each of them allowed the reliance too. Not shown when the lot has none |

## Rules and hidden logic

- **Three conditions**: every rule set the lot is under allows reliance for the test, a signed supplier qualification covers the supplier, the material, the test and the date the lot was received, and the acceptance is signed by a reviewer. This page checks the first two and the lot's records, in the order given below; the first refusal is the one shown.
- **First**: "A supplier's result is already proposed or accepted for this requirement of the lot. Withdraw it before proposing another."; "Supplier results are accepted only while the lot is in quarantine."
- **Rule set**, before the lot's records, so a test the rule set keeps with the laboratory always says so: the lot's rule set must still be approved and effective ("An approved, effective rule revision is required."). A rule set without `supplier_results` refuses: "Rule set rules-syn v1 does not allow a supplier's result to stand in for a test. Every required test is performed by the laboratory." A test listed under its `own_tests` refuses: "Rule set rules-syn v1 requires the laboratory to perform identity itself; a supplier's result cannot stand in for it."
- **Additional rule sets**: the same three checks then run for each additional rule set version frozen with the lot's current requirements (rule sets whose policy states `applies_to`), in the order they were frozen. Every one of them must be approved and effective and must allow the reliance; the message names the rule set that refuses. An additional rule set without `supplier_results` therefore allows no reliance for this lot, and a version retired since refuses with "An approved, effective rule revision is required." until the lot's requirements are assigned again or replaced.
- **Checks on the lot's records**, each with its message: "This certificate record was corrected or withdrawn. Only the current record of a supplier certificate can be relied on."; "Only a lot received from a supplier can rely on a supplier's result."; "The result was compared with a requirement that is not the lot's current one. Correct the certificate record so that it is compared with the current requirements first."; "The supplier's stated result does not meet the specification, so it cannot stand in for a test. Test the requirement in the laboratory."; "The certificate record states no method or no limits for this result. A result is relied on only when the certificate states how it was obtained and against which limits."; "Supplier certificate COA-TEST-002 states a result for assay that does not meet the specification. Correct or withdraw that record if it is wrong, or test the requirement in the laboratory."; "T-12 assay already holds laboratory work (a result, a raw-data file, a QC batch or a decision). A supplier's result cannot stand in for a requirement the laboratory has started testing."
- **Contradicting certificate**: another supplier certificate of the lot whose current record is not withdrawn and states, for the same test, a result that does not meet the specification refuses the proposal. A withdrawn certificate does not count.
- **Testing started**: a test of this requirement on any sample of the lot counts as started when it is no longer Open, is in a QC batch, or holds an observation (a corrected or reported one included) or a raw-data file. An Open test without any of these does not stop the proposal.
- **Supplier qualification**: the supplier named on the lot's current receipt details needs a qualification for the material of the lot's requirement assignment that is signed, not revoked, names the test and whose dates include the date the lot was received, both days inclusive. When several cover it, the one recorded last is relied on. Refusals: "sup-syn-001 is not qualified for api-syn-001."; "The qualification of sup-syn-001 for api-syn-001 does not cover assay."; "No qualification of sup-syn-001 for assay of api-syn-001 covers a lot received on 2026-11-02."; "The qualification of sup-syn-001 for assay of api-syn-001 that covers 2026-11-02 is still awaiting its signature."; "The qualification of sup-syn-001 for assay of api-syn-001 that covered 2026-11-02 was revoked; a revoked qualification is relied on no further."
- **On opening**: a refusal sends you back to the supplier certificate record with the message. Nothing is saved or audited.
- **Stale page**: the hidden Basis is a hash of what the Record card showed. After every other check, the server builds what the proposal would freeze now; if it differs (for example a newer qualification was signed, or the date received was corrected), nothing is saved: "What this proposal would rely on changed after the page was opened. Review what is shown now, then submit again." A submission without the Basis is refused the same way. A proposal never freezes evidence you were not shown.
- **On submitting**: every check runs again under the lot lock. A refusal is shown on the form with status 422 and nothing is saved. The page is shown again with what a proposal would rely on now and the Basis of that, so after the review you submit again. A refusal by the rule set or by the supplier's qualification is audited as `supplier_result.refused` on the lot, on your account, with the test, the certificate number, what refused, the reasons and the reason you entered. Other refusals are not audited.
- **Effect**: one proposal (SRA-n) is added with you as proposer and the state Awaiting acceptance. Everything on the Record card is frozen on it, together with who recorded the certificate. The lot's record revision increases by 1. Audit event `supplier_result.proposed` stores the frozen evidence with your reason. A disposition signing page opened earlier then fails as stale.
- **Until it is accepted**: the proposal blocks the lot's QC disposition ("SRA-1: the supplier's result for assay awaits acceptance by a reviewer."). A test of this requirement takes no observation, no contract laboratory result, no raw-data file and no QC batch, and **Assign required tests** creates no test for it.
- **A proposal that can no longer be signed**: when its qualification is revoked, or the lot's rule set or an additional rule set the lot is under is no longer approved and effective, before a reviewer accepts it, the proposal no longer stands. It then blocks with "SRA-1: the proposal for assay no longer stands: SQ-1 was revoked before the proposal was accepted. Withdraw it, then propose the supplier's result again or test the requirement in the laboratory."
- **One at a time**: one proposal or acceptance stands for a requirement of a lot. Withdraw it before proposing another result (database constraint).
- **Independence**: proposing makes you an author of the lot's data. You cannot accept your own proposal ("You cannot accept a supplier's result you proposed.") and you cannot sign this lot's QC disposition, even with those roles. This stays true after the proposal is withdrawn.
- **Never edited**: a proposal is accepted or withdrawn. The database refuses a proposal without its frozen evidence, for a lot that is not in quarantine, for a result of another lot, for a result that does not meet the specification, for a certificate record that was corrected or withdrawn, and under a qualification that is not approved or does not name the test.
- **Not enforced by this page**: that the entry matches the supplier's certificate (the reviewer checks it); the unit the certificate used; whether the supplier's method is equivalent to the specification's method (the stated method is shown for a person to judge).
- **Assumption**: these are design defaults of this product, not statements of what any regulation requires or permits: the qualification is matched to the date the lot was received; the certificate record must state a method and limits; a stated result that does not meet the specification cannot be proposed; a result that another current certificate of the lot contradicts cannot be proposed; a requirement the laboratory has started testing cannot be relied on; the lot still needs its sampling record and a sample for QC disposition.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." A refused submission keeps your reason. When the evidence can no longer be shown, the Record card lists the lot and the test code only.
- Unknown supplier result: 404.

## Related pages

- Supplier certificate record (where the proposal starts; Cancel returns here).
- Supplier result acceptance record (opened after saving); Accept supplier result in place of a test.
- Supplier qualification record; Supplier record.
- Lot record; Lot testing.
- [Rule sets](/rules/)
- [Material lots](/lots/)
