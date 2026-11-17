---
date: 2026-11-12
type: added
impact: medium
title: Sign-in, failed sign-in and sign-out events are written to the log
area: Sign-in
pr: 20
---
Each sign-in, failed attempt and sign-out leaves one line in the application's log with the event, the username and the request ID. Passwords are never logged.

## Technical notes

Each event writes one `openbga.signin` line to standard output: event, username and the Render `Rndr-Id` request ID. Session expiry or revocation appears as `signout`. The lines live in the platform logs, not in the database, so they survive the demonstration's database resets; the request ID joins the platform's HTTP request log for the client address. A failed attempt names the account only when it exists (`<unknown>` otherwise); a malformed request ID is logged as `-`. Usernames and addresses in these logs are personal data: see the retention table in `docs/operations.md`.
