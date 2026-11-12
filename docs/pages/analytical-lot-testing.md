---
title: Lot testing
urls: analytical:lot_testing
views: analytical.views.lot_testing
templates: analytical/lot_testing.html, analytical/_test_status.html, analytical/_investigation_status.html
models: quality.Lot, quality.Sample, analytical.AnalyticalTest, analytical.Investigation
reviewed: 2026-11-12
---

## Purpose

Show a lot's analytical evidence by sample, say what still blocks QC disposition, and let analysts assign the lot's required tests to each sample.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Assign required tests**: analysts only, and only while the lot is Quarantine. The button is hidden otherwise; the server also requires the analyst role.
- **Admin** or **auditor** alone see no assign button, and a posted assignment is refused with 403 before the sample or reason is read.

## Layout

- **Header**: "LOT testing", lot status (Quarantine or the lot's state), material, Rule set, Lot revision; **Lot record** button.
- **Analytical evidence for QC disposition**: either **Blocked** with the list "QC disposition cannot be approved until these are resolved:" or **Complete**.
- **One card per sample** (collection order): sample reference, test count, **Assign required tests**, collection time, and a table: Test, Code, Kind, Status, Reportable, Acceptance and specification. Empty: "No tests assigned".
- **No samples**: "No samples recorded" with a **Lot record** link.
- **Investigations**: list with status and trigger, or "No investigations".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign required tests** (per sample) | Lot is Quarantine and user is an analyst | Analyst | Posts to this page; creates the missing original tests for that sample; redirects back here |
| **Lot record** | Always | Any viewer | Opens the quality lot record |
| Test and investigation links | Rows present | Any viewer | Open the test or investigation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Rule set | `Lot.rules` | "code vN" | — | Rule revision of the lot |
| Lot revision | `Lot.revision` | Integer | — | Rises with every evidence change; a disposition opened earlier then becomes stale |
| Status | `AnalyticalTest.state`, `conforms` | Text | — | Open, Awaiting review, Reviewed · conforms, Out of specification (awaiting review or reviewed), Invalidated |
| Reportable | `AnalyticalTest.reportable_text` | Text with unit (no unit for qualitative tests) | — | As frozen at submission, e.g. "99.8", "<10" or "Absent"; "—" until submitted |
| Acceptance and specification | `AnalyticalTest.requirement` | Text | — | Acceptance text (for example "less than 0.10 %" or "Absent in 25 g (expected: Absent)") above the source and revision of the frozen requirement |
| Reason (hidden) | `AuditEvent.reason` | Text | Yes | Fixed text: "Assign required tests from the lot's approved requirements" |
| Sample (hidden) | `AnalyticalTest.sample` | Sample of this lot | Yes | The card's sample; a sample of another lot, or a value that is not a whole-number ID of at most 19 digits, returns 404 |

## Rules and hidden logic

- **Requirements come from a configured provider** of approved specifications; tests freeze the requirement and its hash at assignment, so later revisions do not change them. Not enforced by this page: which specifications are approved, or that the provider's data is correct. With no provider every requirement is held.
- **Assign**: needs an approved, effective rule set ("An approved, effective rule revision is required."); lot must be in quarantine ("Lot ... is no longer in quarantine."). Only supported requirements become tests; the others are listed as warnings "Held: ..." and appear as blockers. Existing original tests are not duplicated. Messages: "Assigned N test(s) to REF.", "Every required test is already assigned to this sample.". A failed reason shows "Enter a reason to assign tests.".
- **Revision**: creating at least one test raises the lot revision by 1 and writes a `test.assigned` audit event per test.
- **Blockers** include open or confirmed investigations, tests that are incomplete, awaiting review or non-conforming, held requirements, and samples missing a required test or a reviewed conforming result. A result tested under a requirement that differs from the lot's current approved requirement never counts ("... was tested against a superseded requirement; ...").
- **Complete** means every required test has a reviewed, conforming result and no investigation is open. This is laboratory evidence only; QC disposition is a separate signed decision and does not mean manufacturer release.
- Resample or rerun-only samples answer for the sample they replace.

## Related pages

- [Testing: tests](/testing/)
- [Material lots](/)
- Lot record, Test record, Investigation record.
