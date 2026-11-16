---
title: Supplier result acceptance record
urls: quality:acceptance_detail
views: quality.acceptance_views.acceptance_detail
templates: ops/record.html
models: quality.SupplierResultAcceptance, quality.SupplierCertificateResult, quality.SupplierCertificate, quality.Lot, quality.LotReceipt, suppliers.Supplier, suppliers.SupplierQualification, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

One result of a supplier's certificate proposed or accepted in place of the laboratory's own test of a requirement of a lot: what it relies on, its state, its signature and its history.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- **Accept**: reviewers only, and never the proposer, a user who recorded or corrected the supplier certificate the result comes from, or a user who recorded or corrected the lot's receipt details.
- **Withdraw**: a proposal by analysts, reviewers and quality users; an accepted record by reviewers and quality users only, because it takes a signature. The proposer and the signer of the acceptance are not excluded.
- Buttons are shown only to users who can use them; the server checks again. Admin and Auditor alone are read-only here.

## Layout

- **Header**: breadcrumbs (Material lots, lot number, SRA-n), title "Supplier result · Assay" (the test name), the identifier SRA-n and the state label (Awaiting acceptance, Accepted or Withdrawn), action buttons.
- **Notice**: one of five, see Rules: "Withdrawn", "No longer stands", "Qualification revoked", "Awaiting acceptance" or "Accepted".
- **Details**: what the record relies on, as frozen when it was proposed, then who proposed it and what happened since (see Fields).
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Accept** | Awaiting acceptance, lot is Quarantine, the record still stands, and you neither proposed it nor recorded or corrected its certificate or the lot's receipt details | Reviewer | Opens Accept supplier result in place of a test |
| **Withdraw** | Awaiting acceptance or Accepted, and lot is Quarantine | Awaiting acceptance: analyst, reviewer, quality. Accepted: reviewer, quality | Opens Withdraw supplier result: a reason form for a proposal, a signing page for an accepted record |
| Lot link | Always | Any reader | Opens the lot record |
| Supplier certificate link | Always | Any reader | Opens the supplier certificate record; a record that was corrected since leads to the current one |
| Supplier link / Supplier qualification link | Always | Any reader | Opens the supplier record or the supplier qualification record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `SupplierResultAcceptance.lot` | Link, "number · material" | — | The lot whose requirement is answered |
| Test / Specification / Requirement | `SupplierResultAcceptance.evidence`, `test_code`, `requirement_hash` | Text | — | Test name and code, acceptance criterion and source of the requirement, as frozen |
| Supplier's result | `SupplierResultAcceptance.evidence` (stated) | Text | — | "99.60 %", or "Conforms (stated as: Complies)" for a qualitative result |
| Method stated / Limits stated | `SupplierResultAcceptance.evidence` (stated) | Text | — | As the certificate record stated them |
| Supplier certificate / Lot number on the certificate / Where the certificate is kept | `SupplierResultAcceptance.result` → `SupplierCertificate`; `evidence` (certificate) | Link and text | — | "NUMBER dated DATE, issued by ISSUER", and the record's details as frozen |
| Supplier / Lot received | `SupplierResultAcceptance.evidence` (supplier, received_on) | Link, date | — | "code · name, location" and the date the lot was received, from the receipt details as they stood |
| Supplier qualification | `SupplierResultAcceptance.qualification` | Link | — | "SQ-n · evidence reference · valid START to END": the qualification relied on |
| Rule set | `SupplierResultAcceptance.evidence` (rules) | Text | — | "code version N · the laboratory always performs: identity" ("no test named" when it keeps none) |
| Additional rule set | `SupplierResultAcceptance.evidence` (additional rules) | Text | — | One line, in the same form, for each additional rule set the lot was under when the result was proposed; each allowed the reliance. Not shown when there was none |
| Proposed by / Proposed / Reason | `SupplierResultAcceptance.proposed_by`, `proposed_at`, `reason` | User, time with zone, text | — | Who proposed it, when and why |
| Accepted | `SupplierResultAcceptance.accepted_at` | Time with zone | — | When the reviewer signed; "—" until then. The signer is under Signatures |
| Withdrawn | `SupplierResultAcceptance.withdrawn_at`, `withdrawn_by` | "time by user" | — | "—" unless withdrawn; the reason is in the notice and in History |
| Revision | `SupplierResultAcceptance.revision` | Integer | — | Rises by 1 when the record is accepted and when it is withdrawn |

## Rules and hidden logic

- **States**: Awaiting acceptance, then Accepted once a reviewer signs; either can become Withdrawn, a proposal with a reason and an accepted record with a signature. A withdrawn record is final: propose the supplier's result again.
- **What an accepted result does**: it answers its requirement for the whole lot, not for one sample. No test of that requirement is needed, a test already assigned for it stays Open and takes no result, and the certificate of analysis lists it apart from the laboratory's results, as the supplier's.
- **Frozen evidence**: the Details show what was relied on when the result was proposed. Later changes to the certificate record, the receipt details, the requirements or the qualification do not change this record.
- **No longer stands**: the page checks the lot's records each time it is shown. The notice reads "What this record relied on has changed: REASONS. It answers nothing and blocks the lot's disposition until it is withdrawn. Then propose the supplier's result again or test the requirement in the laboratory." Reasons: "supplier certificate COA-TEST-001 was corrected or withdrawn after the result was taken from it"; "supplier certificate COA-TEST-002 states a result for assay that does not meet the specification" (another current certificate record of the lot); "the receipt details no longer name a supplier"; "the receipt details now name another supplier"; "the date received was corrected from 2026-11-02 to 2026-10-01" (any other day, also one within the qualification's dates); "the lot's requirement for this test has changed"; "T-12 assay already holds laboratory work (a result, a raw-data file, a QC batch or a decision). A supplier's result cannot stand in for a requirement the laboratory has started testing". The stored state does not change by itself; the record must be withdrawn.
- **A proposal that can no longer be signed** also no longer stands: "SQ-1 was revoked before the proposal was accepted"; "rule set rules-syn v1 is no longer approved and effective" (the lot's own rule set, or an additional rule set applied by the lot's current requirements). **Accept** is not offered, and the signing page shows the reason without asking for a PIN. Withdraw the proposal.
- **Notices**, the first that applies: "Withdrawn": "This record no longer stands and is kept as recorded. Reason: REASON"; "No longer stands" (above); "Qualification revoked" (accepted records): "The supplier qualification this acceptance relied on (SQ-1) was revoked on 2026-11-14 10:30 UTC. The acceptance stands as signed. The qualification's record lists every result accepted under it, for quality to assess under the laboratory's procedure."; "Awaiting acceptance": "This proposal answers nothing yet and blocks the lot's disposition until a reviewer accepts it or it is withdrawn."; "Accepted": "The supplier's stated result answers this requirement of the lot in place of a laboratory test. It stays the supplier's result and is named as such on the certificate of analysis."
- **Revoked qualification**: an acceptance signed before the revocation stands and does not block the disposition; it shows "Qualification revoked". A proposal still awaiting acceptance shows "No longer stands" instead (above).
- **Released lot**: the record stays readable and has no buttons. Opening the Withdraw page directly returns you here with "Supplier results are accepted only while the lot is in quarantine."
- **Independence**: the proposer, everyone who recorded or corrected the supplier certificate, and everyone who recorded or corrected the lot's receipt details, cannot accept the result. Recording or signing the supplier qualification does not bar a reviewer from accepting. The proposer cannot sign the lot's QC disposition. Signing the acceptance, or withdrawing the record, is not authorship of the lot's data: the reviewer who accepted may sign the disposition when holding the quality role.
- **Never edited**: the record cannot be edited or deleted; it is accepted or withdrawn, and only while the lot is in quarantine (database guard).
- **Audit**: `supplier_result.proposed`, `signed.accepted`, and `supplier_result.withdrawn` (a proposal withdrawn with a reason) or `signed.withdrawn` (an acceptance withdrawn with a signature) appear under History. The signature of a withdrawal is listed under Signatures with the meaning withdrawn. A refused proposal is audited on the lot, not here.
- **Not enforced by this page**: the software records no assessment of an acceptance whose qualification was revoked, and holds no lot by itself. Place a hold from Holds, or withdraw the acceptance, if the lot must not be dispositioned.
- Signatures and history are those of this record only. An unknown ID returns 404.

## Related pages

- Lot record; Supplier certificate record.
- Accept supplier result in place of a test; Withdraw supplier result.
- Supplier qualification record; Supplier record.
- Lot testing; Sign lot disposition.
- [Holds](/stability/holds/)
- [Material lots](/)
