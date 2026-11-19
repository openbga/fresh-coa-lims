---
title: Method evidence record
urls: catalog:evidence_detail
views: catalog.evidence_views.evidence_detail
templates: ops/record.html
models: catalog.MethodEvidence, catalog.MethodEvidenceCharacteristic, catalog.MethodRevision, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: One evidence record: what was studied, its characteristics with criteria and results, the conclusion, the method versions relying on it, signatures and history. Add characteristics, change, approve or withdraw it here.
---

## Common tasks

### Complete a draft

1. Select [[Add characteristic]] once for each performance characteristic evaluated.
2. Select [[Change]] to correct the fields. Read [[Before approval]] for what is still missing.

### Approve a draft

1. Select [[Review and approve]]. It shows only to a quality user who did not record or change the draft, and only when nothing is missing.
2. Check the record and sign with your PIN on that page.

### Use an approved record in a method version

1. On an approved record that concludes the method is suitable, select [[Rely on it in version N]]. It names the method's newest draft version and shows to quality users.

### Withdraw a record

1. Select [[Withdraw draft]] for a draft, or [[Withdraw]] for an approved record. Both are under the More menu.

## Good to know

- Whoever recorded or changed a draft cannot approve it. The page shows the reason in place of the approve button.
- An approved record is frozen. To correct it, withdraw it and record a new one.
- Withdrawing an approved record does not undo method versions already approved on it. They keep it as approved; no draft can link it again.
- A record that concludes "Not suitable" can be approved but no method version can rely on it.

## Purpose

Shows one method evidence record with its characteristics and the method versions that rely on it, and leads to every action on it.

## Who can use it

- Sign-in required. Viewing: analyst, reviewer, quality, admin or auditor; others receive 403.
- **Add characteristic**, **Change**, **Remove** (characteristic): analyst, reviewer or quality, on a draft.
- **Withdraw draft**: the person who recorded the draft, or a quality user (also holding a recording role).
- **Review and approve**: quality, on a draft, who did not record or change it.
- **Withdraw** (approved): quality. **Rely on it in version N**: quality, on an approved record concluding "Suitable for the intended use" when the method has a draft version.

## Layout

- **Header**: record title, status, MEV-n, "Revision N", and the action buttons; withdrawals under the More menu.
- **Notice**: "Before approval" while a draft has something missing; "Withdrawn" for a record withdrawn after approval.
- **Details**: Conclusion, Method, Kind, Procedure studied, Intended use, Source of the procedure (when given), Transfer approach (for a transfer), Protocol, Report, Report link, Report completed on, Statement of suitability, Deviations, Recorded by, Approved and Withdrawn times when they exist.
- **Characteristics evaluated**: Characteristic, Acceptance criterion, Result obtained, Criterion (Met or Not met), and **Remove** on a draft for recorders. Empty: "No characteristics recorded yet."
- **Method versions relying on it**: Version (link to the method version), Status, In force ("Yes" or "No"). Empty: "No method version relies on this record."
- **Signatures** and **History**: signatures and audit events of the record. Empty: "No signatures yet." and "No history recorded".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add characteristic** | Draft | Analyst, reviewer, quality | Opens the Add characteristic form |
| **Change** | Draft | Analyst, reviewer, quality | Opens the Change draft form |
| **Remove** (row) | Draft | Analyst, reviewer, quality | Opens the Remove characteristic form |
| **Withdraw draft** (More menu) | Draft, you recorded it or are quality | Recorder, quality | Opens the Withdraw draft form |
| **Review and approve** | Draft, quality, independent, nothing missing | Quality | Opens the approval page |
| The reason "You recorded or changed this record; another quality person approves it." | Draft, quality, you recorded or changed it | Quality | Shown in place of the approve button |
| **Withdraw** (More menu) | Approved | Quality | Opens the signed withdrawal page |
| **Rely on it in version N** | Approved, suitable, quality, method has a draft version | Quality | Opens the Suitability evidence page for the newest draft version with this record chosen |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Conclusion | `MethodEvidence.conclusion` | Label | — | Suitable for the intended use, or Not suitable |
| Method, Kind, Procedure studied, Intended use, Source of the procedure, Transfer approach, Protocol, Report, Report link, Report completed on, Statement of suitability, Deviations | `MethodEvidence` fields of those names | Text, date, link | — | As entered |
| Recorded by | `MethodEvidence.recorded_by` | Person | — | Who recorded the draft |
| Approved, Withdrawn | `MethodEvidence.approved_at`, `withdrawn_at` | Date and time | — | Shown when set |
| Revision | `MethodEvidence.revision` | Integer | — | Increases with each change, characteristic added or removed, approval and withdrawal |
| Characteristic, Acceptance criterion, Result obtained, Criterion | `MethodEvidenceCharacteristic` fields | Text, Met or Not met | — | One line per characteristic, in the order added |

## Rules and hidden logic

- **Before approval** lists, joined in one text: "Add the characteristics that were evaluated, each with its criterion and result." (not needed for a transfer waiver); "A criterion was not met but the record concludes that the method is suitable: state under Deviations how this was assessed."; "The report is dated in the future."
- **Independence**: the people who recorded the draft or changed it (read from the audit trail; signatures excluded) cannot approve it.
- **Immutability**: an approved or withdrawn record, and its characteristics, cannot be changed or deleted (database guard). Approval stores the frozen content and its hash.
- **In force** is "Yes" for a relying version that is approved and applies now.
- **Order**: characteristics in the order added; relying versions newest first; history oldest first.

## Related pages

- [Method evidence](/catalog/method-evidence/)
- Change draft, Add characteristic, Remove characteristic, Withdraw record, Approve record, Suitability evidence
- Method record
