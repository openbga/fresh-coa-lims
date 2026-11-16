---
title: Add a security key or passkey
urls: accounts:security_key_add
views: accounts.views.security_key_add
templates: accounts/security_key_add.html
models: accounts.User, accounts.SecurityKey, accounts.RecoveryCode
reviewed: 2026-11-16
---

## Purpose

Register a security key or passkey (Web Authentication) as a second sign-in factor: name it, then answer your browser's prompts. The first key turns two-factor sign-in on.

## Who can use it

Any signed-in user who has just chosen **Set up with a security key or passkey** (or **Add a security key or passkey**) on Two-factor sign-in and confirmed their password, plus a second factor when two-factor sign-in is already on. Without a started, unexpired registration the page redirects to Two-factor sign-in with **Registration was not started or has expired. Start again.** It acts only on your own account. A shared demonstration account cannot register keys (it cannot change its own two-factor sign-in). The page stays reachable while the deployment requires two-factor sign-in for your account and you have none yet; other workspace pages redirect to Two-factor sign-in.

## Layout

The **Two-factor sign-in** breadcrumb and an introduction (what a security key and a passkey are) precede one card, **Register the key**:

- Instructions: name the key, choose Register the key, follow the browser's prompts. **The key works only at** the host name of this site.
- A note: for a first factor, two-factor sign-in turns on and the next page shows recovery codes; otherwise, other second factors keep working and recovery codes do not change.
- The time limit in minutes, then the **Name of the key** field, a status line, **Cancel** and **Register the key**.
- Notices: **This browser cannot register security keys at this address. Use another browser, or an authenticator app.** when the browser lacks Web Authentication or the page is not a secure context; **Registering a security key needs JavaScript.** without JavaScript.

## Actions

| Action | Shown when | Result |
|---|---|---|
| **Register the key** | Always (disabled in a browser without Web Authentication) | Asks the browser to create the key, then submits the name and the answer; the server checks both |
| **Cancel** | Always | Returns to Two-factor sign-in; the started registration stays in the session until it expires or is replaced |

On success: the first second factor shows **Your recovery codes** (ten codes, once) with **Two-factor sign-in is on. Other sessions have been signed out.** An additional key returns to Two-factor sign-in with **Security key “NAME” added. Other sessions have been signed out.** and leaves the recovery codes as they are.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Name of the key | `SecurityKey.name` | Text, max 60 | Yes | Tells your keys apart, for example where you keep it. Prefilled as "Security key N". Whitespace is collapsed; unique among your keys ignoring case |
| security_key_response (hidden) | — | JSON from the browser | Yes | The browser's answer; filled by the page's script, never typed |

## Rules and hidden logic

- **Time limit**: finish within 10 minutes of starting. After that, or when your account's sessions or second factors changed in the meantime, the next visit redirects as above.
- **Browser step**: with JavaScript the button asks the browser first. Without a name the form reports **Enter a name for the key.**; a refusal in the browser (cancelled, timed out, key already registered, not allowed at this address) is shown on the status line and nothing is sent.
- **Validation**: an answer missing from the form shows **Your browser did not return the new key. Choose Register the key and follow your browser's prompts.** A key the server does not accept shows **The key's answer was not accepted. Start again; if it happens again, use another key or browser.** A name already used by one of your keys shows **You already have a key with this name. Choose another name.** A key already registered (on any account) shows **This key is already registered.** At 10 keys, **An account can have at most 10 security keys.** During a sign-in lock, registration is refused with **The security key was not accepted.** Errors return status 422; a new challenge is issued for the next try within the same time limit. Keys already registered are excluded from the browser's choices.
- **Bound to the host name**: the key records the host name it was registered at and works only there. Registration is not offered on an IP address (see Two-factor sign-in).
- **First or additional**: the first factor of an account turns two-factor sign-in on, replaces any recovery codes with a new set and clears the count of wrong codes. An additional key leaves the codes and the other factors unchanged. Either way the management revision and session generation advance: your other sessions end and this one continues.
- **Audit**: **account.two_factor_enabled** for the first factor, **account.security_key_added** for an additional key, with the safe snapshot before and after (`two_factor`, `recovery_codes_left`, `authenticator_app`, `security_keys`). The key's name appears in the reason; the keys themselves, challenges and answers are never recorded. No electronic signature.
- **User verification**: the key's own PIN or fingerprint is requested when the key supports it, not required. Resident (discoverable) credentials are preferred.

## Related pages

- [Two-factor sign-in](/accounts/two-factor/)
- [Account access](/accounts/access/)
