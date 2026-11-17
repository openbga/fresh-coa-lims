---
date: 2026-11-15
type: added
impact: high
title: Signed decision where the requirements that apply to a lot differ
area: Lots
link: quality:lot_list
pr: 30
---
Where the specifications that apply to a lot state a test differently, nothing is merged and neither statement is picked. A quality person who authored none of the lot's data chooses which requirement applies, gives a reason and signs under **Decide conflicting requirements**.

## Technical notes

- A signed decision where the specifications that apply to a lot state a test differently: nothing is merged and neither statement is picked. A quality person who authored none of the lot's data chooses which requirement applies, gives a reason and signs (meaning `requirements_decided`, page **Decide conflicting requirements**); the statements not chosen stay in the record, on the disposition page and on the certificate. During testing the same choice is part of the signed replacement of the lot's requirements.
- The evidence of a replacement (`oq.requirement-replacement/1`) gains `versions` (every specification and additional rule set version that changed), and `decisions` with `signed_at` when a choice between differing statements is part of it. Earlier rows are unchanged and are read as before.
