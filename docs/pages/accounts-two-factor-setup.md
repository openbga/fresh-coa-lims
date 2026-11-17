---
title: Set up two-factor sign-in
urls: accounts:two_factor_setup
views: accounts.views.two_factor_setup
templates: accounts/two_factor_setup.html, accounts/two_factor_codes.html
models: accounts.User, accounts.RecoveryCode, core.AuditEvent
reviewed: 2026-11-17
summary: Add your account to an authenticator app with the QR code or key, then confirm it with a code the app shows. Confirming turns two-factor sign-in on.
---

## Common tasks
### Add the account to your app
1. Scan the QR code with your authenticator app, or enter the [[Key]] shown under [[Account]] in the app.
### Confirm and turn it on
1. Enter the 6-digit code the app shows in [[Code from the app]].
2. Select [[Confirm and turn on]].
3. Save the recovery codes shown once, then select [[I have saved the codes]].
### Stop setting up
1. Select [[Cancel]] to return to Two-factor sign-in. The app is not added.
## Good to know
- Keep the key private: anyone who has it can produce your codes. It is shown only while you set up.
- Finish within 10 minutes of starting, or start again from Two-factor sign-in.
- A recovery code is not accepted here. Enter the code from the app.
- Wrong codes count toward the sign-in failure limit, and can pause sign-in for the account for a while.
- Confirming replaces any earlier app and all earlier recovery codes. Until then your current app keeps working.

## Purpose

Add your account to an authenticator app with a QR code or key, then confirm it with a code the app shows. Confirming turns two-factor sign-in on.

## Who can use it

Any signed-in user who has just started setup on Two-factor sign-in (password, plus a second factor, a code or a key, when two-factor sign-in is already on). Without a started, unexpired setup the page redirects to Two-factor sign-in with **Setup was not started or has expired. Start again.** It acts only on your own account. Shared demonstration accounts are refused on confirmation with the published-credentials message.

## Layout

The **Two-factor sign-in** breadcrumb is followed by two cards.

1. **1. Add this account to your authenticator app**: a QR code (black on white in both themes), **Account** (your username) and **Key** in groups of four characters, with a warning to keep the key private. The key is shown only while you set up.
2. **2. Confirm with a code from the app**: a note that the current app keeps working until the new one is confirmed (when you already have an app), the time limit, and the code field.

After a successful confirmation this URL shows **Your recovery codes**: ten codes once, and **I have saved the codes**.

## Actions

| Action | Shown when | Result |
|---|---|---|
| **Confirm and turn on** | Always | Checks the code; on success turns two-factor sign-in on (or replaces the app) and shows the recovery codes |
| **Cancel** | Always | Returns to Two-factor sign-in; the unconfirmed key is discarded when you next start |
| **I have saved the codes** | Recovery-codes display | Returns to Two-factor sign-in |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| QR code and Key | Authenticator key (not shown elsewhere) | Image and text | — | Add to any app that supports time-based codes; six digits every 30 seconds |
| Code from the app | — | Text, max 64 | Yes | The 6-digit code the app shows for this account now |
| Recovery codes | `RecoveryCode` | 10 codes | — | Shown once after confirmation |

## Rules and hidden logic

- **Time limit**: setup must be confirmed within 10 minutes of starting. Otherwise **Setup expired. Start again.**
- **Stopped**: once 100 consecutive wrong codes or refused keys have stopped two-factor sign-in, a setup started earlier cannot be confirmed (**Two-factor sign-in is stopped for this account after too many wrong codes or refused security keys. Ask an administrator to reset it.**); only an administrator's reset clears the stop.
- **Validation**: a recovery code is not accepted here: **Enter the 6-digit code the app shows.** A wrong code shows **The code was not accepted.**; it counts toward the sign-in failure limit and lock (default five failures, 15 minutes), and during a lock a correct code is refused too. It does not count toward the limit of 100 consecutive wrong codes, which applies to a confirmed authenticator. Starting a setup also discards every other setup older than 10 minutes, and opening this page after the time limit discards your unconfirmed key. Errors return status 422.
- **Confirmation**: the new key replaces any earlier authenticator, and a new set of recovery codes replaces all earlier ones (also when you only have security keys; the keys stay). The recovery-codes display shows **Two-factor sign-in is on. Other sessions have been signed out.** Your other sessions end; this one continues, and what its sign-in proved stays as it was (the password, for a first setup), as later signatures record.
- **Audit**: **account.two_factor_enabled**, **account.authenticator_added** when you already have security keys but no app, or **account.two_factor_replaced** when an app already existed, with before and after values such as `two_factor`, `recovery_codes_left`, `authenticator_app` and `security_keys`. The key and codes are never recorded. No electronic signature.
- **Sign-in log**: later sign-ins log `signin.second_factor_requested`; see Sign in.

## Related pages

- [Two-factor sign-in](/accounts/two-factor/)
- [Account access](/accounts/access/)
