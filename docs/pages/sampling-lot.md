---
title: Lot requirements and sampling
urls: sampling:lot
views: sampling.views.lot_detail
templates: sampling/lot_detail.html, sampling/includes/replacement.html, sampling/includes/decision.html, sampling/includes/decisions.html, sampling/includes/conflicts.html
models: quality.Lot, sampling.LotAssignment, sampling.SamplingRecord, sampling.SamplingPlanRevision, core.RuleSet, core.AuditEvent, core.ElectronicSignature
reviewed: 2026-11-17
summary: One lot's requirements and sampling: the approved specification, methods and sampling plan frozen for it or its applicability hold, the sampling records, and what sampling still blocks.
---

## Common tasks
### Assign or change the lot's requirements
1. Select [[Assign requirements]], or [[Change requirements]] when requirements exist. It shows to analysts and quality while the lot is in Quarantine and before testing starts.
### Record sampling
1. Select [[Record sampling]]. Only analysts see it, once requirements are assigned and not on hold.
2. Enter what was actually sampled on that page.
### Decide requirements the specifications state differently
1. Select [[Decide conflicting requirements]]. Quality sees it while the lot is on hold before testing, if they recorded none of the lot's data.
### Correct a record or assess a deviation
1. Select [[Correct]] on a current record to add a correction. Analysts only.
2. Select [[Assess deviation]] to accept or reject a deviation. Quality only, never the person who sampled, recorded or corrected it.
### Replace the requirements during testing
1. Select [[Replace requirements]]. Quality sees it once testing has started and the versions in force are no longer the frozen ones.
## Good to know
- The readiness panel covers sampling only. Testing and other gates still apply before QC disposition.
- Later approvals do not change the frozen requirements. The lot keeps them until they are assigned again or, during testing, replaced.
- Once any test exists for the lot, its requirements cannot be assigned again. Only quality's signed replacement changes them.
- Quality can assign requirements but cannot record or correct sampling. Those are analyst actions.
- A correction adds a record marked Current. The original stays, marked Corrected.

## Purpose

Shows the approved requirements frozen for one lot (the scopes it is assigned under, specification tests, methods, sampling plan, rule sets), the sampling that was recorded against them, and the history. It is the starting point for assigning requirements, deciding requirements the specifications state differently, replacing requirements during testing and recording sampling.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **Assign requirements** or **Change requirements**: **analyst** or **quality**, lot in Quarantine, and no analytical test exists yet for the lot. Once the current requirements came from quality's signed decision of conflicting requirements, **Change requirements** is offered to **quality** only.
- **Replace requirements**: **quality** only, lot in Quarantine, testing started, current requirements assigned (not on hold) and the versions in force no longer those frozen for the lot. The button is also shown to a quality user who authored data of the lot; the Replace page then explains why that person cannot sign.
- **Decide conflicting requirements**: **quality** only, lot in Quarantine, testing not started, current requirements on hold, the specifications in force for the lot's scopes state at least one test differently and nothing else holds the lot under the versions in force now. The button is not shown to a quality user who authored data of the lot (receipt, supplier certificate, sampling or test data, or a proposed supplier result): that person reads the conflict and who decides it. It is not shown either while other reasons hold the lot: the page says the decision follows once they are resolved in the configuration.
- **Record sampling**: **analyst** only, shown only when sampling can be recorded: lot in Quarantine, requirements assigned and not on hold, and the assigned plan version still Approved.
- **Assess deviation**: **quality** only, never the person who sampled the material or recorded the record or any earlier record it corrects.
- **Correct**: **analyst** only, lot in Quarantine, on records not yet corrected.
- Buttons follow role and state; the server rechecks on each action.

## Layout

- **Breadcrumbs**: Sampling, lot number. Under the heading: the lot status label (Quarantine, Released, Rejected or Cancelled), the material (the assigned catalog material with its kind's icon and code, or the material as received before requirements are assigned), "Record revision N" and a link **Open lot record**.
- **Closed banner** (lot not in Quarantine): "Closed" and "This lot is no longer in quarantine. Its requirements and sampling records are read-only."
- **Sampling readiness for QC disposition** (first panel): "No sampling blockers" with "Every sample has current sampling provenance against the assigned plan. Testing and other gates still apply.", or a "Blocked" alert "QC disposition is blocked by sampling until:" listing the reasons (see Rules).
- **Current requirements**: when testing has started on a quarantined lot, a "Fixed" note reads "Testing has started, so these requirements cannot be assigned again. When a specification, a method or the rule set is revised, quality can replace them with a signature; tests whose requirement changes are then superseded and repeated."
  - **Newer versions** (warning, for every reader, when testing has started on a quarantined lot and the versions in force are not the frozen ones): "The versions in force now are not the ones frozen for this lot: " followed by what differs ("rule set <code> v<N>", "specification <code> v<N>", "rule set <code> v<N> no longer applies", "the specifications in force state <codes> differently, which quality decides with the replacement", "N requirement(s) changed"), or, when the versions in force cannot be applied, "The versions frozen for this lot are no longer the ones in force, and the versions in force cannot be applied to it: " with the reasons; then "The lot keeps its frozen requirements until quality replaces them with a signature.", and, when a rule set version the lot is under (its own or an additional one) is no longer in force, "Its rule set version is no longer in force, so no further test is assigned and the lot is not dispositioned until then." for the lot's own rule set, or "A rule set version that applies to it in addition to its own is no longer in force, …" for an additional one. Quality also sees the link **Review the replacement**.
  - **Another requirement** (quality, when testing has started on a quarantined lot, the versions in force are the frozen ones and the current requirements carry a choice between specifications): "The specifications that apply state a test differently and a requirement was chosen for each. To apply another one, review a replacement of the lot's requirements: it is signed like any other and repeats the test." with a link to Replace lot requirements.
  - **Rule set retired** (warning, quarantined lot, when an additional rule set version frozen with the requirements is no longer in force and the Newer versions warning does not already say so, for example before testing has started): "Rule set <code> v<N>, which applies to this lot in addition to its own, is no longer in force. Assign the lot's requirements again, or have quality replace them once testing has started. No further test is assigned and the lot is not dispositioned until then."
  - **Replaced** (when the current requirements came from a signed replacement): "These requirements replaced the earlier ones during testing. Signed by <name> with the meaning requirements replaced on <time>, bound to lot revision N." and "Reason:" with the signer's reason. A list follows: the rule set and specification versions replaced (only those that changed); every other rule set or specification version that was replaced, "applies from this replacement" or "no longer applies"; each test the specifications state differently, with the statement that applies and those not applied, followed by "Decided earlier by <name> and carried by this replacement: <that person's reason>" when the choice was made before this replacement and carried by it unchanged; each requirement line that changed, was added or was removed (before → after); and each test with "carried over" or "superseded" (with "(had reported <result>)" when it had a result). Test labels link to the test.
  - **Decided** (when the current requirements came from a signed decision): "The specifications that apply to this lot state a test differently, and quality decided which requirement applies. Signed by <name> with the meaning requirements decided on <time>, bound to lot revision N." and "Reason:" with the signer's reason. One line per test follows, saying what its statements differ in: "assay (stated differently in limits): SPEC-TEST-EU v1 (eu-market) applies, 99 – 101 % · rounded to 2 decimals · method M-TEST-001 v2. Not applied: SPEC-TEST-001 v1 (general), 98 – 102 % · rounded to 2 decimals · method M-TEST-001 v2.", with ", information only" after a statement that is not required.
  - No assignment: "Applicability hold: no requirements assigned" and "Assign the approved specification and sampling plan for this lot's material and stage before sampling or testing."
  - On hold: "Applicability hold", "This lot cannot be sampled, tested against limits or dispositioned until quality resolves:" and the reasons, plus Requested (material, stage and the scopes named) and Recorded facts.
  - On hold for conflicting requirements (quarantined lot, before testing): under the reasons, **Requirements the specifications state differently**: "Nothing is merged and neither statement is picked. A quality person who recorded none of this lot's data decides which requirement applies and signs the decision", ending ", once the other reasons above are resolved in the configuration." when other reasons also hold the lot under the versions in force now. A quality user who authored none of the lot's data also sees the link **Decide conflicting requirements** when nothing else holds the lot. Then one group per test, headed by its code and name: "The statements differ in: limits." and a list of the statements, each like "SPEC-TEST-EU v1 (eu-market) · Assay: 99 – 101 % · rounded to 2 decimals · method M-TEST-001 v2" (the specification version is a link; every scope that states it so is named; "· information only" when not required).
  - Assigned: Material, Stage and scope, Specification (link to its version), Sampling plan (link, basis, "at least" amount), Rule set (when present), Frozen (who, when, shortened hash); then a table Test (code and name), Acceptance criterion, Method version (with controlled procedure), Suitability evidence, Required ("Required" or "Information only").
  - Assigned under several scopes, or with an additional rule set: the facts read Stage and scopes, and Specifications (a link to each version with its scope in brackets, for example "SPEC-TEST-EU v1 (eu-market)"); **Additional rule sets** lists each as "code vN · requires <tests>"; the table gains the column **Stated by**, the scopes whose specification states the test.
- **Sampling records**: table Sample (with "sampled" and the time under it), Sampled by (with the location under it), "Containers (sampled / required / total)", Amount, Plan, Deviation, Status ("Current" or "Corrected"), and **Correct** for analysts. A resample shows "Resample of <original sample>" under its reference. A deviation shows its assessment status ("Awaiting quality assessment", "Accepted by quality" or "Rejected by quality"), who decided and when, and an **Assess deviation** button. Empty: "No sampling recorded" ("Record sampling against the assigned plan once requirements are assigned."), with a **Record sampling** button for analysts when requirements are assigned.
- **Earlier requirement assignments**: shown when more than one assignment exists; each marked "Superseded". An earlier signed replacement is titled "Requirements replaced during testing" and an earlier signed decision "Conflicting requirements decided by quality", each with "Signed by" and the signer. A hold that was decided stays listed as "Applicability hold".
- **History**: audit events of all assignments, sampling records and deviation assessments.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign requirements** / **Change requirements** | Viewer is analyst or quality and no assignment blocker applies (lot in Quarantine, no analytical test yet); label is Change when an assignment exists. Hidden from an analyst without the quality role once the current requirements came from a signed decision | Analyst, quality; quality only after a signed decision | Opens the Assign requirements form |
| **Replace requirements**, **Review the replacement** | Viewer has the quality role and made none of the lot's records (otherwise the header says why), the versions in force can be applied to the lot, lot in Quarantine, testing started, current requirements assigned, and the versions in force are not the frozen ones | Quality | Opens Replace lot requirements; refusals are explained there or on return here |
| **Decide conflicting requirements** (button and link) | Viewer has the quality role and authored none of the lot's data, lot in Quarantine, testing not started, current requirements on hold, the specifications in force state a test differently, and nothing else holds the lot | Quality, independent of the lot's data | Opens Decide conflicting requirements |
| review a replacement of the lot's requirements (link) | Quality, testing started, nothing revised since, and a requirement was chosen between specifications | Quality | Opens Replace lot requirements, where another requirement can be chosen and the replacement reviewed and signed |
| **Record sampling** | Viewer is an analyst and no sampling blocker applies (Quarantine, requirements assigned, plan approved) | Analyst | Opens the Record sampling form |
| **Correct** | Lot open, viewer is analyst, record not yet corrected | Analyst | Opens the Correct sampling form |
| **Assess deviation** | Record has a pending deviation assessment, is not corrected, lot in Quarantine, viewer has the quality role and neither sampled nor recorded it or an earlier record it corrects | Quality | Opens the Assess sampling deviation page |
| **Open lot record** | Always | Any viewer | Opens the quality lot record |
| Specification / Sampling plan links | Requirements assigned, or a conflict listed on a hold | Any viewer | Open the frozen specification version (each one, when several apply), the plan, or a specification version that states a test differently |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot status | `Lot.state` | Quarantine, Released | — | Only quarantined lots accept changes here. |
| Record revision | `Lot.revision` | Integer | — | Increases when requirements are assigned, decided or replaced, a sample is recorded (once), a record is corrected or a deviation is assessed; signing pages bind to it. |
| Scope, Scopes | `LotAssignment.scopes` (the first also in `scope`), `LotAssignment.payload` | Scope names | — | The scopes the lot is assigned under: "general" first, then the named market or customer overlays in alphabetical order. An assignment recorded before several could be named has one. |
| Specification, Specifications, Sampling plan | `LotAssignment.payload` | "code vN" | — | Versions frozen when requirements were assigned; one specification for each scope that has one. |
| Rule set | `LotAssignment.payload` (rules) | "code vN · requires <tests>" | — | The version of the lot's own rule set frozen with the requirements. |
| Additional rule sets | `LotAssignment.payload` (additional rules) | "code vN · requires <tests>" | — | Rule set versions whose policy states `applies_to` and that applied to the lot's material, stage or scopes when the requirements were frozen. Each must stay in force for tests to be assigned and for the disposition. |
| Stated by | `LotAssignment.payload` (test sources) | Scope names | — | The scopes whose specification states the test as frozen. After a decision, only the scopes of the statement that applies. |
| Decided | `LotAssignment.origin`, `decision`, `reason`; `ElectronicSignature` (meaning `requirements_decided`) | Text | — | Evidence kept with a decision: for each test the scope that was named, what the statements differ in, the statement that applies, the statements not applied, and who decided it, when and why; the signature and the lot revision it is bound to. |
| Replaced | `LotAssignment.origin`, `replacement`, `reason`; `ElectronicSignature` (meaning `requirements_replaced`) | Text | — | Evidence kept with a replacement: what changed, the choices between differing statements with who decided each, when and why (the replacement's signer, or whoever decided it earlier when the statement that applies is unchanged), which tests carried over or were superseded, the signature and the lot revision it is bound to. |
| Frozen hash | `LotAssignment.payload_hash` | SHA-256, shortened | — | Hash of the frozen requirement content. |
| Acceptance criterion | payload test line | Decimal limits with unit, or expected text | — | "≥" or ">" lower, "≤" or "<" upper, "(rounded to N)" when rounding applies. |
| Sample | `Sample.reference` | Text | — | Sample identifier; corrections show "Corrects record N". |
| Sampled / Sampled by | `SamplingRecord.sampled_at`, `sampled_by`, `location` | Date and time, user, text | — | When (under the sample), by whom and where; "recorded by" appears when another user entered it. When the table does not fit, Amount and then Plan give way first. |
| Containers | `containers_sampled`, `containers_required`, `containers_total` | Integers | — | Sampled / required by the plan / in the lot, then the container IDs. |
| Amount | `SamplingRecord.quantity`, `quantity_unit` | Decimal with unit | — | Total amount collected. |
| Deviation | `SamplingRecord.deviation` | Text | — | "Deviation" label and text, or "None". |
| Deviation assessment | `DeviationReview.status`, `decided_by`, `decided_at` | Status, user, date and time | — | Quality's signed decision on the deviation; blocks disposition until accepted. |
| Resample of | `SamplingRecord.resample_of` | Sample reference | — | Original sample a resample replaces. |
| Status | derived | Current, Corrected | — | Corrected means a later record supersedes it. |

## Rules and hidden logic

- **Frozen content**: an assignment stores the approved specifications, methods, plan and rule set versions as they were; later approvals, including one that retires a frozen version, do not change it until requirements are assigned again or replaced.
- **Several scopes**: the specification of every scope the lot is assigned under applies in full. A test the specifications state alike is one requirement; nothing is merged. Additional rule sets apply beside the lot's own rule set; they are selected by the material, stage and scopes, never chosen at receipt.
- **Conflicting requirements**: where the specifications state a test differently the assignment is an applicability hold with the reason "Specifications <code> v<N> (<scopes>) and <code> v<N> (<scopes>) state different requirements for <test>. Quality decides which one applies to this lot." The list of statements, what they differ in and whether anything else holds the lot are worked out from the versions in force each time the page is shown, so they can differ from the reasons recorded with the hold. "The statements differ in:" uses the words name, result type, unit, limits, expected outcome, rounding, replicates, whether each replicate must meet the limits, retests allowed, method version, required or information only. When the specifications no longer differ, the list and the button are not shown and the hold stays until the requirements are assigned again.
- **Decision**: before testing, a quality person who recorded none of the lot's data signs which statement applies (meaning `requirements_decided`); the hold is then superseded by frozen requirements. A decision settles conflicts only: any other hold reason is resolved in the configuration first, and the decision is offered once nothing else holds the lot. Once testing has started, the choice is made on Replace lot requirements.
- **After a signed decision**: only quality assigns the lot's requirements again. **Change requirements** is hidden from others, and the Assign requirements page returns them here with "Quality decided which requirement applies to this lot where its specifications differ. Only quality assigns its requirements again; the decision is then made again." Assigning again never applies the earlier decision; it needs no signature, and Sign lot disposition then names the decision that was set aside.
- **Additional rule set no longer in force**: tests are not assigned and the lot is not dispositioned while an additional rule set version frozen for it is retired or expired. Before testing, assign the requirements again; once testing has started, quality replaces them.
- **Fixed after testing starts**: once any analytical test exists for the lot, requirements cannot be assigned again; the change button is hidden and the server refuses. Quality can replace them with a signature by the versions in force (Replace requirements). The sampling plan is kept.
- **Append-only**: assigning again adds a new assignment that supersedes the previous one; earlier ones stay listed. Corrections add records; originals are preserved.
- **Readiness blockers** (computed on each view; these exact reasons): "Applicability hold: no specification or sampling requirements are assigned."; "Applicability hold: <hold reason>" for each recorded hold reason; "No sampling has been recorded against the approved sampling plan."; "Sample <ref> has no sampling record against the approved plan."; "Sample <ref> was sampled under <plan vN>; the current requirements use <plan vN>."; "Sampling deviation for sample <ref> awaits quality assessment."; "Sampling deviation for sample <ref> was rejected; correct the record or resample." Only the latest record of each sample counts. Testing and other gates are outside this panel.
- **Hold**: a hold blocks sampling here; its reasons are listed exactly as recorded.
- **Roles**: quality users can assign requirements but cannot record or correct sampling; that is analyst only.
- **Ordering**: sampling records oldest first; assignments newest first, history oldest first.
- Audit actions are shown as stored, for example `lot.requirements_assigned`, `lot.requirements_held`, `lot.requirements_decided`, `lot.requirements_replaced`, `sampling.recorded`, `sampling.corrected`.

## Related pages

- [Lots](/sampling/)
- [Material lots](/lots/)
- Assign requirements, Decide conflicting requirements, Replace lot requirements, Record sampling, Correct sampling.
- Specification version (from a specification link). [Rule sets](/rules/)
- Test record (from a test listed under Replaced).
