---
date: 2026-11-12
type: fixed
impact: medium
title: The sidebar shows only the pages an account's roles can open
area: Whole application
pr: 16
---
**Audit trail** is no longer offered to analysts and reviewers, who could not open it, and laboratory pages are no longer offered to accounts without a recognized role. Laboratory sections with nothing to show are hidden, and an account with several roles sees the pages of all of them.

## Technical notes

The shared menu is filtered by the account's current explicit roles; read-only laboratory destinations stay available. The audit link and the audit route use the same set of reader roles. Server authorization and scientific action permissions are unchanged. No migration and no dependency change.
