---
title: Two-factor sign-in (second step)
urls: login_verify
views: accounts.views.login_verify
templates: registration/login_verify.html
models: accounts.User, accounts.SecurityKey, accounts.RecoveryCode
reviewed: 2026-11-17
summary: The second step of signing in for an account with two-factor sign-in. Use your security key, or enter a code from your authenticator app or a recovery code.
---

## Common tasks
### Sign in with your security key
1. Select [[Use your security key]] and follow your browser's prompts. It shows only when your account has a key added at this address.
### Sign in with a code from your app
1. Enter the 6-digit code your authenticator app shows now in [[Code]].
2. Select [[Verify and sign in]], or [[Verify the code and sign in]] when your account also has keys.
### Use a recovery code
1. Enter one of your recovery codes in [[Code]], or in [[Recovery code]] if you have no app. Hyphens, spaces and case do not matter.
2. Select [[Verify and sign in]] or [[Verify the code and sign in]]. A message then tells you how many unused codes are left.
### Start over
1. Select [[Start again]] to return to Sign in. The pending sign-in is discarded.
## Good to know
- Finish within the time the page shows (300 seconds by default) of your password. After that, sign in again from the start.
- Each app code works once. If you have just used the code shown, wait for the next one.
- A recovery code is spent once used. Make new ones on Two-factor sign-in when you run low.
- Wrong codes and refused keys count toward the same limit as wrong passwords. During the pause even a correct code is refused.
- After 100 wrong codes or refused keys in a row, no code is accepted until an administrator resets two-factor sign-in.

## Purpose

Finish signing in to an account with two-factor sign-in: use a security key or passkey, enter the current code from an authenticator app, or enter a recovery code, after the password was accepted.

## Who can use it

Only someone whose password was just accepted on Sign in, or whom the organization's identity provider just signed in, for an account with two-factor sign-in. Without such a pending sign-in the page redirects to Sign in. The page is outside the signed-in workspace and does not show the documentation panel.

## Layout

The brand, the heading **Two-factor sign-in** and a lead that depends on the account:

| Account has | Lead text | Controls |
|---|---|---|
| App only (or keys not usable at this address) | **Your password was accepted. Enter the code your authenticator app shows for this account.** | **Code** field, **Verify and sign in** |
| App and keys | **Your password was accepted. Use your security key, or enter the code your authenticator app shows for this account.** | **Use your security key**, the **Code** field (empty it to use the key), **Verify the code and sign in** |
| Keys only | **Your password was accepted. Use your security key or passkey.** | **Use your security key**, the field labelled **Recovery code**, **Verify the code and sign in** |

Help text explains that each code works once and gives **Start again**; without an app it says **No access to your key? Enter one of your recovery codes instead; each works once.** A second note states the time allowed and that repeated wrong codes or refused keys pause sign-in. When the account has keys that cannot be used at this address, **Your security keys cannot be used at this address. Enter a code instead.** appears. Notices **This browser cannot use security keys here. Enter a code** (adding **: one of your recovery codes** without an app) and, without JavaScript, **Security keys need JavaScript. Enter a code instead.** The **Theme** menu is at the upper right.

After the provider, the lead starts with **Your organization signed you in.** instead of **Your password was accepted.**; the rest of each lead is unchanged.

## Actions

| Action | Result |
|---|---|
| **Use your security key** | Asks your browser for the key, then submits its answer and signs you in on success. Shown only when the account has a key registered at this host name |
| **Verify and sign in** / **Verify the code and sign in** | Checks the code; on success signs you in and opens the requested local page, or the Dashboard by default. With keys, a typed code is checked as typed; pressing it with an empty code asks for the key |
| **Start again** | Returns to Sign in and discards the pending sign-in |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code (**Recovery code** without an app) | — | Text, max 64 | Yes, unless a key answers | The 6-digit code the app shows now, or one recovery code (hyphens, spaces and case ignored). Without an app only recovery codes are accepted |
| security_key_response (hidden) | — | JSON from the browser | — | The key's answer, filled by the page's script |

## Rules and hidden logic

- **Time limit**: enter the code or use the key within 5 minutes of the password. After that, or when the account's password, sessions or activation changed meanwhile, you are returned to Sign in with **Sign in again: enter your password, then a new code.** (after the provider: **Sign in again with your organization, then enter a new code.**)
- **One use**: an app code is accepted once; the same or an earlier 30-second step is refused. A recovery code is spent when used and the event **account.recovery_code_used** is audited.
- **Validation**: an empty field with no key answer shows **Use your security key, or enter a code.** (with keys) or the message below (without); text of neither shape shows **Enter the 6-digit code from your authenticator app, or a recovery code.** A wrong code shows **The code was not accepted.** and a refused key answer **The security key was not accepted.**, both with status 422. A key answer to a request older than the time limit, or to a request the page has since replaced (another tab, a reload, the same answer sent twice), shows **The security key request expired. Try again.** and is not counted: a key's answer cannot be guessed. Wrong codes and refused keys count toward the same consecutive-failure limit and lock as wrong passwords (default five failures, 15 minutes); during the lock even a correct code is refused. The count resets only when sign-in completes, not when the password alone is accepted. After 100 consecutive wrong codes or refused keys, counted across locks and cleared by any accepted code, no code is accepted and the page shows **Two-factor sign-in is stopped for this account after too many wrong codes or refused security keys. Ask an administrator to reset it.** until an administrator resets two-factor sign-in.
- **Keys**: a key request is made for each visit and answered once; a refused or repeated answer needs the page again. While the browser asks the key, the page's buttons are disabled, and the answer is sent once. Pressing Enter in an empty code field asks the key too. Only keys registered at the host name you are using are offered, so a key registered at another address is not (**Your security keys cannot be used at this address.**). An answer for another account, another site, a replay, or a signature count that did not increase is refused.
- **Session**: the session records how you signed in (password or identity_provider as the first factor, with totp, password and recovery_code, or password and security_key; a sign-in with a key alone on Sign in with a passkey records passkey only); the record is kept in each electronic signature's authentication context. After a recovery code you see a warning with the number of unused recovery codes left and advice for a lost second factor on Two-factor sign-in: set up a new authenticator app (an account with one), or remove the lost key and add another (an account with keys only).
- **Logging**: `signin.second_factor_failed` for a refused code, then the usual `signin.success` on completion. Codes are never logged.

## Related pages

- [Sign in](/accounts/login/)
- [Organization sign-in](/accounts/single-sign-on/)
- [Sign in with a passkey](/accounts/login/passkey/), the way to sign in with a key without the password.
- [Two-factor sign-in settings](/accounts/two-factor/)
