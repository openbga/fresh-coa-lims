---
date: 2026-11-17
type: added
impact: high
title: Record a lot's expiry and retest dates, checked at release and printed on the certificate
area: Lots
link: quality:lot_list
---
An analyst or quality person records a lot's **Expiry date** and **Retest date** with their basis from the lot record while it is in quarantine; a correction keeps the record it replaces, and whoever recorded them cannot sign the lot's disposition. The release is refused after the expiry date and from the retest date on, and when a date the rule set requires is missing. The certificate of analysis prints the dates, released lots show **Retest due** or **Expired**, and **Material lots** can list lots by their dates.

## Technical notes

- Migration `quality.0013_lot_dates` adds the append-only `LotDates` table with its database guards. Audit actions `lot.dates_recorded` and `lot.dates_corrected`.
- A rule policy may carry `material_dates` (`expiry`, `retest`, `expiry_or_retest` or `expiry_and_retest`); rule sets without it require no dates.
- For a lot with dates, the release's `disposition_evidence`, the rejection and cancellation evidence and the certificate evidence gain a `dates` key; other lots keep their evidence shape. Certificates are not issued or amended for a lot that has expired or whose retest date has been reached.
