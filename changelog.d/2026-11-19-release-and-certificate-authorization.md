---
date: 2026-11-19
pr: 65
type: added
impact: high
title: Reserve the release of lots and their certificates for people qualified to authorize them
area: Laboratory
link: laboratory:qualification_list
---
A rule set can now reserve the release of its lots and the certificates issued for them for quality people who hold a current qualification for an activity it names. Qualifications have two new kinds under **Qualified for**: **Release decisions** and **Issuing certificates**. Where a lot's rule sets reserve them, the release, a reassessment concluded **Suitable**, and each certificate issue and amendment are refused before the PIN is asked for unless the signer holds the qualification. The signed decision keeps which qualification it relied on, and the lot record, the reassessment, the certificate version and the qualification's own page show it. Rejection, cancellation and certificate withdrawal are not reserved, and rule sets without the new setting work as before.

## Technical notes

- New optional rule policy key `authorization`, an object with `release`, `certificate` or both, each an activity code of at most 120 characters. `validate_policy` accepts it; earlier rule set versions are unchanged.
- Migration `laboratory.0007` adds the `Qualification.work` choices `release` and `certify` and updates help text. No existing row changes, and no schema or trigger changes.
- The qualifications relied on are stored as `authorization` (a list of `activity`, `rule_sets` and `qualification`), only where something is reserved: in `Lot.disposition_evidence` for a native release, in `Reassessment.result_evidence` for a suitable conclusion, and in `ReportVersion.snapshot["report"]` for a certificate version. The signature content binds each one. Certificate evidence hashes, certificate data and PDFs are unchanged.
- On the qualification list and record, the **Type** of a person's qualification reads **Person** instead of **Analyst**.
