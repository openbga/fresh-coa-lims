---
date: 2026-11-15
type: added
impact: high
title: Results reported by contract laboratories under a signed approval
area: Laboratory
link: laboratory:contract_laboratory_list
pr: 27
---
Quality keeps a register of contract laboratories and approves each laboratory for the methods it may perform, with a second quality person signing. An analyst records what the laboratory's report states for a test, and the result follows the usual review, disposition and certificate path.

## Technical notes

- Results from contract laboratories: quality keeps a register of contract laboratories and, for each method a laboratory may perform, an approval with an evidence reference and validity dates that a second quality person signs and that can be revoked. An analyst records what the laboratory's report states for a test (the laboratory, the report number and date, where the report is kept and every replicate). The entry is refused unless an approval covers the date of the report, and the approval relied on is kept with the result. The result then follows the usual path: independent review, investigation of a failing result, QC disposition and the certificate of analysis, which names the laboratory and its report. The laboratory's and the approval's pages list the results that relied on them.
- A bench class named by `ANALYTICAL_BENCH` now also answers for contract laboratories (`contract_choices`, `authorize_contract`, `record_contract_refusal`, `contract_notice`). A deployment that replaced the bench must add them.
- A test that holds a result reported by a contract laboratory can be submitted and reviewed without a QC batch, and its replicates are corrected together from **Correct contract laboratory result**.
