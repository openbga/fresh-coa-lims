---
title: Accept pull
urls: stability:pull_accept
views: stability.views.pull_accept
templates: ops/sign.html
models: stability.Pull, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

Independently review a pull, its evidence (its own tests, a linked sample or external evidence) and the testing outcome, with meaning **reviewed**.

## Who can use it

- Sign-in required. Role: Reviewer.
- Other roles receive 403. A Reviewer who is not permitted sees the reason and no PIN control (403): "You pulled, documented or produced test data for this pull, so you cannot accept it." (checked first), "This pull is not awaiting acceptance." or,  for a pull tested in the system whose testing is incomplete, "Testing is not complete: …" with each blocker.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Title "Accept pull · <timepoint>". A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and review** | Not denied | Role: Reviewer | Signs with meaning **reviewed**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Required tests / Pulled on / Evidence / Deviation | — | Display (Evidence shows "Tested in the system", the linked sample's reference, or the external sample ID) | — | What you are reviewing |
| One line per reported result (pull tested in the system) | — | Display | — | Test name and code, then the test label, its result with unit and "against <acceptance criterion>"; green when it conforms, red when not |
| Outcome recorded with your signature | `Pull.outcome` | "Meets the acceptance criteria" or "Does not meet the acceptance criteria" | — | Shown once every test is decided; stored with the acceptance |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Pull.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: pulled and study active ("This pull is not awaiting acceptance."); you did not pull it, never linked its evidence (any earlier link counts, even if someone re-linked it since) and, for a linked sample, did not create the sample or record, submit or investigate any of its test data (observations including corrected originals, submission, batch QC, investigation entries), whatever other roles you hold ("You cannot accept a pull you pulled, documented or produced test data for.").
- **Tested in the system** (the pull has tests of its own): acceptance needs every test code of the time point decided, no test open or awaiting review, and no open investigation ("Testing is not complete: …" lists the reasons, such as "<code>: no test is assigned." or "<test> awaits independent review."). A reviewed conforming result counts (if it had an investigation, only when invalidated); an investigation that confirmed an out-of-specification result is a decided failing outcome, not a blocker. You also may not have recorded, submitted or investigated any of the pull's own tests. The outcome is "does not meet" if any test code failed, otherwise "meets". It is stored on the pull together with the frozen results (each test's result, acceptance criterion, method, review signature, any investigation and its conclusion), bound by your signature. The record of the study's lot is not changed.
- With a linked sample: it must have been collected on the pull date, not in the future, and not be evidence for another pull. Each required test code needs a reviewed, conforming analytical test created on or after the pull date (tests created earlier are ignored and reported). Any open investigation, or one that confirmed an out-of-specification result, blocks acceptance; a test that was under investigation counts only if the investigation was invalidated ("Testing is not complete: …" lists the reasons); with external evidence both the external sample and evidence reference are required ("Assign and complete the pull's tests, or link a sample or external stability evidence first." when none of the three exists).
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- Meaning text: "You reviewed the pull, its evidence and the linked testing outcome." For a pull tested in the system: "You reviewed the pull and the reviewed results of its tests. Your signature records how they compare with the acceptance criteria and freezes them with the pull; it does not change the record of the lot." Button **Sign and review**; success message "Pull accepted."; the pull becomes Accepted with its acceptance time.
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Pull record (plain name: opened from [Stability pulls](/stability/pulls/))
