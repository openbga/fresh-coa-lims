---
date: 2026-11-16
type: added
impact: high
title: Sign in with a passkey alone, without the password
area: Sign-in
link: accounts:two_factor
pr: 37
---
**Sign in** offers **Sign in with a passkey** for a key that checks its holder's PIN, fingerprint or face. A deployment that prefers the password first can turn it off.

## Technical notes

- Signing in with a security key or passkey alone, without the password. **Sign in** offers **Sign in with a passkey** (when the site is opened by its host name), which opens `/accounts/login/passkey/`: **Use your passkey** asks the browser for a key the person added on **Two-factor sign-in**, with no account named, and the key must check its holder's PIN, fingerprint or face. The key's credential identifies the account and the answer must carry its user handle. Refused answers are logged and not counted (a signature cannot be guessed, and counting would let anyone who has seen a credential ID lock the account); an account that is locked or stopped refuses even a valid key. A request is answered once within five minutes. A key that does not check its holder still works after the password. The PIN is still re-entered for every signature.
- Signing in with a key alone: `sign_in_factors` can be `["passkey"]`. The new setting `PASSKEY_SIGN_IN` (default `true`) offers it; set it to `false` to ask every account for its password first. `accounts.security_keys.verify_assertion` takes the purpose `passkey`, for which the ceremony names no account, and then requires the user handle and user verification. When a key cannot be used, the message of `static/js/security-keys.js` ends with the form's `data-security-key-fallback` (default "use a code"). The sign-in log gains `signin.passkey_failed`.
