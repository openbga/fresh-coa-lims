---
date: 2026-11-15
type: added
impact: high
title: Several sets of requirements on one lot
area: Specifications
link: catalog:specifications
pr: 30
---
A lot's requirements can be assigned under more than one scope (`general` and named market or customer overlays), and the approved specification of each scope applies in full. A rule set can name the materials, stages or scopes it applies to besides the lot's own. **Assign requirements** takes **Scopes**, separated by commas.

## Technical notes

- Several sets of requirements on one lot: a lot's requirements are assigned under one or more scopes (`general` and named market or customer overlays), and the approved specification of each scope applies in full. A rule set whose policy carries the optional key `applies_to` (`materials`, `stages`, `scopes`) applies to every lot it names beside the lot's own rule set. A test the specifications state alike counts once. A named scope with nothing configured, or a rule set that requires a test no applicable specification requires, places the lot on an applicability hold.
- **Assign requirements** takes **Scopes** (one or more, separated by commas) where it took one **Scope**. `sampling.services.assign_requirements` accepts `scopes` as well as `scope`, and `catalog.services.resolve_requirements` accepts `scopes` and `decisions`.
- A lot assigned under several scopes, or under an additional rule set, freezes a requirement payload with the schema `oq.requirements/2`: the keys of `oq.requirements/1` (`specification` is the first specification) and `scopes`, `specifications`, `additional_rules`, `decisions` and, on each test, the `sources` that state it. A lot under one scope and its own rule set keeps `oq.requirements/1` unchanged. A deployment that reads the payload must accept both.
- A rule set whose policy states `applies_to` is not offered when a lot is received and is refused by `receive_lot`. A rule set cannot gain or lose `applies_to` from one version to the next.
- Assigning tests and the disposition require every rule set version the lot is under to be in force, the additional ones included, and a supplier's result is relied on only when each of them allows it. A requirement provider named by `ANALYTICAL_REQUIREMENT_PROVIDER` may offer `require_additional_rules(lot)`; a provider without it applies no additional rule set.
- The rule set approval page counts, for a version being retired, the quarantined lots whose requirements apply it as an additional rule set as well as the lots received under it.
- The database constraint `lot_assignment_replacement` is replaced by `lot_assignment_origin`, and `sampling_lotassignment` gains the columns `scopes` and `decision`.
- The specification form and page no longer say that overlays are never applied together: a lot is assigned under every scope it falls under.
- The native evidence of a certificate lists `scopes`, `specifications`, `additional_rules` and `decisions` for a lot that has them; evidence of a lot under one specification keeps its shape.
- Assigning a lot's requirements locks the account before the lot, like every other change to a lot.
