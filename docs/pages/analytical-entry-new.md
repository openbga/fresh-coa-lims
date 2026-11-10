---
title: Record investigation entry
urls: analytical:entry_new
views: analytical.views.entry_new
templates: analytical/form.html, analytical/_summary.html
models: analytical.Investigation, analytical.InvestigationEntry
reviewed: 2026-11-10
---

## Purpose

Add a written entry (assessment, hypothesis, evidence or impact) to an open investigation.

## Who can use it

- Sign-in required. **Analysts**, **reviewers** or **quality**; others receive 403.
- Not restricted by authorship. Entries do not require a signature.

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
