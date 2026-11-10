---
title: Release reagent lot for use
urls: laboratory:reagent_release
views: laboratory.views.reagent_release
templates: ops/sign.html
models: laboratory.ReagentLot, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Review provenance, certificate and expiry and release a lot for use, with meaning **reviewed**.

## Who can use it

- Sign-in required. Role: Reviewer.
- Other roles receive the standard 403 page.
- A Reviewer who recorded the lot ("You recorded this lot, so you cannot release it.") or opens a lot that is not awaiting release ("This lot is not awaiting release.") sees that reason, the facts and a **Back to record** link, with no PIN control (403).

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): the lot identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and review** | Not denied | Role: Reviewer | Signs with meaning **reviewed**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Name / Supplier lot / Expiry (last day of use) / Certificate | `ReagentLot.name`, `.lot_number`, `.expiry_date`, `.certificate_ref` | Display | — | From the lot record (the certificate reference, not its link) |
| Recorded by | — | Display | — | The person who recorded the lot |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `ReagentLot.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: awaiting release ("This lot is not awaiting release."); you did not record it ("You cannot release a lot you recorded."); not expired ("The lot has already expired."); receipt or preparation date not in the future ("Receipt or preparation cannot be dated in the future."); for a prepared solution, every source lot up its chain is released ("Every source lot must be released for use."). Source expiry or rejection is not rechecked at release; it is checked at each use.
- Meaning text: "You reviewed the provenance, certificate and expiry and release this lot." Success message: "Lot released for use." The release time is the signature time.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Reagent lot record (Cancel returns here)
