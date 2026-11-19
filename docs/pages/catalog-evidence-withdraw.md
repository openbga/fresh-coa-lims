---
title: Withdraw method evidence record
urls: catalog:evidence_withdraw
views: catalog.evidence_views.evidence_withdraw
templates: catalog/form.html, ops/sign.html
models: catalog.MethodEvidence, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: Withdraw an evidence record. A draft is withdrawn with a reason by its recorder or quality; an approved record is withdrawn by quality with a signature.
---

## Common tasks

### Withdraw a draft

1. Explain why in [[Reason]].
2. Select [[Withdraw draft]]. The record opens and shows Withdrawn.

### Withdraw an approved record

1. Check the method versions relying on it, then enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
2. Select [[Sign and withdraw]]. If you are not allowed, [[Not permitted]] shows instead.

## Good to know

- A draft is withdrawn by the person who recorded it or by a quality user. No signature is needed.
- Only quality withdraws an approved record, and signs for it.
- Method versions already approved on it keep it as approved; no draft version can link it again. Replace those versions where the evidence no longer holds.
- A withdrawn record is never deleted. To continue the work, record a new one.

## Purpose

Withdraws a draft that will not be approved, or an approved record that should no longer support new method versions.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403. The role is checked before the record is looked up.
- **Draft**: the person who recorded it, or a quality user. Anyone else with a recording role is sent back to the record with the message "Only the person who recorded this draft or quality withdraws it." (the service refuses the same).
- **Approved**: quality only. Others see "Not permitted" with "Only quality withdraws an approved record." and status 403.
- **Withdrawn**: "Not permitted" with "This record is already withdrawn."

## Layout

- **Draft**: header "Withdraw draft MEV-n" with the introduction "A withdrawn draft stays in the list and its history and can no longer be changed or approved. Only the person who recorded it or quality withdraws it."; record panel (Record, Method); form with Reason; buttons **Cancel** and **Withdraw draft**.
- **Approved**: a signing dialog titled "Withdraw MEV-n" with facts Record, Method, Conclusion and "Method versions relying on it" (for example "v1 (approved)", or "None"); the signer, the PIN link, the form, **Cancel** and **Sign and withdraw**. Opening it never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw draft** | Draft | Its recorder, quality | Withdraws; message "Draft MEV-n withdrawn."; opens the record |
| **Sign and withdraw** | Approved, not denied | Quality | Signs with meaning **withdrawn**; message "MEV-n withdrawn."; opens the record |
| **Cancel** | Always | Same | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason (draft) | audit reason | Text, max 2000 | Yes | Why the draft is withdrawn |
| Signing username (approved) | — | Text | Yes | Must equal your own username |
| Reason for signing (approved) | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN (approved) | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `MethodEvidence.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Draft**: state becomes Withdrawn with the time and the revision increases by 1; audit event `method_evidence.withdrawn` with before and after and your reason. No signature. Stale: "Record changed. Reload before saving."; "Only a draft record can be changed."
- **Approved**: meaning text "You withdraw this approved record: no draft method version can link it again. Its approved content stays, and the method versions already approved on it keep it as approved; replace them with a new version where the evidence no longer holds." State becomes Withdrawn; approved content and hash stay; audit event `signed.withdrawn` and an immutable signature. Refused if the record is no longer approved: "Only an approved record is withdrawn with a signature." Stale: "Record changed. Reload and review before signing."
- A draft version relying on the record is not changed here; approving it is refused afterwards (see Approve method version).
- **PIN and session**: the usual refusals; failed attempts are audited though the withdrawal is refused.

## Related pages

- Method evidence record
- [Signature PIN](/signature-pin/)
