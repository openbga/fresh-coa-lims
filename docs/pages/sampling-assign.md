---
title: Assign requirements to a lot
urls: sampling:assign
views: sampling.views.assign
templates: catalog/form.html
models: sampling.LotAssignment, quality.Lot, catalog.Material
reviewed: 2026-11-15
---

## Purpose

Freezes what applies to a lot now: the approved specification of every scope the lot falls under, their methods, the sampling plan and the rule sets. If anything is missing, or the specifications state a test differently, it records an applicability hold with the reasons instead.

## Who can use it

- Sign-in required. **analyst** or **quality** role; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the analyst or quality role acts with that role only, with no exception to the independence rules.
- Only lots in Quarantine: otherwise you are redirected to the lot with "Only quarantined lots can receive requirements." (the server also refuses).
- Only before testing starts: once any analytical test exists for the lot you are redirected to the lot with "Testing has started on this lot, so its requirements cannot be assigned again. Quality can replace them with a signature." (the server also refuses). From then on only Replace lot requirements changes them.

## Layout

- **Breadcrumbs**: Sampling, lot number, Assign requirements. Title: "Assign requirements ·" and the lot number.
- **Intro**: "The approved specification of every scope named, its methods and the sampling plan effective now are frozen for this lot, with the rule sets in force that name its material, stage or scopes. If anything is missing or not approved, or the specifications state a test differently, the lot is placed on an applicability hold with the reasons; nothing is guessed, merged or picked."
- **Record card**: Lot, Material as received, Rule set, Current requirements ("None", "Requirements assigned" or "Applicability hold"), Scopes in the configuration (the scope names to choose from, "general" first, or "None").
- **Form sections**: Applicability, Change control. Buttons **Cancel** and **Assign requirements**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Assign requirements** | Always | Analyst, quality | Resolves requirements; redirects to the lot with "Approved requirements frozen for this lot." or the warning "Applicability hold recorded: " followed by the reasons |
| **Cancel** | Always | Analyst, quality | Returns to the lot |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Material | `LotAssignment.material` | Choice of all materials | Yes | Help: "The controlled material this lot is." Prefilled from the current assignment, or a material whose name or code equals the lot's material as received. |
| Stage | `LotAssignment.stage` | Incoming material, In-process, Finished product, Stability | Yes | Stage of the material; prefilled from the current assignment. |
| Scopes | `LotAssignment.scopes` (the first also in `LotAssignment.scope`) | Text, max 768: 1 to 12 scope names separated by commas or spaces; default "general" | Yes | Help: "Every scope this lot falls under, separated by commas: general, and the named market or customer overlays, for example general, eu-market. The specification of each scope applies in full." Prefilled with the scopes of the current assignment. |
| Reason | `LotAssignment.reason` | Text, max 2000 | Yes | Why requirements are assigned or changed; stored on the assignment and in its audit event. |
| Scopes in the configuration | `Specification.scope`, `RuleSet.policy` (`applies_to`) | Scope names | — | The scope of every specification, and every scope named under `applies_to` by an approved additional rule set version. A scope that is not listed can still be entered; it then holds the lot unless something is configured for it. |

## Rules and hidden logic

- **What is resolved**: for the material and stage, at the time you submit: the approved specification version in force of every scope named; the approved effective version of each test's method; the approved effective sampling plan for the material and stage, or, once the lot has been sampled, the plan version its samples were taken under; the version in force of the lot's own rule set; and every additional rule set in force that applies. Nothing is merged, guessed or picked.
- **Scopes**: names are separated by commas or spaces, each counted once, and stored with "general" first and the others in alphabetical order. A name uses letters, digits, hyphen and underscore, at most 60 characters, and is compared exactly with the scope of a specification. "general" is not added for you. Messages: "Name at least one scope, for example general."; "“eu market!” is not a scope name: use letters, digits, - and _."; "A scope name has at most 60 characters."; "A lot is assigned under at most 12 scopes."
- **Several specifications**: the specification of every scope applies in full. A test code that the specifications state alike (same name, acceptance criterion, rounding, replicates and method version, and required alike) is one requirement, shown with every scope that states it. A test only one of them states is a requirement too.
- **Conflicting requirements**: where the specifications state the same test code differently, the assignment is a hold: "Specifications SPEC-TEST-001 v1 (general) and SPEC-TEST-EU v1 (eu-market) state different requirements for assay. Quality decides which one applies to this lot." Neither the stricter nor the wider statement is chosen. A quality person who recorded none of the lot's data then signs the decision on Decide conflicting requirements.
- **Additional rule sets**: a rule set whose policy states `applies_to` is not chosen at receipt. Its latest version in force applies to this lot, beside the lot's own rule set, when every dimension it names matches: the material code, the stage, and at least one of the scopes; a dimension it leaves out matches every lot. Each of its required tests must be required by a specification that applies to the lot. The versions that applied are frozen with the requirements.
- **A scope that only selects rule sets**: a scope without a specification is accepted when an additional rule set that applies to the lot names it. At least one named scope must have a specification.
- **Hold reasons** (any one produces a hold): "Rule set <code> v<N> is not approved and effective." / "No specification exists for <material> at stage <stage> and scope <scope>." (a scope with neither a specification nor an additional rule set that names it) / "No specification applies to <material> at stage <stage>: <scope> selects rule sets only." ("<scopes> select rule sets only." for several) / "Specification <code> has no approved version effective now." / "Method <code> has no approved version effective now." / "Rule set requires tests missing from the specification: <codes>" (one scope and no additional rule set) / "Rule set <code> v<N> requires tests that no specification applying to the lot requires: <codes>" (several scopes or an additional rule set) / the conflict reason above, one for each test / "No sampling plan exists for <material> at stage <stage>." / "Sampling plan <code> has no approved version effective now."
- **After a hold**: a hold for conflicting requirements only is settled by quality's signed decision. Every other reason is resolved in the configuration (or by naming other scopes), after which the requirements are assigned again here. A decision signed earlier is never applied by a new assignment: while the specifications still differ the lot is held again and decided again.
- **Sampling plan once sampled**: when the lot's current sampling records were all taken under one plan version of the same material and stage, that version is kept, also when a later version is in force, so the samples stay valid. When the material or the stage changes, or the records name several plan versions, the plan in force is taken and the sampling gate lists the samples that do not fit ("Sample <ref> was sampled under <plan vN>; the current requirements use <plan vM>.").
- **Append-only**: each submission, ready or hold, adds a new assignment that supersedes the previous one. No signature is needed before testing starts.
- **Rule set**: the lot follows its own rule set. When the lot's version has stopped applying (expired, or retired by a later approval) and another approved version of the same rule set is in force, that version is used, and a submission that freezes requirements moves the lot to it; a hold leaves the lot on the version it had. With no version of the rule set in force the hold reason is "Rule set <code> v<N> is not approved and effective.", naming the lot's version. The lot never moves to a different rule set.
- **Fixed after testing starts**: tests are bound to the frozen requirements, so a new assignment is refused once any analytical test exists for the lot: "Testing has started on this lot, so its requirements cannot be assigned again. Quality can replace them with a signature." Nothing is recorded and the lot revision is unchanged. After testing has started, quality changes the requirements on Replace lot requirements, with a signature.
- **Revision**: the lot's record revision increases by 1, so a disposition signing page opened earlier fails as stale.
- **Audit**: `lot.requirements_assigned` or `lot.requirements_held` with the specification and plan revision, payload hash and your reason, and the rule set version before and after when the lot moved to another version. It also records the scopes when they are not "general" alone, the test codes in conflict on such a hold, and the additional rule set versions frozen. With several specifications, the specification revision recorded is the first one (the "general" scope's when it has one).
- **Reason**: a blank reason is refused by the form ("This field is required.").
- A refused submission returns status 422 with the error.

## Related pages

- Lot requirements and sampling (record page).
- Decide conflicting requirements (quality, when the hold is a conflict between specifications).
- Replace lot requirements (once testing has started).
- [Sampling plans](/sampling/plans/)
- [Specifications](/catalog/)
