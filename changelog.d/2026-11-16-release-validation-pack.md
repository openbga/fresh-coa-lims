---
date: 2026-11-16
type: added
impact: medium
title: Validation pack built with each release
area: Deployment
pr: 38
---
Each release can build a pack that traces every product requirement to the tests that give evidence for it, with each suite's results and the environment. It is supplier evidence for a laboratory's own validation, not a validation of the system.

## Technical notes

- Validation pack of each release. `docs/traceability.toml` traces every product requirement of `docs/product.md` to the tests that give evidence for it, and `tests/test_validation_pack.py` refuses a requirement without a test, an entry that does not exist or a test that is not traced. `scripts/validation_pack.py` (`check`, `environment`, `build`) builds the pack: `index.html`, `requirements.csv`, `traceability.csv`, `pack.json`, each suite's JUnit results and environment, the requirements, regulatory matrix and map of the commit, the release notes and `SHA256SUMS`. Each suite's conftest writes the commit the tests run on into the JUnit file, and `[skips]` in the map names the tests that may be skipped, with the reason. CI's application and browser jobs write their JUnit results, and a new `validation-pack` job builds the pack after both and the container smoke job pass and keeps it as the artifact `validation-pack-<commit>` for 90 days. The pack is supplier evidence for a laboratory's own validation, not a validation of the system.
