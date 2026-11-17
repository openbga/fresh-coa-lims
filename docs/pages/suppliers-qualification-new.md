---
title: Record supplier qualification
urls: suppliers:qualification_new
views: suppliers.qualification_views.qualification_new
templates: suppliers/qualification_material.html, catalog/form.html
models: suppliers.SupplierQualification, suppliers.Supplier, catalog.Material, catalog.SpecificationTest, core.AuditEvent
reviewed: 2026-11-17
summary: Record the evidence that a supplier's certificate results can be relied on for one material and named tests between two dates. A different quality user then approves it.
---

## Common tasks
### Choose the material
1. Choose the [[Material]] and select [[Continue]]. Its specifications decide which tests you can choose.
### Record the evidence
1. Under [[Tests covered]], select the tests. Leave out every test the laboratory performs itself.
2. Fill in [[How the supplier was qualified]], [[Evidence reference]] and, if there is one, [[Evidence link]].
3. Set [[Valid from]] and [[Valid until (inclusive)]].
4. Enter a [[Reason]] and select [[Record qualification]].
### Have it approved
1. A different quality user opens the qualification record and selects [[Approve]].
## Good to know
- Recording evidence qualifies nothing until a different quality user approves it.
- The dates are compared with the date a lot was received, both days inclusive. Past dates are accepted.
- A renewal or a change of scope is a new qualification. The evidence cannot be edited after recording.
- A qualification lets a supplier result stand in for a test only where the lot's rule set allows it, through an acceptance signed on the lot.
- If the material has no test to choose from, add the material's specification first.

## Purpose

Records the evidence that a supplier's certificate results can be relied on for one material, for named tests, between two dates. Recording qualifies nothing: a different Quality user signs it.

## Who can use it

- Sign-in required. Role: Quality; others receive 403. The supplier record shows **Record qualification** only to Quality users.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

The page has two steps at one address. Both show the breadcrumbs (Suppliers, the supplier's code, Record qualification) and the title "Record qualification · sup-syn-001".

- **Step 1, material**: the introduction "A qualification covers one material. Choose it first: the tests it can cover are those of the material's specifications.", a **Record** card with Supplier ("code · name"), the **Material** menu, and a **Cancel** / **Continue** row. Nothing is saved.
- **Step 2, evidence**: the introduction "Recording evidence qualifies nothing. A different quality signer approves it. A qualification lets a result the supplier's certificate states stand in for a test only where the lot's rule set allows it, and only through an acceptance signed on the lot.", a **Record** card with Supplier and Material, the form sections Scope, Evidence, Validity and Change control, and a **Cancel** / **Record qualification** row.
- When the material has no test to choose from, the Record card adds Tests: "No specification of this material states a test yet. Add the material's specification first."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Continue** | Step 1 | Quality | Reloads the page with the chosen material in the address and shows step 2. A missing or unknown material shows step 1 again with the error |
| **Record qualification** | Step 2 | Quality | Saves the evidence as Awaiting approval, shows "Qualification evidence recorded; a second quality signer approves." and opens the qualification record; refusals appear on the form and your entries are kept (status 422) |
| **Cancel** | Both steps | Quality | Returns to the supplier record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Material | `SupplierQualification.material` | Menu of every material in the catalog, by code ("code · name") | Yes | Step 1. Help: "The tests a qualification can cover are those of this material's specifications." Fixed for step 2; to choose another material, cancel and start again |
| Tests covered | `SupplierQualification.test_codes` | Checkboxes, "Name (code)" | Yes, at least one | Help: "A result the supplier's certificate states for a test selected here may stand in for the laboratory's own test. Leave out every test the laboratory performs itself, such as identity." |
| How the supplier was qualified | `SupplierQualification.basis` | Text, max 4000 | Yes | Help: "How the reliability of the supplier's results was established, for example the lots tested in full and compared with the certificates, and the audit." |
| Evidence reference | `SupplierQualification.evidence_ref` | Text, max 200 | Yes | Help: "Qualification report, audit report or comparison record, with its revision." Shown with every result accepted under the qualification |
| Evidence link | `SupplierQualification.evidence_url` | http(s) URL, max 500 | No | Untrusted external link |
| Valid from | `SupplierQualification.valid_from` | Date | Yes | Help: "The qualification covers lots received from this day." |
| Valid until (inclusive) | `SupplierQualification.valid_until` | Date | Yes | Help: "Last day of receipt covered. Set it to when the supplier's results are to be confirmed again; a renewal is a new qualification." Cannot precede Valid from |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the evidence |

## Rules and hidden logic

- **Tests offered**: every test code that a specification version of the chosen material states, by code. Draft and approved versions count; withdrawn drafts do not. When versions name a test differently, the name of the latest version is shown.
- **Scope**: a code that is not among the tests offered is refused: "No specification of MAT-CODE states CODE. Choose tests from the material's specifications." Also "Select at least one test." and "A qualification covers at most 60 tests." The codes are saved once each, in alphabetical order.
- **Dates**: "The last day of validity cannot be before the first." appears on Valid until. One day (the same date twice) is accepted. The dates are compared with the date the lot was received, both days inclusive, not with the date of the certificate or of the acceptance.
- **Past and future dates**: nothing compares the dates with today. Evidence whose dates lie in the past can be recorded and signed; it covers lots received within them.
- **Evidence link**: only http and https addresses are accepted.
- **Awaiting approval**: the record covers nothing until a Quality user other than you signs it. Until then a proposal on a lot is refused as "still awaiting its signature".
- **Several qualifications**: one supplier may hold several qualifications of one material, with dates and tests that overlap or not. When several cover a result, the one recorded last is relied on. A renewal or a change of scope is a new qualification.
- **What a qualification does not do by itself**: it changes nothing on any lot. A supplier result stands in for a test only when the lot's rule set allows it for that test and an acceptance is proposed and signed on the lot.
- **Immutable**: the evidence cannot be edited or deleted after recording (database guard). To change it, record a new qualification; a signed one can be revoked.
- **Audit**: `supplier_qualification.recorded` with the evidence and your reason. Spaces around the text values are removed.
- **Not enforced by this page**: how often a supplier is re-confirmed; the qualification's end date is the only limit. The evidence document is not read or verified. A test selected here may still be one that a rule set keeps with the laboratory; the rule set decides for each lot. The specification that states a test need not be approved.
- **Assumption**: qualifying a supplier per material and test on recorded evidence, with a second Quality signature, and matching the qualification to the date the lot was received are design defaults of this product. They are not a statement of what any regulation requires or permits.
- **Form behaviour**: step 2 shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422 and keeps your entries.
- Unknown supplier: 404.

## Related pages

- Supplier record (Cancel returns here).
- Supplier qualification record (opened after saving), where a second Quality user approves.
- [Suppliers](/suppliers/)
- [Specifications](/catalog/) (the tests of a material come from its specifications).
- [Rule sets](/rules/) (which tests a lot's rule set keeps with the laboratory).
