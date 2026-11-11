---
title: Sampling: Sampling plans
urls: sampling:plans
views: sampling.views.plan_list
templates: sampling/plan_list.html
models: sampling.SamplingPlan, sampling.SamplingPlanRevision, catalog.Material
reviewed: 2026-11-10
---

## Purpose

Lists sampling plans: how many containers and how much material to sample for each material and stage.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New sampling plan**: **quality** role only; hidden for others.

## Layout

- **Intro**: "Approved sampling plans state how many containers and how much material to sample for each material and stage."
- **Tabs**: Lots, Sampling plans.
- **Filter bar**: **Search** (placeholder "Code, title or material"), **Apply**, **Clear filters** when filtered.
- **Table**: Plan (code link with title, sortable), Material, Stage, Versions, Status ("Has approved version" or "No approved version", plus "Draft pending").
- **Footer**: "Showing X–Y of N sampling plans".
- **Empty states**: "No sampling plans yet" ("Create the plan for a material and stage.") with **New sampling plan** for quality; "No sampling plans match these filters" with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New sampling plan** | Quality role | Quality | Opens the New sampling plan form |
| Plan code link | Row exists | Any viewer | Opens the plan |
| Plan header | Always | Any viewer | Toggles code order |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text | No | Case-insensitive contains match on code, title or material code. |
| Plan | `SamplingPlan.code`, `title` | Text | — | Identifier and title. |
| Material | `Material.code` | Text | — | Material covered. |
| Stage | `SamplingPlan.stage` | Choice label | — | Stage covered. |
| Versions | — | Count | — | All versions, any status. |
| Status | `SamplingPlanRevision.status` | Computed | — | Whether an approved or draft version exists. |

## Rules and hidden logic

- **Order**: code ascending by default; code or -code.
- **Paging**: 25 rows per page; `per_page` accepts 25, 50 or 100.
- **One plan per material and stage** (database constraint).
- **Not enforced by this page**: "Has approved version" does not mean the version is effective now.

## Related pages

- [Lots](/sampling/)
- New sampling plan, Sampling plan (record page).
