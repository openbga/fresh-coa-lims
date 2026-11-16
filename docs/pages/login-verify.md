---
title: Two-factor sign-in (second step)
urls: login_verify
views: accounts.views.login_verify
templates: registration/login_verify.html
models: accounts.User, accounts.RecoveryCode
reviewed: 2026-11-16
---

## Purpose

Finish signing in to an account that uses an authenticator app: enter the current code, or a recovery code, after the password was accepted.

## Who can use it

Only someone whose password was just accepted on Sign in for an account with two-factor sign-in. Without such a pending sign-in the page redirects to Sign in. The page is outside the signed-in workspace and does not show the documentation panel.

## Layout

The brand, the heading **Two-factor sign-in**, the text **Your password was accepted. Enter the code your authenticator app shows for this account.**, the **Code** field and **Verify and sign in**. Help text explains that each code works once, that a recovery code can be used instead, and gives **Start again**. A second note states the time allowed and that repeated wrong codes pause sign-in. The **Theme** menu is at the upper right.

## Actions

| Action | Result |
|---|---|
| **Verify and sign in** | Checks the code; on success signs you in and opens the requested local page, or Material lots by default |
| **Start again** | Returns to Sign in and discards the pending sign-in |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | — | Text, max 64 | Yes | The 6-digit code the app shows now, or one recovery code (hyphens, spaces and case ignored) |

## Rules and hidden logic

- **Time limit**: enter the code within 5 minutes of the password. After that, or when the account's password, sessions or activation changed meanwhile, you are returned to Sign in with **Sign in again: enter your password, then a new code.**
- **One use**: an app code is accepted once; the same or an earlier 30-second step is refused. A recovery code is spent when used and the event **account.recovery_code_used** is audited.
- **Validation**: text of neither shape shows **Enter the 6-digit code from your authenticator app, or a recovery code.** A wrong code shows **The code was not accepted.** with status 422. Wrong codes count toward the same consecutive-failure limit and lock as wrong passwords (default five failures, 15 minutes); during the lock even a correct code is refused. The count resets only when sign-in completes, not when the password alone is accepted.
- **Session**: the session records how you signed in (password and totp, or password and recovery code); the record is kept in each electronic signature's authentication context. After a recovery code you see a warning with the number of unused recovery codes left and advice to set up a new app on Two-factor sign-in.
- **Logging**: `signin.second_factor_failed` for a refused code, then the usual `signin.success` on completion. Codes are never logged.

## Related pages

- [Sign in](/accounts/login/)
- [Two-factor sign-in settings](/accounts/two-factor/)
