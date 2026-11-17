---
title: Record investigation entry
urls: analytical:entry_new
views: analytical.views.entry_new
templates: analytical/form.html, analytical/_summary.html
models: analytical.Investigation, analytical.InvestigationEntry
reviewed: 2026-11-17
summary: Add a written entry to an open investigation: a laboratory assessment, a hypothesis or test plan, evidence, or the impact on other lots or products.
---

## Common tasks
### Record the laboratory assessment
1. Choose [[Laboratory assessment]] in [[Entry type]] and write it in [[Entry]].
2. Add a deviation, CAPA or document number in [[Controlled reference]], if any, then select [[Record entry]].
### Add a hypothesis, evidence or impact
1. Choose the kind in [[Entry type]], write the [[Entry]] and select [[Record entry]].
## Good to know
- Quality can authorize a retest or sign a conclusion only after a laboratory assessment is recorded.
- Writing an entry bars you from concluding this investigation and, for a lot's investigation, from signing the lot's QC disposition.
- Entries cannot be edited or removed. Add another entry to correct or extend one.
- The controlled reference is free text. It is not checked against the external quality system.

## Purpose

Add a written entry (assessment, hypothesis, evidence or impact) to an open investigation.

## Who can use it

- Sign-in required. **Analysts**, **reviewers** or **quality**; others receive 403.
- Not restricted by authorship. Entries do not require a signature.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Record entry · INV-n". Summary: Investigation (with phase), Lot, Trigger, Record revision.
- Form: **Entry type**, **Entry**, **Controlled reference**, **Cancel**, **Record entry**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record entry** | Always | Analyst, reviewer, quality | "Investigation entry recorded."; returns to the investigation |
| **Cancel** | Always | Same | Returns to the investigation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Entry type | `InvestigationEntry.kind` | Laboratory assessment, Hypothesis or test plan, Evidence, Impact on other lots or products | Yes | Escalation and retest entries are system-made only |
| Entry | `InvestigationEntry.text` | Text, max 4000 | Yes | The record |
| Controlled reference | `InvestigationEntry.external_reference` | Text, max 200 | No | "Deviation, CAPA or document number in the external quality system, if any." |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the investigation with the warning "This investigation is closed.".
- **Preconditions**: investigation open ("This investigation is closed."); "Choose an investigation entry type."; text not blank.
- **Effect**: the entry is stored with you as author and server time, the investigation revision rises by 1, and `investigation.assessment`, `.hypothesis`, `.evidence` or `.impact` is audited.
- A laboratory assessment is required before a retest can be authorized or a conclusion signed.
- Authors of entries cannot sign the lot's QC disposition.
- The controlled reference is free text; this system does not check it against the external system.

## Related pages

- Investigation record (return target).
