---
title: Record result (development-only manual result)
urls: quality:result_new
views: quality.views.result_new
templates: quality/form.html
models: quality.Result, quality.Sample, quality.Lot, core.RuleSet
reviewed: 2026-11-10
---

## Purpose

Development-only fallback for entering one foundation result with manual limits on a sample. It is not the normal results page: record native observations against approved requirements from Testing and investigations.

## Who can use it

- Sign-in required. **Analysts** only; others receive 403. The signed-in user becomes the result's analyst and can never review it.
- An analyst can always open the form, but saving works only when the server runs in DEBUG and the lot has no requirement assignment.

## Layout

- Title "Record result · <sample reference>", the form, **Record result** and **Cancel**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record result** | Always | Analyst | DEBUG and unassigned lot only: saves the result as Recorded and returns to the lot record; otherwise refused |
| **Cancel** | Always | Any | Returns to Material lots without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | Audit event reason | Text, max 2000 | Yes | Why the result is recorded |
| Test code | `Result.test_code` | Text, max 80; default `identity` | Yes | Must be a required test of the lot's rule set |
| Value | `Result.value` | Decimal, up to 20 digits, 8 decimals | Yes | Reported value, stored exactly |
| Unit | `Result.unit` | Text, max 40 | Yes | Unit for value and limits |
| Lower limit | `Result.lower_limit` | Decimal, same unit | Yes | Inclusive lower acceptance limit |
| Upper limit | `Result.upper_limit` | Decimal, same unit | Yes | Inclusive upper acceptance limit |

## Rules and hidden logic

- **Fallback only**: "Record observations through approved native testing requirements." when DEBUG is off or the lot has any requirement assignment. Use Testing and investigations instead; the rules below apply only to this fallback.
- **Lot state**: only Quarantine lots accept results ("Only quarantined lots accept results.").
- **Test allowed**: "Test is not required by this lot's rule set." when the code is not in the rule set's required tests; the rule set must still be approved and effective.
- **Limits**: "The lower limit must not exceed the upper limit."
- **One result per test**: a sample holds at most one result per test code.
- **Conformance**: lower ≤ value ≤ upper. A value outside is shown as "Out of specification" and blocks review and release on the manual path. This form has no correction step; native observations have their own correction page.
- **Mixed evidence**: a lot that later gets native requirements cannot be released while it holds these results ("Mixed foundation and native evidence requires reconciliation.").
- **Revision and audit**: lot revision +1; writes `result.recorded` with all entered values.

## Related pages

- Lot record.
- Lot testing (Testing and investigations): native observations.
- Sign result review.
