---
date: 2026-11-17
type: changed
impact: medium
title: The validation pack of each commit includes the acceptance journeys' evidence
area: Deployment
pr: 49
---
Every commit's checks now run the acceptance journeys with the application image, and the validation pack built from them includes the evidence the journeys wrote. A failed journey fails the pack.

## Technical notes

CI's container smoke job runs the acceptance journeys with the application image in a new database, and the validation pack includes their evidence under `acceptance/` (`scripts/validation_pack.py build --acceptance DIR`, which checks the folder against its `SHA256SUMS` and refuses a run of another commit); a failed run fails the pack.
