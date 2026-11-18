---
title: Withdraw certificate
urls: reporting:withdraw
views: reporting.views.withdraw
templates: reporting/withdraw.html
models: reporting.Report, reporting.ReportVersion, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: Sign the withdrawal of an issued certificate of analysis. Quality only. The certificate stops being valid; every issued version and its PDF stay exactly as issued.
---

## Common tasks

### Withdraw the certificate

1. Check the certificate, lot, recipient and current version shown.
2. Enter the [[Reference]] of the record behind the withdrawal, if there is one, and the [[Reason for withdrawal]].
3. Enter your [[Signing username]] and [[Signature PIN]], then select [[Sign and withdraw]].
4. You return to the certificate record, now Withdrawn. Tell the recipient, then record the notification there.

### Find out why you cannot withdraw

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Withdrawal is final. A withdrawn certificate is never amended or issued again.
- Nothing issued changes: every version and its PDF stay on record and can still be downloaded.
- The quality person who issued the certificate may withdraw it.
- A new certificate for the same lot and recipient can be issued afterwards. It gets a new number.

## Purpose

Sign a certificate of analysis with meaning **withdrawn**: it stops being valid when you sign. Every issued version and its stored PDF are kept unchanged, and the certificate then waits for its recipient notification to be recorded.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- Refused with the reason and no PIN control (403): "Only an issued certificate can be withdrawn." (a record with no issued version) and "This certificate is already withdrawn.".
- The **Withdraw certificate** item shows under **More** on the certificate record only to quality users while the certificate is issued.
- Not enforced by this page: a different person from the issuer. Withdrawal protects the recipient, so there is no independence rule.

## Layout

- Breadcrumbs (Certificates, the certificate number, Withdraw), then a signing dialog (a plain card without JavaScript): the record and revision, what the withdrawal means, the facts Certificate, Lot (with material), Issued to ("General certificate (no named recipient)" when blank) and Current version (number, issue time and signer), the signer, the PIN link, the form, **Cancel** and **Sign and withdraw** (outlined in red). Opening the page never signs.
- **Denied**: the facts, a red "Not permitted" notice with the reason and **Back to record** (403).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and withdraw** | Not denied | Quality | Signs with meaning **withdrawn**; returns to the certificate record with "CoA-… withdrawn; every issued version is kept. Record the notification of its recipient." |
| **Cancel** / Escape | Always | Any | Returns to the certificate record; nothing is signed |
| **Back to record** | Denied | Any | Returns to the certificate record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Certificate, Lot, Issued to, Current version | `Report.number`, `Report.lot`, `Report.recipient`, latest `ReportVersion` | Display | — | What the signature binds |
| Reference | `Report.withdrawal_reference` | Text, max 200 | No | The impact assessment, deviation or other quality-system record behind the withdrawal, e.g. "IA-3" |
| Reason for withdrawal | `Report.withdrawal_reason`, audit event reason | Text, max 2000 | Yes | Why the certificate is no longer valid. Kept with the signature and shown on the certificate record |
| Signing username | — | Text | Yes | Must equal your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Report.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You withdraw this certificate: it stops being valid when you sign, and it cannot be amended afterwards. Every issued version and its PDF stay on record exactly as issued. Notify each recipient that it is withdrawn, then record the notification on the certificate record."
- **Checked again when signing**, under the certificate's lock: the certificate is still issued and still at the revision you opened ("Record changed. Reload and review before signing." otherwise). A blank reason is refused ("This field is required.").
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN; a wrong username, wrong PIN, expired session or locked PIN is refused inline and nothing changes. Failed PIN attempts are counted and audited even though the withdrawal is refused (five failures lock the PIN for 15 minutes).
- **Effect**: one transaction sets the state to Withdrawn with the signing time, the reason and the reference, raises the revision by 1, writes the audit event `signed.withdrawn` and an immutable signature bound to the new revision. The versions, their PDFs and checksums, and the head's current checksums are not changed.
- **Database guard**: the withdrawal details can be set only by this transition, from issued, with one revision step and the versions unchanged; a withdrawn certificate never changes again and is never deleted.
- **Afterwards**: the certificate cannot be amended. Issuing a certificate for the same lot and Issued to creates a new certificate record with the next number; the withdrawn one keeps its number.

## Related pages

- Certificate record (Cancel returns here), Record notification
- [Certificates of analysis](/reports/)
- [Signature PIN](/signature-pin/)
