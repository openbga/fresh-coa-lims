---
date: 2026-11-18
type: added
impact: high
title: Issue a certificate for a customer or a market of the lot, with each result judged against every specification
area: Certificates
link: reporting:list
pr: 55
---
For a lot under more than one specification, such as the general one and a customer's, the certificate now states for every result whether it conforms to each specification that states the test, including one the lot was not tested against, and says how conformity is judged. On **Review certificate**, **Certificate for** lets quality issue a certificate for one customer or market of the lot instead: it lists the tests that specification states, with its limits, names no other customer or market, and is refused while a result does not meet them. The certificate list, record and versions show the scope, and each method is now listed once on a certificate.

## Technical notes

- Migration `reporting.0004_certificate_scope`: `Report.scope` (blank for all of the lot's requirements) and a replaced head guard: the scope is fixed once a version is issued, and only a record opened but never issued takes another scope (audit action `report.scope_changed`). A recipient's issued certificate is amended, or withdrawn before a certificate for another scope is issued to the same recipient. Reversing the migration restores the guard of `reporting.0003`.
- The certificate evidence of a lot whose frozen requirements name more than one specification gains `native.conformity` (each reportable result and accepted supplier result with one statement per specification: `conforms`, `does_not_conform`, `not_judged` with a reason, `information` or `not_tested`); the issued snapshot keeps the scope under `report.scope`. Evidence of a lot under one specification is unchanged.
- The judgement uses the testing rules on the recorded readings, with no conversion of unit, result type, outcome criterion, replicate count, method or retest allowance, and no measurement uncertainty (simple acceptance).
