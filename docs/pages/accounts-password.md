---
title: Password
urls: accounts:password
views: accounts.views.password
templates: accounts/password.html
models: accounts.User, core.AuditEvent
reviewed: 2026-11-17
summary: See whether your login password must be changed and when you last changed it. Change it from the header.
---

## Common tasks
### Change your password
1. Select [[Change password]] in the header.
2. In the dialog, enter your current password, the new one twice and a reason, then select [[Change password]].
### Check your password's state
1. Read [[Your password]]: Set, or Change required when an administrator requires a new one, and when you last changed it.

## Good to know
- Your password is never shown, here or anywhere else.
- Changing it signs out your other sessions; this one stays signed in.
- When a change is required, signing in takes you straight to the change form.
- A shared demonstration account cannot change its published password here.

## Purpose

Shows the state of your own login password and leads to changing it. It is not your signature PIN, which has its own page.

## Who can use it

- Any signed-in user, for their own account only. No role is required.
- A shared demonstration account sees the explanation instead of the header action.

## Layout

- Title "Password" with one header action, **Change password**.
- One panel, **Your password**: the line "The password you sign in with. It is never shown. Changing it signs out your other sessions.", then **State** as a status (Set, or Change required) and **Last changed by you** (date and time, or "Not recorded").
- For a shared demonstration account: an information notice above the panel and no header action.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Change password** | Not a shared demonstration account | Signed-in user | Opens Change password in the form dialog (its own page without JavaScript) |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| State | `User.password_change_required` | Status | — | Change required while an administrator requires a new password; otherwise Set |
| Last changed by you | `AuditEvent.occurred_at` of `account.password_changed` | Date and time | — | Your latest own password change; a reset by an administrator is not counted here |

## Rules and hidden logic

- **Never shown**: neither the password nor its stored hash is read for this page.
- **Required change**: while it is required, every other page sends you to the Change password form, which then returns you to the Dashboard.
- **Shared demonstration account**: "This is a shared demonstration account. Its password and signature PIN are published on the sign-in page and cannot be changed here." replaces the action.

## Related pages

- Change password (the form)
- [Signature PIN](/signature-pin/)
- [Account access](/accounts/access/)
