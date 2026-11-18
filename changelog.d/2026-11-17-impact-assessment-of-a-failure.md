---
date: 2026-11-17
type: added
impact: high
title: Assess the impact of a failure on tests, lots, stability studies and certificates
area: Impact assessments
link: impact:list
pr: 54
---
When equipment, a reagent or standard, a supplier, a contract laboratory or anything else fails, a quality person starts an assessment under **Impact assessments**, or with **Assess impact** on the page of the record that failed, for the period the problem may have affected. The system lists the tests, lots, stability studies and certificates it can find from the cause; quality adds any other, records for each whether it was **Affected** and what is done about it, and can **Place hold** on an affected lot. A quality person who took no part in it concludes the assessment with a signature, and the lot record and the dashboard show the assessments open.

## Technical notes

- New app `impact` with migrations `impact.0001_initial` and `impact.0002_impact_guards` (the `Assessment` and `Item` tables and their database guards).
- Audit actions `impact.started`, `impact.records_found`, `impact.record_added`, `impact.record_decided` and `impact.hold_placed`; signature meanings `impact_assessed` and `withdrawn` on `impact.assessment`. The conclusion freezes `oq.impact-assessment/1`.
- A hold placed through an assessment is an ordinary `stability.Hold` of kind `quality` whose reference names the assessment. New remote lookups `equipment`, `reagent-lots` and `contract-laboratories`.
- The lot record export gains the section `impact_records` (the lot's records in assessments, not the assessments, which name other lots); the dashboard gains the queue **Impact assessments open**.
