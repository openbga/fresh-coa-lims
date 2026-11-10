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

- Breadcrumbs, title, introduction, the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Link evidence** | Always | Role: Analyst only; others receive 403 | Saves, shows a confirmation message and opens the next page; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Sample reference | `Pull.sample` | Text, max 80 | One of the two | Must exist and belong to the study's lot |
| External sample ID / External evidence reference | `Pull.external_sample_ref`, `.evidence_ref` | Text | Both if no sample | Controlled external link |
| External evidence link | `Pull.evidence_url` | http(s) URL | No | Untrusted external link |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Messages: "No sample has this reference."; "The sample belongs to a different lot than the study."; "Link a sample, or give the external sample and evidence references."
- Allowed until acceptance; earlier links stay in the history as before/after values. A sample is evidence for one pull only ("The sample is already evidence for …; each pull needs its own sample.") and must be collected on the pull date ("The sample was collected on <date>, not on the pull date <date>; it cannot be this pull's evidence."). The documenting analyst cannot later accept the pull. Event `pull.evidence_linked`.

## Related pages

- Pull record
