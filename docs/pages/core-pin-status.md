---
title: Signature PIN
urls: core:pin_status
views: core.views.pin_status
templates: core/pin.html
models: core.PINCredential
reviewed: 2026-11-17
summary: See whether your signature PIN is enrolled or locked, and how many wrong PINs are counted. Enroll or change it from the header.
---

## Common tasks
### Enroll or change your PIN
1. Select [[Enroll signature PIN]] or [[Change signature PIN]] in the header.
2. In the dialog, enter your login password and the new PIN, then select [[Save]].
### Check your PIN's state
1. Read [[Your signature PIN]]: Enrolled, Not enrolled, or Locked until a time, with the failed attempts.
## Good to know
- Your PIN is never shown, here or anywhere else.
- Five wrong PINs in a row while signing lock your PIN for 15 minutes.
- Saving a new PIN clears failed attempts and any temporary lock.
- A shared demonstration account cannot change its published PIN here.

## Purpose

Shows your own signature PIN's state, the secret you re-enter for every electronic signature, and leads to enrolling or changing it.

## Who can use it

- Any signed-in user, for their own account only. No role is required.
- A shared demonstration account sees the explanation instead of the header action.

## Layout

- Title "Signature PIN" with one header action: **Enroll signature PIN** when no PIN is enrolled, otherwise **Change signature PIN**.
- One panel, **Your signature PIN**: the line "The secret you re-enter for every electronic signature. It is never shown.", then **State** as a status (Enrolled, Not enrolled, or Locked until <time>) and, once enrolled, **Failed attempts**.
- For a shared demonstration account: an information notice above the panel and no header action.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Enroll signature PIN** / **Change signature PIN** | Not a shared demonstration account | Signed-in user | Opens the PIN form in the form dialog (its own page without JavaScript) |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| State | `PINCredential` present, `locked_until` | Status | — | Not enrolled without a credential; Locked until <time> while a lock runs; otherwise Enrolled |
| Failed attempts | `PINCredential.failures` | Count | — | Wrong PINs since the last accepted one |

## Rules and hidden logic

- **Lock**: shown while `locked_until` is in the future, in the laboratory's time zone ("Y-m-d H:i" and zone).
- **Never shown**: neither the PIN nor its stored hash is read for this page.
- **Shared demonstration account**: "This is a shared demonstration account. Its password and signature PIN are published on the sign-in page and cannot be changed here." replaces the action.

## Related pages

- Enroll signature PIN / Change signature PIN (the form)
- [Account access](/accounts/access/)
