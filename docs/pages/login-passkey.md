---
title: Sign in with a passkey
urls: login_passkey
views: accounts.views.login_passkey
templates: registration/login_passkey.html
models: accounts.User, accounts.SecurityKey
reviewed: 2026-11-17
summary: Sign in with a passkey or security key alone, without typing your password. The key checks your PIN, fingerprint or face itself.
---

## Common tasks
### Sign in with your passkey
1. Select [[Use your passkey]], then choose the key when your browser asks.
2. Let the key check your PIN, fingerprint or face. You go to the page you asked for, or to the dashboard.
### Sign in with your password instead
1. Select [[Sign in with your password]]. The page you asked for is kept.
## Good to know
- Only a key that checks your PIN, fingerprint or face works here. Any other key works only after your password.
- A key works only at the address where it was added. A key added at another address is not found here.
- Use the key within the time the page shows (300 seconds by default). A late answer is refused as expired and is not counted against the account.
- While sign-in to an account is paused after failed attempts, its keys are refused here too.
- Signing in with a key approves nothing. Your signature PIN is still entered for every signature.

## Purpose

Sign in with a security key or passkey alone, without typing the password. The key must check its holder with its own PIN, fingerprint or face, so it stands for both factors.

## Who can use it

Anyone whose account has a security key or passkey registered at this host name (see Add a security key or passkey). The page is reached by the **Sign in with a passkey** button on Sign in; it has no sign-in requirement of its own and is outside the signed-in workspace, so it does not show the documentation panel. Opening the address directly (a GET) starts nothing and redirects to Sign in. It does the same when the deployment's setting `PASSKEY_SIGN_IN` is false or the site is opened by an IP address.

## Layout

The brand, the heading **Sign in with a passkey** and the lead **Use a passkey or security key you added to your account. Your browser asks which one, then the key checks your PIN, fingerprint or face.** Then, top to bottom:

- Errors of the last attempt, if any.
- Notices **This browser cannot use passkeys here. Sign in with your password.** (browser without Web Authentication) and, without JavaScript, **Passkeys need JavaScript. Sign in with your password.**
- The button **Use your passkey** and a status line where the browser's refusals appear.
- **A key that does not check your PIN, fingerprint or face works only after your password.** with the link **Sign in with your password**, which returns to Sign in and keeps the requested page.
- A note with the time allowed in seconds (300 by default), that an account's keys are refused here while its sign-in is paused after failed attempts, and that the signature PIN is still entered for every signature.
- The licence and **Source code** footer and the **Theme** menu at the upper right.

## Actions

| Action | Shown when | Result |
|---|---|---|
| **Use your passkey** | Always on this page | Asks your browser for a passkey or security key stored for this site; the browser lists the keys it holds and you pick one. The page's script submits the answer and, when it is accepted, signs you in and opens the requested local page, or Material lots by default |
| **Sign in with your password** | Always | Returns to Sign in, keeping the requested page |
| **Sign in with a passkey** (on Sign in) | `PASSKEY_SIGN_IN` is true and the site is opened by a host name, not an IP address | Posts to this page, which starts a new request for the browser and shows this page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| security_key_response (hidden) | — | JSON from the browser, max 64 KB | Empty only to start | The key's answer, filled by the page's script. Sent empty, the page only starts a new request |
| next (hidden) | — | Local destination | No | Where to go after sign-in; kept only when it is a local address of this host |

## Rules and hidden logic

- **Starting**: each visit makes a new random request for the browser. A request is answered once; after any refusal the page is shown again with a new request.
- **Time limit**: use the key within 300 seconds (`MFA_PENDING_SECONDS`) of the request being made. A late answer, an answer to a request the page has since replaced (another tab, a reload, the same answer sent twice) or an answer with no request in the session shows **The security key request expired. Try again.** and is not counted: a key's answer cannot be guessed.
- **Who signs in**: the key's credential ID names the account, so no username is typed. The answer must also carry that account's user handle and show that the key verified its holder; a key that does not is refused.
- **Messages** (status 422 unless noted): **The security key was not accepted.** for a refused answer, an inactive account, an account locked by failed sign-ins, or an answer longer than 64 KB. **This passkey or security key is not registered for an account at this address, or it was removed. Sign in with your password.** when no key registered at this host name matches, including a key removed meanwhile and an answer that cannot be read. **Two-factor sign-in is stopped for this account after too many wrong codes or refused security keys. Ask an administrator to reset it.** when the account's second factor is stopped. The empty first request returns status 200.
- **Counting and lock**: refusals on this page are not counted toward any account's failure limit. A key's signature cannot be guessed and the key checks your PIN, fingerprint or face itself, while a key's credential ID is shown to anyone who passes the password step, so counting unsigned answers here would let that person pause the account or stop its second factor without its password. The account's own state still applies: while its sign-in is paused after failed passwords, codes or keys elsewhere (default five failures, 15 minutes), and once its second factor is stopped after 100 consecutive wrong codes or refused keys, even a valid key is refused here. An accepted key clears the count of wrong codes.
- **Browser messages** on the status line end with **Try again, or sign in with your password.** (for example **The security key was not used, or the request timed out. Try again, or sign in with your password.**); other refusals (**This browser does not allow security keys at this address.**, **The request was cancelled. Try again.**) are as on the second step. While the browser asks for the key the button is disabled.
- **Session**: a successful sign-in records the single factor `passkey` (not password and a second factor) in the session and in each electronic signature's authentication context. A deployment that requires two-factor sign-in for the role is satisfied by it. Any pending second step from the password is discarded.
- **PIN**: your signature PIN is still entered for every signature; signing in with a key approves nothing.
- **Logging**: a refused or expired answer writes `signin.passkey_failed` with the username of the key's owner when a registered key matched and a request was pending, otherwise `<unknown>` (an answer longer than 64 KB is not logged); review repeated lines for one account, since they are not counted; then the usual `signin.success` on completion. Answers are never logged. These lines are not audit events and are not stored in the database.
- **Redirect**: `next` is used only when it is a local address of this host (and HTTPS when the site is); otherwise the default page opens.

## Related pages

- [Sign in](/accounts/login/)
- [Add a security key or passkey](/accounts/two-factor/security-key/)
- [Two-factor sign-in settings](/accounts/two-factor/)
