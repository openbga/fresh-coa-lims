---
title: Accept supplier result in place of a test
urls: quality:acceptance_accept
views: quality.acceptance_views.acceptance_accept
templates: ops/sign.html
models: quality.SupplierResultAcceptance, quality.SupplierCertificateResult, quality.SupplierCertificate, quality.Lot, suppliers.SupplierQualification, core.RuleSet, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

Sign a proposed supplier result with meaning **accepted**. From then on the supplier's stated result answers that requirement of the lot in place of the laboratory's own test.

## Who can use it

- Sign-in required. Role: Reviewer. Other roles receive the standard 403 page.
- Never the analyst who proposed the result, a user who recorded or corrected the supplier certificate the result comes from, or a user who recorded or corrected the lot's receipt details, even with the reviewer role.
- A denied reviewer sees the facts, the reason under "Not permitted", no PIN control and a **Back to record** link (403). Reasons: "You cannot accept a supplier's result you proposed."; "You recorded or corrected the supplier certificate this result comes from; another reviewer accepts it."; "You recorded or corrected the receipt details of this lot, which name the supplier and the date the acceptance relies on; another reviewer accepts it."; "This supplier result is already accepted."; "This proposal was withdrawn. Propose the supplier's result again."; "Supplier results are accepted only while the lot is in quarantine."; "This proposal no longer stands: REASONS. Withdraw it."
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Reviewer role has exactly that role's authority, and the independence rules still apply.

## Layout

- Breadcrumbs (Material lots, lot number, SRA-n, Accept), then a signing dialog (a plain card without JavaScript): SRA-n and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and accept** | Not denied | Role: Reviewer, not the proposer and not an author of the certificate record or of the lot's receipt details | Signs with meaning **accepted**; returns to the acceptance record with "Supplier result accepted in place of a test." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |
| Lot, certificate, supplier and qualification links | Always | Any | Open those records, to check the proposal against them |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Test / Specification / Requirement / Supplier's result / Method stated / Limits stated / Supplier certificate / Lot number on the certificate / Where the certificate is kept / Supplier / Lot received / Supplier qualification / Rule set / Additional rule set | `SupplierResultAcceptance.evidence` | Display | — | Everything the signature binds, as frozen when the result was proposed; see the acceptance record for each. Additional rule set appears once for each additional rule set the lot was under |
| Proposed by / Reason | `SupplierResultAcceptance.proposed_by`, `reason` | Display | — | The analyst who proposed the result, and why |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `SupplierResultAcceptance.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You accept the supplier's stated result in place of the laboratory's own test of this requirement, having checked the record against the supplier's certificate. It stays the supplier's result."
- **Independence**: the signer did not propose the result, recorded no record of the certificate it comes from (the record a correction replaced included) and recorded or corrected none of the lot's receipt details, which name the supplier and the date received that the acceptance relies on. Recording or signing the supplier qualification is not a bar. Checked when the page opens and again under the lock when signing.
- **Everything is checked again when signing**, under the locks of the acceptance, the lot and the qualification. The lot is in quarantine. The certificate record is still the current one, the lot is still received from a supplier, the result still matches the lot's current requirement, meets the specification and states a method and limits, no other current certificate record of the lot states a result for the test that does not meet the specification, and the laboratory has not started testing the requirement (messages as on Propose supplier result in place of a test). The lot's rule set, and every additional rule set applied by the lot's current requirements, is still approved and effective and still allows reliance for the test. The rule set versions the lot is under are the ones frozen with the proposal; otherwise signing is refused: "What this proposal relied on has changed since it was made. Withdraw it and propose the supplier's result again."
- **No longer stands**: the reasons shown on the acceptance record deny this page when it opens and when it is submitted, without a PIN field (403). They include a proposal that can no longer be signed, for example "This proposal no longer stands: SQ-1 was revoked before the proposal was accepted. Withdraw it." or "This proposal no longer stands: rule set rules-syn v1 is no longer approved and effective. Withdraw it."
- **Qualification**: the qualification named by the proposal must still be signed, not revoked, and cover the date the lot was received. A revocation signed while you sign is refused at signing: "SQ-1 no longer covers this result: it was revoked, or the lot's date of receipt is outside its dates. What this proposal relied on has changed since it was made. Withdraw it and propose the supplier's result again." The database repeats that the qualification is approved and that the certificate record is still the current one.
- **Unchanged basis**: what the proposal froze is built again from the records and must be identical: "What this proposal relied on has changed since it was made. Withdraw it and propose the supplier's result again."
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Accepted with the signing time, raises the acceptance revision and the lot revision by 1, writes the audit event `signed.accepted` and an immutable signature bound to the new revision. A disposition signing page opened earlier then fails as stale.
- **What the acceptance does**: the requirement is answered for the whole lot. The lot's testing page lists the result under "Supplier results accepted in place of tests", the QC disposition signing page names it in a notice, and the certificate of analysis prints it under "Results accepted from the supplier's certificate of analysis" with your signature.
- **What it does not do**: it is not a test of this laboratory and the result stays the supplier's. Signing is not authorship of the lot's data: a signer who also holds the quality role may sign the lot's QC disposition.
- **Not enforced by this page**: that the record matches the supplier's certificate; you check it against the document. Whether the supplier's method is equivalent to the specification's method is for you to judge from Method stated.
- **Assumption**: accepting a supplier's result on a second, independent signature, and anchoring the qualification to the date the lot was received, are design defaults of this product. They are not a statement of what any regulation requires or permits. The lot still needs its sample and sampling record for QC disposition.

## Related pages

- Supplier result acceptance record (Cancel returns here)
- Supplier certificate record; Supplier qualification record
- Withdraw supplier result
- [Signature PIN](/signature-pin/)
