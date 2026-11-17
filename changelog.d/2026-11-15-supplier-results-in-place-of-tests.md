---
date: 2026-11-15
type: added
impact: high
title: Rely on a supplier's result in place of a test under a signed qualification
area: Suppliers
link: suppliers:list
pr: 28
---
Quality records a supplier qualification for a supplier, a material and named tests, and a second quality person signs it. Where the lot's rule set allows it, a result on the supplier's certificate can be proposed and then accepted in place of the laboratory's test with a signature.

## Technical notes

- Reliance on a supplier's results: quality records a supplier qualification for one supplier, one material and named tests, with how the supplier's results were confirmed, an evidence reference and validity dates; a second quality person signs it and quality can revoke it. Where the lot's rule set allows it, an analyst proposes a result stated on the lot's current supplier certificate in place of the laboratory's test and a reviewer who neither proposed it nor recorded the certificate or the receipt details signs the acceptance. The proposal is refused unless a signed qualification covers the supplier, the material, the test and the day the lot was received, the certificate states the method and the limits, the stated result meets the specification, no other certificate of the lot contradicts it and the laboratory has not started testing the requirement (a result, a raw-data file, a QC batch or a decision); a refusal by the rule set or for want of a qualification is audited. An accepted result answers its requirement for the whole lot, is listed apart from the laboratory's own results where the disposition is signed and on the certificate of analysis, and can be withdrawn while the lot is in quarantine: a proposal with a reason, a signed acceptance with a signature. An acceptance stops standing, and blocks the disposition, when the certificate record, the receipt's supplier or date, or the requirement it relied on changes. No preset allows reliance, and the software does not decide which tests are identity tests or how often a supplier is confirmed again.
- A rule set policy may carry the optional key `supplier_results` with `own_tests`, the list of test codes the laboratory always performs itself. A rule set without it allows no reliance on supplier results; rule sets approved earlier stay valid unchanged.
- The testing gate asks the class named by the new setting `ANALYTICAL_SUPPLIER_RESULTS` (`lot`, `standing`, `standing_by_lot`) which supplier results were accepted in place of tests. A deployment that replaced the testing adapters must provide it; without the setting no supplier result answers a requirement.
- A supplier certificate result can now count towards QC disposition, but only through a signed acceptance. The lot record, the supplier certificate page and the supplier register say so where they used to say that supplier results never count. The supplier page no longer shows "Not recorded in this register" under Qualification; it lists the supplier's qualifications.
- Whoever proposed a supplier's result in place of a test cannot sign that lot's QC disposition. The refusal now reads "You cannot disposition a lot containing your own receipt, supplier certificate, sampling or test data, or a supplier result you proposed in place of a test."
- A test whose requirement a supplier's result is proposed or accepted for shows "Not tested · supplier result" and takes no observation, reported result, raw-data file or QC batch until that is withdrawn; no test is assigned for such a requirement.
