---
date: 2026-11-17
type: fixed
impact: medium
title: Record pages offer only the actions the server would accept now
area: Whole application
---
A record page no longer offers an action that would only lead to a refusal. Where an action that would be offered cannot be taken now, the page header says why instead, for example on an investigation (**Authorize retest**, **Conclude**), a test (**Sign review**, **Return test**, **Record not completed**, **Record contract laboratory result**), a lot (**Reject lot**, **Cancel lot received in error**, **Review disposition**, **Replace requirements**), a draft version (**Review and approve**), equipment (**Return to service**), a stability protocol or study (**Approve**, **Close study**) and an intended use (**Accept**).

## Technical notes

Each page computes the same refusal its action page and service check (for example `services.authorize_refusal`, `services.review_refusal`, `quality.rejection.rejection_refusals`, `catalog.web.approval_offer`, `stability.views.close_refusal`, `validation.views.accept_denial`); the services still recheck everything under lock. Ops record pages show a refusal with `laboratory.ui.refused`.
