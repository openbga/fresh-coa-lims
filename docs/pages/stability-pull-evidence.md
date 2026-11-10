---
title: Link pull evidence
urls: stability:pull_evidence
views: stability.views.pull_evidence
templates: ops/form.html
models: stability.Pull, quality.Sample, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Link the sample registered for testing, or an external stability system's records, to a pulled pull.

## Who can use it

- Sign-in required. Role: Analyst only; others receive 403.

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

- Messages: "Evidence can be linked only to a pulled, unaccepted pull." (also when the study is closed); "No sample has this reference."; "The sample belongs to a different lot than the study."; "Link a sample, or give the external sample and evidence references."
- Allowed until acceptance; earlier links stay in the history as before/after values. A sample is evidence for one pull only ("The sample is already evidence for …; each pull needs its own sample.") and must be collected on the pull date ("The sample was collected on <date>, not on the pull date <date>; it cannot be this pull's evidence."). The sample must not be dated in the future ("The sample cannot be collected in the future."). The user who links evidence is recorded and cannot later accept the pull. Each save replaces the previous links and sets the revision up by 1. Event `pull.evidence_linked`.

## Related pages

- Pull record
- Accept pull (a Reviewer other than the puller and the linker signs it later)
