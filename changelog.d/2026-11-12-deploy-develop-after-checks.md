---
date: 2026-11-12
type: changed
impact: low
title: The demonstration deploys develop automatically after checks pass
area: Deployment
pr: 17
---
The hosted demonstration is updated from the `develop` branch once the CI checks pass. Controlled deployments are not affected.

## Technical notes

- The Render Blueprint and hosted demo now deploy `develop` automatically once CI checks pass; controlled deployments keep automatic deployment off.

`render.yaml` sets `autoDeployTrigger: checksPass` for the demonstration service. Pull requests into `develop` and pushes to `develop` run every CI job; the application job runs `pytest -n auto` (pytest-xdist).
