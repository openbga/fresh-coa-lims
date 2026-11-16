---
title: Pull record
urls: stability:pull_detail
views: stability.views.pull_detail
templates: ops/record.html
models: stability.Pull, analytical.AnalyticalTest, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

One scheduled pull: timing, collection details, its own tests, a linked sample or external evidence, and acceptance.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs (Studies, the study, the pull), title (condition and timepoint label), identifier (study ID and pull number) and status label, action buttons.
- **Details**: the facts below.
- **Notice** (only when an investigation confirmed a result outside the acceptance criteria of a test of this pull): "Criteria not met" with the text that the record of the study's lot is not changed by a stability result and that any hold or other action on that lot or other lots is for quality to decide.
- **Tests**, in three forms. (1) When the pull has tests of its own: one row for each test of its time point, including reruns and retests, with columns Test (label, name and code; links to the test), Result and status, Acceptance criterion (the one frozen on that test) and Kind; a time-point test without a test shows "No test assigned". Above the table a note says "The pull cannot be accepted yet: …" with each blocker, "Every test is reviewed: the pull meets the acceptance criteria. A reviewer can accept it." (or "does not meet"), or after acceptance "Accepted: <outcome>." (2) When the pull is Pulled with no sample or tests and tests cannot be assigned: a status giving the reason, with the note "This pull is not tested in the system." (3) When it is Pulled with nothing linked and nothing prevents assigning: "No tests assigned yet. An analyst assigns the tests of this time point to test the pull in the system, or links a sample or external evidence instead."
- **Testing evidence** (only when the pull is Pulled and has a linked sample): each current blocker, or "Required tests reviewed and conforming", with a note that acceptance needs every required test reviewed, conforming and free of open investigations.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record pull** | Scheduled and study active | Analyst | Opens the form |
| **Mark missed** | Scheduled and today is after the window closes | Analyst, Quality | Opens the reason form |
| **Assign tests** | An Analyst, the pull is Pulled and its study Active, the protocol names a specification, no sample or external evidence is linked, the specification can state every test of the time point (primary button while the pull has no tests; shown again while a test of the time point is still missing) | Analyst | Opens the Assign pull tests page |
| **Link evidence** | Pulled, and the pull has no tests | Analyst | Opens the evidence form; a pull with tests never shows it |
| **Accept pull** | Pulled; for a pull tested in the system, only once every test has a reviewed result and no investigation is open; you are a Reviewer and are not the puller, anyone who ever linked its evidence, (for a linked sample) the sample's creator or a data or investigation author of its tests, or a data or investigation author of the pull's own tests | Reviewer | Opens the signing page |

For a pull tested in the system the button is hidden while testing is incomplete; the Tests section says what is still open, and opening the signing page directly states why it cannot be signed. The server checks each again (study active, state, role, independence).

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Study | `Pull.study` | Link | — | Parent study |
| Due / Window / Required tests | `Pull.due_date`, `ProtocolTimepoint.window_days`, `.test_codes` | Dates, codes | — | Schedule; window is due date minus/plus window days |
| Pulled on / Pulled by / Quantity / Held at / Chamber | `Pull.pulled_on`, `.pulled_by`, `.quantity` with `.quantity_unit`, `.storage_location`, `.chamber` | Date, user, decimal with unit, text, equipment | — | Collection; blank until recorded |
| Sample | `Pull.sample` | Sample reference | — | Linked testing-spine sample |
| External sample / External evidence | `Pull.external_sample_ref`, `.evidence_ref`, `.evidence_url` | Text, link | — | External stability system; shown as a link when a URL is given |
| Deviation / Missed reason | `Pull.deviation_reason`, `.missed_reason` | Text | — | Exceptions |
| Accepted | `Pull.accepted_at` | Time | — | Signature time of acceptance |
| Outcome | `Pull.outcome` | "Meets the acceptance criteria", "Does not meet the acceptance criteria" or blank | — | Set with the acceptance of a pull tested in the system; blank for a pull accepted on a linked sample or external evidence |
| Revision | `Pull.revision` | Integer | — | Raised by each change |

## Rules and hidden logic

- Results stay in the testing module; this page only reports them and whether acceptance would be blocked. Blockers come from the pull's own tests or, for a linked sample, that sample's tests and investigations. A pull is tested in the system or linked to other evidence, never both.
- A pull's tests belong to the pull and name no lot: assigning, recording and reviewing them does not change the study's lot.
- A test code counts as conforming when a reviewed conforming result stands (an investigation of it, if any, was invalidated) and as failing when an investigation confirmed an out-of-specification result. The outcome is set only when every test of the time point is decided and nothing blocks; one failing test makes the pull "does not meet".
- History shortens a long structured value (such as the results frozen with an acceptance) to "structured record with N entries, kept in full in the audit trail".
- **State**: Scheduled (Upcoming, Due or Overdue by window) -> Pulled -> Accepted, or Scheduled -> Missed. Accepted and Missed are final.
- **Independence**: the Reviewer who accepts must not be the user who recorded the pull, anyone who ever linked its evidence (from the audit history, so re-linking does not clear an earlier recorder), for a linked sample its creator or a data or investigation author of its tests, or a data or investigation author of the pull's own tests (including their investigations).
- **Audit**: events `pull.recorded`, `pull.evidence_linked`, `pull.missed`, the test assignment and the signed acceptance appear in History and Signatures.

## Related pages

- Study record
- Assign pull tests, Record pull, Link pull evidence, Mark pull missed, Accept pull (from the actions)
- [Stability pulls](/stability/pulls/)
