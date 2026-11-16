---
title: Sign in
urls: login
views: accounts.views.SignIn
templates: registration/login.html, accounts/includes/announcement.html
models: accounts.User, accounts.LoginAnnouncement
reviewed: 2026-11-16
---

## Purpose

Sign in to OpenBGA Fresh CoA LIMS with the individual account issued by your laboratory administrator.

## Who can use it

Anyone can open the entrance page. Signing in requires an active account and its correct password. Laboratory roles determine access after sign-in; a superuser has no implicit laboratory authority. There is no public signup.

## Layout

On wide screens, an illustrative manufacturing cutaway appears beside the sign-in panel. It depicts production equipment, a packaging line and a quality-control laboratory. The illustration changes from morning to dusk with the theme. On narrower screens it is hidden so the form remains the focus.

The page shows the certificate-and-leaf mark and **OpenBGA Fresh CoA LIMS** name, **Sign in**, account guidance, the **Sign in with a passkey** button when it is available, and the licence and **Source code** footer. When an administrator has published a sign-in announcement, it appears as a notice between the name and the sign-in panel, with its optional title and formatted text. The **Theme** menu is at the upper right. Validation and session messages appear with the form. This entrance page is outside the signed-in workspace and does not show the page-documentation panel.

## Actions

| Action | Result |
|---|---|
| Sign in with a passkey | Posts to Sign in with a passkey, where a security key or passkey signs you in without the password. Shown only when the deployment's `PASSKEY_SIGN_IN` setting is true (default) and the site is opened by a host name, not an IP address |
| Sign in | Validates the credentials and opens the requested local page, or Material lots by default; for an account with two-factor sign-in it opens the second step instead |
| Theme | Choose Light, Dark or System; the browser remembers the choice |
| Source code | Opens the source repository configured for this deployment; the default is [openbga/fresh-coa-lims](https://github.com/openbga/fresh-coa-lims) |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Username | `User.username` | Text | Yes | Your individual account identifier |
| Password | `User.password` | Masked text | Yes | Your login password; it is not your signature PIN |
| next | — | Hidden local destination | No | Returns you to the requested page after sign-in when the destination is allowed |
| Announcement | `LoginAnnouncement.title`, `body` | Formatted text | — | The published notice, shown to everyone who opens this page |

## Rules and hidden logic

Incorrect credentials and inactive or temporarily locked accounts are refused. Repeated failed attempts temporarily pause sign-in for that account. Rejected forms retain the username and clear the password. Ask your laboratory administrator for account provisioning or recovery.

The announcement is shown only while it is published; it is public, so it appears before any credential is entered. Its text is escaped before formatting, so it cannot add scripts or markup to the page. Only users with the admin role can change it, on Sign-in announcement.

A successful sign-in starts a controlled session. Accounts requiring password replacement go to Change password before entering the workspace. An account without a recognized laboratory role reaches Account access from the workspace entry point. Each destination still checks its own permissions. Signing in does not approve a scientific record or apply an electronic signature.

An account that has set up two-factor sign-in is not signed in by its password alone: an accepted password opens the second step, where you use a security key or passkey, enter a code from your authenticator app, or enter a recovery code (see Two-factor sign-in, second step). The password is not asked again unless the step expires, and opening this page again discards a pending second step. The password check still counts failures as above, and wrong codes count toward the same limit; the count resets only when sign-in completes.

Each successful sign-in, failed attempt and sign-out (including a session ended by expiry or revocation) writes one line to the application log on standard output: `signin.success`, `signin.failed` or `signout`, the username and the platform request ID. For an account with two-factor sign-in, an accepted password writes `signin.second_factor_requested` and a refused code writes `signin.second_factor_failed`, and a refused key on Sign in with a passkey writes `signin.passkey_failed` (each named only when the account is known, otherwise `<unknown>`); `signin.success` follows once the code is accepted. A failed attempt names the account only when it exists; otherwise it shows `<unknown>`. Passwords are never logged. These lines are not audit events and are not stored in the database, so they follow the deployment's log retention rather than database backups or resets.

The help text under the form reads **Accounts are provisioned by your laboratory administrator. Repeated failed attempts pause sign-in for that account for a while.** and, when the passkey button is shown, adds **A passkey or security key you added on Two-factor sign-in signs you in without your password when it checks your PIN, fingerprint or face.** The button carries the hidden `next` destination to Sign in with a passkey. A key refused there is not counted toward the failure limit, but an account paused here is paused there too; see that page.

## Related pages

- [Material lots](/)
- [Account access](/accounts/access/)
- [Change password](/accounts/password/)
- [Sign-in announcement](/accounts/announcement/)
- Sign in with a passkey, reached by the button of that name.
- Two-factor sign-in, second step, reached after an accepted password for an account with two-factor sign-in.
- [Two-factor sign-in settings](/accounts/two-factor/)
