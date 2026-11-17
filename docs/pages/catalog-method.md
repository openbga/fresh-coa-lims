---
title: Method record
urls: catalog:method
views: catalog.views.method_detail
templates: catalog/method_detail.html
models: catalog.Method, catalog.MethodRevision, catalog.MethodQCCheck, catalog.MethodCalculationInput, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One method and all its versions, newest first: procedure, suitability evidence, batch QC checks, calculation, signatures and history. Quality users build and approve drafts here.
---

## Common tasks
### Approve a draft version
1. On the draft's card, select [[Review and approve]]. It shows only if you did not create or change that draft.
2. Check the content and sign with your PIN on that page.
### Start a new version
1. Select [[New version]]. The draft copies the latest version's calculation and inputs, and its QC checks when it runs in a QC batch.
### Set up the calculation of a draft
1. Select [[Set formula]], or [[Change formula]] once one is set, and enter the formula, result unit and decimals.
2. Select [[Add input]] once for each name the formula uses.
3. To start again, select [[Clear calculation]]. It removes the formula and every input.
### Add or remove batch QC checks
1. On a draft that runs in a QC batch, select [[Add QC check]].
2. To take a check or an input off, select [[Remove]] on its row.
### Withdraw a draft
1. Select [[Withdraw draft]] on the draft's card, then give a reason on that page. It shows only to quality users.
## Good to know
- You cannot approve a draft you created or changed, including its QC checks or calculation. The card then says another quality approver must sign.
- A draft's procedure, suitability, resource options and effective period are fixed when it is created. To change them, create a new version.
- The version in force is the approved one that applies now. Approving a later overlapping version retires it; it keeps its content and signature.
- Approval is refused while the names in the formula and the inputs do not match exactly.
- Lots keep the method versions frozen when their requirements were assigned.

## Purpose

Shows a method with every version: procedure, suitability evidence, batch QC checks, signatures and history. Quality users manage drafts here.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New version**, **Withdraw draft**, **Add QC check**, QC check **Remove**: **quality** role only (drafts only for the last three).
- **Review and approve**: quality, draft, and only when you did not author or edit that version. Otherwise the text "Another quality approver must sign this draft." is shown instead.

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code. Under the heading: **Approved** and "Version N in force" for the approved version in force now (the latest that applies at this moment), or **No approved version** when none applies; then the method title.
- **One card per version**, newest first: heading "Version N" with its status; draft buttons for quality; facts Technique, Controlled procedure, Suitability, Effective, Summary (only when entered), QC batch ("Runs in a QC batch" or "No batch QC required"), Instrument and Reagent or standard ("Recorded with every result" or "Not required"), Record revision, Author.
- **Batch QC checks** (batch methods only): table Check, "Limits (inclusive)", with **Remove** on drafts for quality. Empty: "No QC checks yet. Approval requires at least one." **Add QC check** on drafts for quality.
- **Calculation** (every version): formula, result unit and decimals, and a table Input, Unit with **Remove** on drafts for quality. Without a calculation: "No calculation. Results are entered directly." Without inputs: "No inputs yet. Approval requires one input for each name in the formula." On drafts for quality: **Set formula** (**Change formula** once set), **Add input** and, when there is a calculation, **Clear calculation**.
- **Signatures** under each version: signer, meaning, time, record revision, hash, or "Not signed."
- **Empty state**: "No versions" ("Create the first version of this method.").
- **History**: audit events for the method and all its versions (including QC check changes), oldest first.
- **Foot line**: the method code, when the page was viewed and by whom.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New version** | Quality role | Quality | Opens the New version form |
| **Withdraw draft** | Version is Draft, quality role | Quality | Opens the Withdraw page |
| **Review and approve** | Draft, quality, independent of author and editors | Quality | Opens the Approve page |
| **Add QC check** | Draft batch version, quality | Quality | Opens the Add QC check form |
| **Remove** (QC check) | Draft, quality | Quality | Opens the Remove QC check form |
| **Set formula** / **Change formula** | Draft, quality | Quality | Opens the Calculation form |
| **Add input** | Draft, quality | Quality | Opens the Add calculation input form |
| **Remove** (input) | Draft, quality | Quality | Opens the Remove calculation input form |
| **Clear calculation** | Draft with a calculation, quality | Quality | Opens the Clear calculation form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Technique | `MethodRevision.technique` | Text | — | Analytical technique. |
| Summary | `MethodRevision.summary` | Text | — | Free description of the method; shown only when the version has one. |
| Controlled procedure | `MethodRevision.document_ref` | Text | — | Procedure document and revision. |
| Suitability | `MethodRevision.suitability_kind`, `suitability_ref` | "kind · evidence reference" | — | Basis and evidence of suitability. |
| Effective | `MethodRevision.effective_from`, `effective_until`, `superseded_from`, `superseded_by` | Date and time range | — | End exclusive. When a later version retired it, a second line reads "Superseded by version N from <time>", or "Superseded by version N before it took effect" when it never applied. |
| QC batch | `MethodRevision.requires_batch` | Yes/No text | — | Whether results must come from a batch whose QC checks pass. |
| Instrument | `MethodRevision.requires_equipment` | Text | — | Whether every result and batch QC entry must record an instrument. |
| Reagent or standard | `MethodRevision.requires_reagent` | Text | — | Whether every result and batch QC entry must record a reagent or standard lot. |
| Formula | `MethodRevision.calculation_formula` | Text, max 500 | — | Arithmetic over the input codes. |
| Result | `MethodRevision.calculation_unit`, `calculation_decimals` | Unit, 0 to 8 decimals | — | Unit of the calculated value and the decimals it is rounded to. |
| Input | `MethodCalculationInput.code`, `name`, `unit` | Code, name, unit | — | One value the analyst enters, in the order added. |
| Record revision | `MethodRevision.revision` | Integer | — | Increases with QC check and calculation changes, approval and withdrawal. |
| Author | `MethodRevision.author` | User | — | Who created the version. |
| Check | `MethodQCCheck.code`, `name` | Text | — | QC check identifier and name. |
| Limits (inclusive) | `MethodQCCheck.lower_limit`, `upper_limit`, `unit` | Decimal with unit | — | "≥ low and ≤ high unit". |

## Rules and hidden logic

- **Order**: versions newest first; history oldest first.
- **Immutability**: approved and withdrawn versions, and their QC checks, resource options, calculation and inputs, are immutable at the database level.
- **Not shown here**: the reason for change appears only in the audit history.
- **Effective intervals** are half-open. The version used is the approved one that applies now: inside its period and not superseded. Approving a later version whose period overlaps an approved one retires the earlier one from the later of the new version's start and the moment of approval (never retroactively); the earlier version keeps its approved content and signature. Approving a draft that overlaps an approved version numbered after it is refused. Lots keep the versions frozen for them.
- **Independence**: author and anyone who changed the draft cannot approve it.
- A new version starts with the calculation and inputs of the previous version. Approval checks the calculation (see Approve method version); a specification test of a calculated method must be numeric with the calculation's unit.
- Audit actions are shown as stored, for example `method_revision.qc_check_added`, `method_revision.calculation_set`, `method_revision.calculation_cleared`, `method_revision.calculation_input_added`.

## Related pages

- [Methods](/catalog/methods/)
- New version, Approve method, Withdraw draft, Add QC check, Remove QC check, Calculation, Add calculation input, Remove calculation input, Clear calculation.
- Specification version pages list this method for each test.
