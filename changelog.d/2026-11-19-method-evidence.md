---
date: 2026-11-19
type: added
impact: high
title: Record a method's validation, verification or transfer and have method versions rely on it
area: Specifications
link: catalog:evidence_list
---
**Specifications and methods** has a new **Method evidence** tab. An analyst, a reviewer or a quality person records the evidence that a method is suitable for its intended use: a validation, the verification of a compendial procedure, a transfer or another documented demonstration, with its report and each characteristic's acceptance criterion and result. A quality person who neither recorded nor changed the record approves it with a signature, and it cannot be edited afterwards. On a draft method version, **Suitability evidence** lets quality rely on an approved record of the method instead of a reference only; approving the version checks the record again, and the method page links it.

## Technical notes

- Migration `catalog.0009` adds the `MethodEvidence` and `MethodEvidenceCharacteristic` tables, with guard triggers that refuse any change to an approved or withdrawn record other than its withdrawal, refuse deletion, and allow characteristics to be added or removed only on a draft. It adds the nullable `MethodRevision.evidence` column and replaces the revision guard so that a draft version's `suitability_kind`, `suitability_ref` and `evidence` can change; approved versions stay immutable. No existing row changes.
- New pages `catalog:evidence_list`, `catalog:evidence_new`, `catalog:evidence_detail`, `catalog:evidence_edit`, `catalog:evidence_characteristic_new`, `catalog:evidence_characteristic_remove`, `catalog:evidence_approve`, `catalog:evidence_withdraw` and `catalog:suitability_set`.
- New audit actions `method_evidence.recorded`, `method_evidence.changed`, `method_evidence.characteristic_added`, `method_evidence.characteristic_removed`, `method_evidence.withdrawn` and `method_revision.suitability_set`. Records are approved with the meaning `approved` and an approved record is withdrawn with the meaning `withdrawn`; the approval freezes the record as `oq.method_evidence/1`.
- A method version's approved content (`oq.method/1`) carries an `evidence` key (identifier, kind, conclusion and content hash) only when the version relies on a record. Requirement payloads frozen on tests are unchanged.
