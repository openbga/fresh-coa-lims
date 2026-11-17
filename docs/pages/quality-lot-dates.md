---
title: Record or correct expiry and retest dates
urls: quality:lot_dates
views: quality.dates_views.lot_dates
templates: catalog/form.html
models: quality.LotDates, quality.Lot, core.RuleSet, core.AuditEvent
reviewed: 2026-11-17
summary: Record the expiry date, the retest date or both for a lot in quarantine, with where they come from, or correct them. A correction adds a record and keeps the earlier one. Analysts and quality.
---

## Common tasks

### Record the dates of a lot

1. On the lot record, select [[Record dates]] in the Expiry and retest dates card.
2. Enter the [[Expiry date]], the [[Retest date]] or both, and say where they come from in [[Basis]].
3. Enter the [[Reason]], then select [[Record dates]].

### Correct the dates

1. On the lot record, select [[Correct dates]].
2. Change the dates or the basis, and say what was wrong in [[Reason for correction]].
3. Select [[Correct dates]]. The earlier record stays in the dates history.

### Say the lot has no dates after all

1. Select [[Correct dates]], clear [[Expiry date]], [[Retest date]] and [[Basis]], and give the [[Reason for correction]].
2. Select [[Correct dates]]. The lot then shows no expiry or retest date.

## Good to know

- Whoever records or corrects a lot's dates cannot sign its release, rejection or cancellation, decide or replace its requirements, or issue a certificate that prints them.
- Recording or correcting changes the lot, so a disposition page opened earlier is refused. Open it again.
- The retest date cannot be after the expiry date. Dates need a basis; only a correction to no dates has none.
- If the dates were changed after you opened the page, nothing is recorded. Review them as they are now and try again.
- The dates are recorded only while the lot is in quarantine. The release freezes the ones in force.

## Purpose

Records the expiry date and the retest date of a lot's material while the lot is in quarantine, each set with where it comes from, and corrects them by adding a record that replaces the one in force. Nothing is edited: the earlier records stay in the lot's dates history.

## Who can use it

- Sign-in required. **analyst** or **quality** role; every other role, and an account holding only Admin, receives 403 when it opens or submits the page. Admin status is not scientific authority.
- Only a lot in Quarantine. For any other state the page redirects to the lot record with the error "Only lots in quarantine accept expiry and retest dates."
- The **Record dates** or **Correct dates** button on the lot record is shown to analyst and quality users while the lot is in Quarantine.
- Whoever records or corrects the dates is an author of the lot's data and cannot sign its disposition, rejection or cancellation (see Rules).

## Layout

- **Breadcrumbs**: Material lots, the lot number, then the page title.
- **Title**: "Record expiry and retest dates" when the lot has no dates record, "Correct expiry and retest dates" when it has one.
- **Intro**: for a first record, "Record the dates the material carries: its expiry date, its retest date or both, with where they come from."; for a correction, "A correction adds a record and keeps the one it replaces. State what was wrong in the reason." Then, for each rule set the lot is under that requires dates, one sentence "<rule set> requires <what>." (for example "an expiry date and a retest date"), or, when none does, "The lot's rule sets require no dates; record them where they apply."
- **Facts**: Lot, Material and Status of the lot.
- **Form**, in two groups: **Dates** (Expiry date, Retest date, Basis) and **Change control** (Reason, labelled Reason for correction on a correction). A correction starts with the dates and basis in force; the reason starts blank.
- **Buttons**: **Cancel** (to the lot record) and **Record dates** or **Correct dates**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record dates** | The lot has no dates record | Analyst or quality | Adds the first record; message "Dates recorded."; returns to the lot record |
| **Correct dates** | The lot has a dates record | Analyst or quality | Adds a record that replaces the one in force; message "Dates corrected; the record replaced is kept."; returns to the lot record |
| **Cancel** | Always | Analyst or quality | Returns to the lot record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Expiry date | `LotDates.expiry_on` | Date | No | The last day the material may be used. Leave blank if it has none |
| Retest date | `LotDates.retest_on` | Date | No | The day from which the material must be examined again before use. Not after the expiry date. Leave blank if it has none |
| Basis | `LotDates.basis` | Text, max 2000 | When a date is given | Where the dates come from: the supplier's label or certificate, or the shelf life or retest period assigned and its reference |
| Reason / Reason for correction | `LotDates.reason`, audit event reason | Text, max 2000 | Yes | Why the dates are recorded or what was wrong. Stored on the record and in the audit event |
| Current record (hidden) | — | Integer | No | The dates record the page showed (empty when it showed none). A page opened before another record was added is refused |

## Rules and hidden logic

- **At least one date**: a first record needs an expiry date, a retest date or both: "Enter an expiry date, a retest date or both." (on Expiry date).
- **Basis**: "State where the dates come from: the supplier's label or certificate, or the shelf life or retest period assigned and its reference." when a date is given without a basis. A correction that states neither date must give no basis: "A correction to no dates states no basis; give the reason instead."
- **Order**: "The retest date cannot be after the expiry date."
- **Reason**: "A reason is required."
- **Nothing changed**: a correction whose dates and basis equal those in force is refused: "The correction changes nothing."
- **Stale page**: the record in force is compared with the one the page showed. If another record was added since: "The lot's dates changed after this page was opened. Nothing was recorded. Review them as they are now."
- **Not quarantined**: if the lot left quarantine since the page opened, "Only lots in quarantine accept expiry and retest dates."
- **Append-only**: each save adds a record; a correction is linked to the one it replaces and the replaced record is kept. A lot has one original record and a single chain of corrections; the database refuses edits, deletions, a retest date after the expiry date, dates without a basis (other than a correction to none) and records for a lot that is not in quarantine.
- **Correction to none**: a correction may state neither date, when the lot has none after all. The lot record then says the dates were corrected to none.
- **Effects**: the record, an audit event and the lot's revision increase by 1 are committed together. The audit event is `lot.dates_recorded` for the first record and `lot.dates_corrected` for a correction, with the reason, the dates before (for a correction) and after.
- **Independence**: everyone who recorded or corrected the lot's dates, including the recorder of a record that was later corrected, is an author of the lot's data. They cannot sign its disposition, its rejection or its cancellation, decide between its specifications or replace its requirements, even with the quality role. A certificate that prints the dates counts them among its authors, so they cannot issue or amend it either.
- **Why the revision matters**: the revision increase refuses a disposition page opened before the change; the signer reviews the dates as they now stand.
- **Rule set requirement**: a rule set may require dates through its `material_dates` policy key (expiry date, retest date, one of them, or both). The release is refused while a required date is missing. This page does not refuse a record that lacks a required date.
- **Release**: the release is also refused after the expiry date and from the retest date on, comparing with the local date, and freezes the dates in force (see Sign lot disposition). After release the recorded dates are never changed; a reassessment of the released lot may give it a later retest date in force (see Reassessment record).
- Not enforced by this page: that the dates match the supplier's documents or an assigned shelf life; the basis is the recorder's statement.

## Related pages

- Lot record (where this page starts and returns)
- Sign lot disposition (the dates it checks and freezes)
- Reject lot, Cancel lot received in error (freeze the dates in force)
- Start reassessment; Reassessment record (a released lot's retest date in force)
- [Rule sets](/rules/): the `material_dates` policy key
- [Material lots](/lots/)
