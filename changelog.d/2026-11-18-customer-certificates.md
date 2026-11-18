---
date: 2026-11-18
type: added
impact: high
title: Issue a certificate for a customer or a market of the lot, with each result judged against every specification
area: Certificates
link: reporting:list
---
For a lot under more than one specification, such as the general one and a customer's, the certificate now states for every result whether it conforms to each specification that states the test, including one the lot was not tested against, and says how conformity is judged. On **Review certificate**, **Certificate for** lets quality issue a certificate for one customer or market of the lot instead: it lists the tests that specification states, with its limits, names no other customer or market, and is refused while a result does not meet them. The certificate list, record and versions show the scope, and each method is now listed once on a certificate.

## Technical notes

- Migration `reporting.0004_certificate_scope`: `Report.scope` (blank for all of the lot's requirements). It is fixed when the certificate is opened; the existing head guard of `reporting.0003` refuses any change to it. A recipient's open certificate is amended, or withdrawn before a certificate for another scope is issued to the same recipient.
- The certificate evidence of a lot whose frozen requirements name more than one specification gains `native.conformity` (each reportable result and accepted supplier result with one statement per specification: `conforms`, `does_not_conform`, `not_judged` with a reason, `information` or `not_tested`); the issued snapshot keeps the scope under `report.scope`. Evidence of a lot under one specification is unchanged.
- The judgement uses the testing rules on the recorded readings, with no conversion of unit, result type, replicate count or method, and no measurement uncertainty (simple acceptance).
