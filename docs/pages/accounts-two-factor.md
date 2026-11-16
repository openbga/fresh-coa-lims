---
title: Two-factor sign-in
urls: accounts:two_factor
views: accounts.views.two_factor_page
templates: accounts/two_factor.html, accounts/two_factor_codes.html
models: accounts.User, accounts.RecoveryCode, core.AuditEvent
reviewed: 2026-11-16
---

## Purpose

Add a code from an authenticator app (time-based codes) to your own sign-in, make new one-time recovery codes, replace the app or turn it off. Your signature PIN is still entered for every signature.

## Who can use it

Any signed-in user, including an account with no laboratory role. It manages only your own account; no other account can be opened here. When the deployment requires two-factor sign-in for your role (or for everyone) and you have not set it up, every other workspace page redirects here until you do; sign-out, Change password and the documentation panel stay available. A shared demonstration account cannot change its own two-factor sign-in: it sees **This is a shared demonstration account. Its password and signature PIN are published on the sign-in page and cannot be changed here.** and a POST returns status 403.

## Layout

The **Account access** breadcrumb and a short introduction are followed by a **Status** card, then one form card.

- **Status** lists **Two-factor sign-in** (**Off**, or **On: authenticator app, set up** with the date), and, when on, **Code last accepted** (date and time, or **Not yet**) and **Unused recovery codes** (for example 8 of 10). **Required for your account** shows **Yes, by this deployment's settings** or **No**.
- An info notice **Set up two-factor sign-in before continuing. You can sign out from the top bar.** shows when it is required and not set up.
- A warning shows when fewer than 3 recovery codes remain: **Only N recovery code(s) left.** or **No recovery codes left.**, followed by advice to make new ones.
- When off, the **Set up** card has **Current password**. When on, the **Change two-factor sign-in** card has **Current password** and **Code from your authenticator app or a recovery code**.
- After new recovery codes are made, this URL shows **Your recovery codes** instead: ten codes in a numbered list and the link **I have saved the codes**.

## Actions

| Action | Shown when | Result |
|---|---|---|
| **Set up two-factor sign-in** | Off | Starts a new, unconfirmed key and opens Set up two-factor sign-in |
| **Make new recovery codes** | On | Replaces all recovery codes and shows the new set once; message **New recovery codes made. The earlier codes no longer work.** |
| **Set up a new authenticator app** | On | Starts a new key; the current app keeps working until the new one is confirmed |
| **Turn off two-factor sign-in** | On and not required for your account | Removes the authenticator and recovery codes; message **Two-factor sign-in is off. Other sessions have been signed out.** |
| **Cancel** | Off and not required; or On | Returns to Account access |
| **I have saved the codes** | Recovery-codes display | Returns to this page |
| **Return without changes** | Shared demonstration account | Returns to Account access |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Current password | `User.password` (verified) | Masked text | Yes | Your login password, not your signature PIN |
| Code from your authenticator app or a recovery code | — | Text, max 64 | Yes when on | Six digits from the app, or a recovery code; hyphens, spaces and case do not matter. A recovery code used here is spent |
| action | — | Button value: `setup`, `codes` or `disable` | Yes | The button pressed |
| Recovery codes | `RecoveryCode` | 10 codes, 24 characters in groups of four | — | Shown once, never again |
| Status values | `User`, authenticator device, `RecoveryCode.used_at` | Display | — | Since, last accepted code, unused count, required |

## Rules and hidden logic

- **Re-authentication**: every change needs your current password; with two-factor on it also needs a current code. Wrong passwords and wrong codes count toward the same consecutive-failure limit and lock as sign-in (default five failures, 15 minutes). A wrong password shows **Current password was not accepted.** and a wrong code **The code was not accepted.**; while the account is locked, even the correct password and code get these messages.
- **Validation messages**: **Enter the 6-digit code from your authenticator app, or a recovery code.** for text of neither shape; **This field is required.** for a missing password or code; **Two-factor sign-in is required for your account, so it cannot be turned off. Set up a new authenticator app instead.** for a required account. Errors return status 422 with the password and code blank.
- **Required accounts** do not see **Turn off two-factor sign-in**; a POST for it is refused with **Select a valid choice. disable is not one of the available choices.**
- **Recovery codes**: ten per set, each works once in place of an app code. Only digests are stored; the readable codes exist only in the one display. Making a new set replaces all earlier codes and ends no session.
- **Sessions**: turning two-factor on, replacing the app or turning it off increments the management revision and ends your other sessions; this session continues and keeps the record of how it signed in. Making new recovery codes does not end sessions.
- **Stopped after 100 wrong codes**: 100 consecutive wrong codes for your authenticator, counted across sign-in locks and cleared by any accepted code, stop two-factor sign-in: no code is accepted, at sign-in or here, with **Two-factor sign-in is stopped for this account after too many wrong codes. Ask an administrator to reset it.** The Status card shows a warning and **account.two_factor_stopped** is audited. An administrator's **Reset two-factor sign-in** is the way forward; you then set it up again.
- **Password-only checks**: for an account with two-factor sign-in, a correct password on Change password or Signature PIN does not clear the count of failures; the next complete sign-in or accepted code does.
- **Audit**: attributed audit events **account.recovery_codes_replaced** and **account.two_factor_disabled** (the others are written by the setup page) record before and after values `two_factor` and `recovery_codes_left`; neither key nor codes are recorded. These self-service changes carry no electronic signature. A recovery code used here also writes **account.recovery_code_used**.
- **Operator recovery**: if no administrator can sign in, the operator command `reset_two_factor` removes the second factor and writes **account.reset_two_factor** with the named administrator and reason.

## Related pages

- [Account access](/accounts/access/)
- [Set up two-factor sign-in](/accounts/two-factor/setup/)
- [Change password](/accounts/password/)
- [Users and roles](/accounts/users/)
