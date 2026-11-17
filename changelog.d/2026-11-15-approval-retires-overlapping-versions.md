---
date: 2026-11-15
type: changed
impact: high
title: Approving a version retires the earlier version it overlaps
area: Rule sets
link: core:rules
pr: 29
---
Approving a version of a rule set, specification, method or sampling plan whose effective period overlaps an approved version no longer fails. The earlier version is retired and keeps its approved content and signature, and the approval page lists what the signature retires. A lot on a retired version needs its requirements assigned or replaced before tests are assigned or it is dispositioned.

## Technical notes

- Approving a version of a rule set, specification, method or sampling plan whose effective period overlaps an approved version is no longer refused with "Effective dates overlap an approved version." The earlier version is retired instead: it stops applying from the new version's start, or from the moment of approval if that start has passed, and keeps its approved content and signature. The approval page lists what the signature retires. A draft that would retire a later-numbered approved version is refused.
- A lot on a rule version that has been retired cannot have tests assigned or be dispositioned until its requirements are assigned again (before testing) or replaced (during testing) under the version in force. Assigning requirements before testing now moves the lot to the version in force of its own rule set.
- Reviewing a result no longer requires the lot's rule version to be in force, only approved, so a result awaiting review and an open investigation are not stranded when a later rule version is approved. Assigning tests and the disposition still require it.
- The new-lot form offers only the rule versions in force.
- **New QC batch** also offers an earlier revision of a method while open tests not yet in a batch are frozen to it; before, such tests could not get a batch once their method revision was no longer in force. `create_batch` takes an optional `revision`.
