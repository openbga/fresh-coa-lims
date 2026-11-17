---
date: 2026-11-17
type: added
impact: high
title: Reject a lot in quarantine with a signed record
area: Lots
link: quality:lot_list
pr: 44
---
On the lot record, **Reject lot** lets a quality person outside the lot's authors choose the grounds, state the reason and sign. The signature freezes what stood in the way of release, and rejection is refused while an investigation is open or a result outside its limits was not submitted.

## Technical notes

- Signed rejection of a lot in quarantine (`quality:lot_reject`, **Reject lot** on the lot record): a quality person outside the lot's authors chooses the grounds, states the reason and may name the quality system's record; the signature (meaning `rejected`) freezes, as `oq.lot-rejection/1` in `Lot.disposition_evidence`, what stood in the way of release, the lot's tests, investigations, receipt, supplier certificates and results and active holds. Refused while an investigation is open or a test holds a recorded result outside its limits that was not submitted.
- `Lot.state` takes the choices `quarantine`, `released`, `rejected` and `cancelled` under a check constraint, and the lot guard (migration `quality.0012_lot_rejection`) refuses every change of a lot that left quarantine, not only of a released one; a rejected or cancelled lot's evidence must name its `decision` and `schema`, and a released lot's never does.
- Rejecting a failed QC batch leaves the tests of a rejected lot as they are (no invalidation, no rerun) instead of refusing the whole batch.
