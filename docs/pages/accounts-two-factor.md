---
title: Two-factor sign-in
urls: accounts:two_factor
views: accounts.views.two_factor_page
templates: accounts/two_factor.html, accounts/two_factor_codes.html
models: accounts.User, accounts.SecurityKey, accounts.RecoveryCode, core.AuditEvent
reviewed: 2026-11-16
---

## Purpose

Manage your own second sign-in factor: security keys and passkeys, an authenticator app (time-based codes) and one-time recovery codes. Add or remove factors, make new recovery codes or turn two-factor sign-in off. Your signature PIN is still entered for every signature.

## Who can use it

Any signed-in user, including an account with no laboratory role. It manages only your own account; no other account can be opened here. When the deployment requires two-factor sign-in for your role (or for everyone) and you have not set it up, every other workspace page redirects here until you do; the registration and app-setup pages, sign-out, Change password and the documentation panel stay available. A shared demonstration account cannot change its own two-factor sign-in: it sees **This is a shared demonstration account. Its password and signature PIN are published on the sign-in page and cannot be changed here.** and a POST returns status 403.

## Layout

The **Account access** breadcrumb and a short introduction are followed by a **Status** card, a keys table when keys exist, then one form card.

- **Status** lists **Two-factor sign-in** (**Off**, or **On since** the date of the earliest factor), **Security keys and passkeys** (**None**, or "N of at most 10"), **Authenticator app** (**Not set up**, or **Set up** with the date), **Code last accepted** (app only: date and time, or **Not yet**), **Unused recovery codes** (when on, for example 8 of 10) and **Required for your account** (**Yes, by this deployment's settings** or **No**).
- Warnings and notices: **Two-factor sign-in is stopped for this account after too many wrong codes or refused keys. Nothing is accepted until an administrator resets it; you then set it up again.**; the info notice **Set up two-factor sign-in before continuing. You can sign out from the top bar.** when it is required and not set up; and, when fewer than 3 recovery codes remain, **Only N recovery code(s) left.** or **No recovery codes left.** with advice to make new ones.
- **Security keys and passkeys** table: **Name** (with **Works only at HOST** for a key registered at another host name), **Kind** (**Passkey that can be copied to your other devices** or **Kept on one device**), **Added**, **Last used** (date and time, or **Not yet**) and a **Remove** button per key. Below it, instructions for removing; with a single key and no app it warns that removing it turns two-factor sign-in off (and that your account does not allow this when required).
- When the site is opened by an IP address, an info notice says **Security keys work only when this site is opened by its host name over HTTPS, not by an IP address.**
- When off, the **Set up** card has **Current password** and two buttons. When on, the **Change two-factor sign-in** card has **Current password** and a code field (**Code from your authenticator app or a recovery code**, or **Recovery code** without an app), with the hint to leave it empty to confirm with your security key.
- After new recovery codes are made, this URL shows **Your recovery codes** instead: ten codes in a numbered list and the link **I have saved the codes**.

## Actions

Every action needs your current password. When two-factor sign-in is on it also needs a second factor: a code, or the key (leave the code empty and your browser asks for a key registered at this host name).

| Action | Shown when | Result |
|---|---|---|
| **Set up with a security key or passkey** | Off, and the site is not opened by an IP address | Opens Add a security key or passkey (the first key turns two-factor sign-in on) |
| **Set up with an authenticator app** | Off | Starts a new, unconfirmed key and opens Set up two-factor sign-in |
| **Add a security key or passkey** | On, fewer than 10 keys, not opened by an IP address | Opens Add a security key or passkey; the other factors and recovery codes stay |
| **Make new recovery codes** | On | Replaces all recovery codes and shows the new set once; message **New recovery codes made. The earlier codes no longer work.** |
| **Set up a new authenticator app** / **Add an authenticator app** | On, with / without an app | Starts a new key; a current app keeps working until the new one is confirmed |
| **Remove the authenticator app** | On, with an app and at least one key | Removes the app; message **The authenticator app is removed; your security keys remain. Other sessions have been signed out.** |
| **Remove** (beside a key) | On, keys exist | Removes that key; message **The key is removed.** If it was the last second factor, two-factor sign-in turns off and the message adds that the recovery codes no longer work |
| **Turn off two-factor sign-in** | On and not required for your account | Removes all keys, the app and the recovery codes; message **Two-factor sign-in is off. Other sessions have been signed out.** |
| **Cancel** | Off and not required; or On | Returns to Account access |
| **I have saved the codes** | Recovery-codes display | Returns to this page |
| **Return without changes** | Shared demonstration account | Returns to Account access |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Current password | `User.password` (verified) | Masked text | Yes | Your login password, not your signature PIN |
| Code from your authenticator app or a recovery code (**Recovery code** without an app) | — | Text, max 64 | When on, unless a key confirms | Six digits from the app, or a recovery code; hyphens, spaces and case do not matter. A recovery code used here is spent. Empty means "use my key" and needs a key registered at this host name |
| action | — | Button value: `add_key`, `setup`, `codes`, `remove_app`, `remove_key:N`, `disable` | Yes | The button pressed |
| security_key_response (hidden) | — | JSON from the browser | — | The key's answer, filled by the page's script |
| Keys table | `SecurityKey.name`, `backup_eligible`, `created_at`, `last_used_at`, `rp_id` | Display | — | Your registered keys |
| Recovery codes | `RecoveryCode` | 10 codes, 24 characters in groups of four | — | Shown once, never again |
| Status values | `User`, authenticator device, `SecurityKey`, `RecoveryCode.used_at` | Display | — | Since, keys, app, last accepted code, unused count, required |

## Rules and hidden logic

- **Re-authentication**: every change needs your current password; with two-factor on it also needs a current code or key answer. Wrong passwords, wrong codes and refused keys count toward the same consecutive-failure limit and lock as sign-in (default five failures, 15 minutes). A wrong password shows **Current password was not accepted.**, a wrong code **The code was not accepted.** and a refused key **The security key was not accepted.**; while the account is locked, even the correct password and code get these messages. A key request older than 10 minutes, or one the page has since replaced (another tab, a reload, the same answer sent twice), shows **The security key request expired. Try again.** and is not counted. Pressing Enter in the form does nothing: choose an action button, so that Enter can never remove a key. With two-factor on, an empty code and no key answer shows **Use your security key, or enter a code.** (when a key is usable here) or **Enter the 6-digit code from your authenticator app, or a recovery code.**
- **Validation messages**: **Enter the 6-digit code from your authenticator app, or a recovery code.** for text of neither shape; **This field is required.** for a missing password; **Two-factor sign-in is required for your account, so it cannot be turned off. Set up a new authenticator app instead.** for a required account. Errors return status 422 with the password and code blank.
- **Keys at this host**: a key works only at the host name it was registered at; keys registered elsewhere are listed (**Works only at HOST**) but cannot confirm a change here, so with only such keys you confirm with a recovery code. Security keys are not offered when the site is opened by an IP address.
- **Limits**: at most 10 keys (**An account can have at most 10 security keys.**). **Add a security key or passkey** only starts registration; nothing changes until the key is registered.
- **Removing factors**: removing the last remaining factor (a single key and no app) turns two-factor sign-in off and deletes the recovery codes. A required account is refused with **Two-factor sign-in is required for your account, and this is its only second factor. Add another security key or an authenticator app first.** **Remove the authenticator app** is refused without a key (**The authenticator app is your only second factor. Turn off two-factor sign-in instead, or add a security key first.**), and a key already removed in another session shows **That key is no longer registered.**
- **Required accounts** do not see **Turn off two-factor sign-in**; a POST for it is refused with **Select a valid choice. disable is not one of the available choices.** A required account is satisfied by a key alone.
- **Recovery codes**: ten per set, each works once in place of an app code. Only digests are stored; the readable codes exist only in the one display. Making a new set replaces all earlier codes and ends no session. The first factor of an account and a newly confirmed app make a new set; an additional key does not.
- **Sessions**: turning two-factor on, adding or replacing an app or key, removing a key or the app, or turning it off increments the management revision and ends your other sessions; this session continues and keeps the record of how it signed in. Making new recovery codes does not end sessions.
- **Stopped after 100 wrong codes**: 100 consecutive wrong codes or refused keys, counted across sign-in locks and cleared by any accepted code, stop two-factor sign-in: nothing is accepted, at sign-in or here, with **Two-factor sign-in is stopped for this account after too many wrong codes or refused security keys. Ask an administrator to reset it.** The Status card shows a warning and **account.two_factor_stopped** is audited. An administrator's **Reset two-factor sign-in** is the way forward; you then set it up again.
- **Password-only checks**: for an account with two-factor sign-in, a correct password on Change password or Signature PIN does not clear the count of failures; the next complete sign-in or accepted code does.
- **Audit**: attributed audit events record before and after values `two_factor`, `two_factor_stopped`, `recovery_codes_left`, `authenticator_app` and `security_keys`; neither keys nor codes are recorded. Written here: **account.recovery_codes_replaced**, **account.security_key_removed**, **account.authenticator_removed** and **account.two_factor_disabled** (also when the last key is removed). **account.two_factor_enabled**, **account.security_key_added**, **account.authenticator_added**, **account.two_factor_replaced** are written by the registration and setup pages. These self-service changes carry no electronic signature. A recovery code used here also writes **account.recovery_code_used**.
- **Operator recovery**: if no administrator can sign in, the operator command `reset_two_factor` removes the second factor and writes **account.reset_two_factor** with the named administrator and reason.

## Related pages

- [Account access](/accounts/access/)
- [Set up two-factor sign-in](/accounts/two-factor/setup/)
- [Add a security key or passkey](/accounts/two-factor/security-key/)
- [Change password](/accounts/password/)
- [Users and roles](/accounts/users/)
