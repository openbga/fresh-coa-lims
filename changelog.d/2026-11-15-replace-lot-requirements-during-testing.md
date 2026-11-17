---
date: 2026-11-15
type: added
impact: high
title: Replace a lot's requirements during testing with a signature
area: Lots
link: quality:lot_list
pr: 29
---
When a specification, a method or the rule set has been revised, a quality person who authored none of the lot's data reviews what the versions in force would change and signs the replacement with a reason. Tests with the same requirement carry over; the others are kept as recorded, marked superseded and never counted.

## Technical notes

- Controlled replacement of a lot's requirements during testing: when a specification, a method or the rule set has been revised, a quality person who authored none of the lot's data reviews what the versions in force would change and signs the replacement with a reason. Tests whose requirement is exactly the same carry over. The others are kept as recorded, marked superseded and never counted; assigning the lot's tests again adds a linked repeat under the new requirement. The earlier requirements stay in the record, the sampling plan is kept, and the lot moves to the version in force of its rule set. A replacement is refused while an investigation is open on the lot or while a test that would be superseded holds results or raw-data files that were not submitted. Migrations `core.0006`, `catalog.0006`, `sampling.0004`, `analytical.0007` and `quality.0011` add the columns and replace the database guards; they change no existing row.
- Once testing has started, assigning a lot's requirements again is refused with "Testing has started on this lot, so its requirements cannot be assigned again. Quality can replace them with a signature."
- The testing gate matches a test to a requirement by what the requirement asks for, not by the document that states it, so a test carries over when a lot's requirements are replaced by identical ones.
- Tests have a new state, Superseded, and a new kind, Repeat under replaced requirements. A deployment that reads test states or kinds must handle both.
- `core.services.sign_transition` takes an optional `prepare` step that runs after the signer is locked and before the signed record is.
- Replacing a lot's requirements during testing asks the class named by the new setting `REQUIREMENT_REPLACEMENT_TESTING` (`effects`, `lock`, `apply`) what happens to the lot's tests. Without the setting requirements cannot be replaced once testing has started.
