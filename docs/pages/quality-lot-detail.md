---
title: Lot record
urls: quality:lot_detail
views: quality.views.lot_detail
templates: quality/lot_detail.html
models: quality.Lot, quality.Sample, quality.Result, core.RuleSet, core.ElectronicSignature, sampling.LotAssignment, reporting.Report
reviewed: 2026-11-11
---

## Purpose

The hub for one material lot: its facts and samples, links to its requirements, sampling and native testing, the signed QC disposition that releases it, and its certificates of analysis.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- **Add sample** and **Record result**: analysts only.
- **Review result**: reviewers only, and never the analyst who recorded that result.
- **Review disposition** and **Issue certificate of analysis**: quality role only.
- Scientific action links require their corresponding role as well as the state condition. Admin-only viewers see records and navigation links, without laboratory mutation controls. The server independently checks roles, independence and state.

## Layout

- **Back link**: "Material lots".
- **Facts**: Material, Status, Rule set, Record revision.
- **Actions row** (Quarantine lots only): **Add sample**, **Review disposition**.
- **Requirements line**: **Requirements and sampling** with the assignment status ("Requirements assigned", "Applicability hold" or "Not assigned"), and **Testing and investigations**.
- **Samples and results**: one card per sample with its collection time, a **Record result** link (Quarantine lots only) and the foundation results table: Test, Result, Limits, Analyst, Review. This table shows only manual foundation results; native observations, reviews and investigations are on Testing and investigations. "No results recorded." here does not mean no native testing exists. "No samples recorded." when the lot has no samples.
- **Certificates of analysis** (Released lots only): **Issue certificate of analysis** for quality users, then links to issued reports, or "No certificate issued yet."
- **Electronic signatures**: foundation result review signatures, then lot disposition signatures, or "No lot disposition signature yet." Native test review signatures are not listed here.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add sample** | Analyst role and lot is Quarantine | Analyst | Opens Add sample for this lot |
| **Review disposition** | Quality role and lot is Quarantine | Quality, independent of the lot's data | Opens Sign lot disposition |
| **Requirements and sampling** | Always | Viewers of that page | Opens the lot's requirement assignment and sampling records |
| **Testing and investigations** | Always | Viewers of that page | Opens native tests, observations, reviews and investigations |
| **Record result** | Analyst role and lot is Quarantine | Analyst | Opens the development-only manual result form; saving is refused outside DEBUG or once requirements are assigned |
| **Review result** | Reviewer role, result is Recorded and not its analyst | Reviewer, not its analyst | Opens Sign result review |
| **Issue certificate of analysis** | Quality role and lot is Released | Quality | Opens the certificate preview for this lot |
| Report number link | Lot is Released and a report exists | Viewers of reports | Opens the certificate record |
| **Material lots** | Always | Any viewer | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot number (heading) | `Lot.number` | Text | — | Lot identifier |
| Material | `Lot.material` | Text | — | Material received |
| Status | `Lot.state` | Quarantine, Released | — | Released only by signed disposition |
| Rule set | `Lot.rules` | "code vN" | — | Foundation rule revision chosen at receipt |
| Record revision | `Lot.revision` | Integer | — | Rises with each change to the lot, its samples, tests or holds; disposition signatures bind to it |
| Assignment status | `LotAssignment.status` (latest) | Requirements assigned, Applicability hold, or "Not assigned" | — | Whether approved specification and sampling requirements are attached |
| Sample heading | `Sample.reference` | Text, unique | — | Sample identifier |
| Collected | `Sample.collected_at` | Date and time | — | Labelled UTC; shown in the deployment time zone (default UTC) |
| Test, Result, Limits, Analyst, Review | `Result.test_code`, `value`, `unit`, `lower_limit`, `upper_limit`, `analyst`, `state` | Text, decimal with unit | — | Foundation manual results only; "Out of specification" when outside the inclusive limits |
| Report link | `Report.number` | Text | — | Issued certificates for this lot |
| Signature lines | `ElectronicSignature.object_id`, `revision`, `signer_name`, `meaning`, `signed_at` | Text, integer, date-time | — | Who signed which meaning, when, bound to which revision |

## Rules and hidden logic

- **Quarantine only**: samples and foundation results are accepted only while the lot is Quarantine ("Only quarantined lots accept new samples.").
- **Record result link vs. permission**: the link stays visible to analysts on Quarantine samples, but saving is refused with "Record observations through approved native testing requirements." unless the server runs in DEBUG and the lot has no requirement assignment. Record native results through Testing and investigations.
- **Release paths**: with assigned requirements or native tests (and always outside DEBUG), release depends on the assignment, sampling records, native analytical evidence and holds. The manual foundation path (required rule-set tests, reviewed and conforming results) applies only in DEBUG on lots with neither. See Sign lot disposition for every condition and message.
- **Revision and stale pages**: signing pages bind to the revision shown when opened (the result's for review, the lot's for disposition); if it changed, signing fails with "Record changed. Reload and review before signing."
- **Independence**: no user dispositions a lot containing their own sampling or test data, even when holding the quality role. **Review disposition** still shows for them; the disposition page explains the refusal before any PIN is requested.
- **No reject path**: this version only releases; a lot that cannot be released stays in Quarantine.
- **Review link after release**: a Recorded foundation result still shows **Review result** to independent reviewers on a released lot, but signing is refused ("This result is not awaiting review.").
- **Certificates**: the section appears only after release; issuing is a separate signed step on the certificate pages.

## Related pages

- [Material lots](/)
- Lot requirements and sampling; Lot testing (Testing and investigations).
- Add sample, Record result, Sign result review, Sign lot disposition.
- Review certificate; Certificate record.
- [Audit trail](/audit/)
