---
title: Record notification
urls: reporting:notify
views: reporting.views.notify
templates: reporting/notify.html
models: reporting.RecipientNotification, reporting.Report, core.AuditEvent
reviewed: 2026-11-17
summary: Record that a recipient was told a certificate of analysis is withdrawn: who, when, how, and where the evidence is kept. Quality only, for a withdrawn certificate.
---

## Common tasks

### Record that the recipient was told

1. Check [[Recipient notified]]. It starts as the certificate's Issued to; change it to the person or company you told.
2. Enter the [[Date notified]] and choose the [[Means]].
3. Enter the [[Evidence reference]]: where the notice and any acknowledgement are kept.
4. Select [[Record notification]]. You return to the certificate record.

### Record a further notification

1. On the certificate record, select [[Record notification]] in [[Recipient notifications]], then fill in the form again.

## Good to know

- A notification cannot be changed or removed once recorded. Record a further one if something was missed.
- The date cannot be in the future or before the day the certificate was withdrawn.
- A note is required when the means is Other.
- Recording a notification does not sign or change the certificate; it is kept in the certificate's history.

## Purpose

Keep the evidence that a recipient of a withdrawn certificate of analysis was told that it is withdrawn. Each notification is an append-only record on the certificate; several can be recorded.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- Only for a withdrawn certificate: opening the page for any other certificate returns to the certificate record with "A recipient notification is recorded only for a withdrawn certificate."; a direct submission is refused with the same message.
- The **Record notification** button shows on the certificate record only to quality users while it is withdrawn: in the page header while no notification is recorded, then in the **Recipient notifications** panel.

## Layout

- Breadcrumbs (Certificates, the certificate number, Record notification), the line "Record that a recipient was told the certificate is withdrawn, and where the notice and any acknowledgement are kept. A notification cannot be changed or removed once recorded."
- **Certificate** panel: Certificate, Status (Withdrawn), Issued to ("General certificate (no named recipient)" when blank), Withdrawn (time and signer).
- The form, with "The notification is recorded in the certificate's audit trail with your name." in the required-fields note, **Cancel** and **Record notification**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record notification** | Always | Quality | Records the notification; returns to the certificate record with "Notification of … recorded." |
| **Cancel** | Always | Any | Returns to the certificate record; nothing is recorded |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Recipient notified | `RecipientNotification.recipient` | Text, max 160 | Yes | Who was told. Starts as the certificate's Issued to |
| Date notified | `RecipientNotification.notified_on` | Date (local) | Yes | When they were told |
| Means | `RecipientNotification.means` | Email, Letter, Telephone, In person, Other | Yes | How they were told |
| Evidence reference | `RecipientNotification.evidence_ref` | Text, max 200 | Yes | Where the notice and any acknowledgement are kept, for example a document number or the location in your controlled records |
| Note | `RecipientNotification.note` | Text, max 2000 | With Other | Anything else; required when the means is Other |
| Recorded by, Recorded (shown on the record) | `RecipientNotification.recorded_by`, `recorded_at` | User, server time | — | Set by the server |

## Rules and hidden logic

- **Checked under lock**: your account, then the certificate, are locked; the certificate must be withdrawn. Errors show at their fields and your entries are kept: a blank recipient, means or evidence reference shows "This field is required."; "Describe how the recipient was notified." (Other without a note); "The date notified cannot be in the future." and "The certificate was withdrawn on YYYY-MM-DD; the date notified cannot be earlier." Dates are compared with the local date.
- **Effect**: one notification row and the audit event `report.recipient_notified` on the certificate, with the notification's content, in one transaction. The certificate's state, its revision and its signatures do not change; the certificate stops showing "Recipient notification not recorded" and leaves the Awaiting notification filter.
- **Database guard**: notifications cannot be changed or deleted, are accepted only for a withdrawn certificate (the insert waits for a withdrawal being signed) and must name the recipient and the evidence reference.
- **Exported record**: the lot's exported record includes the notifications of its certificates.

## Related pages

- Certificate record (Cancel returns here), Withdraw certificate
- [Certificates of analysis](/reports/)
