---
title: New evaluation
urls: stability:shelf_life_new
views: stability.shelf_life_views.shelf_life_new
templates: ops/form.html
models: stability.ShelfLifeEvaluation, stability.ShelfLifeStudy, core.AuditEvent
reviewed: 2026-11-19
summary: Draft a shelf-life evaluation of one test at one storage condition. Choose a study first, then the condition, test, expected change and purpose. Quality only.
---

## Common tasks

### Draft an evaluation

1. Choose a [[Study]] and select [[Continue]].
2. Choose the [[Storage condition]], the [[Test]] and the [[Expected change]].
3. State the [[Purpose]] and the [[Reason]], then select [[Draft evaluation]].

### Start from a study

1. On the study record, select [[Evaluate shelf life]] under More. The study is already chosen.

## Good to know

- The evaluation starts with every study of the protocol in the same container closure. You can leave some out afterwards with Change.
- The acceptance criterion is the one the protocol's specification in force states now. It is kept with the evaluation.
- Only numeric and count tests with a limit can be evaluated. If the protocol has none, the page says nothing can be evaluated.
- You become a drafter: you cannot conclude this evaluation.

## Purpose

Starts a shelf-life evaluation as a draft. Drafting does not sign. The laboratory decides which studies, conditions and tests to evaluate; the system works the figures out from the recorded results.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.
- Only studies whose protocol names a specification can be chosen, because only their pulls are tested in the system.

## Layout

- Breadcrumbs (Stability and retention, Shelf-life evaluations, New evaluation).
- **Step 1**, without a study chosen: the introduction, the **Study** field, **Cancel** and **Continue**. **Cancel** returns to the evaluations list.
- **Step 2**, with a study chosen (from Continue or from the study's **Evaluate shelf life**): an introduction naming the protocol, product and container closure, the form, **Cancel** (back to the study) and **Draft evaluation**. When the specification states no testable limit, the introduction says nothing can be evaluated.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Continue** | No study chosen | Quality | Opens step 2 for the chosen study |
| **Draft evaluation** | Study chosen | Quality | Creates the draft; message "SLE-n drafted with every study of CODE in this container closure."; opens its record |
| **Cancel** | Always | Quality | Returns to the study or the list; nothing is saved |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Study | `Study` (not stored) | Search and select | Yes | Any study of the protocol and container closure to evaluate; the evaluation uses every study of both |
| Storage condition | `ShelfLifeEvaluation.condition` | Choice of the protocol's conditions | Yes | The condition whose results are evaluated, usually the long-term one. A study's time-zero result counts at every condition that has none of its own |
| Test | `test_code` | Choice | Yes | A numeric or count test of the protocol with a limit, with its criterion shown in the choice |
| Expected change | `direction` | Choice | Yes | Expected to decrease: lower one-sided 95 % limit against the lower limit. Expected to increase: upper one-sided limit against the upper limit. Could change either way, or not known: two-sided 95 % limits against both |
| Purpose | `purpose` | Text, max 2000 | Yes | Why the shelf life is evaluated now |
| Reason | audit reason | Text, max 2000 | Yes | Recorded in the history |

## Rules and hidden logic

- **Drafting**: the evaluation keeps the protocol code, product, container closure, condition, specification and its version in force, the test with its unit, reporting decimals and limits, the direction and the purpose.
- **Studies**: all studies of the protocol code in this container closure, oldest start first, up to 20; the study you chose is always included.
- **One draft per scope**: "A draft evaluation of this test at this condition exists: change it, or withdraw it first."
- **Validations**: "Choose a storage condition of <protocol>."; "Choose a numeric or count test with a limit that the protocol names and its specification in force states."; "The test has no lower limit, so a decrease never meets it: choose another."; "The test has no upper limit, so an increase never meets it: choose another."; "State why the shelf life is evaluated."
- **Audit**: event `shelf_life.drafted` with the studies, specification and your reason. Drafting counts you as an author for independence.
- **Study query**: an unusable `study` value in the address is ignored and step 1 shows.

## Related pages

- [Shelf-life evaluations](/stability/shelf-life/)
- Study record (its **Evaluate shelf life** action)
- Evaluation record
