---
date: 2026-11-16
type: fixed
impact: low
title: Text typed into a signing form before the page loaded stays in its field
area: Whole application
pr: 38
---
Text typed into a signing form before the page had finished loading no longer continues in the PIN field.

## Technical notes

- Text typed into a signing form before the page had finished loading no longer continues in the PIN field: the dialog script now leaves the focus in the field being typed in. The stability browser journey had failed on this once in CI.
