---
title: Link pull evidence
urls: stability:pull_evidence
views: stability.views.pull_evidence
templates: ops/form.html
models: stability.Pull, quality.Sample, core.AuditEvent
reviewed: 2026-11-17
summary: Link a pulled stability pull to its sample registered for testing, or to an external stability system's records, when it is not tested in the system. Analysts only.
---

## Common tasks
### Link a registered sample
1. Enter the [[Sample reference]] exactly as recorded.
2. Enter a [[Reason]] and select [[Link evidence]].
### Link external stability evidence
1. Enter the [[External sample ID]] and the [[External evidence reference]]. Both are needed.
2. Add the [[External evidence link]] if there is one, enter a [[Reason]] and select [[Link evidence]].
## Good to know
- A pull with tests of its own cannot take linked evidence. A pull is tested in the system or linked to other evidence, never both.
- The sample must belong to the study's lot, be collected on the pull date and not be evidence for another pull.
- Linking again replaces the links. The earlier ones stay in the history.
- Whoever links evidence cannot accept the pull, even after someone else re-links it.

## Purpose

Link the sample registered for testing, or an external stability system's records, to a pulled pull that has no tests of its own.

## Who can use it

- Sign-in required. Role: Analyst only; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Studies, study, pull), title "Link evidence" with the timepoint, the introduction (link the registered sample or the external system's references; earlier links stay in the history), the form in one panel, and a **Cancel** / **Link evidence** row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Link evidence** | Always | Role: Analyst only; others receive 403 | Saves, shows "Evidence linked; independent acceptance needed." and returns to the pull record; refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sample reference | `Pull.sample` | Text, max 80 | One of the two | Sample registered for testing, exactly as recorded (exact match, surrounding spaces ignored) |
| External sample ID | `Pull.external_sample_ref` | Text, max 120 | Both if no sample | Sample or study ID in the external system |
| External evidence reference | `Pull.evidence_ref` | Text, max 200 | Both if no sample | Reference to the external evidence |
| External evidence link | `Pull.evidence_url` | http(s) URL, max 500 | No | Untrusted external link; other schemes are refused |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- A pull that already has tests assigned in the system is not linked: opening or submitting this page shows the warning "This pull is tested in the system: its own tests are its evidence. A pull is tested in the system or linked to other evidence, never both." and returns to the pull record; a save is also refused with that text. Linking evidence and assigning tests exclude each other.
- Messages: "Evidence can be linked only to a pulled, unaccepted pull." (also when the study is closed); "No sample has this reference."; "The sample belongs to a different lot than the study."; "Link a sample, or give the external sample and evidence references."
- Allowed until acceptance; earlier links stay in the history as before/after values. A sample is evidence for one pull only ("The sample is already evidence for …; each pull needs its own sample.") and must be collected on the pull date ("The sample was collected on <date>, not on the pull date <date>; it cannot be this pull's evidence."). The sample must not be dated in the future ("The sample cannot be collected in the future."). The user who links evidence is recorded and cannot later accept the pull. Each save replaces the previous links and sets the revision up by 1. Event `pull.evidence_linked`.

## Related pages

- Pull record
- Accept pull (a Reviewer other than the puller and the linker signs it later)
