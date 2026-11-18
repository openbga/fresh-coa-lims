---
date: 2026-11-17
type: added
impact: high
title: Withdraw an issued certificate with a signature and record that its recipients were notified
area: Certificates
link: reporting:list
pr: 54
---
A quality person withdraws a certificate of analysis that can no longer be relied on with **Withdraw certificate** under **More** on its page, stating why and, optionally, the impact assessment or quality-system record behind it. The certificate then shows **Withdrawn** and takes no amendment; every issued version and its PDF stay exactly as issued, and a later certificate for the lot is a new numbered one. **Record notification** keeps who was told, when, how and where the evidence is kept; the certificate list filters **Withdrawn** and **Awaiting notification**, and the dashboard counts withdrawn certificates whose recipients are not yet recorded as notified.

## Technical notes

- Migration `reporting.0003_certificate_withdrawal`: `Report.withdrawn_at`, `withdrawal_reason` and `withdrawal_reference`, the state `withdrawn`, the partial unique constraint `report_lot_recipient_current` in place of `report_lot_recipient`, the `RecipientNotification` table, a replaced head guard and an append-only guard on notifications. Reversing it is refused while a withdrawn certificate exists.
- Signature meaning `withdrawn` on `reporting.report`; audit action `report.recipient_notified`. The lot record export gains the section `report_notifications`.
- The dashboard's **Certificates to issue** counts a released lot again once all its certificates are withdrawn.
