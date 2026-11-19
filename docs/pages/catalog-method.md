---
title: Method record
urls: catalog:method
views: catalog.views.method_detail
templates: catalog/method_detail.html
models: catalog.ProficiencyParticipation, catalog.Method, catalog.MethodRevision, catalog.MethodEvidence, catalog.MethodQCCheck, catalog.MethodResource, catalog.MethodCalculationInput, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One method and its versions, newest first: procedure, evidence, QC checks, suitable resources, calculation, file import, signatures and history, then evidence records and proficiency testing. Quality users manage drafts.
---

## Common tasks
### Approve a draft version
1. On the draft's card, select [[Review and approve]]. It shows only if you did not create or change that draft.
2. Check the content and sign with your PIN on that page.
### Start a new version
1. Select [[New version]]. The draft copies the latest version's calculation, inputs, file import and suitable resources, and its QC checks when it runs in a QC batch.
### Set up the calculation, file import and suitable resources of a draft
1. Select [[Set formula]], or [[Change formula]] once one is set, enter the formula, result unit and decimals, then [[Add input]] once for each name it uses.
2. To let analysts import results from the instrument's export, select [[Set file import]].
3. To list the instruments, reagents and standards suitable for the method, select [[Add suitable resource]]; [[In the register now]] shows what matches each line today.
4. On a draft that runs in a QC batch, select [[Add QC check]]. Select [[Remove]] on a row to take a check, input or resource off.
### Set the suitability evidence of a draft
1. On the draft's card, select [[Suitability evidence]]. It shows only to quality users.
2. Choose an approved evidence record of this method, or name an external report, and save. To record new evidence first, select [[New evidence record]] in the Evidence records panel.
### Withdraw a draft
1. Select [[Withdraw draft]] on the draft's card, then give a reason on that page. It shows only to quality users.
## Good to know
- You cannot approve a draft you created or changed, including its QC checks, suitable resources or calculation. The card then says another quality approver must sign.
- A draft's procedure, resource options, reviewer qualification and effective period are fixed at creation. Its suitability can be set later; whoever sets it cannot approve the version.
- The version in force is the approved one that applies now. Approving a later overlapping version retires it; it keeps its content and signature.
- Approval is refused while the names in the formula and the inputs do not match exactly.
- Lots keep the method versions frozen when their requirements were assigned. Suitable resources are frozen with the approval.

## Purpose

Shows a method with every version: procedure, suitability evidence, batch QC checks, signatures and history. Quality users manage drafts here.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New version**, **Withdraw draft**, **Suitability evidence**, **Add QC check**, QC check **Remove**, **Add suitable resource**, suitable resource **Remove**: **quality** role only (drafts only for all but the first).
- **New evidence record**: analyst, reviewer or quality.
- **New participation**: quality. **All participations** shows to every viewer once the method has a participation.
- **Review and approve**: quality, draft, and only when you did not author or edit that version. Otherwise the text "Another quality approver must sign this draft." is shown instead, or, when a later version is already approved for the same dates, that reason.

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code. Under the heading: **Approved** and "Version N in force" for the approved version in force now (the latest that applies at this moment), or **No approved version** when none applies; then the method title.
- **One card per version**, newest first: heading "Version N" with its status; draft buttons for quality; facts Technique, Controlled procedure, Suitability (the linked evidence record with its kind, report and title, with "Record withdrawn" once the record was withdrawn, or the kind and report with "External reference; no evidence record kept here"), Effective, Summary (only when entered), QC batch ("Runs in a QC batch" or "No batch QC required"), Instrument and Reagent or standard ("Recorded with every result" or "Not required"), Review ("By a reviewer qualified to review this method" or "By any reviewer"), Record revision, Author.
- **Batch QC checks** (batch methods only): table Check, "Limits (inclusive)", with **Remove** on drafts for quality. Empty: "No QC checks yet. Approval requires at least one." **Add QC check** on drafts for quality.
- **Suitable instruments, reagents and standards** (every version): table Resource (name, with "Instrument category", Reagent, Reference standard or Prepared solution below), Use ("Recorded with every result" or "May be used", and "Qualified for <method code>" for an instrument whose line asks for it). On a draft and on an approved version that has not stopped applying (in force now or later), a column **In the register now** lists, for each line, the instruments of that category with their status ("Not qualified for the method" added where the line asks for a qualification and none is current), or the lots that are neither rejected nor expired with their release and expiry status, each linking to its record; at most 8, then "and N more". Empty cell: "No instrument of this category" or "No lot in use or awaiting release". Without lines: "None listed. Any instrument, reagent or standard that passes its calibration, release and expiry checks may be recorded." On drafts for quality: **Add suitable resource** and, per row, **Remove**.
- **Calculation** (every version): formula, result unit and decimals, and a table Input, Unit with **Remove** on drafts for quality. Without a calculation: "No calculation. Results are entered directly." Without inputs: "No inputs yet. Approval requires one input for each name in the formula." On drafts for quality: **Set formula** (**Change formula** once set), **Add input** and, when there is a calculation, **Clear calculation**.
- **File import** (every version): Export, Format ("<separator> separated, decimal mark <mark>, <encoding>"), Column names ("Row N") and Rows read, then a table Input, Column of the file ("Entered by the analyst for each row" for an input the file does not hold). Without one: "No file import. Analysts record each result by hand." On drafts for quality: **Set file import** (**Change file import** once set) and, when there is one, **Clear file import**.
- **Evidence records** (after the versions): table Record (link with title below), Kind, Completed on, Conclusion, State, for every evidence record of this method, newest completion first. Empty: "No evidence records" ("Records of the validation, verification or transfer of this method appear here."). **New evidence record** opens the form with this method chosen.
- **Proficiency testing** (after Evidence records): table Participation (PT-n link with the round beneath), Provider, Results due, Outcome (empty until reviewed), State (Planned, Results overdue, Results reported, Follow-up open, Closed or Cancelled), newest due day first, at most 10. When there are more: "Showing the latest N of M." Empty: "No participations" ("Proficiency testing rounds and other interlaboratory comparisons planned for this method appear here."). Buttons **All participations** and **New participation**.
- **Signatures** under each version: signer, meaning, time, record revision, hash, or "Not signed."
- **Empty state**: "No versions" ("Create the first version of this method.").
- **History**: audit events for the method and all its versions (including QC check changes), oldest first.
- **Foot line**: the method code, when the page was viewed and by whom.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New version** | Quality role | Quality | Opens the New version form |
| **Withdraw draft** | Version is Draft, quality role | Quality | Opens the Withdraw page |
| **Suitability evidence** | Version is Draft, quality role | Quality | Opens the Suitability evidence page |
| **New evidence record** | Analyst, reviewer or quality | Same roles | Opens the New method evidence record form for this method |
| **All participations** | The method has at least one participation | Any viewer | Opens Proficiency testing listing this method's participations only |
| **New participation** | Quality role | Quality | Opens the New participation form with this method chosen |
| Record number (Proficiency testing) | Each row | Any viewer | Opens the participation |
| Record number (Evidence records) | Each row | Any viewer | Opens the evidence record |
| **Review and approve** | Draft, quality, independent of author and editors, and no later version is already approved for the same dates (otherwise the card says why in its place) | Quality | Opens the Approve page |
| **Add QC check** | Draft batch version, quality | Quality | Opens the Add QC check form |
| **Remove** (QC check) | Draft, quality | Quality | Opens the Remove QC check form |
| **Add suitable resource** | Draft, quality | Quality | Opens the Add suitable resource form |
| **Remove** (suitable resource) | Draft, quality | Quality | Opens the Remove suitable resource form |
| **Set formula** / **Change formula** | Draft, quality | Quality | Opens the Calculation form |
| **Add input** | Draft, quality | Quality | Opens the Add calculation input form |
| **Remove** (input) | Draft, quality | Quality | Opens the Remove calculation input form |
| **Clear calculation** | Draft with a calculation, quality | Quality | Opens the Clear calculation form |
| **Set file import** / **Change file import** | Draft, quality | Quality | Opens the File import form |
| **Clear file import** | Draft with a file import, quality | Quality | Opens the Clear file import form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Technique | `MethodRevision.technique` | Text | — | Analytical technique. |
| Summary | `MethodRevision.summary` | Text | — | Free description of the method; shown only when the version has one. |
| Controlled procedure | `MethodRevision.document_ref` | Text | — | Procedure document and revision. |
| Suitability | `MethodRevision.evidence`, `suitability_kind`, `suitability_ref` | Record link, "kind · evidence reference" | — | Basis and evidence of suitability. With a record kept here it links the record (MEV-n) and shows its title; otherwise the reference is external. |
| Effective | `MethodRevision.effective_from`, `effective_until`, `superseded_from`, `superseded_by` | Date and time range | — | End exclusive. When a later version retired it, a second line reads "Superseded by version N from <time>", or "Superseded by version N before it took effect" when it never applied. |
| QC batch | `MethodRevision.requires_batch` | Yes/No text | — | Whether results must come from a batch whose QC checks pass. |
| Instrument | `MethodRevision.requires_equipment` | Text | — | Whether every result and batch QC entry must record an instrument. |
| Reagent or standard | `MethodRevision.requires_reagent` | Text | — | Whether every result and batch QC entry must record a reagent or standard lot. |
| Review | `MethodRevision.requires_review_qualification` | Text | — | "By a reviewer qualified to review this method" when reviewing or returning a result of this version needs a qualification to review the method; otherwise "By any reviewer". |
| Resource | `MethodResource.kind`, `name` | Kind and name | — | An equipment category, or the kind and name of a reagent lot, as the laboratory register records them. |
| Use | `MethodResource.required`, `method_qualified` | Text | — | Whether every result must record one, and whether an instrument also needs an approved, current qualification whose activity is the method code. |
| In the register now | laboratory register | Links with status | — | Computed when the page opens; not part of the version. |
| Formula | `MethodRevision.calculation_formula` | Text, max 500 | — | Arithmetic over the input codes. |
| Result | `MethodRevision.calculation_unit`, `calculation_decimals` | Unit, 0 to 8 decimals | — | Unit of the calculated value and the decimals it is rounded to. |
| Input | `MethodCalculationInput.code`, `name`, `unit` | Code, name, unit | — | One value the analyst enters, in the order added. |
| File import | `MethodRevision.file_import` | Format, rows and columns | — | How analysts import the version's results from its instrument's export; frozen with the approval and with each test assigned under the version. |
| Record revision | `MethodRevision.revision` | Integer | — | Increases with QC check, suitable resource and calculation changes, approval and withdrawal. |
| Author | `MethodRevision.author` | User | — | Who created the version. |
| Check | `MethodQCCheck.code`, `name` | Text | — | QC check identifier and name. |
| Limits (inclusive) | `MethodQCCheck.lower_limit`, `upper_limit`, `unit` | Decimal with unit | — | "≥ low and ≤ high unit". |

## Rules and hidden logic

- **Order**: versions newest first; history oldest first.
- **Immutability**: approved and withdrawn versions, and their QC checks, suitable resources, resource options, calculation and inputs, are immutable at the database level.
- **Not shown here**: the reason for change appears only in the audit history.
- **Effective intervals** are half-open. The version used is the approved one that applies now: inside its period and not superseded. Approving a later version whose period overlaps an approved one retires the earlier one from the later of the new version's start and the moment of approval (never retroactively); the earlier version keeps its approved content and signature. Approving a draft that overlaps an approved version numbered after it is refused. Lots keep the versions frozen for them.
- **Independence**: author and anyone who changed the draft cannot approve it.
- A new version starts with the calculation, inputs, file import and suitable resources of the previous version. Approval checks the calculation (see Approve method version); a specification test of a calculated method must be numeric with the calculation's unit.
- Audit actions are shown as stored, for example `method_revision.qc_check_added`, `method_revision.resource_added`, `method_revision.resource_removed`, `method_revision.calculation_set`, `method_revision.calculation_cleared`, `method_revision.calculation_input_added`, `method_revision.file_import_set`, `method_revision.file_import_cleared`, `method_revision.suitability_set`.

## Related pages

- [Methods](/catalog/methods/)
- New version, Approve method, Withdraw draft, Add QC check, Remove QC check, Add suitable resource, Remove suitable resource, Calculation, Add calculation input, Remove calculation input, Clear calculation, File import of a method version, Clear file import.
- [Proficiency testing](/catalog/proficiency/) and New participation.
- Specification version pages list this method for each test.
