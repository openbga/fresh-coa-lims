---
date: 2026-11-17
type: added
impact: high
title: Cancel a lot received in error with a signed record
area: Lots
link: quality:lot_list
pr: 44
---
**Cancel lot received in error** records, with a signature, that a lot should not have been received. It is refused once the lot has a sample, test, reserve sample, stability study or standing supplier result.

## Technical notes

- Signed cancellation of a lot received in error (`quality:lot_cancel`, **Cancel lot received in error**): meaning `cancelled`, evidence `oq.lot-cancellation/1`; refused once the lot has a sample, test, reserve sample, stability study or standing supplier result, and signed by someone other than whoever received the lot or made its records.
