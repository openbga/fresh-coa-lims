---
date: 2026-11-19
type: added
impact: high
title: List the instruments, reagents and standards suitable for each method version
area: Specifications and methods
link: catalog:methods
---
On a draft method version, quality can now list what is suitable for the method under **Suitable instruments, reagents and standards**: kinds of instrument by equipment category, and reagents, reference standards and prepared solutions as the register names their lots; each kind is checked on its own. Each line is either recorded with every result or only allowed, and an instrument line can ask for an instrument qualified for the method. Results, corrections, file imports and batch QC results under that version then offer and accept only what it lists, beside the calibration, release and expiry checks, and the method page shows each line next to the matching instruments and lots and their status. Versions without a list, and tests already assigned, work as before.

## Technical notes

- Migration `catalog.0010` adds the table `catalog_methodresource` with a database guard: lines are added or removed only while their version is a draft, never updated, at most 20 per version. No existing row changes.
- A version that lists resources carries `resources` (a list of `kind`, `name`, `required` and `method_qualified`) in its approved content; the content and hash of every other version are unchanged. New audit actions: `method_revision.resource_added` and `method_revision.resource_removed`.
- The bench contract passes the frozen method version: `choices(method_code=, method_revision=)` and `authorize(..., method_revision=)` (`config.integrations.LaboratoryBench`). A custom `ANALYTICAL_BENCH` written to the earlier contract must accept these keyword arguments. `choices` can also return `required` (`equipment`, `reagents`) to make a field mandatory, and the bench holds an entry frozen to a version of a catalog method that is not approved. Bench evidence can now carry `suitable_as` for each resource and `method_qualification` for an instrument. A refused entry is still audited as `resource.use_blocked`, and its refusals can include a subject `Method <code>` for a required line that was not answered.
- To qualify an instrument for one method, record an equipment qualification whose stage or intended use is the method's code.
