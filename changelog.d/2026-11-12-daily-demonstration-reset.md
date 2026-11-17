---
date: 2026-11-12
type: added
impact: medium
title: Hosted demonstration is reset daily and its shared accounts are locked
area: Deployment
pr: 19
---
The hosted demonstration can be returned to a known state every day. The password and PIN of a published demonstration account can no longer be changed by whoever signs in with it, so one visitor cannot lock out the others.

## Technical notes

`reset_demo` (new command) empties every application table, creates `demo_admin` with its own private password and PIN, runs `seed_demo` and, with `--publish-accounts`, locks the listed accounts and publishes the announcement, signed by `demo_admin`.

- Refused before anything is erased: `ALLOW_DEMO_RESET=true` is not set (`DEBUG` alone is not enough); one of the four credentials is missing, malformed or shared between `demo_admin` and the published pair; the schema is not this release's; the database has accounts but not the seed's `demo_admin`; `--journey` outside `DEBUG`.
- Credential lock: `User.credentials_locked` (migration `accounts.0006`). The services refuse a change of password or PIN of a locked account and the two pages explain it instead of showing the form. An administrator's forced password reset or PIN re-enrollment ends the lock.
- `seed_demo` also runs without `DEBUG` where `ALLOW_DEMO_RESET=true` is set, refuses `--journey` outside `DEBUG`, says what each account is for in the announcement and can end it with `DEMO_RESET_NOTE`.
- `render.demo.yaml` is a separate Blueprint with one cron job, every day at 08:00 UTC. It creates nothing until it is created by hand (`docs/operations.md`, "Demonstration reset").
- The reset is not one transaction (signing refuses to run inside an enclosing transaction): the erase, the accounts and the draft configuration commit together and the signed steps follow. The whole-table erase bypasses the history triggers on purpose, which is why the command is fenced by the opt-in and the demonstration-database check. The first run erases accounts created by hand.
