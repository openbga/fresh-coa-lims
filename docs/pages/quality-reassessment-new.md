---
title: Start reassessment
urls: quality:reassessment_new
views: quality.reassessment_views.reassessment_new
templates: catalog/form.html
models: quality.Reassessment, quality.Lot, core.AuditEvent
reviewed: 2026-11-17
summary: Start the reassessment of a released lot by recording the sample taken to examine its material again. Analysts and quality. The lot's record, dates and disposition do not change.
---

## Common tasks

### Start the reassessment of a released lot

1. On the lot record, select [[Start reassessment]] in the Reassessments card.
2. Enter the sample in [[Sample reference]], [[Date sampled]], [[Quantity taken]], [[Quantity unit]] and [[Containers sampled]].
3. Say why in [[Why the material is examined again]], then select [[Start reassessment]]. You land on the reassessment record to assign its tests.

### Find out why you cannot start one

1. If you are sent back to the lot record with an error message, read it. It says which condition the lot does not meet.

## Good to know

- Only a released lot that still has a retest date in force, that has not expired and whose use has not ended can be reassessed. One reassessment of a lot is open at a time.
- The sample is a new one taken for the purpose. Its tests are assigned on the next page from the specifications in force now, not those frozen at release.
- Starting changes nothing on the lot: its record, its dates as frozen at release and its disposition stay as signed.
- Whoever starts the reassessment cannot conclude it.
- The retest date does not have to be reached yet: a lot with a retest date in the future can be reassessed early.

## Purpose

Starts the reassessment of a released lot: the material is examined again on a sample taken for the purpose, so that quality can give it a later retest date or end its use. This page records the sample and the reason. The tests are assigned afterwards.

## Who can use it

- Sign-in required. **analyst** or **quality** role; every other role, and an account holding only Admin, receives 403.
- The **Start reassessment** button on the lot record is shown to analyst and quality users when the lot is Released and nothing prevents a reassessment. The lot record says why it cannot be started when that is not already visible in the Reassessments table.
- Opening the page for a lot that cannot be reassessed returns you to the lot record with the reason as an error message (see Rules).

## Layout

- **Breadcrumbs**: Material lots, the lot number, then "Start reassessment". Title "Start reassessment".
- **Intro**: "Record the sample taken to examine the material again. Its tests are then assigned from the specifications in force for the lot. The tests belong to the reassessment: the lot's record, its dates as frozen at release and its disposition are not changed."
- **Facts**: Lot, Material, Retest date (the date in force) and Expiry date ("None" when not stated).
- **Form**, in two groups: **Sample** (Sample reference, Date sampled, Quantity taken, Quantity unit, Containers sampled) and **Reason** (Why the material is examined again).
- **Buttons**: **Cancel** (to the lot record) and **Start reassessment**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Start reassessment** | Always (the page opens only for a lot that can be reassessed) | Analyst or quality | Adds the reassessment (RA-n, state Open); message "RA-n started; assign its tests."; opens the reassessment record |
| **Cancel** | Always | Analyst or quality | Returns to the lot record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sample reference | `Reassessment.sample_reference` | Text, max 80, unique | Yes | The identifier on the sample taken for the reassessment. No other reassessment may use it |
| Date sampled | `Reassessment.sampled_on` | Date, default today | Yes | When the sample was taken; not in the future |
| Quantity taken | `Reassessment.quantity` | Decimal, up to 4 decimal places | Yes | Greater than zero |
| Quantity unit | `Reassessment.quantity_unit` | Choice | Yes | The unit of the quantity |
| Containers sampled | `Reassessment.containers` | Text, max 200 | Yes | Which containers of the lot were sampled, and where the lot is stored |
| Why the material is examined again | `Reassessment.reason`, audit event reason | Text, max 2000 | Yes | Stored on the reassessment and in the audit event |
| Lot, Material, Retest date, Expiry date | `Lot`, dates in force | Display | — | What the lot's dates are now. The retest date is the one in force: a later one given by an earlier reassessment replaces the one frozen at release |

## Rules and hidden logic

- **Who may open it**: analyst or quality, otherwise 403.
- **Refusals on opening** (error message, redirect to the lot record), also checked again when the form is submitted: "Only a released lot is reassessed."; "The use of this lot ended with RA-n."; "RA-n of this lot is open."; "The lot has no retest date. A reassessment gives a released lot a later retest date."; "The lot expired after <date>; it is not reassessed."; "The lot was released without requirements assigned in the system." The retest date need not have been reached.
- **Field messages**: "A reason is required."; "Name the sample taken for the reassessment."; "Say which containers were sampled and where the lot is stored."; "Enter a date."; "The sample cannot be taken in the future."; "Enter a quantity greater than zero."; "Another reassessment already uses this sample reference."
- **Concurrent starts**: the lot is locked while the reassessment is created. Two people starting at the same moment get one reassessment; the second is refused because the first is open. Nothing is saved on a refusal.
- **Freezes the dates it started from**: the lot's expiry date and retest date in force when it was started are kept on the reassessment ("Retest date when started").
- **Effects**: the reassessment and the audit event `lot.reassessment_started` (with the reason, sample reference, date sampled, quantity, containers and the dates in force) are committed together. The lot's revision does not change, and no test exists yet.
- **Independence**: whoever starts a reassessment is an author of it and cannot conclude it, even with the quality role.
- Not enforced by this page: that the sample was taken from the containers stated, or that the material is the lot's; the record is the person's statement.

## Related pages

- Lot record (starts here and returns here)
- Reassessment record (opens after starting)
- Assign reassessment tests; Conclude reassessment
